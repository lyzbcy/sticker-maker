"""Official Windows Codex install without Node.js or administrator privileges."""
import hashlib
import json
import os
import platform
import re
import subprocess
import tempfile
import zipfile
import urllib.request
import urllib.error
from pathlib import Path

RELEASE_API='https://api.github.com/repos/openai/codex/releases/latest'
def _install_component(metadata, folder, name, target_name, progress, validate=True):
    assets=[a for a in metadata.get('assets',[]) if a.get('name')==name+'.zip']
    if not assets: assets=[a for a in metadata.get('assets',[]) if a.get('name')==name]
    if len(assets)!=1: raise ValueError('没有找到当前系统的官方生图工具')
    asset=assets[0];url=asset.get('browser_download_url','');digest=asset.get('digest','')
    if not re.fullmatch(r'sha256:[a-f0-9]{64}',digest) or not url.startswith('https://github.com/openai/codex/releases/download/'):
        raise ValueError('官方安装文件缺少校验信息，请稍后重试')
    folder.mkdir(parents=True,exist_ok=True)
    target=folder/target_name
    raw=next((a for a in metadata.get('assets',[]) if a.get('name')==name),{})
    if target.is_file() and raw.get('digest','').startswith('sha256:'):
        with target.open('rb') as existing:
            check=hashlib.sha256()
            for chunk in iter(lambda: existing.read(1024*1024),b''):check.update(chunk)
            if check.hexdigest()==raw['digest'][7:]:return str(target)
    fd,temp=tempfile.mkstemp(prefix='codex-',suffix='.exe',dir=folder);os.close(fd)
    sha=hashlib.sha256();received=0
    try:
        progress('正在下载官方生图工具，无需安装 Node.js…',0.2)
        total=int(asset.get('size') or 0)
        for attempt in range(3):
            headers={'User-Agent':'StickerMaker/0.5.1'}
            if received: headers['Range']=f'bytes={received}-'
            try:
                with urllib.request.urlopen(urllib.request.Request(url,headers=headers),timeout=45) as response:
                    if received and response.status != 206:
                        received=0;sha=hashlib.sha256()
                    if not total: total=int(response.headers.get('Content-Length') or 0)
                    with open(temp,'ab' if received else 'wb') as output:
                        while True:
                            chunk=response.read(1024*1024)
                            if not chunk: break
                            output.write(chunk);sha.update(chunk);received+=len(chunk)
                            if received>512*1024*1024:raise ValueError('安装文件大小异常')
                            progress(f'正在下载生图工具：{received//1048576} / {total//1048576 if total else "?"} MB',min(.85,.2+.65*received/total) if total else .3)
                if not total or received == total: break
            except (OSError, urllib.error.URLError) as error:
                if attempt==2: raise ValueError('下载中断，请检查网络后重试') from error
            progress('下载中断，正在续传，请稍候…',min(.85,.2+.65*received/total) if total else .3)
        if total and received != total:raise ValueError('下载尚未完成，请稍后重试')
        if sha.hexdigest()!=digest[7:]:raise ValueError('安装文件校验失败，请重试')
        binary=temp
        extracted=None
        if asset['name'].endswith('.zip'):
            with zipfile.ZipFile(temp) as archive:
                candidates=[i for i in archive.infolist() if Path(i.filename).name in {name,target_name} and not i.is_dir()]
                if len(candidates)!=1 or candidates[0].file_size>512*1024*1024:raise ValueError('官方压缩包结构异常')
                fd,extracted=tempfile.mkstemp(prefix='codex-unpacked-',suffix='.exe',dir=folder);os.close(fd)
                with archive.open(candidates[0]) as src,open(extracted,'wb') as dst:
                    import shutil
                    shutil.copyfileobj(src,dst)
                binary=extracted
        if validate:
            result=subprocess.run([binary,'--version'],capture_output=True,encoding='utf-8',errors='replace',timeout=20,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            if result.returncode!=0:raise ValueError('官方工具启动验证失败')
        os.replace(binary,target);progress('生图工具已安装，请打开登录窗口完成登录。',1)
        return str(target)
    finally:
        if Path(temp).exists():Path(temp).unlink()
        if 'extracted' in locals() and extracted and Path(extracted).exists():Path(extracted).unlink()


def install_native(user_data, progress=lambda message,percent:None):
    arch='aarch64' if platform.machine().lower() in {'arm64','aarch64'} else 'x86_64'
    req=urllib.request.Request(RELEASE_API,headers={'User-Agent':'StickerMaker/0.5.1','Accept':'application/vnd.github+json'})
    try:
        with urllib.request.urlopen(req,timeout=30) as response:metadata=json.load(response)
    except (OSError,urllib.error.URLError):
        from .. import resources_path
        metadata=json.loads((resources_path()/'codex-release.json').read_text(encoding='utf-8'))
        progress('版本服务暂时繁忙，使用内置已验证的官方版本。',.1)
    if metadata.get('prerelease') or metadata.get('draft'):raise ValueError('官方正式版本信息异常')
    import shutil
    components=[('codex','codex.exe'),('codex-code-mode-host','codex-code-mode-host.exe'),('codex-command-runner','codex-command-runner.exe'),('codex-windows-sandbox-setup','codex-windows-sandbox-setup.exe')]
    names={a.get('name') for a in metadata.get('assets',[])}
    for component,_ in components:
        name=f'{component}-{arch}-pc-windows-msvc.exe'
        if name not in names and name+'.zip' not in names:
            raise ValueError('官方版本缺少完整运行组件，请稍后重试')
    folder=Path(user_data)/'tools/codex'
    folder.parent.mkdir(parents=True,exist_ok=True)
    stage=Path(tempfile.mkdtemp(prefix='codex-stage-',dir=folder.parent))
    backup=stage.with_name(stage.name+'-previous')
    swapped=False
    try:
        if folder.exists(): shutil.copytree(folder,stage,dirs_exist_ok=True)
        for component,target in components:
            progress(f'正在校验并安装运行组件：{component}',.1)
            _install_component(metadata,stage,f'{component}-{arch}-pc-windows-msvc.exe',target,progress,validate=component=='codex')
        (stage/'release-manifest.json').write_text(json.dumps({'release':metadata.get('tag_name'),'files':{target:hashlib.sha256((stage/target).read_bytes()).hexdigest() for _,target in components}},indent=2),encoding='utf-8')
        if folder.exists(): folder.rename(backup)
        try:
            stage.rename(folder);swapped=True
        except OSError:
            if backup.exists():backup.rename(folder)
            raise
        progress('生图工具与运行组件已安装，请登录自己的账号。',1)
        return str(folder/'codex.exe')
    finally:
        if stage.exists():shutil.rmtree(stage)
        if swapped and backup.exists():shutil.rmtree(backup)
