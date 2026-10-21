import hashlib
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from scripts import collect_extension_sources as sources


class Response:
    def __init__(self, content, status=200, headers=None):
        from io import BytesIO
        self.body = BytesIO(content)
        self.status = status
        self.headers = headers or {}

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, amount):
        return self.body.read(amount)


def test_short_eof_resumes_and_verifies_complete_hash(tmp_path):
    data = b'0123456789'
    target = tmp_path / 'source.bin'
    replies = [Response(data[:4], headers={'Content-Length': '10'}),
               Response(data[4:], 206, {'Content-Range': 'bytes 4-9/10'})]
    calls = []
    def open_request(request, **kwargs):
        calls.append(request.get_header('Range'))
        return replies.pop(0)
    with patch.object(sources, 'urlopen', side_effect=open_request):
        sources.fetch('https://example.invalid/source.bin', target, hashlib.sha256(data).hexdigest(), len(data))
    assert target.read_bytes() == data
    assert calls == [None, 'bytes=4-']
    assert not target.with_suffix('.bin.part').exists()


def test_resume_when_server_ignores_range_replaces_only_partial(tmp_path):
    target = tmp_path / 'source.bin'
    target.with_suffix('.bin.part').write_bytes(b'old incomplete data')
    body = b'correct whole asset'
    with patch.object(sources, 'urlopen', return_value=Response(body, 200, {'Content-Length': str(len(body))})):
        sources.fetch('https://example.invalid/source.bin', target, hashlib.sha256(body).hexdigest(), len(body))
    assert target.read_bytes() == body


def test_wrong_resume_range_is_not_accepted(tmp_path):
    target = tmp_path / 'source.bin'
    partial = target.with_suffix('.bin.part')
    partial.write_bytes(b'0123')
    with patch.object(sources, 'urlopen', return_value=Response(b'56789', 206, {'Content-Range': 'bytes 5-9/10'})):
        with pytest.raises(ValueError, match='resume offset'):
            sources.fetch('https://example.invalid/source.bin', target, expected_size=10)
    assert not target.exists()
    assert partial.read_bytes() == b'0123'


def test_completed_source_checksum_drift_is_never_overwritten(tmp_path):
    target = tmp_path / 'source.bin'
    target.write_bytes(b'preserve this source')
    with patch.object(sources, 'urlopen') as network:
        with pytest.raises(ValueError, match='Cached source checksum mismatch'):
            sources.fetch('https://example.invalid/source.bin', target, hashlib.sha256(b'other bytes').hexdigest())
    network.assert_not_called()
    assert target.read_bytes() == b'preserve this source'


def test_extension_preserves_all_legacy_identities_and_never_invents_original_ids():
    root = Path(__file__).resolve().parents[1]
    old = json.loads((root / 'docs/dataset/food-identities-v1.json').read_text(encoding='utf-8'))
    new = json.loads((root / 'docs/dataset/food-identities-v2.json').read_text(encoding='utf-8'))
    assert new['foods'][:len(old['foods'])] == old['foods']
    additions = new['foods'][len(old['foods']):]
    assert [f['name_vi'] for f in additions] == ['Chuối', 'Táo', 'Gà nướng', 'Cá hồi nướng', 'Khoai lang', 'Khóm', 'Cà phê', 'Nước ngọt']
    assert all(f['original_class_id'] is None for f in additions)
    assert len({f['id'] for f in new['foods']}) == len(new['foods'])
    assert [f['training_class_id'] for f in new['foods']] == list(range(len(new['foods'])))
    assert new['foods'][27]['name_vi'] == 'Củ kiệu'
    assert all(f['original_class_id'] != 27 for f in new['foods'])
