"""CLI repair routing with local byte fixtures; no downloads or actual login."""
import hashlib
import json
import subprocess
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from sticker_engine import cli
from sticker_engine.providers import codex, native_installer


def installed_fixture(tmp_path, monkeypatch):
    device = tmp_path / 'isolated-device'
    folder = device / 'tools' / 'codex'
    folder.mkdir(parents=True)
    files = {}
    for name in ['codex.exe', 'codex-code-mode-host.exe', 'codex-command-runner.exe', 'codex-windows-sandbox-setup.exe']:
        content = ('deterministic fixture '+name).encode()
        (folder / name).write_bytes(content)
        files[name] = hashlib.sha256(content).hexdigest()
    manifest = folder / 'release-manifest.json'
    manifest.write_text(json.dumps({'files': files}), encoding='utf-8')
    monkeypatch.setenv('STICKER_ENGINE_USER_DATA', str(device))
    # Replace module-local sys handles, not real sys.platform: Path remains the
    # host's native class on Mac/Linux runners while exercising Windows routing.
    monkeypatch.setattr(cli, 'sys', SimpleNamespace(platform='win32'))
    monkeypatch.setattr(codex, 'sys', SimpleNamespace(platform='win32'))
    monkeypatch.setattr(codex.CodexProvider, '_resolve_codex_path', lambda self: str(folder / 'codex.exe'))
    monkeypatch.setattr(codex.Path, 'home', lambda: tmp_path / 'empty-home')
    monkeypatch.setattr(cli, '_ensure_engine', lambda: SimpleNamespace(config=SimpleNamespace(
        paths=SimpleNamespace(user_data=device, codex_output_dir=tmp_path / 'no-images'))))
    monkeypatch.setattr(codex.subprocess, 'run', Mock(side_effect=lambda command,**kwargs: SimpleNamespace(returncode=1 if command[1:]==['login','status'] else 0)))
    install = Mock(return_value=str(folder / 'codex.exe'))
    monkeypatch.setattr(native_installer, 'install_native', install)
    result, emit = Mock(), Mock()
    monkeypatch.setattr(cli, '_result', result)
    monkeypatch.setattr(cli, '_emit', emit)
    return folder, manifest, device, install, result


def test_cli_repairs_manifest_mismatch_even_when_all_helper_files_exist(tmp_path, monkeypatch):
    folder, manifest, device, install, result = installed_fixture(tmp_path, monkeypatch)
    data = json.loads(manifest.read_text(encoding='utf-8'))
    data['files']['codex-code-mode-host.exe'] = '0' * 64
    manifest.write_text(json.dumps(data), encoding='utf-8')
    assert all((folder / name).is_file() for name in data['files'])
    assert codex.CodexProvider().check().needs_repair is True
    cli.cmd_install_codex('repair-manifest', {})
    install.assert_called_once()
    assert install.call_args.args[0] == device
    assert result.call_args.args[:2] == ('repair-manifest', 'ok')


@pytest.mark.parametrize('failure', ['version_failed', 'version_timeout'])
def test_cli_repairs_installed_binary_marked_needs_repair(tmp_path, monkeypatch, failure):
    _, _, device, install, result = installed_fixture(tmp_path, monkeypatch)
    if failure == 'version_timeout':
        monkeypatch.setattr(codex.subprocess, 'run', Mock(side_effect=subprocess.TimeoutExpired('fixture-version', 15)))
    else:
        monkeypatch.setattr(codex.subprocess, 'run', Mock(return_value=SimpleNamespace(returncode=1)))
    assert codex.CodexProvider().check().needs_repair is True
    cli.cmd_install_codex('repair-runtime', {})
    install.assert_called_once()
    assert install.call_args.args[0] == device
    assert result.call_args.args[:2] == ('repair-runtime', 'ok')


def test_cli_does_not_reinstall_valid_complete_install_just_because_logged_out(tmp_path, monkeypatch):
    _, _, _, install, result = installed_fixture(tmp_path, monkeypatch)
    status = codex.CodexProvider().check()
    assert status.installed is True
    assert status.logged_in is False
    assert status.image_ready is False
    assert status.needs_repair is False
    cli.cmd_install_codex('already-installed', {})
    install.assert_not_called()
    assert result.call_args.args[:2] == ('already-installed', 'ok')
    assert result.call_args.kwargs['data']['image_ready'] is False
