"""亂數機器人：玩完一整季，把心得花在武學上。用於整季測試與平衡模擬。

大多數時候隨機選一個可用的選項；只有三件事照規矩來：遇到結識的選項一定接受、
收徒只在名冊還塞不滿已開放的隊伍而且付完還付得起下一次時收（見 wants_apprentice），
每一步之後把本隊換成統御上限內最強的組合（見 arrange_team）。
付費機器人（play_season 給了 yuanbao）開季先把元寶全花在招賢（見 spend_yuanbao），其餘和免費機器人一樣。
"""
from __future__ import annotations

import random
from collections.abc import Callable
from itertools import combinations

from . import roster, team
from .engine import Game, Option
from .models import Content
from .state import PLAYER, TEAM_SIZE

HALF_HOUR = 1800
APPRENTICE = "act:apprentice"


def spend_xinde(game: Game) -> None:
    """貪心花心得：只要付得起，就把目前最便宜的一門升一成（同價時取排在前面的）。"""
    state, content = game.state, game.content
    while True:
        costs = []
        for _, target in game.upgrade_options():
            level = team.target_level(state, content, target)
            if level is not None and level < team.MAX_SKILL_LEVEL:
                costs.append((team.upgrade_cost(content, level), target))
        if not costs:
            return
        cost, target = min(costs, key=lambda c: c[0])
        if state.player.stats.get("xinde", 0) < cost:
            return
        game.upgrade(target)


def wants_apprentice(game: Game) -> bool:
    """要不要收徒：名冊（含你）還塞不滿已開放的隊伍（每隊 TEAM_SIZE 人），而且付完這次還付得起下一次
    （銀兩 ≥ 2 × 收徒的銀兩）。這是模擬用的策略，不是遊戲規則：不讓機器人為了收徒把銀兩花光、改變主線的走向。"""
    p, cfg = game.state.player, game.content.config
    return len(p.members) < TEAM_SIZE * game.team_count() and p.stats.get("silver", 0) >= 2 * cfg.apprentice_silver


def pick(game: Game, options: list[Option], rng: random.Random) -> str | None:
    """結識的選項一定接受；想收徒（wants_apprentice）時一定收徒，不想收時也不會隨機選到它；其餘隨機挑一個。
    沒得挑（只剩不想收的收徒）時回傳 None。"""
    s = game.state
    if s.pending_event:
        choices = game.content.events[s.pending_event].choices
        for option in options:
            if option.id.startswith("choice:") and choices[int(option.id.partition(":")[2])].effect.recruit:
                return option.id
    if any(option.id == APPRENTICE for option in options) and wants_apprentice(game):
        return APPRENTICE
    rest = [option for option in options if option.id != APPRENTICE]
    return rng.choice(rest).id if rest else None


def arrange_team(game: Game) -> None:
    """把本隊你以外的兩格換成統御上限內最強的兩人（強弱看目前四項屬性加總，一樣強時取名冊裡排前面的）。"""
    s, c = game.state, game.content
    room = game.command_cap() - roster.command_of(c, PLAYER)
    others = [key for key in roster.roster(s, c) if key != PLAYER]
    power = {key: sum(team.member_stats(s, c, key).values()) for key in others}
    pairs = [pair for pair in combinations(others, 2) if sum(roster.command_of(c, k) for k in pair) <= room]
    if not pairs:
        return
    best = max(pairs, key=lambda pair: sum(power[k] for k in pair))
    if set(best) == set(game.team_keys()[1:]):
        return
    game.set_member(0, 2, None)
    game.set_member(0, 1, None)
    for key in best:
        game.set_member(0, 2, key)


def spend_yuanbao(game: Game) -> None:
    """付費機器人開季時的招賢：元寶夠十連就一直十連，剩下的零頭夠單抽就單抽。"""
    for count in sorted(Game.PULL_SIZES, reverse=True):
        while game.pull_button(count)[1]:
            game.pull(count)


def play_season(
    content: Content, seed: int, max_steps: int = 20000, observe: Callable[[Game], None] | None = None,
    yuanbao: int = 0,
) -> Game:
    """玩完一季。yuanbao 大於 0 時是付費機器人：開季先拿這麼多元寶招賢，花掉換來的心得、排好本隊，再開始玩。
    observe 不是 None 時，開始玩之前呼叫一次（開季的樣子），之後每一步之後都呼叫一次（模擬器用來記錄名冊與交手的時間點）。"""
    game = Game.new(content, f"機器人{seed}", rng=random.Random(seed))
    rng = random.Random(seed)
    if yuanbao:
        game.state.player.yuanbao += yuanbao
        spend_yuanbao(game)
        spend_xinde(game)
        arrange_team(game)
    if observe is not None:
        observe(game)
    for step in range(max_steps):
        if game.state.world.ended:
            break
        options = [o for o in game.options(odds=False) if o.enabled]
        choice = pick(game, options, rng) if options else None
        if choice is not None:
            game.choose(choice)
            spend_xinde(game)
            arrange_team(game)
        if choice is None or step % 4 == 0:
            game.advance(HALF_HOUR)
        if observe is not None:
            observe(game)
    return game
