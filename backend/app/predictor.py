"""Versioned67/75 mapping; missing verified weights remain unavailable."""
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Protocol
from uuid import UUID,uuid5,NAMESPACE_URL,uuid4
from pydantic import Field,ValidationError
from .images import CanonicalImage
from .models import DTO,Coordinate,Detection
from .errors import ApiError


@dataclass(frozen=True)
class PredictorInfo:
    model_version:str
    class_map_version:str
    class_map_sha256:str


class RawAlternative(DTO):
    training_class_id:int=Field(ge=0,le=74,strict=True)
    confidence:float=Field(ge=0,le=1,strict=True)


class RawDetection(DTO):
    training_class_id:int=Field(ge=0,le=74,strict=True)
    bbox:list[Coordinate]=Field(min_length=4,max_length=4)
    confidence:float=Field(ge=0,le=1,strict=True)
    alternatives:list[RawAlternative]=Field(default_factory=list,max_length=3)


class Predictor(Protocol):
    def status(self)->PredictorInfo | None: ...
    async def predict(self,image:CanonicalImage,info:PredictorInfo)->list[RawDetection]: ...


class UnavailablePredictor:
    def status(self): return None
    async def predict(self,image,info): raise model_not_ready()


def model_not_ready():
    return ApiError(503,'MODEL_NOT_READY','Detector weights and matching class map are not ready.')


class ClassMap:
    VERSIONS={'vietfood-67-2026-10-12-v1':(1,67,'food-identities-v1.json'),
              'foodlens-75-2026-10-16-v2':(2,75,'food-identities-v2.json')}

    def __init__(self,version='vietfood-67-2026-10-12-v1'):
        if version not in self.VERSIONS:raise ValueError('Unsupported class map version')
        artifact_version,count,self.filename=self.VERSIONS[version]
        directory=Path(__file__).resolve().parents[2]/'docs/dataset'
        path=directory/self.filename
        raw=path.read_bytes(); artifact=json.loads(raw)
        if artifact.get('artifact_version')!=artifact_version or artifact.get('class_map_version')!=version:
            raise ValueError('Unsupported class map version')
        self.version=artifact['class_map_version']; self.digest=hashlib.sha256(raw).hexdigest()
        foods=artifact['foods']; self.foods={f['training_class_id']:f for f in foods}
        if len(foods)!=count or set(self.foods)!=set(range(count)) or len({f['id'] for f in foods})!=count or len({f['slug'] for f in foods})!=count:
            raise ValueError('Class map must contain its exact unique identities and training IDs')
        if artifact_version==2:
            legacy_raw=(directory/'food-identities-v1.json').read_bytes();legacy=json.loads(legacy_raw)
            if foods[:67]!=legacy['foods'] or artifact.get('base_class_map_sha256')!=hashlib.sha256(legacy_raw).hexdigest():
                raise ValueError('Extension must preserve the exact original67 identities')
            if [f['slug'] for f in foods[67:]]!=['chuoi','tao','ga_nuong','ca_hoi_nuong','khoai_lang','khom','ca_phe','nuoc_ngot']:
                raise ValueError('Unsupported owner extension classes')
        for t,f in self.foods.items():
            o=f['original_class_id']
            valid_original=(type(o) is int and o!=27 and 0<=o<=67 and t==(o if o<27 else o-1)) if t<67 else (
                o is None and f.get('source_namespace')=='foodlens-owner-extension-2026-10-16' and type(f.get('source_class_id')) is int and f['source_class_id']==t-67)
            if type(t) is not int or not valid_original or f['id']!=str(uuid5(NAMESPACE_URL,'urn:foodlens:food:'+f['slug'])):
                raise ValueError('Invalid portable food identity')

    def compatible(self,info):
        return isinstance(info,PredictorInfo) and isinstance(info.model_version,str) and 1<=len(info.model_version)<=128 and info.class_map_version==self.version and info.class_map_sha256==self.digest

    def detections(self,rows):
        try:
            if not isinstance(rows,list) or len(rows)>100: raise ValueError()
            result=[]
            for raw in rows:
                d=RawDetection.model_validate(raw)
                f=self.foods[d.training_class_id]
                alternatives=[dict(food_id=self.foods[a.training_class_id]['id'],confidence=a.confidence) for a in d.alternatives]
                dto=Detection(detection_id=uuid4(),predicted_food_id=f['id'],training_class_id=d.training_class_id,
                              original_class_id=f['original_class_id'],bbox=d.bbox,confidence=d.confidence,alternatives=alternatives)
                encoded=dto.model_dump(mode='json')
                if not alternatives: encoded.pop('alternatives')  # Never manufacture a Top-3 field.
                result.append(encoded)
            return result
        except (ValueError,TypeError,KeyError,ValidationError):
            raise ApiError(503,'PREDICTION_INVALID_OUTPUT','Detector output is invalid for the FoodLens class map.') from None
