"""名冊與編隊：誰在門下、各隊有誰、每隊的統御與上限、隊伍依主線幕數開放。

名冊就是 PlayerState.members（你本人加上這一季入門的所有同伴）；隊伍是 PlayerState.teams，第一支是本隊，
一定有你、而且你固定是隊長。沒排進任何一隊的人是候補。1c-1 只有本隊會出手（歷練、探索、交遊、劇情戰、檢定），
第二隊起的派遣隊要到 1c-2 才會出門。
"""
from __future__ import annotations

import random

from . import rules, team  # 與 rules 互相 import：只能引入整個模組、呼叫時才取屬性，不能 from .rules import current_day
from .models import COMPANION_TIERS, Content, Squad
from .state import PLAYER, TEAM_SIZE, GameState, Member, Team

NUMERALS = "零一二三四五六七八九十"
EMPTY_CHOICE = ""  # 門下頁「換人」選單裡「（空）」的值


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
    if not 0 <= index < len(p.teams) or not 0 <= slot < TEAM_SIZE:
        return ["（沒有這個位置。）"]
    name = team_name(index)  # 先確認有這一隊：隊名的數字只寫到「十」
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


# ── 入門 ──────────────────────────────────────────────


def join_level(state: GameState) -> int:
    """新人的等級：目前各隊成員中最低的等級（候補不算），至少 1。"""
    p = state.player
    return max(1, min((p.members[key].level for key in team.lined_up(state)), default=1))


def recruit(state: GameState, content: Content, char_id: str) -> list[str]:
    """char_id 入門：從 join_level 起算、先列候補。已經在門下時照 config.duplicate_xinde 改給心得
    （劇情事件萬一給了已入門的人時；不算進 1c-3 的付費心得上限）。回傳敘事與數值變化。"""
    p, ch = state.player, content.characters[char_id]
    if char_id in p.members:
        amount = content.config.duplicate_xinde[ch.tier]
        p.stats["xinde"] = p.stats.get("xinde", 0) + amount
        return [f"【{ch.name}】早已在門下，這份緣分化為心得。", f"心得 +{amount}"]
    level = join_level(state)
    p.members[char_id] = Member(level=level)
    p.loadouts[char_id] = [None] * team.FREE_SLOTS
    return [f"【{ch.name}】入門（{ch.tier}品・{ch.style}・統御 {ch.command}），從第 {level} 級練起，先列候補。"]


def joined_tag(content: Content, char_id: str) -> str:
    """有人入門的那一則江湖紀錄的結果標記，例如「地品・入門」。"""
    return f"{content.characters[char_id].tier}品・入門"


# ── 收徒 ──────────────────────────────────────────────


def apprentice_candidates(state: GameState, content: Content) -> list[str]:
    """在目前所在地收得到、還沒入門的人：有「收徒」管道，寫了 recruit_at 的只在那些地點。"""
    p, weights = state.player, content.config.apprentice_weights
    return [
        cid for cid, ch in content.characters.items()
        if "收徒" in ch.sources and ch.tier in weights and cid not in p.members
        and (not ch.recruit_at or p.location in ch.recruit_at)
    ]


def apprenticed_today(state: GameState) -> int:
    p = state.player
    return p.apprentice_count if p.apprentice_day == rules.current_day(state) else 0


def apprentice_block(state: GameState, content: Content) -> str | None:
    """「收徒」選項的狀態：這裡不是城鎮或門派時為 None（不顯示）；收得了時是空字串（體力由 engine 照一般行動判斷）；
    收不了時是按鈕上要寫的原因。"""
    cfg = content.config
    if not set(content.locations[state.player.location].tags) & set(cfg.apprentice_tags):
        return None
    if not apprentice_candidates(state, content):
        return "此地已無可收之徒"
    if apprenticed_today(state) >= cfg.apprentice_per_day:
        return f"收徒（今天已收了 {cfg.apprentice_per_day} 次）"
    if state.player.stats.get("silver", 0) < cfg.apprentice_silver:
        return f"收徒（銀兩不足，要 {cfg.apprentice_silver} 兩）"
    return ""


def apprentice(state: GameState, content: Content, rng: random.Random) -> list[str]:
    """收徒：花銀兩與體力，從這裡收得到的人裡先依 config.apprentice_weights 抽品階（只在還有人的品階之間）、
    再在同品階裡平均抽一位。呼叫前 engine 已確認 apprentice_block 是空字串、體力也夠。"""
    cfg, p = content.config, state.player
    pool = apprentice_candidates(state, content)
    tiers = [tier for tier in cfg.apprentice_weights if any(content.characters[k].tier == tier for k in pool)]
    tier = rng.choices(tiers, weights=[cfg.apprentice_weights[t] for t in tiers])[0]
    pick = rng.choice([k for k in pool if content.characters[k].tier == tier])
    p.stamina -= cfg.apprentice_stamina
    p.stats["silver"] -= cfg.apprentice_silver
    p.apprentice_count = apprenticed_today(state) + 1
    p.apprentice_day = rules.current_day(state)
    return [f"銀兩 -{cfg.apprentice_silver}"] + recruit(state, content, pick)


