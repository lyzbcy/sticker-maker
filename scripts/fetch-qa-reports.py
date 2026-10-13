"""Read small QA reports from an Actions ZIP using ranges; no installer download."""
import json,os,struct,subprocess,sys,urllib.request,urllib.error,zlib
from pathlib import Path
run,name=sys.argv[1:]
for key in ['HTTP_PROXY','HTTPS_PROXY','ALL_PROXY','http_proxy','https_proxy','all_proxy']:os.environ.pop(key,None)
metadata=json.loads(subprocess.check_output(['gh','api',f'repos/lyzbcy/sticker-maker/actions/runs/{run}/artifacts'],encoding='utf-8'))
artifact=next(a for a in metadata['artifacts'] if a['name']==name)
token=subprocess.check_output(['gh','auth','token'],encoding='utf-8').strip()
class NoRedirect(urllib.request.HTTPRedirectHandler):
 def redirect_request(self,*args,**kwargs):return None
opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect())
try:opener.open(urllib.request.Request(artifact['archive_download_url'],headers={'Authorization':'Bearer '+token,'User-Agent':'Sticker-QA'}),timeout=30);raise RuntimeError('expected artifact redirect')
except urllib.error.HTTPError as error:
 if error.code!=302:raise
 url=error.headers['Location']
token=None
def fetch(spec,maximum):
 request=urllib.request.Request(url,headers={'Range':spec,'User-Agent':'Sticker-QA'})
 with opener.open(request,timeout=45) as response:
  if response.status!=206:raise RuntimeError('artifact server did not support bounded range')
  data=response.read(maximum+1)
  if len(data)>maximum:raise RuntimeError('unexpected large range')
  return data,response.headers.get('Content-Range','')
with opener.open(urllib.request.Request(url,method='HEAD'),timeout=30) as response:
 total=int(response.headers['Content-Length'])
tail,range_header=fetch(f'bytes={max(0,total-65536)}-{total-1}',65536)
position=tail.rfind(b'PK\x05\x06');assert position>=0
eocd=struct.unpack_from('<4s4H2IH',tail,position)
count,cd_size,cd_offset=eocd[4:7]
assert count<1000 and cd_size<1024*1024
start=int(range_header.split()[1].split('-')[0])
central=tail[cd_offset-start:cd_offset-start+cd_size] if cd_offset>=start else fetch(f'bytes={cd_offset}-{cd_offset+cd_size-1}',cd_size)[0]
index=0;destination=Path('verification')/f'ci-{run}'/name;destination.mkdir(parents=True,exist_ok=True)
for _ in range(count):
 header=struct.unpack_from('<4s6H3I5H2I',central,index);assert header[0]==b'PK\x01\x02'
 method,compressed,plain=header[4],header[8],header[9]
 name_length,extra_length,comment_length=header[10:13];offset=header[16]
 filename=central[index+46:index+46+name_length].decode('utf-8');index+=46+name_length+extra_length+comment_length
 if Path(filename).name not in {'clean-install.json','clean-install.png','installed-runtime.txt','real-upgrade.json','packaged-app.png','windows-package.json'}:continue
 if plain>5*1024*1024:raise RuntimeError('oversized report')
 local,_=fetch(f'bytes={offset}-{offset+29}',30);fields=struct.unpack('<4s5H3I2H',local);assert fields[0]==b'PK\x03\x04'
 data_offset=offset+30+fields[-2]+fields[-1]
 body,_=fetch(f'bytes={data_offset}-{data_offset+compressed-1}',compressed)
 if method==8:body=zlib.decompress(body,-15)
 else:assert method==0
 assert len(body)==plain
 target=destination/Path(filename).name;target.write_bytes(body)
 print(target.name,len(body))
