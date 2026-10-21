from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from sticker_engine.publish import browser_runtime as runtime


def test_browser_paths_cover_windows_and_mac_without_hardcoded_user():
    win=runtime.browser_options('win32', {'PROGRAMFILES': 'X:/Programs'})
    assert any(str(p).replace('\\','/').endswith('Microsoft/Edge/Application/msedge.exe') for _,p in win)
    assert any('Google Chrome.app/Contents/MacOS/Google Chrome' in str(p).replace('\\','/') for _,p in runtime.browser_options('darwin', {}))


def test_system_browser_is_preferred_and_used_for_both_modes(tmp_path, monkeypatch):
    system=tmp_path/'edge';system.touch()
    monkeypatch.setattr(runtime,'browser_options',lambda:[('Edge',system)])
    pw=MagicMock()
    for headless in (True,False):
        runtime.launch_browser(pw,headless=headless)
        assert pw.chromium.launch.call_args.kwargs['executable_path']==str(system)
        assert pw.chromium.launch.call_args.kwargs['headless']==headless


def test_missing_browser_is_actionable_without_silent_download(tmp_path,monkeypatch):
    monkeypatch.setattr(runtime,'browser_options',lambda:[])
    pw=SimpleNamespace(chromium=SimpleNamespace(executable_path=str(tmp_path/'missing'),launch=MagicMock()))
    with pytest.raises(RuntimeError,match='问题与警告'):
        runtime.launch_browser(pw,headless=True)
    pw.chromium.launch.assert_not_called()


def test_optional_component_is_used_and_can_recover_system_launch_failure(tmp_path,monkeypatch):
    component=tmp_path/'component';component.touch()
    system=tmp_path/'chrome';system.touch()
    monkeypatch.setattr(runtime,'browser_options',lambda:[('Chrome',system)])
    launch=MagicMock(side_effect=[RuntimeError('system unavailable'),'component-browser'])
    pw=SimpleNamespace(chromium=SimpleNamespace(executable_path=str(component),launch=launch))
    assert runtime.launch_browser(pw,headless=True)=='component-browser'
    assert launch.call_args.kwargs['executable_path']==str(component)
