"""Inference-only frozen67 + new8 detector. No additional training is performed."""
from copy import deepcopy
import torch


class FrozenLegacyPlus8(torch.nn.Module):
    def __init__(self,extension,legacy=None):
        super().__init__()
        if len(extension.names)!=75:raise ValueError('Exact75-class extension required')
        if legacy is not None and (len(legacy.names)!=67 or any(legacy.names[i]!=extension.names[i] for i in range(67))):
            raise ValueError('Legacy67 names must match the preserved prefix')
        self.extension=extension.eval().requires_grad_(False)
        self.legacy=legacy.eval().requires_grad_(False) if legacy is not None else None
        self.names=dict(extension.names);self.nc=75;self.yaml=deepcopy(extension.yaml)
        self.args=dict(getattr(extension,'args',{}));self.task='detect';self.end2end=False
        self.register_buffer('stride',extension.stride.detach().clone())
        self.eval()

    def fuse(self,verbose=False):
        self.extension.fuse(verbose=verbose)
        if self.legacy is not None:self.legacy.fuse(verbose=verbose)
        return self

    def is_fused(self):
        return self.extension.is_fused() and (self.legacy is None or self.legacy.is_fused())

    def forward(self,x,augment=False,visualize=False,embed=None,**kwargs):
        if self.training or embed is not None:raise ValueError('Frozen pair is inference-only')
        value=self.extension(x,augment=augment)
        new=value[0] if isinstance(value,(tuple,list)) else value
        if new.shape[1]!=79:raise ValueError('Unexpected75-class prediction tensor')
        new=new.clone();new[:,4:71,:]=0.  # Only IDs67..74 from the fine-tuned model.
        if self.legacy is None:return new,[]
        value=self.legacy(x,augment=augment)
        old=value[0] if isinstance(value,(tuple,list)) else value
        if old.shape[1]!=71:raise ValueError('Unexpected67-class prediction tensor')
        old=torch.cat((old,torch.zeros_like(old[:,:8,:])),dim=1)
        return torch.cat((old,new),dim=2),[]


def load_yolo(extension_weights,legacy_weights=None):
    from ultralytics import YOLO
    extension=YOLO(str(extension_weights))
    legacy=YOLO(str(legacy_weights)) if legacy_weights is not None else None
    extension.model=FrozenLegacyPlus8(extension.model,legacy.model if legacy is not None else None)
    return extension


def validator_class():
    from ultralytics.models.yolo.detect.val import DetectionValidator
    from backend.app.taxonomy import keep_specific_foods
    class ConsistentValidator(DetectionValidator):
        def postprocess(self,preds):
            rows=super().postprocess(preds)
            for row in rows:
                keep=keep_specific_foods(row['bboxes'].tolist(),row['cls'].tolist(),row['conf'].tolist())
                for key in row:row[key]=row[key][keep]
            return rows
    return ConsistentValidator
