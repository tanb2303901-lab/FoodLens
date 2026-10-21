import math
from pathlib import Path

from PIL import Image
import pytest

from ml.train_extension import remaining_seconds, accepted_export, progress_epoch, resume_consumed, available_seconds
from scripts.build_extension_dataset import crop_region


@pytest.mark.parametrize('hours,consumed', [(3.01,0),(4,0),(0,0),(3,-1),(math.nan,0),(3,math.inf)])
def test_extension_budget_cannot_exceed_owner_limit_or_reset_elapsed(hours, consumed):
    with pytest.raises(ValueError): remaining_seconds(hours, consumed)


def test_extension_budget_accounts_for_consumed_time():
    assert remaining_seconds(3, 3600) == 7200
    assert remaining_seconds(3, 10801) < 0


def test_progress_callback_accepts_ultralytics_before_first_epoch():
    from types import SimpleNamespace
    assert progress_epoch(SimpleNamespace(start_epoch=0))==0
    assert progress_epoch(SimpleNamespace(start_epoch=7,epoch=9))==9


def pause_fixture():
    from datetime import datetime,timezone
    previous=dict(stage='paused_by_owner',created_at='2026-10-16T03:37:00+00:00',paused_at='2026-10-16T03:49:00+00:00',
        resume_checkpoint_sha256='own-checkpoint',training_job_elapsed_seconds=720.)
    control=dict(consumed_before_child_seconds=60.,child_dispatch_at='2026-10-16T03:38:00+00:00')
    pause=dict(status='paused_by_owner',first_started_at=previous['created_at'],paused_at=previous['paused_at'],
        resume_checkpoint_sha256='own-checkpoint',training_elapsed_seconds=720.)
    ledger=dict(paused_at=previous['paused_at'],training_elapsed_seconds_at_verified_pause=720.,training_budget_hours=3)
    return previous,control,pause,ledger,datetime(2026,10,16,4,49,tzinfo=timezone.utc)


def test_verified_pause_excludes_offline_time_without_resetting_training_elapsed():
    previous,control,pause,ledger,now=pause_fixture()
    assert resume_consumed(previous,control,pause,ledger,now,'own-checkpoint')==(720.,3600.)


def test_pause_cannot_hide_unknown_crash_downtime_or_be_applied_twice():
    previous,control,pause,ledger,now=pause_fixture()
    previous['stage']='training_failed'
    assert resume_consumed(previous,control,pause,ledger,now,'own-checkpoint')==(4320.,0.)
    previous['stage']='paused_by_owner';ledger['pause_resume_dispatch_at']='already consumed'
    assert resume_consumed(previous,control,pause,ledger,now,'own-checkpoint')==(4320.,0.)


@pytest.mark.parametrize('alter',['checkpoint','elapsed','pause_time'])
def test_tampered_pause_never_gets_free_training_time(alter):
    previous,control,pause,ledger,now=pause_fixture()
    sha='own-checkpoint'
    if alter=='checkpoint':sha='changed-checkpoint'
    if alter=='elapsed':pause['training_elapsed_seconds']=0
    if alter=='pause_time':ledger['paused_at']='2026-10-16T04:00:00+00:00'
    with pytest.raises(ValueError,match='Pause evidence'):
        resume_consumed(previous,control,pause,ledger,now,sha)


def test_absolute_cutoff_stops_earlier_than_remaining_active_budget():
    from datetime import datetime,timezone
    now=datetime(2026,10,16,4,45,tzinfo=timezone.utc)
    assert available_seconds(3,720,'2026-10-16T06:00:00+00:00',now)==4500
    assert available_seconds(3,10700,'2026-10-16T06:00:00+00:00',now)==100
    assert available_seconds(3,720,'2026-10-16T04:44:00+00:00',now)<0


def test_training_rejects_unrelated_dataset_before_reading_files(tmp_path):
    with pytest.raises(ValueError, match='isolated ML-05'):
        accepted_export(tmp_path)


def test_crop_preserves_original_object_geometry_and_clips_context_at_edge():
    image=Image.new('RGB',(200,100))
    cropped, box, bounds=crop_region(image,[0,.2,.5,.8],context=.1)
    assert bounds == (0,14,110,86)
    assert cropped.size == (110,72)
    assert box == pytest.approx([0,6/72,100/110,66/72])
    # Transforming back must recover the approved box, not the crop extent.
    assert [box[0]*cropped.width+bounds[0], box[1]*cropped.height+bounds[1],
            box[2]*cropped.width+bounds[0], box[3]*cropped.height+bounds[1]] == pytest.approx([0,20,100,80])


@pytest.mark.parametrize('box', [[.5,.2,.4,.8],[0,0,math.nan,1],[-.1,0,.5,1],[0,0,1.1,1]])
def test_invalid_region_never_becomes_a_full_frame_fake_label(box):
    with pytest.raises(ValueError): crop_region(Image.new('RGB',(200,100)),box)
