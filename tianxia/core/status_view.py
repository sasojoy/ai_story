"""狀態列（核心本體；第二輪第 81 批，計畫 docs/superpowers/plans/2026-11-07-第二輪-第81批.md，導覽 docs/guide/核心與存檔.md）。

status_data 是狀態列的資料（數字與短字串，/api/main 的 status，網頁前端照它排版），status_text 是同一份資料的文字版。原本是 Game 上的 5 個方法
（第一階 ctx 就是 Game，開發規範手冊 3.3）；Game 留 2 個一行委派（status_data、status_text），_attr_rows、_calendar_status、_when_text 外面沒人叫，不留。
模組裡互相叫直接叫函式（沒有一個被測試換掉，量過）；留在 Game 上的（stamp、_preparing、pills_left_today、xinshen_view……）一律經 ctx，測試換 Game 上的照樣打得到。

- status_data 的閉包整段不拆：鍵的先後算行為，一格一格的先後在 core/features.py 的 STATUS_ORDER["status"]。閉包的參數也叫 ctx，跟外面是同一個物件（status_run 傳的就是進來的那一個）。
- 名字的綁法照 engine：engine 拿名字的（rules 的 season_one、stances……）這裡也拿名字，engine 叫模組屬性的（team.、calendar.、art_cards.……）這裡也叫模組屬性——測試換掉的東西兩邊打得到的一樣。
- DAY、HOUR 拿 calendar 的（同值）；engine 留自己的（別的方法與測試在用）。
- stat_uses、STAT_CHECK_NOTE、practice_hint 讀共用層 art_cards（第 88 批從 skillview 切出來，同一批物件）。

engine 在 `from .core.event_check import …` 之後才 import 這一份（這裡 import 的模組那時都已經載入，載入順序不變）。

改這一份要跑的測試：scripts/test_for.py（CORE_SERVICES：這個檔的底 status、jianghu、explain、explain2、fronts，加改到的函式那一群）；
same_behavior 所有軌（/api/main 逐位元組），status_text 沒有路由，走 lantern 一軌（--track lantern）。
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from .. import attrset, calendar, forge_secrets, gender, orders, ranger, renown, roster, secret_recipes, art_cards, team, timetable
from .. import prologue as prologue_rules
from ..calendar import DAY, HOUR
from ..rules import chaos_fronts, front_ids, season_one, stance_rule_note, stance_sum_note, stances, trend_name, trend_value
from ..state import PLAYER
from ..world_state import season_length_days
from . import features as features_core
from . import presence, xinshen

if TYPE_CHECKING:
    from ..engine import Game  # noqa: F401  ctx 就是 Game（第一階）


def _attr_rows(ctx: Game, names: dict[str, str]) -> list[tuple[str, int, str]]:
    """狀態列的屬性（名字, 數值, 鍵）：舊的季照存檔的五屬性；五項屬性的季照 attrset 算（武力、統御……）。"""
    s, c = ctx.state, ctx.content
    if attrset.on(c, s.world):
        shown = attrset.names(c, s.world)
        return [(shown[k], int(attrset.value(s, c, k)), k) for k in attrset.keys(c)]
    return [(names[k], s.player.stats[k], k) for k in team.COMBAT_STATS]


def status_data(ctx: Game) -> dict:
    """狀態列的資料（數字與短字串），網頁前端照這份自己排版；status_text 是同一份資料的文字版。照 core/features.py 的 STATUS_ORDER["status"]
    一格一格合（全部拆包第 66 批：鍵的先後算行為）：包的格在各包的 status_slots，核心的格是這裡的閉包。"""
    s, c = ctx.state, ctx.content
    p, w = s.player, s.world
    names = c.config.stat_names
    now, cap = team.member_neili(c, p.member, team.con_of(s, c, ctx.world, PLAYER), season=w)
    mates = []
    for cid in p.team:
        progress = ctx.world.get_companion(cid)
        mate_now, mate_cap = team.member_neili(c, progress, team.con_of(s, c, ctx.world, cid), season=w)
        mates.append({"name": c.characters[cid].name, "level": progress.level,
                      "hp": round(mate_now), "hp_max": round(mate_cap)})

    def head(ctx, data) -> dict:
        return {
            "name": p.name,
            "affiliation": presence.affiliation(s, c),
            "ranger": ranger.status(s, c),  # 散人的遊俠名號（名號、階、俠名、下一階）；陣營的人、劇本沒有陣營、名聲開著是 None
            "renown": renown.status(s, c),  # 名聲（狀態列 1B、2C 的稱號與說明卡）；名聲關著是 None
        }

    def manual(ctx, data) -> dict:
        return {
            # 武學譜（口訣與秘方）：這一季聽過口訣或合中過的秘方，一條一筆 {"clues": [聽過的口訣], "solved": 名號或 None}
            "manual": secret_recipes.view(s, c, ctx.world),
            "manual_total": secret_recipes.progress(s, c, ctx.world)[1],  # 武學譜入口的分母：這一季全服共有幾條（不是「你聽過的」）
        }

    def forge_manual(ctx, data) -> dict:
        # 鑄譜（打造的隱藏配方）：這一季聽過口訣或打中過的，一條一筆 {"clues", "solved", "recipe"}（打造隱藏配方設計 6.3）
        return {"forge_manual": forge_secrets.view(s, c, ctx.world)}

    def self_row(ctx, data) -> dict:
        return {
            "anonymous": p.anonymous,
            "gender": gender.of(p),  # 性別：修練頁的人物面板照它換男女版（web/app.js 的 HERO_FIGURES）
            "gender_chosen": p.gender_chosen,  # 選過了沒：設定頁沒選過的舊角色給一次改的機會
            "hints_off": p.hints_off,  # 設定頁「不再提示」的勾（新手引導計畫三）
            "level": p.member.level,
            "exp": team.exp_view(c, p.member),  # 這一級攢了多少、升下一級要多少（狀態列展開那一行）；滿級是 None
            "location": c.locations[p.location].name,
            "season": p.season_number,  # 第幾季；週次每一季都從 1 起，網頁記「看過哪一季哪一週的大事」要帶它
            "day": int(w.time // DAY) + 1,
            "clock": f"{int(w.time % DAY // HOUR):02d}:{int(w.time % HOUR // 60):02d}",
            "season_days": season_length_days(w, c),  # 這一季蓋章的季長（舊季照它自己的章，不跟著設定變）
            "stamina": int(p.stamina),
            "stamina_max": c.config.stamina_max,
            # 回體丹（企劃者 2026-10-07）：有丹、而且不在草廬序章裡才給，網頁照它在體力條旁畫「服丹」鈕（體力滿了鈕是灰的）
            # 測試期間一鍵補滿（Config.beta_free_refill）打開時：沒有丹也給（鈕照樣畫），多一個鍵 refill＝鈕上的字，網頁見它就寫
            # 「補滿」不寫「丹 N」；關著時這個鍵不存在，整份跟 joy 的一個字不差
            "pills": None if (p.stamina_pills <= 0 and not c.config.beta_free_refill) or (
                prologue_rules.active(s, c) and not prologue_rules.pills_open(s, c)) else {
                "name": c.config.stamina_pill_name, "count": p.stamina_pills, "restore": c.config.stamina_pill_restore,
                "full": p.stamina >= c.config.stamina_max,
                # 今天還能服幾顆（一天的上限，台灣時間 00:00 換日，企劃者 2026-10-12）；不限（stamina_pills_per_day 0）時沒有這個鍵
                **({"today": ctx.pills_left_today()} if c.config.stamina_pills_per_day > 0 else {}),
                **({"refill": c.config.beta_free_refill_label} if c.config.beta_free_refill and not prologue_rules.active(s, c) else {}),
            },
            **({"xinshen": ctx.xinshen_view()} if xinshen.on(c) else {}),  # 心神（跟人物交談扣的）：關著時沒有這個鍵，畫面照舊
        }

    def vitals(ctx, data) -> dict:
        return {
            "hp": round(now),  # 跟角色卡（修練包 art_view.member_card 的 {:.0f}）同一種進位：兩邊寫出來的數字一樣
            "hp_max": round(cap),
            "injury": int(p.member.injury),
            "silver": p.stats.get("silver", 0),
            "xinde": p.stats.get("xinde", 0),
            "minor": [(names[k], p.stats.get(k, 0)) for k in ("fame", "good", "evil")],
            "attrs": _attr_rows(ctx, names),  # 第三項是鍵：配點鈕送它（allocate_stat）
            "stat_points": p.stat_points,
            "stat_cap": c.config.stat_cap if not attrset.on(c, s.world) else 10**9,  # 五項屬性的季沒有上限
            **({"growth": attrset.view(s, c)} if attrset.on(c, s.world) else {}),  # 挑成長配比的那一塊（屬性與跨季架構 v2 3.1）
            # 歷練：這一季從事件得來的屬性有多少、上限多少（展開的屬性底下那一條，企劃者 2026-11-05）
            **({"lilian": {"have": attrset.event_total(s), "cap": c.config.attributes.v2.event_cap}} if attrset.on(c, s.world) else {}),
            # ＋鈕底下那一行：五項各管什麼、事件檢定也看它們（計畫二最終審查 M2）；網頁只在有點可配時畫
            "stat_uses": art_cards.stat_uses(c, s),  # 減法季屬性五段開著時寫「現在給你什麼」的數字（設計 4.5）
            "stat_uses_note": art_cards.STAT_CHECK_NOTE,
            # 心得付得起、又真的有事可做時才有；籌備中練成、合成都被擋，不提示（explain-2 審查 Minor 1）
            "hint": None if ctx._preparing() else art_cards.practice_hint(s, c),
            "team": mates,
            "busy_hours": None if p.busy_until is None else round((p.busy_until - w.time) / HOUR / c.config.time_scale, 1),  # 現實小時
        }

    def help_row(ctx, data) -> dict:
        # 點體力條看的說明（explain-1）：怎麼回、新手期、回體丹（一天的上限）或補滿，數字全讀設定；體力條上沒有那顆鈕（序章、沒丹）就不提它
        newbie = roster.newbie(s, c, c.config.newbie_stamina_days)
        return {
            "stamina_help": ctx._stamina_help(newbie, data["pills"] is not None),
            # 江湖頁行動列底下的「玩法說明」入口（explain-2）：新手期（跟體力回復加快同一段，newbie_stamina_days）才有、序章裡沒有（師父會說）；
            # 過了新手期只剩設定抽屜那一顆
            "howto_entry": newbie and not prologue_rules.active(s, c),
        }

    def war(ctx, data) -> dict:
        if not season_one(c, w):  # 第一季濃縮版：江湖頁的三條戰況與三方態勢；開關關著時沒有這兩個鍵，畫面照舊
            return {}
        # FB-065：圖卡畫亂局帶（兩端讀設定，跟 in_chaos 同一份、含兩端）、標出在亂局裡的戰線；態勢那一行的說明也由這裡給，
        # 前端不寫死 35／65，也不自己數條數。全服公開的戰況，誰看都一樣
        in_the_chaos = set(chaos_fronts(s, c))
        return {
            "fronts": [
                {"id": tid, "name": trend_name(c, tid), "value": trend_value(s, c, tid), "chaos": tid in in_the_chaos}
                for tid in front_ids(c)
            ],
            "chaos_band": {"low": c.config.chaos_low, "high": c.config.chaos_high},
            "stances": stances(s, c),
            "stance_notes": {"sum": stance_sum_note(c)},
            "stance_rule": stance_rule_note(s, c),  # 態勢卡底下的收季規則（正式版辛）
            # 點戰況圖卡、態勢、大事、主線看的說明（explain-2）：這一季在打什麼、亂局、大事怎麼定、你能怎麼出力。
            # 門檻讀設定、此刻在亂局的讀 chaos_fronts、大事的件數讀時刻表（howto.war_help）；網頁點開才畫，不推動第一屏
            "war_help": ctx._war_help(),
        }

    core = {"head": head, "manual": manual, "forge_manual": forge_manual, "self": self_row, "vitals": vitals,
            "calendar": lambda ctx, data: _calendar_status(ctx),  # 第一季：季曆與下一件大事的倒數；開關關著時沒有這兩欄
            "help": help_row, "war": war}
    return features_core.status_run("status", core, {}, ctx)


def _calendar_status(ctx: Game) -> dict:
    """狀態列的季曆（第 N 週、週幾、幾點）與下一件大事：季曆時刻 at，加上倒數 in_seconds。倒數是現實秒：(大事時刻 − 世界秒) ÷ time_scale。"""
    w, c = ctx.state.world, ctx.content
    if not calendar.season_one_on(w, c):
        return {}
    at = calendar.point(w.time, c, w)
    # 休季時沒有下一件（計畫 T9）；籌備中時鐘沒走，也不倒數（FB-049）
    upcoming = None if w.ended or ctx._preparing() else timetable.next_event(ctx.state, c)
    cal = {
        "week": at.week, "weekday": at.weekday, "clock": f"{at.hour:02d}:{at.minute:02d}",
        # 畫面第二行直接用這一句，不自己拼（7 天濃縮季寫「第 N 天 HH:MM」）
        "weeks": calendar.weeks(c, w), "text": calendar.point_text(at, by_day=calendar.week7_on(w, c)),
    }
    if orders.daily(ctx.state, c):  # 21 天季的軍令每天一道：軍令卡收起來照季曆第幾天記（網頁 orderKey），隔天重新展開
        cal["day"] = at.cal_day
    # 7 天濃縮季：畫面上寫「週」的地方換成段（網頁 calWords，FB-501）；21 天季只有軍令的字（FB-502）；週末、14 天沒有這個鍵
    words = calendar.week_words(c, w)
    if words is not None:
        cal["words"] = words
    return {
        "calendar": cal,
        "next_event": None if upcoming is None else {
            "title": upcoming.title,
            "at": ctx.stamp(timetable.when(ctx.state, c, upcoming)),  # 季曆時刻「第 9 週・週四 20:44」，畫面寫在倒數前面（FB-062）
            "in_seconds": round((timetable.when(ctx.state, c, upcoming) - w.time) / c.config.time_scale),
        },
    }


def _when_text(d: dict) -> str:
    cal = d.get("calendar")
    if cal is None:
        return f"第 {d['day']} 天 {d['clock']}（本季共 {d['season_days']:g} 天）"
    return cal["text"]


def status_text(ctx: Game) -> str:
    d = status_data(ctx)
    names = ctx.content.config.stat_names
    # 排版刻意很緊：這一塊在手機上原本是 13 段 Markdown（每段一個 <p>），光狀態就吃掉
    # 半個螢幕，選項按鈕被推到摺線以下。現在把**玩家真的一直在看的四個數字**（體力、
    # 氣血、銀兩、心得）收成一行，其餘降級到第二行，隊伍只有帶人時才列出來。
    vitals = (
        f"⚡ 體力 {d['stamina']}/{d['stamina_max']}　"
        f"❤ 氣血 {d['hp']}/{d['hp_max']}　"
        f"💰 {names['silver']} {d['silver']}　"
        f"📘 {names['xinde']} {d['xinde']}"
    )
    if d["injury"] >= 1:
        vitals += f"　🩹 內傷 {d['injury']}"
    minor = "　".join(f"{k} {v}" for k, v in d["minor"])
    attrs = "　".join(f"{k} {v}" for k, v, _ in d["attrs"])
    lines = [
        f"### {d['name']}　·　{d['affiliation']}" + ("（匿名行走）" if d["anonymous"] else "")
        + f"　第{d['level']}級",
        f"📍 {d['location']}　⏳ {_when_text(d)}",
        vitals,
        f"{minor}　｜　{attrs}",
    ]
    if d["hint"] is not None:
        lines.append(d["hint"])
    for mate in d["team"]:  # 只有真的帶了同伴才列隊伍，一個人時不佔版面
        lines.append(f"🧍 {mate['name']}　第{mate['level']}級　氣血 {mate['hp']}/{mate['hp_max']}")
    if d["busy_hours"] is not None:
        lines.append(f"🧘 閉關中，現實約 {d['busy_hours']:.1f} 小時後出關")
    if d["journey"] is not None:
        lines.append(f"🧭 在路上：{d['journey']}")
    return "\n\n".join(lines)
