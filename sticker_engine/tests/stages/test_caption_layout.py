import json
from pathlib import Path
from unittest.mock import MagicMock

import numpy as np
import pytest
from PIL import Image, ImageDraw

from sticker_engine.stages.postprocess import (
    draw_caption, prepare_caption_canvas, normalize_solid_background, PostprocessStage,
)
from sticker_engine.stages.assets import pick_header_candidates
from sticker_engine.pipeline.context import PipelineContext, EpisodeSpec
from sticker_engine.config.schema import Config


def panel():
    im = Image.new('RGBA', (240, 240), (200, 225, 250, 255))
    d = ImageDraw.Draw(im)
    d.rectangle((70, 20, 170, 239), fill=(30, 40, 50, 255))
    d.rectangle((80, 230, 160, 239), fill=(10, 240, 30, 255))
    return im


def test_entire_bottom_foot_moves_above_caption_band():
    im = draw_caption(panel(), '开心')
    a = np.array(im)
    foot = (a[:, :, 1] > 220) & (a[:, :, 0] < 40) & (a[:, :, 2] < 70)
    assert foot.any()
    assert np.where(foot)[0].max() < int(240 * .82)
    assert not foot[int(240 * .82):].any()
    red = (a[:, :, 0] > 210) & (a[:, :, 1] < 90) & (a[:, :, 2] < 90)
    assert red.any() and np.where(red)[0].min() >= int(240 * .84)


def test_layout_has_exact_empty_band_before_caption():
    im = prepare_caption_canvas(panel())
    a = np.array(im)
    assert np.unique(a[int(240 * .82):].reshape(-1, 4), axis=0).shape[0] == 1
    assert im.size == (240, 240)


def test_empty_caption_does_not_change_pixels():
    im = panel()
    assert draw_caption(im, '').tobytes() == im.tobytes()


