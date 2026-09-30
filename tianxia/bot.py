"""亂數機器人：玩完一整季，用於整季測試與平衡模擬。

sanguo-companions 合併大幅重寫：拿掉抽卡、收徒、多隊派遣——招募到新同伴後不用機器人
額外處理，roster.attempt_recruit/recruit 已經自動把人加進隊伍（見 roster.py）。大多數
時候隨機選一個可用的選項（含深度對話的 talk:N，用一般 fallback 反應即可，不需要真的連
Ollama）；只有「結識」一定接受；心得攢夠一定步數就拿去練功（沒學過的功法先自創，已經
學過的就鍛鍊，見 spend_xinde）。
"""
from __future__ import annotations

import random
from collections.abc import Callable

from . import team
from .engine import Game, Option
from .models import Content
from .world_state import WorldStateStore

HALF_HOUR = 1800
SPEND_XINDE_EVERY = 5  # 每幾步檢查一次要不要拿心得去練功/療傷


def wants_heal(game: Game) -> bool:
    now, cap = team.member_neili(game.content, game.state.player.member)
    return now < cap * 0.5


def spend_xinde(game: Game, rng: random.Random) -> None:
    """氣血掉到五成以下先療傷；接著每門（內功/武學）沒學過的就自創（隨機取名），已經學過
    的就鍛鍊一成——不追求最優策略，只求機器人不會把心得放著不用。"""
    if wants_heal(game):
        game.heal()
    member = game.state.player.member
    for kind, slot in (("內功", "neigong_id"), ("武學", "wugong_id")):
        if getattr(member, slot) is None:
            game.create_skill(f"{kind}{rng.randint(0, 10 ** 9)}", kind)
        else:
            game.practice(kind)


def pick(game: Game, options: list[Option], rng: random.Random) -> str | None:
    """結識（choice 的 effect.recruit）一定接受；其餘隨機挑一個。沒得挑時回傳 None。"""
    s = game.state
    if s.pending_event:
        choices = game.content.events[s.pending_event].choices
        for option in options:
            if option.id.startswith("choice:") and choices[int(option.id.partition(":")[2])].effect.recruit:
                return option.id
    return rng.choice(options).id if options else None


def play_season(
    content: Content, seed: int, max_steps: int = 20000, observe: Callable[[Game], None] | None = None,
    world: WorldStateStore | None = None,
) -> Game:
    """玩完一季：隨機挑選項、遇到結識一定接受、每隔幾步把攢下的心得拿去練功。
    observe 不是 None 時，開始玩之前呼叫一次（開季的樣子），之後每一步之後都呼叫一次
    （模擬器用來記錄名冊與交手的時間點）。"""
    game = Game.new(content, f"機器人{seed}", rng=random.Random(seed), world=world)
    rng = random.Random(seed)
    if observe is not None:
        observe(game)
    for step in range(max_steps):
        if game.state.world.ended:
            break
        options = [o for o in game.options(odds=False) if o.enabled]
        choice = pick(game, options, rng) if options else None
        if choice is not None:
            game.choose(choice)
            if step % SPEND_XINDE_EVERY == 0:
                spend_xinde(game, rng)
        if choice is None or step % 4 == 0:
            game.advance(HALF_HOUR)
        if observe is not None:
            observe(game)
    return game
