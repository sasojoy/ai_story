"""玩家之間的邀請（玩家互動第二層：切磋、論武；介面 thread 的結伴同行也掛在這裡）：一個人在同一地點向另一個人發邀請，
對方接受、婉拒，或放著等它逾時。邀請存在這一季的 WorldState.invites（跟 echoes 一樣在賽季裡，換季自然清空，不改資料庫結構）。

這個模組只管邀請本身（發、查、收、作廢），純函式、只動傳進來的 WorldState；誰在不在同一地點、接受之後做什麼，
由 Game 讀雙方的存檔來判（Game.invite／reply_invite）。時間一律是世界秒（引擎不讀電腦時鐘）。"""
from __future__ import annotations

import hashlib

from .characters import name_key
from .models import Content
from .state import Invite, WorldState

KINDS = {"spar": "切磋", "discuss": "論武"}  # 介面 thread 的結伴同行加 "travel"


def kind_name(kind: str) -> str:
    return KINDS.get(kind, kind)


def _id(sender: str, target: str, kind: str, sent_at: float) -> str:
    """邀請的編號：雜湊（同 Plot.id 的做法），不必另外記流水號。"""
    raw = f"{name_key(sender)}|{name_key(target)}|{kind}|{sent_at!r}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]


def expire(world: WorldState) -> list[Invite]:
    """拿掉逾時的邀請，回傳拿掉的那幾張（呼叫端要不要記一則紀錄自己決定）。"""
    gone = [i for i in world.invites if i.expires_at <= world.time]
    if gone:
        world.invites = [i for i in world.invites if i.expires_at > world.time]
    return gone


def incoming(world: WorldState, name: str) -> list[Invite]:
    key = name_key(name)
    return [i for i in world.invites if name_key(i.target) == key and i.expires_at > world.time]


def outgoing(world: WorldState, name: str) -> list[Invite]:
    key = name_key(name)
    return [i for i in world.invites if name_key(i.sender) == key and i.expires_at > world.time]


def find(world: WorldState, invite_id: str) -> Invite | None:
    return next((i for i in world.invites if i.id == invite_id and i.expires_at > world.time), None)


def between(world: WorldState, a: str, b: str, kind: str) -> Invite | None:
    """這兩個人之間（不分誰發的）還在等的同一種邀請；一對人同一種一次只有一張。"""
    pair = {name_key(a), name_key(b)}
    return next(
        (i for i in world.invites
         if i.kind == kind and {name_key(i.sender), name_key(i.target)} == pair and i.expires_at > world.time),
        None,
    )


def send(
    world: WorldState, content: Content, kind: str, sender: str, target: str, location: str, payload: dict | None = None,
) -> Invite:
    """記一張新邀請（呼叫端先驗過能不能發）。逾時是 invite_ttl_seconds 個世界秒。"""
    invite = Invite(
        id=_id(sender, target, kind, world.time), kind=kind, sender=sender, target=target, location=location,
        sent_at=world.time, expires_at=world.time + content.config.invite_ttl_seconds, payload=dict(payload or {}),
    )
    world.invites.append(invite)
    return invite


def drop(world: WorldState, invite_id: str) -> Invite | None:
    """收走一張（接受、婉拒、取消、作廢都走這裡）；不在了回 None。"""
    invite = next((i for i in world.invites if i.id == invite_id), None)
    if invite is not None:
        world.invites = [i for i in world.invites if i.id != invite_id]
    return invite


def drop_involving(world: WorldState, name: str, *, away_from: str | None = None) -> list[Invite]:
    """跟這個人有關的邀請全部作廢（他離開了 away_from 這個地點、換季、叛投……）；away_from 給了就只作廢在那個地點的。"""
    key = name_key(name)
    gone = [
        i for i in world.invites
        if key in (name_key(i.sender), name_key(i.target)) and (away_from is None or i.location == away_from)
    ]
    if gone:
        ids = {i.id for i in gone}
        world.invites = [i for i in world.invites if i.id not in ids]
    return gone
