"""Packaged desktop first-screen feedback receipt, loopback mock only."""
import json, os, subprocess, threading, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from playwright.sync_api import sync_playwright

root = Path(__file__).resolve().parents[1]
for key in ['HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY', 'http_proxy', 'https_proxy', 'all_proxy']: os.environ.pop(key, None)
folder = root / 'verification/feedback-layout'
folder.mkdir(parents=True, exist_ok=True)
class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        data = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        assert data['text']['content'].startswith('表情包一键制作 0.5.1')
        body = b'{"errcode":0}'
        self.send_response(200); self.send_header('Content-Length', str(len(body))); self.end_headers(); self.wfile.write(body)
    def log_message(self, *args): pass
server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
threading.Thread(target=server.serve_forever, daemon=True).start()
env = dict(os.environ, STICKER_FEEDBACK_URL=f'http://127.0.0.1:{server.server_port}/feedback', STICKER_DESKTOP_USER_DATA=str(folder/'desktop'), STICKER_ENGINE_USER_DATA=str(folder/'engine'), STICKER_ENGINE_NO_LOCK='1')
proc = subprocess.Popen([str(root/'desktop/release/win-unpacked/表情包一键制作.exe'), '--remote-debugging-port=9489'], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
try:
    with sync_playwright() as p:
        for i in range(40):
            try: browser = p.chromium.connect_over_cdp('http://127.0.0.1:9489'); break
            except Exception:
                if i == 39: raise
                time.sleep(.5)
        page = browser.contexts[0].pages[0]; page.wait_for_timeout(2500)
        page.get_by_role('button', name='遇到问题反馈', exact=True).click()
        page.locator('.feedback textarea').fill('layout fixture only')
        page.locator('.feedback input[type=checkbox]').uncheck()
        page.get_by_role('button', name='发送给作者', exact=True).click()
        status = page.locator('.feedback [role=status]')
        status.filter(has_text='已送达作者').wait_for(state='visible')
        box = status.bounding_box(); height = page.evaluate('innerHeight')
        assert box and box['y'] >= 0 and box['y'] + box['height'] < height - 64, box
        assert page.locator('.feedback textarea').input_value() == ''
        page.screenshot(path=str(folder/'receipt-visible.png'))
        result = {'status': 'FEEDBACK_LAYOUT_PASS', 'receipt_box': box, 'viewport_height': height, 'transport': 'loopback_mock_only', 'real_messages': 0}
        (folder/'result.json').write_text(json.dumps(result, indent=2)); print(json.dumps(result))
finally:
    proc.terminate(); proc.wait(timeout=30); server.shutdown(); server.server_close()
