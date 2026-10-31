"""同伴招募（sanguo-companions 合併大幅重寫，見設計文件四.4）：每位歷史人物全服唯一，
招募是有風險的玩家行動（可能被搶輸、可能惹惱對方要求決鬥），不是抽卡或收徒。

同伴的等級/武學進度存在共用世界狀態（world_state.py::CompanionProgress），不是玩家存檔
的一部分；`state.player.team` 只記「目前帶在身邊出戰的同伴 id」，`state.player.affinities`
記玩家對每一位歷史人物（不管有沒有招到）的好感度。
"""
from __future__ import annotations

import random

from . import calendar, ranger, rules, team
from .characters import name_key
from .models import Content
from .state import MAX_TEAM_COMPANIONS, GameState
from .world_state import WorldStateStore

# 招募鈕灰掉時寫的原因（歷史武將同行第二、四節；待 joy 潤）
SIDE_ONLY = "只追隨{side}"
FULL = "名下已有 {n} 位同伴"
# 修練頁名冊上的「放他回江湖」（第四節【PM】；待 joy 潤）
RELEASE_CONFIRM = "放{name}回江湖？他會回到他常在的地方，誰都可以去招他；你們的情誼不變。"
RELEASE_DONE = "{name}拱手道別，回江湖去了；你們的情誼還在，日後可以再去找他。"
RELEASE_NOT_YOURS = "（他不在你的名下。）"
RELEASE_TITLE = "放{name}回江湖"
# 叛投帶不走（9.5；待 joy 潤）：確認畫面「會失去」的那一項、確定叛投之後那一句
DEFECT_LOST = "{names}不會隨你改投，回江湖去（情誼減半）"
DEFECT_LEFT = "{name}不肯隨你改投，回江湖去了（情誼 {before}→{after}）。"


def left_behind(state: GameState, content: Content, world: WorldStateStore, side: str) -> list[str]:
    """叛投到 side（陣營 id）時帶不走的同伴（9.5）：名下、寫了 side 而且跟新陣營不合的；沒寫 side 的照舊跟著你。開關關著是空的。"""
    if not on(content):
        return []
    return [
        cid for cid in owned_companions(world, state.player.name)
        if cid in content.characters and content.characters[cid].side not in (None, side)
    ]


def on(content: Content) -> bool:
    """歷史武將同行開著沒（Config.companions）：招募開放、名下上限、放走、決戰助陣、叛投帶不走都看它。"""
    return content.config.companions.enabled


def cap(content: Content) -> int:
    """名下最多幾位：開著是 Config.companions.max_owned（3），關著照舊 MAX_TEAM_COMPANIONS（一個字都不變）。"""
    return content.config.companions.max_owned if on(content) else MAX_TEAM_COMPANIONS


def _capped(content: Content) -> dict:
    """try_recruit 的上限參數：開著才帶 cap（關著照舊兩個參數，一個字都不變）。"""
    return {"cap": cap(content)} if on(content) else {}


def owns(owner: str | None, player_name: str) -> bool:
    """owner 是不是這個人（名號比對不分大小寫，同 characters.name_key）。"""
    return owner is not None and name_key(owner) == name_key(player_name)


def owned_by(world: WorldStateStore, companion_id: str) -> str | None:
    return world.get_companion(companion_id).owner


def owned_companions(world: WorldStateStore, player_name: str) -> list[str]:
    return [cid for cid, p in world.companions().items() if owns(p.owner, player_name)]


def recruit_problem(state: GameState, content: Content, world: WorldStateStore, companion_id: str) -> str | None:
    """歷史武將同行：招不了他的原因（照陣營、名下滿了）；招得了是 None。有沒有主、在不在這裡由呼叫端看。
    陣營照自己投靠的那一個（豪強分屬兩軍時照舊算豪強，p.faction）。"""
    ch = content.characters[companion_id]
    if ch.side is not None and state.player.faction != ch.side:
        return SIDE_ONLY.format(side=content.scenario.faction_name(ch.side, ch.side))
    n = len(owned_companions(world, state.player.name))
    return FULL.format(n=n) if n >= cap(content) else None


def affinity_ok(state: GameState, content: Content, companion_id: str) -> bool:
    """情誼到 Config.recruit_min_affinity 了沒（Joy 2026-10-21）：沒到的人選單上不畫招募鈕、招募也不受理。"""
    return state.player.affinities.get(companion_id, 0) >= content.config.recruit_min_affinity


def recruit_chance(content: Content, state: GameState, companion_id: str) -> float:
    cfg = content.config
    affinity = state.player.affinities.get(companion_id, 0)
    bonus = ranger.recruit_bonus(state, content)  # 散人的遊俠名號第 2 階起加成（陣營的人是 0）
    return min(0.95, max(0.05, cfg.recruit_base_chance + (affinity / 100) * cfg.recruit_affinity_bonus + bonus))


