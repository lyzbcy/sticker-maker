from pathlib import Path
from unittest.mock import MagicMock
import pytest
from sticker_engine.publish.publisher import Publisher, EpisodeAssets
from sticker_engine.publish.config import PublishConfig
from sticker_engine.publish import selectors as S


@pytest.mark.parametrize('actual', ['星星布丁精选表情', '星星布丁精选表情13'])
def test_actual_album_name_must_match_requested_title(actual):
    page = MagicMock()
    page.locator.return_value.input_value.return_value = actual
    publisher = Publisher(PublishConfig(), MagicMock())
    assets = EpisodeAssets(episode_dir=Path('fixture'), album_name='星星布丁精选表情13')
    if actual == assets.album_name:
        publisher._step_fill_album_info(page, assets)
    else:
        with pytest.raises(RuntimeError, match='专辑名称被平台修改.*未提交'):
            publisher._step_fill_album_info(page, assets)
    page.fill.assert_called_once_with(S.ALBUM_NAME_INPUT, assets.album_name)
    page.locator.assert_called_once_with(S.ALBUM_NAME_INPUT)
