"""名冊與編隊：誰在門下、各隊有誰、每隊的統御與上限、隊伍依主線幕數開放。

名冊就是 PlayerState.members（你本人加上這一季入門的所有同伴）；隊伍是 PlayerState.teams，第一支是本隊，
一定有你、而且你固定是隊長。沒排進任何一隊的人是候補。1c-1 只有本隊會出手（歷練、探索、交遊、劇情戰、檢定），
第二隊起的派遣隊要到 1c-2 才會出門。
"""
from __future__ import annotations

from . import team
from .models import COMPANION_TIERS, Content
from .state import PLAYER, TEAM_SIZE, GameState, Team

NUMERALS = "零一二三四五六七八九十"


# ── 隊伍數與統御上限 ─────────────────────────────────────


def stage(state: GameState, content: Content) -> int:
    """隊伍數與統御上限看本季到過的最遠一幕（主線改寫會把幕數歸零，已開放的隊伍不會因此關上）。"""
    return min(state.world.act_reached, len(content.config.team_counts) - 1)


def team_count(state: GameState, content: Content) -> int:
    """目前開放幾隊（含本隊）。"""
    return content.config.team_counts[stage(state, content)]


def command_cap(state: GameState, content: Content) -> int:
    """每隊的總統御上限。"""
    return content.config.command_caps[stage(state, content)]


def team_name(index: int) -> str:
    """本隊、第二隊、第三隊……"""
    return "本隊" if index == 0 else f"第{NUMERALS[index + 1]}隊"


def opens_at(content: Content, index: int) -> str:
    """還沒開放的隊伍什麼時候開放，例如「第二幕開放」；設定裡永遠不會開放時寫「未開放」。"""
    act = next((a for a, n in enumerate(content.config.team_counts) if n > index), None)
    return "未開放" if act is None else f"第{NUMERALS[act + 1]}幕開放"


def command_of(content: Content, key: str) -> int:
    """一個人的統御：你本人是 config.player_command，同伴寫在人物資料上。"""
    return content.config.player_command if key == PLAYER else content.characters[key].command or 0


def team_command(state: GameState, content: Content, index: int) -> int:
    """第 index 隊目前的總統御。"""
    return sum(command_of(content, key) for key in team.team_keys(state, index))


# ── 名冊 ──────────────────────────────────────────────


def roster(state: GameState, content: Content) -> list[str]:
    """名冊：你本人在最前，其餘依品階（天地玄黃）排，同品階依入門先後。"""
    order = {tier: i for i, tier in enumerate(COMPANION_TIERS)}
    others = [key for key in state.player.members if key != PLAYER]
    return [PLAYER] + sorted(others, key=lambda key: order[content.characters[key].tier])


def bench(state: GameState, content: Content) -> list[str]:
    """候補：在名冊裡、但不在任何一隊的人，順序同 roster。"""
    return [key for key in roster(state, content) if team.team_of(state, key) is None]


def normalize(state: GameState, content: Content) -> None:
    """讀檔或換了內容之後整理隊伍：補齊到設定裡最多的隊伍數；丟掉已不在門下、重複出現或待在還沒開放的隊伍裡的人
    （他們回到候補）；每隊最多 TEAM_SIZE 人；你本人固定是本隊的隊長。Team 上的其他欄位原封不動。"""
    p = state.player
    size = max(content.config.team_counts)
    teams = p.teams[:size] + [Team() for _ in range(size - len(p.teams))]
    opened = team_count(state, content)
    seen = {PLAYER}
    for i, t in enumerate(teams):
        keep: list[str] = []
        room = TEAM_SIZE - 1 if i == 0 else TEAM_SIZE
        for key in t.members if i < opened else []:
            if key in p.members and key not in seen and len(keep) < room:
                keep.append(key)
                seen.add(key)
        t.members = [PLAYER] + keep if i == 0 else keep
    p.teams = teams


# ── 換人 ──────────────────────────────────────────────


def set_member(state: GameState, content: Content, index: int, slot: int, key: str | None) -> list[str]:
    """門下頁的「換人」：把第 index 隊第 slot 位（從 0 起算）換成 key。key 為 None 時空出這一位，後面的人往前補；
    slot 超過目前人數時補在最後。key 原本在別隊時從那一隊移過來，被換下的人回到候補。
    換成之後，那一隊裡配著隊友本命武學的人會被卸下那門武學，每卸一門多回傳一句說明。
    換不成時回傳「（原因。）」、什麼都不改；沒有變化時回傳空清單。"""
    p = state.player
    name = team_name(index)
    if not 0 <= index < len(p.teams) or not 0 <= slot < TEAM_SIZE:
        return ["（沒有這個位置。）"]
    if index >= team_count(state, content):
        return [f"（{name}{opens_at(content, index)}。）"]
    if index == 0 and slot == 0:
        return ["（你本人固定是本隊的隊長。）"]
    if key == PLAYER:
        return ["（你本人只能待在本隊。）"]
    if key is not None and key not in p.members:
        return ["（名冊裡沒有這個人。）"]
    members = team.team_keys(state, index)
    old = members[slot] if slot < len(members) else None
    if key == old:
        return []
    if key is not None and key in members:
        return [f"（{team.member_name(state, content, key)}已經在{name}。）"]
    new = list(members)
    if key is None:
        new.remove(old)
    elif old is None:
        new.append(key)
    else:
        new[slot] = key
    total, cap = sum(command_of(content, k) for k in new), command_cap(state, content)
    if key is not None and total > cap:
        return [f"（統御 {total}／{cap}，{team.member_name(state, content, key)}換不進{name}。）"]
    source = team.team_of(state, key) if key is not None else None
    if source is not None:
        p.teams[source].members.remove(key)
    p.teams[index].members = new
    usage = f"（{name}統御 {total}／{cap}）"
    if key is None:
        return [f"{team.member_name(state, content, old)}移到候補{usage}"]
    came = f"從{team_name(source)}" if source is not None else ""
    moved = f"{team.member_name(state, content, key)}{came}編入{name}"
    if old is not None:
        moved += f"，{team.member_name(state, content, old)}移到候補"
    return [moved + usage] + _unequip_innates(state, content, index)


def _unequip_innates(state: GameState, content: Content, index: int) -> list[str]:
    """第 index 隊裡，把配著隊友本命武學的自選欄清空（某人的本命不能配給同隊的人）；回傳每一門的說明。"""
    p = state.player
    members = team.team_keys(state, index)
    owners = {sid: k for k in members if (sid := team.innate_of(state, content, k))}
    msgs = []
    for holder in members:
        slots = p.loadouts.get(holder, [])
        for i, sid in enumerate(slots):
            if sid in owners:
                slots[i] = None
                msgs.append(
                    f"{content.skills[sid].name}是{team.member_name(state, content, owners[sid])}的本命，"
                    f"已從{team.member_name(state, content, holder)}的武學欄卸下。"
                )
    return msgs
