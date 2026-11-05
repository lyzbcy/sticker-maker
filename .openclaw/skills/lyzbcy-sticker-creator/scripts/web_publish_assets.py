"""Render all per-album publishing assets using the project's current algorithms."""
import argparse,hashlib,json,shutil,datetime
from pathlib import Path
from PIL import Image
from web_source import PROJECT_ROOT
from sticker_engine.stages.assets import make_big_head_cover, AssetsStage
from make_banner import make_banner

def digest(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument('--episode-dir',required=True,type=Path);p.add_argument('--head-source',required=True,type=Path);p.add_argument('--banner-sources',required=True,nargs='+',type=Path);p.add_argument('--tip-source',required=True,type=Path);p.add_argument('--replace',action='store_true');a=p.parse_args();root=a.episode_dir
 for source in [a.head_source,*a.banner_sources,a.tip_source]:
  if not source.is_file():raise FileNotFoundError(source)
  source.resolve().relative_to(root.resolve())
 proof=json.loads((root/'头像裁切.json').read_text(encoding='utf-8'))
 source=root/proof['source'];source.resolve().relative_to((root/'最终版').resolve())
 if proof.get('origin')!='current_album_sticker' or digest(source)!=proof['source_sha256'] or digest(a.head_source)!=proof['head_sha256']:
  raise ValueError('Head must be cropped from this album current sticker, with current provenance; no base portrait fallback')
 targets=['横幅/横幅.png','封面/封面.png','图标/图标.png','赞赏图/赞赏引导图.png','赞赏图/赞赏致谢图.png']
 if any((root/t).exists() for t in targets) and not a.replace:raise FileExistsError('Assets already exist; review and back up before --replace')
 stage=root/'.cache/publish-assets-stage';stage.mkdir(parents=True,exist_ok=True)
 for sub in ['横幅','封面','图标','赞赏图']:(stage/sub).mkdir(exist_ok=True)
 if proof.get('method') in ('first_panel_center_80','first_panel_fixed_square_80'):
  if Image.open(a.head_source).size!=(240,240):raise ValueError('Fixed crop must be 240 square')
  shutil.copyfile(a.head_source,stage/'封面/封面.png')
 elif not make_big_head_cover(a.head_source,stage/'封面/封面.png'):raise RuntimeError('Head-cover generation failed; no full-body fallback')
 cover=Image.open(stage/'封面/封面.png').convert('RGBA');cover.resize((50,50),Image.Resampling.LANCZOS).save(stage/'图标/图标.png')
 make_banner([str(p) for p in a.banner_sources],str(stage/'横幅/横幅.png'))
 # Current engine owns tip rendering. Require its supported CJK font rather than silently dropping text.
 if not any(Path(f).is_file() for f in [r'C:\Windows\Fonts\msyhbd.ttc', r'C:\Windows\Fonts\msyh.ttc', r'C:\Windows\Fonts\simhei.ttf']):
  raise RuntimeError('Current engine tip renderer requires a supported Windows CJK font; do not use a copied renderer or silently publish textless cards.')
 AssetsStage(None)._make_tip_images([a.tip_source],a.head_source,stage/'赞赏图')
 stamp=datetime.datetime.now().strftime('%Y%m%d-%H%M%S-%f')
 backup=root/'修复记录'/stamp
 records=[]
 for rel in targets:
  target=root/rel;target.parent.mkdir(exist_ok=True)
  if target.exists():
   dest=backup/rel;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(target,dest)
  shutil.copyfile(stage/rel,target)
  records.append({'path':rel,'sha256':digest(target),'size':target.stat().st_size,'dimensions':list(Image.open(target).size)})
 sources=[a.head_source,*a.banner_sources,a.tip_source]
 data={'generated_at':datetime.datetime.now().astimezone().isoformat(),'album':root.name,'head_source':str(a.head_source.relative_to(root)),'sources':[{'path':str(f.relative_to(root)),'sha256':digest(f)} for f in sources],'files':records,'visual_review_required':True,'fallback_assets_used':False}
 (root/'发布素材清单.json').write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
 print(json.dumps({'album':root.name,'files':records,'visual_review_required':True},ensure_ascii=False))
if __name__=='__main__':main()
