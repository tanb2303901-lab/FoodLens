"""Exact human-authorized local preview binding; synthetic metadata only."""
from copy import deepcopy
import pytest

from ml.activate_local import owner_preview_matches


@pytest.mark.parametrize('damage',['none','no_owner','wrong_scope','version','weights_sha256','legacy_weights_sha256',
    'evaluation_sha256','class_map_sha256','other_failure','quality_digest'])
def test_owner_preview_cannot_apply_to_another_candidate_or_unknown_failure(damage):
    manifest=dict(model_version='SYNTHETIC-OWNER-PREVIEW-FIXTURE',weights_sha256='a'*64,
        legacy_weights_sha256='b'*64,evaluation_sha256='c'*64,class_map_sha256='d'*64)
    decision=deepcopy(manifest)|dict(authorized_by_owner=True,scope='local_owner_preview_only')
    quality=dict(status='failed',weights_sha256=manifest['weights_sha256'],evaluation_sha256=manifest['evaluation_sha256'],
        checks=[dict(name='legacy_validation',passed=True),dict(name='extension_test_class_71',passed=False)])
    if damage=='no_owner':decision['authorized_by_owner']=False
    elif damage=='wrong_scope':decision['scope']='cloud_or_general_approval'
    elif damage=='version':decision['model_version']='OTHER-SYNTHETIC-CANDIDATE'
    elif damage in manifest:decision[damage]='f'*64
    elif damage=='other_failure':quality['checks'].append(dict(name='extension_test_class_69',passed=False))
    elif damage=='quality_digest':quality['evaluation_sha256']='f'*64
    assert owner_preview_matches(manifest,quality,decision) is (damage=='none')
