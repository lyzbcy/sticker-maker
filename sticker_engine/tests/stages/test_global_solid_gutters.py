import hashlib,json
from pathlib import Path
import numpy as np
import pytest
from PIL import Image,ImageDraw
from sticker_engine.stages.grid_cutter import _trim_solid_gutters,solid_cell_boxes,cut_grid

def sheet():
    a=np.full((200,200,3),(255,211,223),dtype=np.uint8)
    a[:,98:102]=255;a[98:102]=255
    a[:,0:2]=255;a[:,-2:]=255;a[:2]=255;a[-2:]=255
    # White shaded cuff reaches the real gutter but occupies one cell only.
    a[35:65,75:98]=(220,219,218)
    return a

def test_global_core_trims_gutter_without_erasing_attached_cuff():
    a=sheet();b=_trim_solid_gutters(a,[(0,100),(100,200)],1)
    assert b==[(3,97),(103,197)]
    clipped=a[3:97,3:97];assert np.count_nonzero((clipped==(220,219,218)).all(2))==30*22

@pytest.mark.parametrize('kind',['local_outline','broad_white','all_white','dark_crossing'])
def test_foreground_without_thin_bright_global_core_is_not_trimmed(kind):
    a=np.full((100,100,3),(250,210,220),dtype=np.uint8)
    if kind=='local_outline':a[20:50,:2]=255
    if kind=='broad_white':a[:,:20]=255
    if kind=='all_white':a[:]=255
    if kind=='dark_crossing':a[:,:2]=255;a[50,0]=(20,20,20)
    assert _trim_solid_gutters(a,[(0,100)],1)==[(0,100)]

def test_outside_core_removes_only_one_bright_fringe_pixel():
    a=np.full((100,100,3),(250,210,220),dtype=np.uint8)
    a[:,50:52]=255;a[:,49]=(240,222,228)
    assert _trim_solid_gutters(a,[(0,50)],1)==[(0,49)]
    a[3,49]=(30,20,20)
    assert _trim_solid_gutters(a,[(0,50)],1)==[(0,50)]

def grid_episode(ep):
    from sticker_engine.config.series import save_meta,EpisodeMeta
    save_meta(ep,EpisodeMeta(work_id='grid-repair',album_name='修复'))
    raw=ep/'原图';(raw/'_panels').mkdir(parents=True);(raw/'_noword').mkdir();(ep/'最终版').mkdir()
    mapping={str(i):f'{name}.png' for i,name in enumerate(['甲','乙','丙','丁'],1)}
    (ep/'cell_sources.json').write_text(json.dumps(mapping),encoding='utf-8')
    (raw/'prompt.txt').write_text('single FLAT SOLID PASTEL COLOR',encoding='utf-8')
    Image.fromarray(sheet()).save(raw/'grid_2x2.png')
    for i,name in mapping.items():
        for p in (raw/'_panels'/f'panel_{int(i):02d}.png',raw/'_noword'/name,ep/'最终版'/name):
            Image.new('RGBA',(100,100),(250,210,220,255)).save(p)
    (ep/'rating.json').write_text('{"overall":1}',encoding='utf-8')
    return {'episode_dir':str(ep),'reflow_solid_captions':True,'recover_solid_sources_from_grid':True}

def run(ep,args,monkeypatch):
    from sticker_engine import cli
    results=[];monkeypatch.setattr(cli,'_result',lambda *a,**kw:results.append((a,kw)))
    monkeypatch.setattr(cli,'_regen_episode_assets',lambda *a:[])
    cli.cmd_regen_assets('test',args);return results[-1]

def test_explicit_grid_recovery_uses_same_boxes_as_s2_preserves_raw_and_rating(tmp_path,monkeypatch):
    args=grid_episode(tmp_path)
    raw={str(p.relative_to(tmp_path)):p.read_bytes() for p in (tmp_path/'原图').rglob('*') if p.is_file() and '_noword' not in str(p)}
    rating=(tmp_path/'rating.json').read_bytes();before={p.name:p.read_bytes() for p in (tmp_path/'最终版').glob('*.png')}
    assert run(tmp_path,args,monkeypatch)[0][1]=='ok'
    proof=json.loads((tmp_path/'solid_source_recovery.json').read_text(encoding='utf-8'));assert proof['kind']=='grid' and len(proof['sources'])==4
    boxes=solid_cell_boxes(sheet(),2)
    assert [x['box'] for x in proof['sources'].values()]==[list(x) for x in boxes]
    expected=hashlib.sha256((tmp_path/'原图/grid_2x2.png').read_bytes()).hexdigest()
    assert all(x['sha256']==expected for x in proof['sources'].values())
    a=np.array(Image.open(tmp_path/'原图/_noword/甲.png'));assert ((a[:,:,:3]==(220,219,218)).all(2)).sum()>=30*22
    assert all((tmp_path/p).read_bytes()==b for p,b in raw.items()) and (tmp_path/'rating.json').read_bytes()==rating
    first={p.name:p.read_bytes() for p in (tmp_path/'最终版').glob('*.png')}
    assert run(tmp_path,args,monkeypatch)[0][1]=='ok'
    assert all((tmp_path/'最终版'/n).read_bytes()==b for n,b in first.items())
    assert all((tmp_path/'原图/_caption_layout_backup/最终版'/n).read_bytes()==b for n,b in before.items())

@pytest.mark.parametrize('failure',['missing_grid','corrupt_grid','small_grid','mapping','published','bound','no_reflow','both_flags'])
def test_invalid_grid_recovery_fails_before_any_artwork_write(tmp_path,monkeypatch,failure):
    from sticker_engine.config.series import load_meta,save_meta
    args=grid_episode(tmp_path);grid=tmp_path/'原图/grid_2x2.png'
    if failure=='missing_grid':grid.unlink()
    elif failure=='corrupt_grid':grid.write_bytes(b'not png')
    elif failure=='small_grid':Image.new('RGB',(3,3),'white').save(grid)
    elif failure=='mapping':(tmp_path/'cell_sources.json').write_text('{"1":"../甲.png"}',encoding='utf-8')
    elif failure in ('published','bound'):
        m=load_meta(tmp_path);m.published=failure=='published';m.platform_item_id='existing' if failure=='bound' else '';save_meta(tmp_path,m)
    elif failure=='no_reflow':args.pop('reflow_solid_captions')
    else:args['recover_solid_sources_from_panels']=True
    before={str(p):p.read_bytes() for p in list((tmp_path/'最终版').glob('*.png'))+list((tmp_path/'原图/_noword').glob('*.png'))}
    assert run(tmp_path,args,monkeypatch)[0][1]=='fail'
    assert all(Path(p).read_bytes()==b for p,b in before.items())
    assert not (tmp_path/'原图/_caption_layout_backup').exists()
