from pathlib import Path
from unittest.mock import MagicMock
import pytest
from sticker_engine.publish.publisher import Publisher, EpisodeAssets
from sticker_engine.publish.config import PublishConfig

def setup_upload(tmp_path):
    pub=Publisher(PublishConfig(),MagicMock())
    page=MagicMock()
    fi=MagicMock();fi.get_attribute.return_value='.png'
    page.query_selector_all.return_value=[fi]
    assets=EpisodeAssets(tmp_path,stickers=[Path(str(i)+'.png') for i in range(20)],meanings=['好']*20)
    return pub,page,assets

def test_upload_requires_exact_twenty_accepted_cells(tmp_path):
    pub,page,assets=setup_upload(tmp_path)
    handle=page.wait_for_function.return_value
    handle.json_value.return_value={'count':20,'error':''}
    pub._step_upload_stickers(page,assets)
    assert page.wait_for_function.call_args.kwargs['arg'][1]==20
    handle.dispose.assert_called_once()

def test_platform_duplicate_is_not_a_successful_upload(tmp_path):
    pub,page,assets=setup_upload(tmp_path)
    page.wait_for_function.return_value.json_value.return_value={'count':4,'error':'与已上架表情重复'}
    with pytest.raises(RuntimeError,match='4/20.*与已上架表情重复.*未提交'):
        pub._step_upload_stickers(page,assets)

def test_upload_timeout_blocks_partial_album(tmp_path):
    pub,page,assets=setup_upload(tmp_path)
    page.wait_for_function.side_effect=TimeoutError()
    page.locator.return_value.count.return_value=4
    with pytest.raises(RuntimeError,match='4/20.*未提交'):
        pub._step_upload_stickers(page,assets)

def test_meanings_exhausted_retries_stop_before_submit(tmp_path):
    pub,page,assets=setup_upload(tmp_path)
    page.evaluate.side_effect=[None,{'n':4,'filled':4}]*3
    with pytest.raises(RuntimeError,match='4/20.*未提交'):
        pub._step_fill_meanings(page,assets)
    assert len(pub.warnings)==3

def test_extra_cells_are_not_silently_submitted(tmp_path):
    pub,page,assets=setup_upload(tmp_path)
    page.evaluate.side_effect=[None,{'n':21,'filled':21}]*3
    with pytest.raises(RuntimeError,match='平台 21 格'):
        pub._step_fill_meanings(page,assets)
