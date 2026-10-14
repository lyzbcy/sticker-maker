from dataclasses import replace
from unittest.mock import MagicMock
import pytest
from sticker_engine.api import StickerEngine,Episode
from sticker_engine.config.schema import Config,Paths,Prefs
from sticker_engine.config.prompts import builtin_set,builtin_standard_set,apply_set
from sticker_engine.stages.generate import _apply_background_mode

def engine_at(tmp_path):
    paths=Paths(tmp_path,tmp_path/'episodes',tmp_path/'refs',tmp_path/'prefs.yaml','codex',tmp_path/'images')
    return StickerEngine(Config(paths=paths,prefs=Prefs(background_mode='transparent')))

@pytest.mark.parametrize('variant',[builtin_set,builtin_standard_set])
def test_solid_is_flat_and_caption_band_is_empty(variant):
    prompt=_apply_background_mode(apply_set('keyword_combo',variant()),'solid')
    assert 'single FLAT SOLID PASTEL COLOR' in prompt
    assert 'OR a simple gentle environment' not in prompt
    assert 'no environment' in prompt and 'upper 82%' in prompt
    assert 'bottom 18% contains ONLY' in prompt
    assert 'Background: solid magenta' not in prompt

def test_transparent_prompt_unchanged():
    original=apply_set('keyword_combo',builtin_set())
    assert _apply_background_mode(original,'transparent')==original

@pytest.mark.parametrize('background',['solid','transparent'])
def test_real_stage_sends_same_background_prompt_as_archived(tmp_path,monkeypatch,background):
    from PIL import Image
    from sticker_engine.stages.generate import GenerateStage
    from sticker_engine.pipeline.context import PipelineContext,EpisodeSpec
    engine=engine_at(tmp_path);engine.config.prefs.background_mode=background
    engine.config.prefs.ref_lib_priority=False
    ctx=PipelineContext(config=engine.config,episode=EpisodeSpec(grid_size=4));ctx.episode_dir=tmp_path/'episode';ctx.episode_dir.mkdir()
    source=tmp_path/'source.png';Image.new('RGB',(400,400),'blue').save(source)
    stage=GenerateStage(codex=MagicMock());seen=[]
    initial=builtin_set().style_block
    monkeypatch.setattr(stage,'_build_prompt_and_refs',lambda c,m:(initial,[]))
    monkeypatch.setattr(stage,'_gather_bases',lambda c:[])
    def generated(c,m,p,r,b):seen.append(p);return source
    monkeypatch.setattr(stage,'_generate_with_identity_gate',generated)
    stage.run(ctx)
    assert seen==[_apply_background_mode(initial,background)]
    archived=(ctx.episode_dir/'原图/prompt.txt').read_text(encoding='utf-8')
    assert archived.split('\n',2)[2]==seen[0]
    assert archived.count('REMINDER (background')==(1 if background=='solid' else 0)

def test_one_run_overrides_restore_config_and_do_not_write_defaults(tmp_path,monkeypatch):
    engine=engine_at(tmp_path);original=engine.config;seen=[]
    monkeypatch.setattr('sticker_engine.library.hooks.runtime_for',lambda e:None)
    def run(**kwargs):
        seen.append(engine.config.prefs);return Episode()
    monkeypatch.setattr(engine,'_run_impl',run)
    for ps in (builtin_set(),builtin_standard_set()):
        assert engine.run(prefs_override={'prompt_set_id':ps.id,'background_mode':'solid','sticker_text':True}).success
        assert engine.config is original and original.prefs.background_mode=='transparent'
        assert seen[-1].prompt_set_id==ps.id and seen[-1].background_mode=='solid'
    assert not original.paths.prefs_file.exists()

def test_exception_restores_original_config(tmp_path,monkeypatch):
    engine=engine_at(tmp_path);original=engine.config
    monkeypatch.setattr('sticker_engine.library.hooks.runtime_for',lambda e:None)
    def broken(**kwargs):raise RuntimeError('generation failed')
    monkeypatch.setattr(engine,'_run_impl',broken)
    with pytest.raises(RuntimeError):engine.run(prefs_override={'background_mode':'solid'})
    assert engine.config is original

@pytest.mark.parametrize('overrides',[{'default_series_id':'other'},{'grid_size':20},{'sticker_text':1},{'background_mode':'scenery'},{'prompt_set_id':'missing'},['solid']])
def test_unknown_or_invalid_overrides_fail_before_generation(tmp_path,monkeypatch,overrides):
    engine=engine_at(tmp_path)
    monkeypatch.setattr('sticker_engine.library.hooks.runtime_for',lambda e:None)
    generator=MagicMock();monkeypatch.setattr(engine,'_run_impl',generator)
    with pytest.raises(ValueError):engine.run(prefs_override=overrides)
    generator.assert_not_called()

def test_shared_reload_precedes_override_and_restore_capture(tmp_path,monkeypatch):
    engine=engine_at(tmp_path);rt=MagicMock();rt.refresh.return_value={}
    monkeypatch.setattr('sticker_engine.library.hooks.runtime_for',lambda e:rt)
    def reload(e,r):e.config.prefs=replace(e.config.prefs,background_mode='transparent',prompt_set_id=builtin_standard_set().id)
    monkeypatch.setattr('sticker_engine.library.hooks.reload_engine_config',reload)
    ep_dir=tmp_path/'new';ep_dir.mkdir();seen=[]
    def run(**kwargs):
        assert engine.config.prefs.prompt_set_id==builtin_set().id
        return Episode(episode_dir=ep_dir)
    monkeypatch.setattr(engine,'_run_impl',run)
    rt.capture.side_effect=lambda path:seen.append(engine.config.prefs.prompt_set_id)
    monkeypatch.setattr('sticker_engine.library.settings.SharedSettings',MagicMock())
    assert engine.run(prefs_override={'prompt_set_id':builtin_set().id}).success
    assert seen==[builtin_standard_set().id]

def test_cli_forwards_overrides_without_changing_normal_run(tmp_path,monkeypatch):
    from sticker_engine import cli
    engine=MagicMock();engine.run.return_value=Episode(episode_dir=tmp_path)
    monkeypatch.setattr(cli,'_ensure_engine',lambda:engine)
    monkeypatch.setattr(cli,'_sync_custom_bases',lambda e:None)
    monkeypatch.setattr(cli,'_result',MagicMock())
    cli.cmd_run('sample',{'prefs_override':{'background_mode':'solid'}})
    assert engine.run.call_args.kwargs['prefs_override']=={'background_mode':'solid'}
    cli.cmd_run('sample',{})
    assert 'prefs_override' not in engine.run.call_args.kwargs
