const fs = require('fs/promises'), path = require('path'), assert = require('assert/strict')
const {launchUpdateHelper} = require('../desktop/src/main/update-handoff')
const quote=s=>"'"+s.replaceAll("'","''")+"'"
;(async()=>{
 const root=path.resolve('verification/handoff-real');await fs.mkdir(root,{recursive:true})
 const template=path.join(root,'fixture.ps1')
 await fs.writeFile(template,`param([string]$PayloadFile)
$p=[IO.File]::ReadAllText($PayloadFile,[Text.Encoding]::UTF8)|ConvertFrom-Json
[IO.File]::WriteAllText($p.readyFile,(@{status='ready';nonce=$p.nonce;version=$p.version;pid=$PID}|ConvertTo-Json -Compress))
$deadline=[DateTime]::UtcNow.AddSeconds(15)
while(!(Test-Path -LiteralPath $p.commitFile)){if((Test-Path -LiteralPath $p.abortFile) -or [DateTime]::UtcNow -gt $deadline){exit 1};Start-Sleep -Milliseconds 50}
[IO.File]::WriteAllText($p.resultFile,'fixture committed')
`)
 const payload={version:'0.5.1',resultFile:path.join(root,'result.txt')}
 const result=await launchUpdateHelper(payload,root,{templatePath:template})
 assert.equal(await fs.readFile(path.join(result.attempt,'commit'),'utf8'),result.nonce)
 assert.equal(JSON.parse(await fs.readFile(path.join(result.attempt,'ready.json'),'utf8')).nonce,result.nonce)
 const bad=path.join(root,'bad.ps1');await fs.writeFile(bad,`param([string]$PayloadFile)
throw "fixture failure"`)
 await assert.rejects(launchUpdateHelper({...payload,resultFile:path.join(root,'failed.json')},root,{templatePath:bad,timeoutMs:2500}))
 const dirs=(await fs.readdir(root)).filter(n=>n.startsWith('install-'))
 let aborts=0;for(const d of dirs){if(await fs.access(path.join(root,d,'abort')).then(()=>true,()=>false))aborts++}
 assert(aborts>=1)
 console.log('REAL_HANDOFF ready=verified commit=verified failed_start=aborted old_app=retained; installer_execution=fixture_only')
})().catch(e=>{console.error(e);process.exit(1)})
