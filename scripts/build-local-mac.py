"""Build and verify the native Mac candidate locally, including over SSH. No CI."""
import argparse
import hashlib
import json
import os
import platform
import subprocess
import sys
import sysconfig
import uuid
import shutil
from pathlib import Path

parser=argparse.ArgumentParser()
parser.add_argument('--output', required=True)
parser.add_argument('--node-bin', required=True)
parser.add_argument('--resume-from', choices=['all','engine-build','desktop-package','packaged-ui'], default='all')
args=parser.parse_args()
if sys.platform!='darwin' or platform.machine()!='arm64':
    raise SystemExit('This native candidate builder requires an Apple Silicon Mac')
repo=Path(__file__).resolve().parents[1]
out=Path(args.output).expanduser().resolve();out.mkdir(parents=True,exist_ok=True)
node=Path(args.node_bin).expanduser().resolve()
version=json.loads((repo/'desktop/package.json').read_text())['version']
if b'\r\n' in (repo/'desktop/install.command').read_bytes():
    raise SystemExit('Mac install.command must use LF line endings')
env=dict(os.environ,PATH=str(node)+os.pathsep+os.environ.get('PATH',''),
         PYTHONIOENCODING='utf-8',PYTHONUTF8='1',CSC_IDENTITY_AUTO_DISCOVERY='false',
         PYTHON_KEYRING_BACKEND='keyring.backends.null.Keyring')
env.pop('STICKER_BUNDLE_BROWSERS',None)
env.pop('ELECTRON_RUN_AS_NODE',None)

def run(stage,command,cwd=repo,extra_env=None,force=False):
    order=['python-tests','npm-ci','electron-runtime','frontend-tests','frontend-build','engine-build','desktop-package','codesign','codesign-verify','packaged-ui','installer-test','installer-verify','zip-app','zip-installer']
    if not force and args.resume_from!='all' and order.index(stage)<order.index(args.resume_from):
        print('REUSE '+stage,flush=True);return
    print('START '+stage,flush=True)
    with (out/(stage+'.log')).open('w') as log:
        result=subprocess.run([str(v) for v in command],cwd=cwd,env=dict(env,**(extra_env or {})),stdout=log,stderr=subprocess.STDOUT)
    print('DONE '+stage+' exit='+str(result.returncode),flush=True)
    if result.returncode:
        print((out/(stage+'.log')).read_text(errors='replace')[-6000:],flush=True)
        raise SystemExit(result.returncode)

run('python-tests',[sys.executable,'-m','pytest','tests','../server','-q','--basetemp',out/'pytest','--tb=short'],repo/'sticker_engine')
run('npm-ci',[node/'npm','ci'],repo/'desktop')
if args.resume_from in ('all','engine-build'):
    run('electron-runtime',[node/'node',repo/'desktop/node_modules/electron/install.js'],repo/'desktop',force=True)
run('frontend-tests',[node/'npm','test','--','--reporter=dot'],repo/'desktop')
run('frontend-build',[node/'npm','run','build'],repo/'desktop')
run('engine-build',[sys.executable,'-m','PyInstaller','sticker-engine-cli.spec','--noconfirm','--distpath',out/'engine-dist','--workpath',out/'engine-work'],repo/'sticker_engine')
config=out/'electron-builder.cjs'
config.write_text("const base=require("+json.dumps(str(repo/'desktop/package.json'))+").build;module.exports={...base,directories:{output:"+json.dumps(str(out/'desktop-release'))+"},electronDist:"+json.dumps(str(repo/'desktop/node_modules/electron/dist'))+",mac:{...base.mac,identity:null,extraResources:[{from:"+json.dumps(str(out/'engine-dist/sticker-engine-cli'))+",to:'sticker-engine-cli'},{from:"+json.dumps(str(repo/'desktop/install.command'))+",to:'install.command'}]}};",encoding='utf-8')
run('desktop-package',[node/'npx','electron-builder','--mac','--arm64','--config',config,'--publish','never'],repo/'desktop')
apps=list((out/'desktop-release').glob('*/*.app'))
if len(apps)!=1:raise SystemExit('Expected exactly one native Mac app')
app=apps[0]
run('codesign',['/usr/bin/codesign','--force','--deep','--sign','-',app])
run('codesign-verify',['/usr/bin/codesign','--verify','--deep','--strict',app])
run('packaged-ui',[node/'node',repo/'scripts/verify-docx-tasks.cjs'],extra_env={
    'STICKER_QA_PLAYWRIGHT':str(Path(sysconfig.get_paths()['purelib'])/'playwright/driver/package'),
    'STICKER_QA_APP':str(app/'Contents/MacOS/表情包一键制作'),
    'STICKER_QA_EVIDENCE':str(out/'qa')})
installer=repo/'desktop/install.command';installer.chmod(0o755)
shutil.copy2(installer,app.parent/'install.command')
install_root=out/('qa-install-'+uuid.uuid4().hex[:8])
run('installer-test',['/bin/bash',app.parent/'install.command'],extra_env={
    'STICKER_INSTALL_ROOT':str(install_root),'STICKER_INSTALL_NO_LAUNCH':'1'})
run('installer-verify',['/usr/bin/codesign','--verify','--deep','--strict',install_root/app.name])
archive=out/f'sticker-maker-mac-v{version}-local-candidate.zip'
run('zip-app',['/usr/bin/ditto','-c','-k','--sequesterRsrc','--keepParent',app,archive])
run('zip-installer',['/usr/bin/zip','-j',archive,installer])
receipt={'version':version,'platform':platform.platform(),'arch':platform.machine(),'source':str(repo),
         'artifact':str(archive),'bytes':archive.stat().st_size,
         'sha256':hashlib.file_digest(archive.open('rb'),'sha256').hexdigest(),
         'ci_used':False,'installed':False,'public_release':False,'signed':'ad-hoc','notarized':False,
         'isolated_install_verified':True,'isolated_install_root':str(install_root)}
(out/'build-receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(receipt,ensure_ascii=False),flush=True)
