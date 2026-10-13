const fs=require('fs'),path=require('path'),cp=require('child_process')
const root=path.resolve(__dirname,'..'),version=require('../package.json').version
function find(dir){if(!fs.existsSync(dir))return null;for(const e of fs.readdirSync(dir,{withFileTypes:true})){const p=path.join(dir,e.name);if(e.isFile()&&e.name==='makensis.exe'&&path.basename(dir)==='Bin')return p;if(e.isDirectory()){const got=find(p);if(got)return got}}}
async function main(){
const {getBinFromUrl}=require('app-builder-lib/out/binDownload')
const directory=process.env.ELECTRON_BUILDER_NSIS_DIR || await getBinFromUrl('nsis','3.0.4.1','VKMiizYdmNdJOWpRGz4trl4lD++BvYP2irAXpMilheUP0pc93iKlWAoP843Vlraj8YG19CVn0j+dCo/hURz9+Q==')
const nsis=process.env.STICKER_NSIS||find(directory)
if(!nsis)throw Error('NSIS not found; first run electron-builder Windows packaging')
function size(dir){return fs.readdirSync(dir,{withFileTypes:true}).reduce((sum,e)=>sum+(e.isDirectory()?size(path.join(dir,e.name)):fs.statSync(path.join(dir,e.name)).size),0)}
const bytes=size(path.join(root,'release','win-unpacked'))
cp.execFileSync(nsis,[`/DVERSION=${version}`,`/DROOT=${root}`,`/DPAYLOAD_BYTES=${bytes}`,'fan-installer.nsi'],{cwd:path.join(root,'build'),stdio:'inherit',windowsHide:true,timeout:600000})
const file=path.join(root,'release',`sticker-maker-win-v${version}-setup.exe`)
const sha=require('crypto').createHash('sha256').update(fs.readFileSync(file)).digest('hex')
fs.writeFileSync(path.join(root,'release','windows-package.json'),JSON.stringify({version,file:path.basename(file),sha256:sha,sizeBytes:fs.statSync(file).size},null,2))
console.log('WINDOWS_PACKAGE_VERIFIED',path.basename(file),sha)
}
main().catch(error=>{console.error(error);process.exit(1)})