def _seed_starting_skills(world: WorldStateStore, companion_id: str, ch) -> None:
    """第一次被招募時，把內容裡的 starting_wugong/starting_neigong 配給他（不覆蓋既有進度：
    同伴被放走又再招募，等級/武學是全服共用的，原封不動保留，見 world_state.py）。"""
    def _apply(progress):
        if progress.wugong_id is None and ch.starting_wugong:
            progress.wugong_id = ch.starting_wugong
        if progress.neigong_id is None and ch.starting_neigong:
            progress.neigong_id = ch.starting_neigong

    world.update_companion(companion_id, _apply)


# 他已經有主了（招募撲空、兩個分頁搶慢了一步 FB-363）：寫主人的名號（匿名只在地方傳聞，rules.display_name）
TAKEN = "【{name}】已經被{owner}招攬走了，這次撲了個空。"


def attempt_recruit(
    state: GameState, content: Content, world: WorldStateStore, companion_id: str, rng: random.Random,
) -> list[str]:
    """設計文件四.4：唯一、可搶、失敗有代價。呼叫前 engine 已確認體力足夠、地點正確。"""
    ch = content.characters[companion_id]
    disp = ch.name
    owner = owned_by(world, companion_id)
    if owns(owner, state.player.name):
        return [f"【{disp}】已經是你的同伴了。"]
    if owner is not None:
        return [TAKEN.format(name=disp, owner=owner)]
    p = state.player
    p.stamina -= content.config.recruit_stamina
    chance = recruit_chance(content, state, companion_id)
    if rng.random() < chance:
        if not world.try_recruit(companion_id, p.name, **_capped(content)):
            if owned_by(world, companion_id) is None:  # 沒人搶走：是名下滿了（另一個分頁剛招到一位）
                return [f"（{FULL.format(n=len(owned_companions(world, p.name)))}，招不了更多人。）"]
            return [f"晚了一步，【{disp}】剛剛被別人招攬走了。"]
        _seed_starting_skills(world, companion_id, ch)
        msgs = [f"【{disp}】被你的誠意打動，願意追隨於你！"]
        return msgs + team.add_to_team(state, companion_id)
    if rng.random() < content.config.duel_chance_on_fail:
        loss = min(p.stats.get("silver", 0), content.config.duel_fail_silver_loss)
        p.stats["silver"] = p.stats.get("silver", 0) - loss
        msgs = [f"【{disp}】對你的貿然嘗試大為不悅，當場要求與你一較高下——你吃了幾下教訓，倉皇退走。"]
        if loss:
            msgs.append(f"銀兩 -{loss}")
        return msgs
    return [f"【{disp}】婉拒了你這次的招攬，看來還需要多花心思——先多來幾趟「交友」，培養情誼再試，成功率會更高。"]


def recruit(state: GameState, content: Content, world: WorldStateStore, char_id: str) -> list[str]:
    """劇情事件（結識/福緣）想直接送一位同伴：對方是自由之身就直接收入隊伍；已經有主的話
    （被別的玩家搶先招走了）改給一筆心得當安慰，不會覆蓋別人的招募結果。"""
    ch = content.characters[char_id]
    owner = owned_by(world, char_id)
    if owns(owner, state.player.name):
        amount = content.config.recruit_consolation_xinde
        state.player.stats["xinde"] = state.player.stats.get("xinde", 0) + amount
        return [f"【{ch.name}】早已在你身邊，這份緣分化為心得。", f"心得 +{amount}"]
    if owner is not None:
        amount = content.config.recruit_consolation_xinde
        state.player.stats["xinde"] = state.player.stats.get("xinde", 0) + amount
        return [f"【{ch.name}】已經是{owner}的同伴了，這份緣分化為心得。", f"心得 +{amount}"]
    problem = recruit_problem(state, content, world, char_id) if on(content) else None
    if problem is not None:  # 歷史武將同行第七節：劇情送人也照陣營、名下三位擋
        amount = content.config.recruit_consolation_xinde
        state.player.stats["xinde"] = state.player.stats.get("xinde", 0) + amount
        return [f"【{ch.name}】{problem}，這份緣分化為心得。", f"心得 +{amount}"]
    if not world.try_recruit(char_id, state.player.name, **_capped(content)):
        amount = content.config.recruit_consolation_xinde
        state.player.stats["xinde"] = state.player.stats.get("xinde", 0) + amount
        return [f"【{ch.name}】剛剛被別人招攬走了，這份緣分化為心得。", f"心得 +{amount}"]
    _seed_starting_skills(world, char_id, ch)
    return [f"【{ch.name}】加入了你的隊伍！"] + team.add_to_team(state, char_id)


