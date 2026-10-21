from datetime import date,datetime
from typing import Annotated,Literal
import re
from uuid import UUID
from pydantic import BaseModel,ConfigDict,Field,field_validator,model_validator,model_serializer

URI=Annotated[str,Field(json_schema_extra={'format':'uri'})]


def valid_uri(value):
    if not re.match(r'^[A-Za-z][A-Za-z0-9+.-]*:',value) or re.search(r'[\x00-\x20]',value):
        raise ValueError('Expected an absolute URI')
    return value


class DTO(BaseModel):
    model_config=ConfigDict(extra='forbid',allow_inf_nan=False)


class ErrorDetail(DTO):
    field:str | None
    message:str


class ErrorBody(DTO):
    code:str
    message:str
    details:list[ErrorDetail]
    request_id:str


class Error(DTO):
    error:ErrorBody


class Health(DTO):
    status:Literal['alive']='alive'


class Capabilities(DTO):
    catalog:bool
    scan:bool=False


class Readiness(DTO):
    status:Literal['ready','not_ready']
    database:Literal['ready','not_ready']
    model:Literal['ready','not_ready']='not_ready'
    capabilities:Capabilities


class Food(DTO):
    id:UUID
    slug:str
    name_vi:str
    name_en:str | None
    scope_kind:Literal['prepared_food','ingredient_or_component','broad_food_category']
    original_class_id:int | None=Field(ge=0,le=67,json_schema_extra={'not':{'const':27}})
    training_class_id:int=Field(ge=0,le=74)
    class_map_version:str

    @field_validator('original_class_id')
    @classmethod
    def exclude_face(cls,value):
        if value==27: raise ValueError('Original face class is excluded')
        return value

    @model_validator(mode='after')
    def validate_food_map(self):
        original=self.original_class_id;training=self.training_class_id
        if training<67:
            if original is None or original==27 or training!=(original if original<27 else original-1) or self.class_map_version!='vietfood-67-2026-10-12-v1':
                raise ValueError('Invalid legacy catalog identity')
        elif original is not None or self.class_map_version!='foodlens-75-2026-10-16-v2':
            raise ValueError('Owner extension has no VietFood original class ID')
        return self


class FoodPage(DTO):
    items:list[Food]
    next_cursor:str | None


DESCRIPTION_FIELDS=('short_intro','origin_text','ingredients_summary','characteristics','scope_note')
DESCRIPTION_NOTICE='Thông tin giới thiệu phổ thông về món ăn; không phải tư vấn sức khỏe, dinh dưỡng hay y tế.'
DescriptionField=Literal['short_intro','origin_text','ingredients_summary','characteristics','scope_note']


class ContentSource(DTO):
    source_key:str=Field(pattern=r'^[a-z0-9]+(-[a-z0-9]+)*$',max_length=100)
    title:str=Field(min_length=1,max_length=300)
    publisher:str=Field(min_length=1,max_length=200)
    url:URI
    language:Literal['vi','en']
    source_kind:Literal['government_tourism','government','university','museum','book','open_license_encyclopedia','other']
    revision_ref:str | None=Field(max_length=200)
    accessed_on:date
    license_note:str=Field(min_length=1,max_length=500)
    supports:list[DescriptionField]=Field(min_length=1,max_length=5)
    locator:str | None=Field(max_length=300)

    @field_validator('url')
    @classmethod
    def https_url(cls,value):
        if not valid_uri(value).startswith('https://'): raise ValueError('Content sources require HTTPS URLs')
        return value

    @field_validator('supports')
    @classmethod
    def unique_supports(cls,values):
        if len(set(values))!=len(values): raise ValueError('Duplicate supported field')
        return values


class DescriptionContent(DTO):
    locale:Literal['vi']
    version:int=Field(ge=1)
    content_status:Literal['published']
    short_intro:str=Field(min_length=1)
    origin_text:str | None
    ingredients_summary:str=Field(min_length=1)
    characteristics:str=Field(min_length=1)
    scope_note:str | None
    authoring_method:Literal['manual','ai_assisted_draft']
    reviewed_at:datetime
    published_at:datetime
    updated_at:datetime
    sources:list[ContentSource]=Field(min_length=1,max_length=20)

    @field_validator('reviewed_at','published_at','updated_at')
    @classmethod
    def aware(cls,value):
        if value.tzinfo is None: raise ValueError('Review timestamps must include timezone')
        return value

    @model_validator(mode='after')
    def every_field_cited(self):
        cited={f for s in self.sources for f in s.supports}
        if any(getattr(self,f) is not None and f not in cited for f in DESCRIPTION_FIELDS):
            raise ValueError('Every published field requires a cited source')
        return self


