'use strict';
const fs=require('node:fs/promises'),path=require('node:path'),crypto=require('node:crypto');
const {spawn}=require('node:child_process');
const delay=ms=>new Promise(resolve=>setTimeout(resolve,ms));
const quote=value=>"'"+value.replaceAll("'","''")+"'";

async function launchUpdateHelper(payload,directory,{spawnFn=spawn,timeoutMs=15000,templatePath=path.join(__dirname,'install-update.ps1')}={}) {
 await fs.mkdir(directory,{recursive:true});
 const attempt=await fs.mkdtemp(path.join(directory,'install-'));
 const nonce=crypto.randomBytes(24).toString('hex');
 const readyFile=path.join(attempt,'ready.json'),commitFile=path.join(attempt,'commit'),abortFile=path.join(attempt,'abort');
 const scriptFile=path.join(attempt,'worker.ps1'),payloadFile=path.join(attempt,'payload.json');
 const data={...payload,nonce,readyFile,commitFile,abortFile};
 const template=await fs.readFile(templatePath,'utf8');
 // Windows PowerShell -File assumes ANSI without a BOM, even though our source is UTF-8.
 await fs.writeFile(scriptFile,'\uFEFF'+template.replace(/^\uFEFF/,''),'utf8');
 await fs.writeFile(payloadFile,JSON.stringify(data));
 // Start-Process creates an independent grandchild. Never use DETACHED_PROCESS for PowerShell.
 // A file keeps nested encoded commands below Windows' command-line size limit.
 const workerErrorFile=path.join(attempt,'worker-stderr.log');
 const workerEntry=`$ErrorActionPreference='Stop';try { & ${quote(scriptFile)} -PayloadFile ${quote(payloadFile)} } catch { [IO.File]::WriteAllText(${quote(workerErrorFile)},$_.ToString());exit 1 }`;
 const args='-NoProfile -NonInteractive -ExecutionPolicy Bypass -EncodedCommand '+Buffer.from(workerEntry,'utf16le').toString('base64');
 // RedirectStandardOutput/Error makes Windows PowerShell wait for descendant streams.
 // The independent worker writes diagnostics itself; bootstrap must be able to exit first.
 const bootstrap=`$ErrorActionPreference='Stop'; $ProgressPreference='SilentlyContinue'; $child=Start-Process -FilePath (Join-Path $PSHOME 'powershell.exe') -ArgumentList ${quote(args)} -WindowStyle Hidden -PassThru; $child.Id`;
 let child,stderr='',exit=null,launchError=null;
 const end=Date.now()+timeoutMs;
 try {
  child=spawnFn('powershell.exe',['-NoProfile','-NonInteractive','-EncodedCommand',Buffer.from(bootstrap,'utf16le').toString('base64')],{detached:false,stdio:['ignore','pipe','pipe'],windowsHide:true});
  child.stdout?.resume();child.stderr?.on('data',data=>{stderr=(stderr+data).slice(-3000);});
  child.once('error',error=>{launchError=error;});child.once('close',(code,signal)=>{exit={code,signal};});
  while(Date.now()<end) {
   if(launchError)throw launchError;
   if(exit&&exit.code!==0)throw Error(`更新引导器退出异常（${exit.code??exit.signal}）：${stderr}`);
   let ready;
   try{ready=JSON.parse(await fs.readFile(readyFile,'utf8'));}catch{}
   if(exit?.code===0&&ready?.nonce===nonce&&ready.version===payload.version&&ready.status==='ready'&&Number.isInteger(ready.pid)&&ready.pid>0) {
    await fs.writeFile(commitFile,nonce);
    return {attempt,helperPid:ready.pid,nonce};
   }
   try{const result=JSON.parse((await fs.readFile(payload.resultFile,'utf8')).replace(/^\uFEFF/,''));if(result.nonce===nonce&&result.status==='failed')throw Error(result.message||'更新助手启动失败');}
   catch(error){if(error.code!=='ENOENT'&&!(error instanceof SyntaxError))throw error;}
   await delay(75);
  }
  throw Error('更新助手未确认就绪，已保留当前软件，请重试或手动安装。');
 }catch(error){
  await fs.writeFile(abortFile,nonce).catch(()=>{});
  if(child&&exit===null)child.kill();
  const workerError=await fs.readFile(workerErrorFile,'utf8').catch(()=>'');
  await fs.writeFile(path.join(attempt,'launch-error.json'),JSON.stringify({version:payload.version,message:error.message,stderr,workerError})).catch(()=>{});
  throw error;
 }
}

async function confirmUpdateRestart(resultFile,{version,executable,readShortcut}) {
 let result;
 try{result=JSON.parse((await fs.readFile(resultFile,'utf8')).replace(/^\uFEFF/,''));}catch{return null;}
 if(result.status!=='installed'||result.version!==version||path.resolve(result.exe||'')!==path.resolve(executable))return null;
 const shortcuts=[];
 for(const link of result.shortcuts||[]) {
  const actual=readShortcut(link);
  if(path.resolve(actual.target)!==path.resolve(executable))throw Error('升级后的快捷方式仍指向旧版：'+link);
  shortcuts.push(link);
 }
 result.status='restarted';result.runningVersion=version;result.runningExe=executable;result.restartConfirmedAt=new Date().toISOString();result.shortcuts=shortcuts;
 await fs.writeFile(resultFile,JSON.stringify(result,null,2));return result;
}
module.exports={launchUpdateHelper,confirmUpdateRestart};