# ── 招降 ──────────────────────────────────────────────


def surrender(state: GameState, content: Content, squad: Squad, rng: random.Random) -> list[str]:
    """打贏有 surrender 的敵方隊伍後擲一次招降；沒有招降或那人已經入門時不擲（不動亂數）。"""
    offer = squad.surrender
    if offer is None or offer.character in state.player.members:
        return []
    chance = content.config.surrender_chance if offer.chance is None else offer.chance
    if rng.random() >= chance:
        return []
    name = content.characters[offer.character].name
    return [f"{squad.name}敗退，【{name}】願意投效！"] + recruit(state, content, offer.character)


# ── 新立門戶福緣 ─────────────────────────────────────────


def fortune_due(state: GameState, content: Content) -> bool:
    """福緣還沒發生，而且已經是第 fortune_day_min 天（含）以後：這時交遊必定先觸發福緣事件
    （福緣要來的人都已經在門下時改送賀禮，見 Game._fortune_gift）。"""
    return not state.player.fortune and rules.current_day(state) >= content.config.fortune_day_min


def fortune_overdue(state: GameState, content: Content) -> bool:
    """第 fortune_day_max 天已經結束，福緣還沒發生：直接送上門。"""
    return not state.player.fortune and state.world.time >= content.config.fortune_day_max * rules.DAY


# ── 門下頁的文字 ──────────────────────────────────────────


def where(state: GameState, key: str) -> str:
    """這個人在哪裡：本隊、第二隊……或候補。"""
    index = team.team_of(state, key)
    return "候補" if index is None else team_name(index)


def team_choices(state: GameState, content: Content) -> list[tuple[str, int]]:
    """隊伍切換：（「本隊」「第二隊」「第三隊（第二幕開放）」, 第幾隊），設定裡的每一隊都列出來。"""
    opened = team_count(state, content)
    return [
        (team_name(i) if i < opened else f"{team_name(i)}（{opens_at(content, i)}）", i)
        for i in range(len(state.player.teams))
    ]


def team_info(state: GameState, content: Content, index: int) -> str:
    """選中那一隊的資訊列（Markdown），例如「**本隊**　統御 12／15　跟著你行動」「**第二隊**　統御 0／15　待命」；
    還沒開放的隊伍寫「**第三隊**　第二幕開放」。"""
    name = f"**{team_name(index)}**"
    if index >= team_count(state, content):
        return f"{name}　{opens_at(content, index)}"
    status = "跟著你行動" if index == 0 else "待命"
    return f"{name}　統御 {team_command(state, content, index)}／{command_cap(state, content)}　{status}"


def _label(state: GameState, content: Content, key: str) -> tuple[str, str, int, int]:
    """（品階, 流派, 統御, 等級）；你本人的品階寫「本人」。"""
    rank = "本人" if key == PLAYER else content.characters[key].tier
    return rank, team.member_style(content, key)[0], command_of(content, key), state.player.members[key].level


def roster_lines(state: GameState, content: Content) -> list[tuple[str, str]]:
    """名冊列表：（「玄　韓鐵　剛　統御 3　第 1 級　本隊」, key），順序同 roster。"""
    lines = []
    for key in roster(state, content):
        rank, style, command, level = _label(state, content, key)
        name = team.member_name(state, content, key)
        lines.append((f"{rank}　{name}　{style}　統御 {command}　第 {level} 級　{where(state, key)}", key))
    return lines


def swap_choices(state: GameState, content: Content, index: int, slot: int) -> list[tuple[str, str]]:
    """第 index 隊第 slot 位的「換人」選單：先是這一位目前的人（空位時沒有），再來是候補與別隊的人（依名冊順序），
    最後是「（空）」（值是 EMPTY_CHOICE，空位時沒有）。你本人與同一隊的其他人不在選單裡。"""
    members = team.team_keys(state, index)
    current = members[slot] if slot < len(members) else None
    keys = ([current] if current else []) + [k for k in roster(state, content) if k != PLAYER and k not in members]
    items = []
    for key in keys:
        rank, style, command, level = _label(state, content, key)
        name = team.member_name(state, content, key)
        items.append((f"{name}（{rank}品・{style}・統御 {command}・第 {level} 級・{where(state, key)}）", key))
    if current:
        items.append(("（空）", EMPTY_CHOICE))
    return items
