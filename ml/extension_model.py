"""Expand YOLO11n's class branch while retaining its learned legacy outputs.

This initializes a separate model, never overwrites the active 67-class weights.
It is an initialization technique, not evidence of post-training model quality.
"""
from copy import deepcopy


def preserve_classifier_prefix(target, source):
    import torch
    old_count, new_count = source.model[-1].nc, target.model[-1].nc
    if (old_count, new_count) != (67, 75) or len(source.model) != len(target.model):
        raise ValueError('Expected the exact owner-authorized 67-to-75 expansion')
    prefix = 'model.' + str(len(target.model) - 1) + '.cv3.'
    original, destination = source.state_dict(), target.state_dict()
    if set(original) != set(destination):
        raise ValueError('Unexpected architecture/state change; cannot safely preserve classifier')
    expanded = []
    with torch.no_grad():
        for key, value in destination.items():
            before = original[key].to(device=value.device, dtype=value.dtype)
            if before.shape == value.shape:
                value.copy_(before)
                continue
            if not key.startswith(prefix) or before.ndim != value.ndim or not all(
                    a == b or (a, b) == (old_count, new_count) for a, b in zip(before.shape, value.shape)):
                raise ValueError('Unexpected shape mismatch outside the expanded classifier: ' + key)
            # Expanded hidden channels must not perturb old output/hidden rows.
            if value.ndim >= 2 and value.shape[0] == new_count:
                value[:old_count].zero_()
            value[tuple(slice(0, n) for n in before.shape)].copy_(before)
            expanded.append(key)
        for branch in target.model[-1].cv3:
            if not isinstance(branch[-1], torch.nn.Conv2d) or branch[-1].out_channels != new_count:
                raise ValueError('Unexpected class projection layout')
            branch[-1].bias[old_count:].fill_(-6.)
    if not expanded:
        raise ValueError('No classifier expansion was performed')
    return dict(source_classes=old_count, target_classes=new_count, expanded_tensors=expanded,
                initialization='copy legacy channels; zero new-to-legacy input connections; new class prior -6')


def make_expanded(source, verbose=False):
    from ultralytics.nn.tasks import DetectionModel
    target = DetectionModel(deepcopy(source.yaml), nc=75, ch=3, verbose=verbose)
    report = preserve_classifier_prefix(target, source)
    return target, report


def extension_trainer_class():
    from .train_budget import atomic_trainer_class
    class ExtensionTrainer(atomic_trainer_class()):
        def check_resume(self,overrides):
            super().check_resume(overrides)
            if self.resume:
                # Saved args contain the old four-hour time setting. Resume must
                # use the remaining authorized time and earlier absolute cutoff.
                self.args.time=overrides['time']
        def get_model(self, cfg=None, weights=None, verbose=True):
            model = super().get_model(cfg=cfg, weights=weights, verbose=verbose)
            if not weights or not hasattr(weights, 'state_dict'):
                raise ValueError('The trusted trained 67-class source model is required')
            if getattr(self, 'resume', False) and weights.model[-1].nc == 75:
                return model
            self.extension_initialization = preserve_classifier_prefix(model, weights)
            return model
    return ExtensionTrainer
