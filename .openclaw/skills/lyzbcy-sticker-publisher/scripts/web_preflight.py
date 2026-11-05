"""Validate the concrete local submission package; does not submit."""
import argparse,hashlib,json,re
from pathlib import Path
import numpy as np
from PIL import Image

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument('--episode-dir',type=Path,required=True);p.add_argument('--role',required=True,choices=['女人','男人','人物合辑']);a=p.parse_args();r=a.episode_dir;errors=[];checks=[]
 def check(ok,text):checks.append({'pass':bool(ok),'check':text});errors.extend([] if ok else [text])
 prep=json.loads((r/'prep_state.json').read_text(encoding='utf-8'));chars=prep.get('characters',[])
 expected='男人' if chars==['捞鱼'] else ('女人' if len(chars)==1 and chars[0] in ['星星布丁','周三涵','周五涵'] else ('人物合辑' if len(chars)>=2 else None))
 check(expected is not None and a.role==expected,'角色定义与平台性别标签一致')
 files=sorted((r/'最终版').glob('*.png'));check(12<=len(files)<=24,'表情数量12至24');check(len({f.stem for f in files})==len(files) and all(1<=len(f.stem)<=4 for f in files),'含义词唯一且1至4字');check(len({sha(f) for f in files})==len(files),'成品无相同哈希')
 check(all(re.fullmatch(r'[\u3400-\u9fff]{1,4}',f.stem) for f in files),'平台含义词1至4汉字，不含问号等标点')
 for f in files:
  im=Image.open(f).convert('RGBA');alpha=np.asarray(im)[:,:,3];check(Image.open(f).format=='PNG' and im.width==im.height and 240<=im.width<=360 and f.stat().st_size<=500*1024 and (alpha==0).any() and (alpha>0).any(),'表情尺寸格式透明:'+f.name)
 spec={'横幅/横幅.png':(750,400),'封面/封面.png':(240,240),'图标/图标.png':(50,50),'赞赏图/赞赏引导图.png':(939,701),'赞赏图/赞赏致谢图.png':(939,939)}
 for rel,size in spec.items():
  f=r/rel;check(f.is_file(),'素材存在:'+rel)
  if f.is_file():
   im=Image.open(f);check(im.size==size and im.format=='PNG' and f.stat().st_size<=500*1024,'素材尺寸格式:'+rel)
   if '封面' in rel or '图标' in rel:check(im.mode=='RGBA' and np.asarray(im)[:,:,3].min()==0,'头像真实透明:'+rel)
 text=(r/'介绍.txt').read_text(encoding='utf-8').strip();check(1<=len(text)<=80,'介绍1至80字')
 recipe=json.loads((r/'发布素材清单.json').read_text(encoding='utf-8'));check(all((r/x['path']).is_file() and sha(r/x['path'])==x['sha256'] for x in recipe['files']),'本轮素材哈希匹配')
 proof_path=r/'头像裁切.json';proof=json.loads(proof_path.read_text(encoding='utf-8')) if proof_path.exists() else {}
 source=r/proof.get('source','__missing__')
 inside=source.resolve().is_relative_to((r/'最终版').resolve())
 head=r/recipe['head_source']
 check(proof.get('origin')=='current_album_sticker' and inside and source.is_file() and sha(source)==proof.get('source_sha256') and sha(head)==proof.get('head_sha256'),'头像来自当弹成品并绑定当前源图哈希，非复用base头像')
 review=json.loads((r/'发布素材复核.json').read_text(encoding='utf-8'));check(review.get('approved') is True and review.get('role')==a.role and review.get('head_only') is True,'AI视觉复核与角色分类')
 check(review.get('asset_hashes')=={x['path']:x['sha256'] for x in recipe['files']},'视觉复核对应当前素材而非旧图')
 result={'ok':not errors,'album':r.name,'role':a.role,'sticker_count':len(files),'checks':checks,'errors':errors,'submitted':False}
 (r/'投稿前校验.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps({'ok':not errors,'checks':len(checks),'errors':errors,'count':len(files),'role':a.role},ensure_ascii=False))
 if errors:raise SystemExit(1)
if __name__=='__main__':main()
