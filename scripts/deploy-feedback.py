"""Deploy only the approved relay on the existing host; never print webhook secrets."""
import hashlib,json,os,re,subprocess,sys,uuid
from pathlib import Path
root=Path(__file__).resolve().parents[1]
out=root/'verification/feedback-deployment';out.mkdir(parents=True,exist_ok=True)
ssh=['ssh','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-i',str(Path.home()/'.ssh/id_ed25519'),'ubuntu@111.231.25.152']
def remote(command,input=None):
 result=subprocess.run(ssh+[command],input=input,capture_output=True)
 if result.returncode:raise RuntimeError('remote operation failed: '+result.stderr.decode('utf-8','replace')[:1200])
 return result.stdout
resume='--resume' in sys.argv
original=(out/'ORIGINAL_FILE.conf').read_bytes() if resume else remote('sudo cat /etc/nginx/conf.d/laoyu-https.conf')
expected=hashlib.sha256(original).hexdigest()
assert expected=='1537733f12047cdb95f41c3c386359fa56ae94391ee36f39735a286e1791ca34','shared configuration changed; re-inspect before modifying'
(out/'ORIGINAL_FILE.conf').write_bytes(original)
modified=original.replace(b' location / { return 404; }',b' include /etc/nginx/snippets/sticker-feedback.conf;\n location / { return 404; }')
assert modified!=original and original.count(b' location / { return 404; }')==1
if resume:
 assert hashlib.sha256(remote('sudo cat /etc/nginx/conf.d/laoyu-https.conf')).hexdigest()==hashlib.sha256(modified).hexdigest(),'live shared configuration changed'
(out/'MODIFIED_FILE.conf').write_bytes(modified)
import difflib
(out/'DIFF_FILE.patch').write_text(''.join(difflib.unified_diff(original.decode().splitlines(True),modified.decode().splitlines(True),fromfile='original/laoyu-https.conf',tofile='modified/laoyu-https.conf')),encoding='utf-8')
upload='/tmp/sticker-feedback-'+uuid.uuid4().hex
remote('mkdir -m 700 '+upload)
for name in ['feedback_relay.py','sticker-feedback.service','nginx-location.conf']:
 remote('cat > '+upload+'/'+name,(root/'server'/name).read_bytes().replace(b'\r\n',b'\n'))
remote('cat > '+upload+'/nginx-modified.conf',modified)
rollback=f'''#!/bin/sh
set -eu
test "$(sha256sum /opt/sticker-feedback/rollback/laoyu-https.conf | cut -d' ' -f1)" = {expected}
test "$(sha256sum /etc/nginx/conf.d/laoyu-https.conf | cut -d' ' -f1)" = {hashlib.sha256(modified).hexdigest()}
cp /opt/sticker-feedback/rollback/laoyu-https.conf /etc/nginx/conf.d/laoyu-https.conf
nginx -t
systemctl reload nginx
systemctl stop sticker-feedback.service
printf 'ROLLBACK original_nginx_hash=verified relay=stopped existing_services=retained\\n'
'''
(out/'ROLLBACK.sh').write_text(rollback,encoding='utf-8',newline='\n')
remote('cat > '+upload+'/rollback.sh',rollback.encode())
standard=Path('E:/共享/tools/软件开发/软件组件/用户提意见&反馈.md').read_text(encoding='utf-8')
url=re.search(r'https://qyapi\.weixin\.qq\.com/cgi-bin/webhook/send\?key=[a-f0-9-]{36}',standard).group()
remote("sudo sh -c 'umask 077; cat > /etc/sticker-feedback.env'",('FEEDBACK_WEBHOOK='+url+'\nFEEDBACK_DATABASE=/var/lib/sticker-feedback/receipts.sqlite3\n').encode())
url=standard=None
command=f'''set -eu
test "$(sudo sha256sum /etc/nginx/conf.d/laoyu-https.conf | cut -d' ' -f1)" = {expected}
sudo install -d -m 755 /opt/sticker-feedback/releases/0.5.1 /opt/sticker-feedback/rollback
sudo cp /etc/nginx/conf.d/laoyu-https.conf /opt/sticker-feedback/rollback/laoyu-https.conf
sudo install -m 644 {upload}/feedback_relay.py /opt/sticker-feedback/releases/0.5.1/feedback_relay.py
if ! sudo test -L /opt/sticker-feedback/current; then sudo ln -s /opt/sticker-feedback/releases/0.5.1 /opt/sticker-feedback/current; fi
sudo install -m 644 {upload}/sticker-feedback.service /etc/systemd/system/sticker-feedback.service
sudo install -m 644 {upload}/nginx-location.conf /etc/nginx/snippets/sticker-feedback.conf
sudo install -m 755 {upload}/rollback.sh /opt/sticker-feedback/ROLLBACK.sh
sudo systemctl daemon-reload
sudo systemctl enable --now sticker-feedback.service
sudo systemctl restart sticker-feedback.service
for n in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 19 20; do curl -fsS http://127.0.0.1:18774/health >/dev/null 2>&1 && break; sleep 1; done
curl -fsS http://127.0.0.1:18774/health
sudo install -m 644 {upload}/nginx-modified.conf /etc/nginx/conf.d/laoyu-https.conf
if ! sudo nginx -t; then sudo /opt/sticker-feedback/ROLLBACK.sh; exit 1; fi
sudo systemctl reload nginx
curl -fsS https://111.231.25.152:8443/sticker-maker-feedback/health
printf '\\nMODIFIED relay=active existing_nginx_routes=retained\\n'
'''
baseline=remote('curl -fsS http://127.0.0.1:18773/health')
first=remote('curl -fsS https://111.231.25.152:8443/sticker-maker-feedback/health; printf "\\nMODIFIED relay=active existing_nginx_routes=retained\\n"') if resume else remote(command)
restored=remote('sudo /opt/sticker-feedback/ROLLBACK.sh; sudo sha256sum /etc/nginx/conf.d/laoyu-https.conf; curl -fsS http://127.0.0.1:18773/health')
assert expected.encode() in restored
assert b'"ok":true' in restored
reapply=remote(f'''set -eu
sudo systemctl start sticker-feedback.service
sudo install -m 644 {upload}/nginx-modified.conf /etc/nginx/conf.d/laoyu-https.conf
sudo nginx -t
sudo systemctl reload nginx
for n in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 19 20; do curl -fsS http://127.0.0.1:18774/health >/dev/null 2>&1 && break; sleep 1; done
for n in 1 2 3 4 5 6 7 8 9 10; do curl -fsS https://111.231.25.152:8443/sticker-maker-feedback/health >/dev/null 2>&1 && break; sleep 1; done
curl -fsS https://111.231.25.152:8443/sticker-maker-feedback/health
printf '\\nMODIFIED restored_service=active after_rollback_test=true\\n'
''')
report={'original_nginx_sha256':expected,'baseline':baseline.decode(),'modified':first.decode(),'rollback':restored.decode(),'reapplied':reapply.decode(),'commands':{'baseline':'curl -fsS http://127.0.0.1:18773/health','modified':'curl -fsS https://111.231.25.152:8443/sticker-maker-feedback/health' if resume else command,'rollback':'sudo /opt/sticker-feedback/ROLLBACK.sh; sudo sha256sum /etc/nginx/conf.d/laoyu-https.conf; curl -fsS http://127.0.0.1:18773/health'},'exit':0,'scope':'only relay, new include; existing routes and data retained'}
(out/'VERIFICATION.txt').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print('DEPLOYMENT_PASS loopback=true HTTPS=true rollback_hash=original existing_analytics=retained final_relay=active')
