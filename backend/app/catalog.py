import json
from pydantic import ValidationError
from .errors import ApiError,dependency_unavailable
from .models import ContentSource,DescriptionContent,Food,FoodDescription,FoodPage

FOOD_COLUMNS='id,slug,name_vi,name_en,scope_kind,original_class_id,training_class_id,class_map_version'
SOURCE_COLUMNS='source_key,title,publisher,url,language,source_kind,revision_ref,accessed_on,license_note'
DESCRIPTION_COLUMNS=('locale,version,content_status,is_current,short_intro,origin_text,ingredients_summary,characteristics,scope_note,'
                     'authoring_method,reviewed_at,published_at,updated_at,food_description_sources(supports,locator,content_sources('+SOURCE_COLUMNS+'))')


def description_dto(row):
    sources=[ContentSource(**link['content_sources'],supports=link['supports'],locator=link['locator'])
             for link in row['food_description_sources']]
    return DescriptionContent(**{k:row[k] for k in ['locale','version','content_status','short_intro','origin_text','ingredients_summary',
        'characteristics','scope_note','authoring_method','reviewed_at','published_at','updated_at']},
        sources=sorted(sources,key=lambda s:s.source_key))


def literal_pattern(q):
    # Quoted PostgREST values protect filter syntax. LIKE metacharacters are escaped.
    escaped=q.replace('\\','\\\\').replace('%','\\%').replace('_','\\_').replace('*','\\*')
    return json.dumps('%'+escaped+'%',ensure_ascii=False)


class Catalog:
    def __init__(self,db,cursor): self.db,self.cursor=db,cursor

    async def food(self,id,context):
        rows=await self.db.request('/rest/v1/foods',context,dict(select=FOOD_COLUMNS,id='eq.'+str(id),active='eq.true',limit='1'))
        if not rows: raise ApiError(404,'NOT_FOUND','Food was not found.')
        return rows[0]

    async def page(self,context,q,limit,cursor):
        params=dict(select=FOOD_COLUMNS,active='eq.true',order='slug.asc,id.asc',limit=str(limit+1))
        if q:
            value=literal_pattern(q)
            params['or']='('+','.join(n+'.ilike.'+value for n in ['name_vi','name_en','slug'])+')'
        if cursor:
            slug,id=self.cursor.decode(cursor,q)
            params['and']=f'(or(slug.gt.{slug},and(slug.eq.{slug},id.gt.{id})))'
        rows=await self.db.request('/rest/v1/foods',context,params)
        more=len(rows)>limit; rows=rows[:limit]
        items=[Food(**f) for f in rows]
        token=self.cursor.encode(q,rows[-1]['slug'],rows[-1]['id']) if more and rows else None
        return FoodPage(items=items,next_cursor=token)

    async def detail(self,id,context):
        return Food(**await self.food(id,context))

    async def description(self,id,context):
        # Only the current published version is user-visible (RLS repeats these filters);
        # drafts and reviewed-but-unpublished content are reported as unavailable.
        food=await self.food(id,context)
        rows=await self.db.request('/rest/v1/food_descriptions',context,dict(select=DESCRIPTION_COLUMNS,food_id='eq.'+str(id),
            locale='eq.vi',content_status='eq.published',is_current='eq.true',limit='2'))
        try:
            if len(rows)>1 or any(r['is_current'] is not True for r in rows): raise ValueError('Ambiguous current description')
            body=description_dto(rows[0]) if rows else None
            return FoodDescription(food_id=id,**{k:food[k] for k in ['slug','name_vi','name_en','scope_kind']},
                status='available' if body else 'description_unavailable',reason=None if body else 'not_published',description=body)
        except (ValidationError,ValueError,KeyError,TypeError): raise dependency_unavailable() from None
