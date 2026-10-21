"""Strict JSON inputs; preserve omitted fields when passing PATCH through to RPC."""
from datetime import datetime,timezone
import re
from typing import Annotated
from uuid import UUID
from pydantic import BeforeValidator,ConfigDict,Field,WithJsonSchema,model_validator
from .models import DTO


def iso_timestamp(value):
    if not isinstance(value,str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})',value):
        raise ValueError('Expected an ISO timestamp with timezone')
    try:
        parsed=datetime.fromisoformat(value.replace('Z','+00:00'))
        if parsed.tzinfo is None: raise ValueError('Timezone required')
        return parsed.astimezone(timezone.utc)
    except OverflowError:
        raise ValueError('Timestamp is outside the supported UTC calendar range') from None


Timestamp=Annotated[datetime,BeforeValidator(iso_timestamp),WithJsonSchema({'type':'string','format':'date-time',
    'pattern':r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})$'},mode='validation')]
def strict_input_schema(schema):
    for name,prop in schema.get('properties',{}).items():
        if prop.get('default','not-null') is None: prop.pop('default')
        if 'anyOf' in prop:
            valid=[s for s in prop['anyOf'] if s.get('type')!='null']
            if len(valid)==1: prop.pop('anyOf'); prop.update(valid[0])
            else: prop['anyOf']=valid
    if schema.get('title')=='ProfilePatch': schema['minProperties']=1


class InputDTO(DTO):
    model_config=ConfigDict(extra='forbid',allow_inf_nan=False,json_schema_extra=strict_input_schema)


class Partial(InputDTO):
    @model_validator(mode='after')
    def partial_non_null(self):
        if not self.model_fields_set: raise ValueError('At least one field required')
        if any(getattr(self,n) is None for n in self.model_fields_set): raise ValueError('Explicit NULL is not accepted')
        return self


class ProfilePatch(Partial):
    display_name:str | None=Field(default=None,max_length=100)
    timezone:str | None=Field(default=None,min_length=1)


class ConfirmationInput(InputDTO):
    detection_id:UUID
    food_id:UUID


class ScanResultPatch(InputDTO):
    confirmations:list[ConfirmationInput]=Field(max_length=100)

    @model_validator(mode='after')
    def unique_detections(self):
        if len({c.detection_id for c in self.confirmations})!=len(self.confirmations): raise ValueError('Duplicate detection ID')
        return self