# ── 新手福利與新立門戶福緣（第一季設計第十四節：從自己加入的那天起算）────────


def since_join(state: GameState, content: Content) -> float | None:
    """第一季（rules.season_one）：自己加入這一季以來過了多少季曆秒。世界裡的天數看季曆（PM 2026-10-06），所以跟著
    週末設定縮：2.5 天的季，季曆 3 天是現實約 2 小時。joined_at 還沒蓋（新角色第一次同步之前）算剛加入。
    不是第一季回 None：新手福利照舊從季初起算、用世界的天數，beta 一點都不變。"""
    w = state.world
    if not rules.season_one(content, w):
        return None
    joined = state.player.joined_at
    elapsed = 0.0 if joined is None else max(0.0, w.time - joined)
    return elapsed * calendar.cal_scale(content, w)


def newbie(state: GameState, content: Content, days: float | None = None) -> bool:
    """新手福利還在：加入以來還沒過 days 個季曆天（沒給就是 newbie_days，氣血回復加倍那一條；體力那一條給
    newbie_stamina_days）。beta 那一季沒有 joined_at，從季初照同一個季曆比例算（14 天的季，18 季曆天＝3 天）。"""
    if content.config.newbie_real_hours > 0:
        return _real_newbie(state, content)
    since = since_join(state, content)
    elapsed = state.world.time * calendar.cal_scale(content, state.world) if since is None else since
    limit = content.config.newbie_days if days is None else days
    return elapsed <= limit * rules.DAY


def raid_newbie(state: GameState, content: Content) -> bool:
    """截殺與通緝的新手期（企劃者 2026-10-10，懸賞榜設計 14.1 丁）：一律從自己加入這一季的那一刻（joined_at）算 newbie_days 個季曆天，
    不看第一季開關——規則關著的季（14 天）開季三天之後才來的人也有保護。joined_at 還沒蓋（第一次同步之前）算剛加入。
    第一季的結果跟 newbie 一樣（第一季本來就從 joined_at 算）。新手的體力、氣血福利照舊走 newbie（beta 從季初算），since_join 不動。"""
    if content.config.newbie_real_hours > 0:
        return _real_newbie(state, content)
    w = state.world
    joined = state.player.joined_at
    elapsed = 0.0 if joined is None else max(0.0, w.time - joined)
    return elapsed * calendar.cal_scale(content, w) <= content.config.newbie_days * rules.DAY


def _real_newbie(state: GameState, content: Content) -> bool:
    """新手期照現實時間（Config.newbie_real_hours，Joy 2026-10-17「新手期 48 小時」）：從自己加入這一季那一刻（joined_at）
    過了多少世界秒，除以 time_scale 換成現實秒。joined_at 還沒蓋（第一次同步之前）算剛加入。體力、氣血、丹、截殺通緝的保護都照它。"""
    joined = state.player.joined_at
    elapsed = 0.0 if joined is None else max(0.0, state.world.time - joined)
    return elapsed / content.config.time_scale <= content.config.newbie_real_hours * 3600


def fortune_due(state: GameState, content: Content) -> bool:
    """新立門戶福緣：第 fortune_day_min 天起交友必定先觸發（第 1 天是加入那一刻起的頭 24 個鐘頭；beta 是季的第幾天）。"""
    if state.player.fortune:
        return False
    since = since_join(state, content)
    day = rules.current_day(state) if since is None else int(since // rules.DAY) + 1
    return day >= content.config.fortune_day_min


def fortune_overdue(state: GameState, content: Content) -> bool:
    """第 fortune_day_max 天結束還沒發生，就直接送上門。"""
    if state.player.fortune:
        return False
    since = since_join(state, content)
    elapsed = state.world.time if since is None else since
    return elapsed >= content.config.fortune_day_max * rules.DAY


# ── 門下頁的文字 ──────────────────────────────────────────


def roster_lines(state: GameState, content: Content, world: WorldStateStore) -> list[tuple[str, str]]:
    """名冊列表：（顯示文字, key），本人在最前，其餘是這個玩家目前擁有的同伴。"""
    lines = [(f"本人　{state.player.name}　第 {state.player.member.level} 級", "player")]
    for cid in owned_companions(world, state.player.name):
        ch = content.characters[cid]
        progress = world.get_companion(cid)
        status = "出戰" if cid in state.player.team else "在門下"
        lines.append((f"{ch.name}　第 {progress.level} 級　{status}", cid))
    lines += [(f"部下・{follower.name}", key) for key, follower in team.follower_rows(state, content)]  # 計畫 T5
    return lines
