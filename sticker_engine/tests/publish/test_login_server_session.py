from unittest.mock import MagicMock
from sticker_engine.publish.browser import BrowserSession
from sticker_engine.publish.config import PublishConfig


def page_with(ret):
    page=MagicMock();response=MagicMock();response.ok=True
    response.json.return_value={'base_resp':{'ret':ret},'List':[]}
    page.context.request.get.return_value=response
    return page


def test_cached_header_does_not_prove_expired_server_session():
    session=BrowserSession(PublishConfig());page=page_with(-3)
    assert session._is_logged_in(page) is False
    assert page.context.request.get.call_count==2


def test_valid_authenticated_list_proves_session_without_exposing_cookies():
    session=BrowserSession(PublishConfig());page=page_with(0)
    assert session._is_logged_in(page) is True
    assert page.context.request.get.call_count==1


def test_timeout_login_uses_visible_text_and_waits_for_password_form(monkeypatch):
    from sticker_engine.publish import browser
    monkeypatch.setattr(browser.time,'sleep',lambda _:None)
    session=BrowserSession(PublishConfig());page=MagicMock()
    page.evaluate.return_value=True
    monkeypatch.setattr(session,'_is_logged_in',lambda _:True)
    monkeypatch.setattr(session,'save_state',MagicMock())
    assert session._do_password_login(page,'fixture@example.com','not-a-real-password')
    page.get_by_text.assert_any_call('重新登录',exact=True)
    page.get_by_text.assert_any_call('账号密码登录',exact=True)
    page.locator.assert_any_call('input[type="password"]')
