"""Use an installed browser first; Chromium is an optional local component."""
import os
import sys
from pathlib import Path


def browser_options(platform=None, environ=None):
    platform = platform or sys.platform
    env = os.environ if environ is None else environ
    options = []
    if env.get('STICKER_BROWSER_EXECUTABLE'):
        options.append(('指定浏览器', Path(env['STICKER_BROWSER_EXECUTABLE'])))
    if platform == 'win32':
        for label, suffix in [('Microsoft Edge', 'Microsoft/Edge/Application/msedge.exe'),
                              ('Google Chrome', 'Google/Chrome/Application/chrome.exe')]:
            for variable in ('PROGRAMFILES(X86)', 'PROGRAMFILES', 'LOCALAPPDATA'):
                if env.get(variable):
                    options.append((label, Path(env[variable]) / suffix))
    elif platform == 'darwin':
        for base in (Path('/Applications'), Path.home() / 'Applications'):
            for label, executable in [('Google Chrome', 'Google Chrome.app/Contents/MacOS/Google Chrome'),
                                      ('Microsoft Edge', 'Microsoft Edge.app/Contents/MacOS/Microsoft Edge')]:
                options.append((label, base / executable))
    return options


def browser_status(playwright=None):
    for label, executable in browser_options():
        if executable.is_file():
            return dict(ready=True, source='system', name=label, executable_path=str(executable))
    if playwright is not None:
        executable = Path(playwright.chromium.executable_path)
        if executable.is_file():
            return dict(ready=True, source='component', name='Chromium', executable_path=str(executable))
    return dict(ready=False, source='', name='', guidance='未找到 Edge/Chrome，请在「问题与警告」安装浏览器组件；浏览、评分和导出不受影响。')


def launch_browser(playwright, *, headless, args=None):
    status = browser_status(playwright)
    if not status['ready']:
        raise RuntimeError(status['guidance'])
    try:
        return playwright.chromium.launch(headless=headless, args=args or [],
                                           executable_path=status['executable_path'])
    except Exception as exc:
        fallback = Path(playwright.chromium.executable_path)
        if status['source'] == 'system' and fallback.is_file() and str(fallback) != status['executable_path']:
            return playwright.chromium.launch(headless=headless, args=args or [], executable_path=str(fallback))
        raise RuntimeError(f"{status['name']} 启动失败，请在「问题与警告」重新检测或安装浏览器组件：{exc}") from exc
