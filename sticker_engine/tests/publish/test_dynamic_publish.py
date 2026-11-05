import json
from pathlib import Path
from unittest.mock import MagicMock
import pytest
from PIL import Image
from sticker_engine.publish.publisher import EpisodeAssets,Publisher
from sticker_engine.publish.config import PublishConfig

def episode(tmp_path,n=8):
 p=tmp_path/'动态';f=p/'最终版';f.mkdir(parents=True)
 for i in range(n):
  a=Image.new('RGBA',(240,240),(255,0,i*10,255));b=Image.new('RGBA',(240,240),(0,255,i*10,255))
  a.save(f/f'词{i}.gif',save_all=True,append_images=[b],duration=100,loop=0)
 (p/'meaning_map.json').write_text(json.dumps({str(i+1):f'词{i}' for i in range(n)},ensure_ascii=False),'utf-8')
 return p

def test_dynamic_detect_and_order(tmp_path):
 p=episode(tmp_path);mm={str(i+1):f'词{7-i}' for i in range(8)};(p/'meaning_map.json').write_text(json.dumps(mm),'utf-8')
 a=EpisodeAssets.from_dir(p)
 assert len(a.stickers)==8
 assert a.stickers[0].name=='词7.gif'
 assert a.sticker_type=='dynamic'
 assert a.validate()==[]

def test_cli_detail_preserves_gif(tmp_path):
 from sticker_engine.cli import _episode_stickers
 p=episode(tmp_path);assert len(_episode_stickers(p))==8
 assert all(x['file'].endswith('.gif') for x in _episode_stickers(p))

@pytest.mark.parametrize('mode',['mixed','single_frame','bad_size','corrupt','wrong_content','duplicate','missing_map','extra_file'])
def test_bad_dynamic_blocks(tmp_path,mode):
 p=episode(tmp_path);f=p/'最终版'
 if mode=='mixed':Image.new('RGB',(240,240)).save(f/'别的.png')
 if mode=='single_frame':Image.new('RGB',(240,240)).save(f/'词0.gif')
 if mode=='bad_size':
  a=Image.new('RGB',(10,10));b=Image.new('RGB',(10,10),'red');a.save(f/'词0.gif',save_all=True,append_images=[b],duration=100,loop=0)
 if mode=='corrupt':(f/'词0.gif').write_bytes(b'GIF89a broken')
 if mode=='wrong_content':Image.new('RGB',(240,240)).save(f/'词0.gif',format='PNG')
 if mode=='duplicate':(f/'词1.gif').write_bytes((f/'词0.gif').read_bytes())
 if mode=='missing_map':(p/'meaning_map.json').write_text('{"1":"缺图"}','utf-8')
 if mode=='extra_file':(f/'多余.gif').write_bytes((f/'词0.gif').read_bytes())
 assert EpisodeAssets.from_dir(p).validate()

def test_dynamic_count_blocks(tmp_path):
 assert EpisodeAssets.from_dir(episode(tmp_path,9)).validate()

def test_static_legacy_unchanged(tmp_path):
 p=tmp_path/'静态';f=p/'最终版';f.mkdir(parents=True);Image.new('RGB',(1,1)).save(f/'你好.png')
 a=EpisodeAssets.from_dir(p);assert len(a.stickers)==1;assert not a.validate()

@pytest.mark.parametrize('kind,label',[('dynamic','动态表情'),('static','静态表情')])
def test_form_type_selection(kind,label):
 pub=Publisher(PublishConfig(),MagicMock());pub._sticker_type=kind;pub._click_label=MagicMock();page=MagicMock()
 pub._step_open_submit_form(page)
 pub._click_label.assert_called_with(page,label,check=True)

@pytest.mark.parametrize('kind,label',[('dynamic','动态表情'),('static','静态表情')])
def test_form_check_uses_expected_type(kind,label):
 pub=Publisher(PublishConfig(),MagicMock());pub._sticker_type=kind;page=MagicMock();page.evaluate.return_value=[]
 assert pub._verify_form(page)==[]
 assert page.evaluate.call_args.args[1]==label

def test_dynamic_check_fails_closed():
 pub=Publisher(PublishConfig(),MagicMock());pub._sticker_type='dynamic';page=MagicMock();page.evaluate.side_effect=RuntimeError('lost page')
 assert pub._verify_form(page)
