from .errors import ApiError,parse_result
from .models import Profile


class Profiles:
    def __init__(self,db): self.db=db

    async def profile(self,context,patch=None):
        if patch is not None:
            data=await self.db.rpc('patch_profile',{'p_request':patch.model_dump(mode='json',exclude_unset=True)},context)
        else:
            rows=await self.db.request('/rest/v1/profiles',context,params=dict(select='id,display_name,timezone,created_at,updated_at',id='eq.'+str(context.user_id),limit='1'))
            if not rows: raise ApiError(404,'NOT_FOUND','Profile was not found.')
            data=rows[0]
        return parse_result(Profile,data)
