"""減法季批 7b QA 之後的修正（FB-845～849）測試共用的建法：正式內容、減法季開著，官軍（或散人）站在長社，帳上有 5000 元寶。
測試檔：test_fb845_art_ticket.py、test_fb846_quote_order.py、test_fb847_verdict_list.py、test_fb848_fixed_lines.py、test_fb849_art_note.py。"""
from __future__ import annotations

import random

from jianfa_kit import jianfa_game, ready
from tianxia import annals, calendar
from tianxia.characters import CharacterStore, name_key
from tianxia.engine import Game
from tianxia.wallet import Wallet

ADMIN = "史館管理者"


def make_game(profile: str = "season21", side: str | None = "guan", **flags) -> Game:
    game = jianfa_game(profile, **flags)
    game.content.config.admins = [ADMIN]
    ready(game, side=side, loc="changshe")
    game.sync(game.now)
    Wallet(game.world.db).post(name_key(game.state.player.name), 5000, "grant", "test:fix", time=game.now)
    CharacterStore(game.world.db).save(game.state)
    return game


def row(game: Game, item_id: str) -> dict | None:
    """商城貨架上的那一列（沒上架是 None）。"""
    return next((r for r in game.mall_view()["items"] if r["id"] == item_id), None)


def to_week(game: Game, week: int) -> None:
    w = game.state.world
    w.time = calendar.week_start(week, game.content, w) + 60
    game._save_season()


def admin_of(game: Game) -> Game:
    game.content.config.admins = [ADMIN]  # next_season 會把名單改成它自己的管理者
    admin = Game.new(game.content, ADMIN, rng=random.Random(1), world=game.world)
    admin.client = None
    return admin


def close_season(game: Game) -> Game:
    """管理者收季，這個人同步一次（進休季）。"""
    admin_of(game).admin_end_season(game.now + 10)
    CharacterStore(game.world.db).save(game.state)
    game.sync(game.now + 20)
    return game


def add_story(game: Game) -> None:
    """列傳要有行狀才寫得成。"""
    annals.note(game.state, game.content, annals.DEED, "在長社城下守了一夜。", 3)
    CharacterStore(game.world.db).save(game.state)


def option_ids(game: Game) -> set[str]:
    return {o.id for o in game.options()}


def figures(entry: dict) -> list[str]:
    """main.zhuan／biography_view 的 verdicts 裡的人物 id（照順序）。"""
    return [v["figure"] for v in entry["verdicts"]]


def verdict_paras(paragraphs: list[str]) -> list[str]:
    """傳的段落裡人物寫的評曰（「評曰：某某云：「…」」；史官自己的評曰不算）。"""
    return [p for p in paragraphs if p.startswith("評曰：") and "云：「" in p[:10]]
