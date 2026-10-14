"""Human feedback: conversation wording and actual subject centering, not AI grades."""
import json
from unittest.mock import MagicMock
import numpy as np
import pytest
from PIL import Image,ImageDraw
from sticker_engine.stages import postprocess as post
from sticker_engine.config.schema import Config
from sticker_engine.pipeline.context import PipelineContext,EpisodeSpec

@pytest.mark.parametrize('action,chat', [('俏皮招手','哈喽'),('傲娇不满','随你便'),('双手点赞','你真棒'),('困意来袭','困困')])
def test_user_identified_action_labels_become_chat_phrases(action,chat):
 transform=getattr(post,'conversational_meaning',lambda x:x)
 assert transform(action)==chat

def test_unknown_or_already_usable_text_is_not_invented():
 transform=getattr(post,'conversational_meaning',lambda x:x)
 for word in ['开心','拜托啦','抓住爱','自定义短句']:assert transform(word)==word

def test_human_reported_detached_nine_percent_divider_removed_not_outline():
 im=Image.new('RGBA',(240,240),(255,219,184,255));d=ImageDraw.Draw(im)
 d.line((22,0,22,220),fill='white',width=1);d.ellipse((70,20,180,170),fill='white');d.ellipse((74,24,176,166),fill=(40,45,50,255))
 a=np.array(post.normalize_solid_background(im))
 assert tuple(a[150,22])==(255,219,184,255)
 assert tuple(a[20,125])==(255,255,255,255)

def small_subject():
 im=Image.new('RGBA',(240,240),(206,232,255,255));ImageDraw.Draw(im).rectangle((90,15,150,95),fill=(30,40,50,255));return im

def test_real_sample_pastel_green_edge_fringe_removed():
 im=Image.new('RGBA',(314,314),(254,220,184,255));d=ImageDraw.Draw(im)
 d.line((0,0,0,313),fill=(224,250,215,255));d.line((1,0,1,313),fill=(238,235,198,255))
 d.ellipse((50,10,270,298),fill='white');d.ellipse((55,15,265,293),fill=(30,40,50,255))
 a=np.array(post.normalize_solid_background(im))
 assert tuple(a[150,0])==(254,220,184,255)
 assert tuple(a[10,160])==(255,255,255,255)

def test_colored_edge_with_foreground_interruption_is_preserved():
 im=Image.new('RGBA',(314,314),(254,220,184,255));d=ImageDraw.Draw(im)
 d.line((0,0,0,313),fill=(224,250,215,255));d.rectangle((0,100,8,150),fill=(30,40,50,255))
 a=np.array(post.normalize_solid_background(im))
 assert tuple(a[125,0])==(30,40,50,255)
 assert tuple(a[50,0])==(224,250,215,255)

def test_subject_fills_and_centers_artwork_area_not_original_canvas():
 a=np.array(post.prepare_caption_canvas(small_subject()));foreground=(a[:196,:,:3].min(axis=2)<100)
 ys,xs=np.where(foreground)
 assert ys.max()-ys.min()+1>=175
 assert abs((ys.max()+ys.min())/2-97.5)<=3
 assert abs((xs.max()+xs.min())/2-119.5)<=3
 assert np.unique(a[196:].reshape(-1,4),axis=0).shape[0]==1

def test_nonuniform_scene_keeps_original_whole_source_behavior():
 im=small_subject();ImageDraw.Draw(im).rectangle((0,120,239,239),fill=(120,150,180,255))
 out=post.prepare_caption_canvas(im);assert out.size==(240,240)
 a=np.array(out);assert ((a[:196,:,0]==120)&(a[:196,:,1]==150)).any()

def test_s2_caption_filename_and_published_meaning_stay_identical(tmp_path):
 cfg=Config.placeholder();cfg.prefs.background_mode='solid';cfg.prefs.vision_calls=False
 ctx=PipelineContext(config=cfg,episode=EpisodeSpec(grid_size=1));ctx.episode_dir=tmp_path;ctx.grid_image=tmp_path/'source.png';small_subject().save(ctx.grid_image);ctx.preset_meanings=['双手点赞']
 post.PostprocessStage(MagicMock(),MagicMock()).run(ctx)
 assert json.loads((tmp_path/'meaning_map.json').read_text(encoding='utf-8'))=={'1':'你真棒'}
 assert (tmp_path/'最终版/你真棒.png').exists() and (tmp_path/'原图/_noword/你真棒.png').exists()
 assert json.loads((tmp_path/'cell_sources.json').read_text(encoding='utf-8'))=={'1':'你真棒.png'}

def test_new_word_collision_stops_before_meaning_or_final_write(tmp_path,monkeypatch):
 cfg=Config.placeholder();cfg.prefs.background_mode='solid';cfg.prefs.vision_calls=False
 ctx=PipelineContext(config=cfg,episode=EpisodeSpec(grid_size=2));ctx.episode_dir=tmp_path;ctx.grid_image=tmp_path/'source.png';small_subject().save(ctx.grid_image)
 ctx.preset_meanings=['俏皮招手','哈喽','开心','委屈'];monkeypatch.setattr(post,'cut_grid',lambda *a,**kw:([ctx.grid_image]*4,[]))
 with pytest.raises(ValueError,match='聊天文案'):
  post.PostprocessStage(MagicMock(),MagicMock()).run(ctx)
 assert not (tmp_path/'meaning_map.json').exists() and not (tmp_path/'最终版').exists()
