"""Prepare an episode from verified platform evidence and the creator skill configuration."""
import argparse,datetime,hashlib,json,math,secrets,shutil,re
import yaml
from pathlib import Path
HERE=Path(__file__).resolve().parents[1]
def weighted(items):
    total=sum(w for _,w in items)
    if any(w<0 for _,w in items) or not math.isclose(total,1.0): raise ValueError('Weights must sum to one')
    r=secrets.randbits(53)/2**53; acc=0
    for key,w in items:
        acc+=w
        if r<acc:return key,r
    raise ValueError('Invalid distribution')
def main():
    p=argparse.ArgumentParser();p.add_argument('--episode',type=int);p.add_argument('--output-root',required=True,type=Path);p.add_argument('--evidence',required=True,type=Path);p.add_argument('--assets-root',required=True,type=Path);args=p.parse_args()
    evidence=json.loads(args.evidence.read_text(encoding='utf-8'))
    for key in ['max_episode','source_url','checked_at','verification_note']:
        if key not in evidence or evidence[key] in [None,'']:raise ValueError('Missing evidence: '+key)
    if not isinstance(evidence['max_episode'],int) or evidence['max_episode']<0:raise ValueError('Invalid platform episode')
    stamp=datetime.datetime.fromisoformat(evidence['checked_at'].replace('Z','+00:00'))
    if stamp.tzinfo is None or abs((datetime.datetime.now(datetime.timezone.utc)-stamp).total_seconds())>3600:raise ValueError('Refresh platform evidence within one hour with explicit timezone')
    cfg=yaml.safe_load((HERE/'config.yaml').read_text(encoding='utf-8'))
    mode,rm=weighted(list(cfg['mode_probabilities'].items()));rc=None
    if mode=='single':char,rc=weighted(list(cfg['single_character_probabilities'].items()));chars=[char]
    else:chars=cfg['duo_bases']
    selected={};draws={}
    for char in chars:
        name,r=weighted([(k,w) for k,w in cfg['character_costume_probabilities'][char].items() if w>0])
        filename=re.split(r'[\\/]',cfg['base_images'][char][name])[-1]
        source=args.assets_root/filename
        if not source.is_file():raise FileNotFoundError(source)
        selected[char]=source;draws[char]=r
    episode=args.episode if args.episode is not None else evidence['max_episode']+1
    if episode<=evidence['max_episode']:raise ValueError('Requested episode must exceed platform maximum')
    name=f'周三涵做表情{episode}';out=args.output_root/name
    args.output_root.mkdir(parents=True,exist_ok=True);out.mkdir(exist_ok=False)
    for d in ['参考图','原图','原图_透明ChromaKey','最终版','横幅','封面','图标']:(out/d).mkdir()
    bases=[]
    for i,(char,src) in enumerate(selected.items(),1):
        target=out/'参考图'/f'base{i}{src.suffix}';shutil.copyfile(src,target)
        bases.append({'character':char,'asset':src.name,'path':str(target.relative_to(out)),'sha256':hashlib.sha256(target.read_bytes()).hexdigest()})
    state={'episode':episode,'episode_name':name,'mode':mode,'characters':chars,'bases':bases,'random':{'mode':rm,'single_character':rc,'costumes':draws},'probabilities':{k:cfg[k] for k in ['mode_probabilities','single_character_probabilities','character_costume_probabilities']},'status':'prepared','generation_channel':'ChatGPT Web','published':False}
    (out/'prep_state.json').write_text(json.dumps(state,ensure_ascii=False,indent=2),encoding='utf-8')
    shutil.copyfile(args.evidence,out/'微信后台核对.json')
    card=f'# {name}\n- 模式：{mode}\n- 角色：'+', '.join(chars)+f'\n- 含捞鱼：{chr(26159) if "捞鱼" in chars else chr(21542)}\n- 只含捞鱼：{chr(26159) if chars==["捞鱼"] else chr(21542)}\n'
    (out/'本次制作角色.md').write_text(card,encoding='utf-8')
    print(json.dumps({'output_dir':str(out),'mode':mode,'characters':chars},ensure_ascii=False))
if __name__=='__main__':main()
