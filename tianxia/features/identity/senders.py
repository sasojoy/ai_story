"""寄送與真人驗證的介面（帳號與客服第 203 批；設計 4.6、4.7）：程式只認 SmsSender、MailSender、TurnstileVerifier 三個介面。

- 測試、開發與 QA 一律用假的（Config.identity.fake_services 開著：FakeSms、FakeMail 只記進 outbox，FakeTurnstile 只認 token "ok"）。
- 正式機在服務商接上之前用 NoSender（一寄就丟 SendFailed，路由回「現在無法寄送」）；Turnstile 走 CloudflareTurnstile（伺服器端 siteverify，
  驗 success、hostname、action，逾時 5 秒；網路出錯、沒有 secret 都當沒過）。
- Turnstile 的 secret 在 .local/identity.json 的 turnstile_secret（同金鑰那一份，路徑 identity_base.KEY_FILE；不進版控）。
寄送與 siteverify 是網路呼叫：路由不拿行動鎖，不會卡住別人。
"""
from __future__ import annotations

import json
import urllib.parse
import urllib.request
from pathlib import Path
from typing import NamedTuple, Protocol

from tianxia.core import identity_base

SITEVERIFY = "https://challenges.cloudflare.com/turnstile/v0/siteverify"
TIMEOUT = 5


class SendFailed(Exception):
    """寄送服務本身出錯（不是額度、不是玩家打錯）。"""


class SmsSender(Protocol):
    def send(self, to: str, text: str) -> None: ...


class MailSender(Protocol):
    def send(self, to: str, subject: str, text: str) -> None: ...


class TurnstileVerifier(Protocol):
    def verify(self, token: str, ip: str, hostname: str | None) -> bool: ...


class FakeSms:
    def __init__(self):
        self.outbox: list[tuple[str, str]] = []
        self.fail = False

    def send(self, to: str, text: str) -> None:
        if self.fail:
            raise SendFailed("fake sms down")
        self.outbox.append((to, text))


class FakeMail:
    def __init__(self):
        self.outbox: list[tuple[str, str]] = []
        self.subjects: list[str] = []
        self.fail = False

    def send(self, to: str, subject: str, text: str) -> None:
        if self.fail:
            raise SendFailed("fake mail down")
        self.outbox.append((to, text))
        self.subjects.append(subject)


class FakeTurnstile:
    def verify(self, token: str, ip: str, hostname: str | None) -> bool:
        return token == "ok"


class NoSender:
    """服務商還沒接上：寄什麼都丟 SendFailed。"""

    def send(self, to: str, *rest: str) -> None:
        raise SendFailed("no sender configured")


class CloudflareTurnstile:
    def __init__(self, secret: str, action: str, urlopen=None):
        self.secret, self.action = secret, action
        self.urlopen = urlopen or urllib.request.urlopen

    def verify(self, token: str, ip: str, hostname: str | None) -> bool:
        if not self.secret or not token:
            return False
        form = {"secret": self.secret, "response": token}
        if ip:
            form["remoteip"] = ip
        req = urllib.request.Request(SITEVERIFY, data=urllib.parse.urlencode(form).encode("utf-8"), method="POST")
        try:
            with self.urlopen(req, timeout=TIMEOUT) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except (OSError, ValueError):
            return False
        if not isinstance(data, dict) or data.get("success") is not True:
            return False
        if hostname and data.get("hostname") != hostname:
            return False
        return data.get("action") == self.action


class Senders(NamedTuple):
    sms: SmsSender
    mail: MailSender
    turnstile: TurnstileVerifier


FAKES = Senders(FakeSms(), FakeMail(), FakeTurnstile())  # fake_services 開著時大家共用這一組（測試讀 outbox）


def turnstile_secret(path: Path | None = None) -> str:
    try:
        data = json.loads(Path(path or identity_base.KEY_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return ""
    secret = data.get("turnstile_secret") if isinstance(data, dict) else None
    return secret if isinstance(secret, str) else ""


def pick(content) -> Senders:
    cfg = content.config.identity
    if cfg.fake_services:
        return FAKES
    return Senders(NoSender(), NoSender(), CloudflareTurnstile(turnstile_secret(), cfg.turnstile_action))