class FoodDescription(DTO):
    food_id:UUID
    slug:str
    name_vi:str
    name_en:str | None
    scope_kind:Literal['prepared_food','ingredient_or_component','broad_food_category']
    status:Literal['available','description_unavailable']
    reason:Literal['not_published'] | None
    description:DescriptionContent | None
    notice:Literal['Thông tin giới thiệu phổ thông về món ăn; không phải tư vấn sức khỏe, dinh dưỡng hay y tế.']=DESCRIPTION_NOTICE

    @model_validator(mode='after')
    def consistent_status(self):
        if (self.status=='available')!=(self.description is not None) or (self.reason is None)!=(self.status=='available'):
            raise ValueError('Description status, reason and body disagree')
        if self.description is not None and self.scope_kind=='broad_food_category' and self.description.scope_note is None:
            raise ValueError('Broad classes require a scope note')
        return self


class Profile(DTO):
    id:UUID
    display_name:str=Field(max_length=100)
    timezone:str
    created_at:datetime
    updated_at:datetime


Coordinate=Annotated[float,Field(ge=0,le=1,strict=True)]


class Alternative(DTO):
    food_id:UUID
    confidence:float=Field(ge=0,le=1,strict=True)


class Detection(DTO):
    detection_id:UUID
    predicted_food_id:UUID
    training_class_id:int=Field(ge=0,le=74,strict=True)
    original_class_id:int | None=Field(ge=0,le=67,strict=True,json_schema_extra={'not':{'const':27}})
    bbox:list[Coordinate]=Field(min_length=4,max_length=4)
    confidence:float=Field(ge=0,le=1,strict=True)
    alternatives:list[Alternative]=Field(default_factory=list,max_length=3)

    @model_serializer(mode='wrap')
    def preserve_optional_scores(self,handler):
        value=handler(self)
        if 'alternatives' not in self.model_fields_set: value.pop('alternatives',None)
        return value

    @model_validator(mode='after')
    def valid_geometry_and_remap(self):
        if self.bbox[0]>=self.bbox[2] or self.bbox[1]>=self.bbox[3]: raise ValueError('Invalid xyxy bbox')
        original=self.original_class_id
        if self.training_class_id<67:
            if original is None or original==27 or self.training_class_id!=(original if original<27 else original-1):raise ValueError('Invalid legacy class remap')
        elif original is not None:raise ValueError('Extension original class ID must be null')
        if len({a.food_id for a in self.alternatives})!=len(self.alternatives): raise ValueError('Duplicate alternative')
        return self


class Confirmation(DTO):
    detection_id:UUID
    confirmed_food_id:UUID


class ScanSummary(DTO):
    id:UUID
    status:Literal['processing','completed','failed']
    input_source:Literal['camera','gallery','share']
    revision:int=Field(ge=1)
    created_at:datetime
    updated_at:datetime


class Scan(ScanSummary):
    model_version:str | None
    class_map_version:str | None
    detections:list[Detection]=Field(max_length=100)
    confirmations:list[Confirmation]=Field(max_length=100)
    image_url:URI | None
    image_url_expires_at:datetime | None
    error_code:str | None

    @model_validator(mode='after')
    def validate_prediction_map(self):
        if self.status=='completed':
            if not self.model_version or self.class_map_version not in ('vietfood-67-2026-10-12-v1','foodlens-75-2026-10-16-v2'):
                raise ValueError('Completed scans require a known prediction map and model')
            if self.class_map_version=='vietfood-67-2026-10-12-v1' and any(d.training_class_id>=67 for d in self.detections):
                raise ValueError('Legacy scans cannot contain extension predictions')
        return self


class ScanPage(DTO):
    items:list[ScanSummary]
    next_cursor:str | None
