const fs=require('fs/promises'),path=require('path'),crypto=require('crypto'),{spawn,execFileSync}=require('child_process');
const {launchUpdateHelper}=require('../desktop/src/main/update-handoff');
const wait=ms=>new Promise(r=>setTimeout(r,ms));
(async()=>{
 if(!process.env.RUNNER_TEMP)throw Error('clean CI runner required; do not replace a personal installation');
 const root=path.join(process.env.RUNNER_TEMP,'fan-app'),exe=path.join(root,'表情包一键制作.exe');
 const profile=path.join(process.env.RUNNER_TEMP,'upgrade-profile');await fs.mkdir(profile,{recursive:true});
 process.env.STICKER_DESKTOP_USER_DATA=profile;
 process.env.STICKER_ENGINE_USER_DATA=path.join(profile,'library');process.env.STICKER_ENGINE_NO_LOCK='1';
 await fs.mkdir(process.env.STICKER_ENGINE_USER_DATA,{recursive:true});
 const artwork=path.join(process.env.STICKER_ENGINE_USER_DATA,'retained-work.txt');await fs.writeFile(artwork,'original artwork sentinel');
 const file=path.resolve('desktop/release/sticker-maker-win-v0.5.1-setup.exe');
 const sha256=crypto.createHash('sha256').update(await fs.readFile(file)).digest('hex');
 const old=spawn(exe,[],{env:process.env,stdio:'ignore',windowsHide:false});await wait(5000);
 if(old.exitCode!==null)throw Error('old installed application exited before upgrade');
 const resultFile=path.join(profile,'update-result.json');
 await launchUpdateHelper({root,oldExe:exe,pid:old.pid,file,sha256,version:'0.5.1',resultFile},path.join(profile,'updates'));
 old.kill();
 let result;
 for(let i=0;i<600;i++){
  await wait(1000);try{result=JSON.parse(await fs.readFile(resultFile,'utf8'));}catch{}
  if(result?.status==='failed')throw Error(result.message);
  if(result?.status==='restarted')break;
 }
 if(result?.status!=='restarted')throw Error('real installer/restart confirmation timed out');
 if(await fs.readFile(artwork,'utf8')!=='original artwork sentinel')throw Error('user artwork not retained');
 const escaped=exe.replaceAll("'","''");
 let visible=false;
 for(let i=0;i<30&&!visible;i++){
  visible=execFileSync('powershell.exe',['-NoProfile','-Command',`@(Get-Process | Where-Object {$_.Path -eq '${escaped}' -and $_.MainWindowHandle -ne 0}).Count`],{encoding:'utf8',windowsHide:true}).trim()!=='0';await wait(500);
 }
 if(!visible)throw Error('new application window not visible');
 await fs.mkdir('verification',{recursive:true});
 await fs.writeFile('verification/real-upgrade.json',JSON.stringify({status:'REAL_UPGRADE_PASS',from:'0.5.0',to:result.runningVersion,executable:result.runningExe,visible,artwork:'retained'},null,2));
 // The ephemeral CI runner disposes of this visible test app at job teardown.
 console.log('REAL_UPGRADE_PASS from=0.5.0 to=0.5.1; visible=true; artwork=retained');
})().catch(e=>{console.error(e);process.exit(1)});
