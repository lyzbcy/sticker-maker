"""微信表情开放平台发布凭据的安全保管。

用户需求：账号密码由用户在软件里填写一次，之后安全保管在系统凭据库——
Windows → 凭据管理器（Credential Manager）；macOS → 钥匙串（Keychain）。
不落明文文件。新凭据仅写系统凭据库；旧版本地文件只用于兼容读取。
"""
from pathlib import Path

SERVICE = "StickerEngine-WeChatPublish"
ACCOUNT_KEY = "account"
PASSWORD_KEY = "password"


def _fallback_file() -> Path:
    from ..config.paths import resolve_paths, current_platform
    return resolve_paths(current_platform()).user_data / "publish_credentials.json"


def _keyring_ok() -> bool:
    try:
        import keyring  # noqa: F401
        return True
    except Exception:
        return False


def save_credentials(account: str, password: str) -> dict:
    """保存凭据。返回 {"backend": "keyring"|"file"}。"""
    if not account or not password:
        raise ValueError("账号和密码都不能为空")
    if _keyring_ok():
        import keyring
        keyring.set_password(SERVICE, ACCOUNT_KEY, account)
        keyring.set_password(SERVICE, PASSWORD_KEY, password)
        return {"backend": "keyring"}
    raise RuntimeError("系统凭据库不可用，账号密码尚未保存。请重新安装完整软件后再试；不会写入明文文件。")


def load_credentials():
    """读凭据。返回 (account, password) 或 (None, None)。"""
    if _keyring_ok():
        try:
            import keyring
            account = keyring.get_password(SERVICE, ACCOUNT_KEY)
            password = keyring.get_password(SERVICE, PASSWORD_KEY)
            if account and password:
                return account, password
        except Exception:
            pass
    f = _fallback_file()
    if f.exists():
        try:
            import json
            data = json.loads(f.read_text(encoding="utf-8"))
            password = data.get("password")
            if not password and data.get("password_b64"):
                # 旧版引擎（2026-07 前后）把密码存成 password_b64——
                # 读不出来会导致"未配置发布账号密码"假报（2026-09-07 实测）
                import base64
                try:
                    password = base64.b64decode(data["password_b64"]).decode("utf-8")
                except Exception:
                    password = None
            return data.get("account"), password
        except (json.JSONDecodeError, OSError):
            pass
    return None, None


def clear_credentials() -> None:
    if _keyring_ok():
        try:
            import keyring
            keyring.delete_password(SERVICE, ACCOUNT_KEY)
            keyring.delete_password(SERVICE, PASSWORD_KEY)
        except Exception:
            pass
    f = _fallback_file()
    if f.exists():
        f.unlink()


def credentials_status() -> dict:
    """凭据配置状态（不回传密码本体）。"""
    account, password = load_credentials()
    return {
        "configured": bool(account and password),
        "account": account or "",
        "backend": "keyring" if _keyring_ok() else "file",
    }
