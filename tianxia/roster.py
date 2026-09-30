"""同伴招募（sanguo-companions 合併大幅重寫，見設計文件四.4）：每位歷史人物全服唯一，
招募是有風險的玩家行動（可能被搶輸、可能惹惱對方要求決鬥），不是抽卡或收徒。

同伴的等級/武學進度存在共用世界狀態（world_state.py::CompanionProgress），不是玩家存檔
的一部分；`state.player.team` 只記「目前帶在身邊出戰的同伴 id」，`state.player.affinities`
記玩家對每一位歷史人物（不管有沒有招到）的好感度。
"""
from __future__ import annotations

import random

from . import rules, team
from .models import Content
from .state import GameState
from .world_state import CompanionProgress, WorldStateStore


def owned_by(world: WorldStateStore, companion_id: str) -> str | None:
    return world.get_companion(companion_id).owner


def owned_companions(world: WorldStateStore, player_name: str) -> list[str]:
    return [cid for cid, p in world.read().companions.items() if p.owner == player_name]


def recruitable_here(content: Content, world: WorldStateStore, location: str) -> list[str]:
    """在這個地點可以嘗試招募的人：內容標了 kind=recruitable、目前自由之身。"""
    return [
        cid for cid, ch in content.characters.items()
        if ch.kind == "recruitable" and ch.recruit_at == location and owned_by(world, cid) is None
    ]


def recruit_chance(content: Content, state: GameState, companion_id: str) -> float:
    cfg = content.config
    affinity = state.player.affinities.get(companion_id, 0)
    return min(0.95, max(0.05, cfg.recruit_base_chance + (affinity / 100) * cfg.recruit_affinity_bonus))


def _seed_starting_skills(world: WorldStateStore, companion_id: str, ch) -> None:
    """第一次被招募時，把內容裡的 starting_wugong/starting_neigong 配給他（不覆蓋既有進度：
    同伴被放走又再招募，等級/武學是全服共用的，原封不動保留，見 world_state.py）。"""
    def _apply(progress):
        if progress.wugong_id is None and ch.starting_wugong:
            progress.wugong_id = ch.starting_wugong
        if progress.neigong_id is None and ch.starting_neigong:
            progress.neigong_id = ch.starting_neigong

    world.update_companion(companion_id, _apply)


def attempt_recruit(
    state: GameState, content: Content, world: WorldStateStore, companion_id: str, rng: random.Random,
) -> list[str]:
    """設計文件四.4：唯一、可搶、失敗有代價。呼叫前 engine 已確認體力足夠、地點正確。"""
    ch = content.characters[companion_id]
    disp = ch.name
    owner = owned_by(world, companion_id)
    if owner == state.player.name:
        return [f"【{disp}】已經是你的同伴了。"]
    if owner is not None:
        return [f"【{disp}】已經被{owner}招攬走了，這次撲了個空。"]
    p = state.player
    p.stamina -= content.config.recruit_stamina
    chance = recruit_chance(content, state, companion_id)
    if rng.random() < chance:
        if not world.try_recruit(companion_id, p.name):
            return [f"晚了一步，【{disp}】剛剛被別人招攬走了。"]
        _seed_starting_skills(world, companion_id, ch)
        msgs = [f"【{disp}】被你的誠意打動，願意追隨於你！"]
        return msgs + team.add_to_team(state, companion_id)
    if rng.random() < content.config.duel_chance_on_fail:
        return [f"【{disp}】對你的貿然嘗試大為不悅，當場要求與你一較高下——你惹上了一場決鬥。"]
    return [f"【{disp}】婉拒了你這次的招攬，看來還需要多花心思。"]


def recruit(state: GameState, content: Content, world: WorldStateStore, char_id: str) -> list[str]:
    """劇情事件（結識/福緣）想直接送一位同伴：對方是自由之身就直接收入隊伍；已經有主的話
    （被別的玩家搶先招走了）改給一筆心得當安慰，不會覆蓋別人的招募結果。"""
    ch = content.characters[char_id]
    owner = owned_by(world, char_id)
    if owner == state.player.name:
        amount = content.config.recruit_consolation_xinde
        state.player.stats["xinde"] = state.player.stats.get("xinde", 0) + amount
        return [f"【{ch.name}】早已在你身邊，這份緣分化為心得。", f"心得 +{amount}"]
    if owner is not None:
        amount = content.config.recruit_consolation_xinde
        state.player.stats["xinde"] = state.player.stats.get("xinde", 0) + amount
        return [f"【{ch.name}】已經是{owner}的同伴了，這份緣分化為心得。", f"心得 +{amount}"]
    if not world.try_recruit(char_id, state.player.name):
        amount = content.config.recruit_consolation_xinde
        state.player.stats["xinde"] = state.player.stats.get("xinde", 0) + amount
        return [f"【{ch.name}】剛剛被別人招攬走了，這份緣分化為心得。", f"心得 +{amount}"]
    _seed_starting_skills(world, char_id, ch)
    return [f"【{ch.name}】加入了你的隊伍！"] + team.add_to_team(state, char_id)


# ── 新立門戶福緣 ─────────────────────────────────────────


def fortune_due(state: GameState, content: Content) -> bool:
    return not state.player.fortune and rules.current_day(state) >= content.config.fortune_day_min


def fortune_overdue(state: GameState, content: Content) -> bool:
    return not state.player.fortune and state.world.time >= content.config.fortune_day_max * rules.DAY


# ── 門下頁的文字 ──────────────────────────────────────────


def roster_lines(state: GameState, content: Content, world: WorldStateStore) -> list[tuple[str, str]]:
    """名冊列表：（顯示文字, key），本人在最前，其餘是這個玩家目前擁有的同伴。"""
    lines = [(f"本人　{state.player.name}　第 {state.player.member.level} 級", "player")]
    for cid in owned_companions(world, state.player.name):
        ch = content.characters[cid]
        progress = world.get_companion(cid)
        status = "出戰" if cid in state.player.team else "在門下"
        lines.append((f"{ch.name}　第 {progress.level} 級　{status}", cid))
    return lines