def test_flatten_preserves_outline_and_enclosed_pastel_character():
    a = np.zeros((100, 100, 4), dtype=np.uint8)
    for y in range(100):
        a[y] = (200 + y // 5, 220, 245, 255)
    im = Image.fromarray(a)
    d = ImageDraw.Draw(im)
    d.rectangle((25, 20, 75, 90), fill='white')
    d.rectangle((28, 23, 72, 87), fill=(210, 220, 245, 255))
    before = np.array(im)
    after = np.array(normalize_solid_background(im))
    assert np.array_equal(after[20:91, 25:76], before[20:91, 25:76])
    assert np.unique(after[:, :20].reshape(-1, 4), axis=0).shape[0] == 1


def test_dark_unknown_background_untouched():
    im = Image.new('RGBA', (240, 240), 'black')
    assert normalize_solid_background(im).tobytes() == im.tobytes()


def test_outer_grid_line_removed_but_character_white_outline_retained():
    im = panel(); d = ImageDraw.Draw(im)
    d.line((7, 0, 7, 239), fill='white', width=4)
    d.ellipse((80, 30, 160, 110), fill='white')
    result = np.array(normalize_solid_background(im))
    assert tuple(result[150, 7]) == (200, 225, 250, 255)
    assert tuple(result[70, 120]) == (255, 255, 255, 255)


def test_white_component_touching_frame_and_character_not_removed():
    im = panel();d = ImageDraw.Draw(im)
    d.line((7, 0, 7, 239), fill='white', width=4)
    d.line((7, 80, 120, 80), fill='white', width=4)
    a = np.array(normalize_solid_background(im))
    assert tuple(a[80, 120]) == (255, 255, 255, 255)


@pytest.mark.parametrize('cloth', [(225, 222, 220, 255), (210, 209, 211, 255), (240, 237, 238, 255)])
def test_shaded_white_clothing_open_to_frame_is_not_pastel_background(cloth):
    im = Image.new('RGBA', (120, 120), (225, 214, 250, 255))
    d = ImageDraw.Draw(im)
    d.rectangle((38, 68, 85, 119), fill=cloth)
    before = np.array(im);after = np.array(normalize_solid_background(im))
    assert np.array_equal(before[68:, 38:86], after[68:, 38:86])
    assert tuple(after[100, 10]) == (225, 214, 250, 255)


def test_neutral_light_background_stays_conservative():
    im = Image.new('RGBA', (120, 120), (230, 229, 231, 255))
    assert normalize_solid_background(im).tobytes() == im.tobytes()


def episode(tmp_path, words):
    final = tmp_path / '最终版'
    final.mkdir()
    no = tmp_path / '原图' / '_noword'
    no.mkdir(parents=True)
    paths = []
    for w in words:
        p = final / (w + '.png')
        panel().save(p); panel().save(no / p.name); paths.append(p)
    (tmp_path / 'meaning_map.json').write_text(json.dumps(dict(enumerate(words, 1))), encoding='utf-8')
    return paths, no


def test_runtime_header_slots_use_noword_not_final(tmp_path):
    paths, no = episode(tmp_path, ['场景', '视觉改名'])
    assert pick_header_candidates(paths, header_slots=[2]) == [no / '视觉改名.png']


def test_persisted_names_work_with_sorted_paths_and_changed_words(tmp_path):
    paths, no = episode(tmp_path, ['Z场景', 'A视觉改名'])
    (tmp_path / 'header_sources.json').write_text(json.dumps({'2': 'A视觉改名.png'}), encoding='utf-8')
    assert pick_header_candidates(sorted(paths), ep_dir=tmp_path) == [no / 'A视觉改名.png']


def test_legacy_prompt_proves_slots_after_vision_rename(tmp_path):
    words = ['视觉词' + str(i) for i in range(1, 17)]
    paths, no = episode(tmp_path, words)
    (tmp_path / '原图' / 'prompt.txt').write_text(
        '# mode: keyword_combo\n' + '\n'.join(f'{i}. HEADER SHOT (happy)' for i in range(13, 17)), encoding='utf-8')
    assert {p.name for p in pick_header_candidates(sorted(paths), ep_dir=tmp_path)} == {w + '.png' for w in words[12:]}
    assert all(p.parent == no for p in pick_header_candidates(sorted(paths), ep_dir=tmp_path))


def test_no_provenance_never_assumes_last_four_are_headers(tmp_path):
    paths, _ = episode(tmp_path, ['视觉词' + str(i) for i in range(1, 17)])
    assert pick_header_candidates(paths, ep_dir=tmp_path) == []


def test_path_traversal_in_header_sources_does_not_escape(tmp_path):
    paths, _ = episode(tmp_path, ['视觉改名'])
    (tmp_path / 'header_sources.json').write_text(json.dumps({'13': '../escape.png'}), encoding='utf-8')
    assert pick_header_candidates(paths, ep_dir=tmp_path) == []


def test_s2_persists_exact_deduplicated_header_filename(tmp_path, monkeypatch):
    import sticker_engine.stages.postprocess as post
    grid = tmp_path / 'grid.png';panel().save(grid)
    cfg = Config.placeholder();cfg.prefs.background_mode = 'solid';cfg.prefs.vision_calls = False
    ctx = PipelineContext(config=cfg, episode=EpisodeSpec(grid_size=2))
    ctx.episode_dir = tmp_path;ctx.grid_image = grid;ctx.header_slots = [4]
    ctx.preset_meanings = ['视觉改名', '同名', '同名', '视觉改名']
    monkeypatch.setattr(post, 'cut_grid', lambda *a, **kw: ([grid] * 4, []))
    stage = PostprocessStage(MagicMock(), MagicMock());stage.run(ctx)
    assert json.loads((tmp_path / 'header_sources.json').read_text(encoding='utf-8')) == {'4': '视觉改名2.png'}
    assert json.loads((tmp_path / 'cell_sources.json').read_text(encoding='utf-8')) == {
        '1': '视觉改名.png', '2': '同名.png', '3': '同名2.png', '4': '视觉改名2.png'}
    assert (tmp_path / '原图' / '_noword' / '视觉改名2.png').exists()
    paths = sorted((tmp_path / '最终版').glob('*.png'))
    assert pick_header_candidates(paths, ep_dir=tmp_path) == [tmp_path / '原图' / '_noword' / '视觉改名2.png']


def test_regen_reflow_is_repeatable_and_keeps_original_backup_and_rating(tmp_path, monkeypatch):
    import hashlib
    from sticker_engine import cli
    from sticker_engine.config.series import save_meta, EpisodeMeta
    paths, no = episode(tmp_path, ['视觉改名'])
    save_meta(tmp_path, EpisodeMeta(work_id='test', album_name='测试'))
    (tmp_path / '原图' / 'prompt.txt').write_text('single FLAT SOLID PASTEL COLOR', encoding='utf-8')
    rating = tmp_path / 'rating.json';rating.write_text('{"overall":1}', encoding='utf-8')
    old = paths[0].read_bytes();old_no = (no / paths[0].name).read_bytes();score = rating.read_bytes()
    result = []
    monkeypatch.setattr(cli, '_result', lambda *a, **kw: result.append((a, kw)))
    args = {'episode_dir': str(tmp_path), 'reflow_solid_captions': True}
    cli.cmd_regen_assets('test', args)
    once = paths[0].read_bytes()
    cli.cmd_regen_assets('test', args)
    assert result[-1][0][1] == 'ok'
    assert paths[0].read_bytes() == once and once != old
    backup = tmp_path / '原图' / '_caption_layout_backup'
    assert (backup / '最终版' / paths[0].name).read_bytes() == old
    assert (backup / '_noword' / paths[0].name).read_bytes() == old_no
    assert rating.read_bytes() == score
    manifest = json.loads((backup / 'manifest.json').read_text(encoding='utf-8'))
    assert all(hashlib.sha256((backup / n).read_bytes()).hexdigest() == h for n, h in manifest.items())


def test_regen_missing_noword_stops_before_any_final_write(tmp_path, monkeypatch):
    from sticker_engine import cli
    from sticker_engine.config.series import save_meta, EpisodeMeta
    paths, no = episode(tmp_path, ['视觉改名'])
    save_meta(tmp_path, EpisodeMeta(work_id='test'))
    (tmp_path / '原图' / 'prompt.txt').write_text('single FLAT SOLID PASTEL COLOR', encoding='utf-8')
    (no / paths[0].name).unlink()
    before = paths[0].read_bytes();result = []
    monkeypatch.setattr(cli, '_result', lambda *a, **kw: result.append((a, kw)))
    cli.cmd_regen_assets('test', {'episode_dir': str(tmp_path), 'reflow_solid_captions': True})
    assert result[0][0][1] == 'fail'
    assert paths[0].read_bytes() == before
    assert not (tmp_path / '原图' / '_caption_layout_backup').exists()


def test_regen_explicit_pick_prefers_uncaptioned_source(tmp_path):
    from sticker_engine import cli
    from sticker_engine.config.series import EpisodeMeta
    paths, no = episode(tmp_path, ['视觉改名'])
    Image.new('RGBA', (240, 240), 'red').save(paths[0])
    meta = EpisodeMeta(work_id='test', cover_mode='pick', cover_pick=0)
    cli._regen_episode_assets(tmp_path, meta)
    assert Image.open(tmp_path / '封面' / '封面.png').tobytes() == Image.open(no / paths[0].name).tobytes()


def recovery_episode(tmp_path):
    from sticker_engine.config.series import save_meta, EpisodeMeta
    paths, no = episode(tmp_path, ['开心', '委屈'])
    save_meta(tmp_path, EpisodeMeta(work_id='repair', album_name='修复'))
    (tmp_path / '原图' / 'prompt.txt').write_text('single FLAT SOLID PASTEL COLOR', encoding='utf-8')
    (tmp_path / 'meaning_map.json').write_text(json.dumps({'1': '开心', '2': '委屈'}), encoding='utf-8')
    raw = tmp_path / '原图' / '_panels';raw.mkdir()
    for i in (1, 2):
        im = Image.new('RGBA', (120, 120), (225, 214, 250, 255))
        ImageDraw.Draw(im).rectangle((38, 68, 85, 119), fill=(225, 222, 220, 255))
        im.save(raw / f'panel_{i:02d}.png')
    return paths, no, raw


def test_panel_recovery_preserves_originals_rating_and_is_repeatable(tmp_path, monkeypatch):
    import hashlib
    from sticker_engine import cli
    paths, no, raw = recovery_episode(tmp_path)
    old = {str(p.relative_to(tmp_path)): p.read_bytes() for p in paths + list(no.glob('*.png'))}
    raw_bytes = {p.name: p.read_bytes() for p in raw.glob('*.png')}
    rating = tmp_path / 'rating.json';rating.write_text('{"overall":1}', encoding='utf-8');score = rating.read_bytes()
    result=[];monkeypatch.setattr(cli, '_result', lambda *a, **kw: result.append(a))
    args={'episode_dir':str(tmp_path),'reflow_solid_captions':True,'recover_solid_sources_from_panels':True}
    cli.cmd_regen_assets('test', args);assert result[-1][1]=='ok'
    first={p.name:p.read_bytes() for p in paths}
    a=np.array(Image.open(no/'开心.png'));assert tuple(a[100,60])==(225,222,220,255)
    cli.cmd_regen_assets('test', args);assert result[-1][1]=='ok'
    assert {p.name:p.read_bytes() for p in paths}==first and rating.read_bytes()==score
    assert {p.name:p.read_bytes() for p in raw.glob('*.png')}==raw_bytes
    backup=tmp_path/'原图/_caption_layout_backup'
    assert (backup/'最终版/开心.png').read_bytes()==old['最终版/开心.png' if '/' in str(paths[0].relative_to(tmp_path)) else '最终版\\开心.png']
    manifest=json.loads((backup/'manifest.json').read_text(encoding='utf-8'))
    assert all(hashlib.sha256((backup/n).read_bytes()).hexdigest()==h for n,h in manifest.items())
    proof=json.loads((tmp_path/'solid_source_recovery.json').read_text(encoding='utf-8'))
    assert len(proof['sources'])==2


@pytest.mark.parametrize('failure', ['missing', 'ambiguous', 'traversal', 'corrupt', 'published', 'missing_flag'])
def test_invalid_panel_recovery_never_writes_finals_or_backup(tmp_path, monkeypatch, failure):
    from sticker_engine import cli
    from sticker_engine.config.series import load_meta, save_meta
    paths,no,raw=recovery_episode(tmp_path)
    args={'episode_dir':str(tmp_path),'reflow_solid_captions':True,'recover_solid_sources_from_panels':True}
    if failure=='missing':(raw/'panel_02.png').unlink()
    elif failure=='corrupt':(raw/'panel_02.png').write_text('not an image')
    elif failure=='ambiguous':(tmp_path/'meaning_map.json').write_text(json.dumps({'1':'开心','2':'开心'}),encoding='utf-8')
    elif failure=='traversal':(tmp_path/'cell_sources.json').write_text(json.dumps({'1':'../开心.png','2':'委屈.png'}),encoding='utf-8')
    elif failure=='published':
        meta=load_meta(tmp_path);meta.published=True;save_meta(tmp_path,meta)
    else:args.pop('reflow_solid_captions')
    before={str(p):p.read_bytes() for p in paths+list(no.glob('*.png'))};result=[]
    monkeypatch.setattr(cli,'_result',lambda *a,**kw:result.append(a));cli.cmd_regen_assets('test',args)
    assert result[-1][1]=='fail'
    assert all(Path(p).read_bytes()==data for p,data in before.items())
    assert not (tmp_path/'原图/_caption_layout_backup').exists()
