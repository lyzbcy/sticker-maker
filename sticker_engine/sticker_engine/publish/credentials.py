"""微信表情开放平台发布凭据的安全保管。

用户需求：账号密码由用户在软件里填写一次，之后安全保管在系统凭据库——
Windows → 凭据管理器（Credential Manager）；macOS → 钥匙串（Keychain）。
不落明文文件。keyring 不可用时回退到 user_data 下的本地文件（带警告）。
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
    # 回退：本地 JSON（明文，但只在 keyring 不可用时）
    import json
    f = _fallback_file()
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps({"account": account, "password": password},
                            ensure_ascii=False), encoding="utf-8")
    return {"backend": "file"}


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
            return data.get("account"), data.get("password")
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
