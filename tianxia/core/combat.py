"""單打服務（核心本體；第二輪第 79 批，計畫 docs/superpowers/plans/2026-11-07-第二輪-第79批.md，導覽 docs/guide/戰鬥.md）：
打一場的每一包都用的那幾段。原本是 Game 上的 40 個方法，本體照抄、self 換成 ctx（第一階 ctx 就是 Game，開發規範手冊 3.3），函式名拿掉開頭的底線
（is_big、fight_request 照舊），Game 留 36 個一行委派（第 98 批收進 squad_encounter 多一個；server、假人、事件檢定、各包、測試與 Game 原位在叫；只有這裡叫的 exp_changes、trait_say、
trait_lines、thin_drops、battle_mount 不留）。_narrate、_spar_power、_spar_mirror 在 Game 上照舊是 staticmethod（懸賞、玉璽的測試用 staticmethod 換 _spar_power）。

- 大場面：is_big、fight_squad、fight_request（A 段，鎖內只讀）、checked_fight（C 段重驗）、fight_gone、judged、fight_with、style_note、terrain_note、narrate
- 戰力快照：battle_power、battle_scores、battle_role、battle_mount、battle_troops、battle_gear、battle_marks、battle_road、battle_neili_cap
- 操練的帳與立功：drill_gains、exp_changes、famed_news、deed_fame、record_exp
- 收場：lose_silver、player_hp_and_cap、player_hp、hp_facts、take_toll、play_rounds、trait_say、trait_lines、story_squad、tier3、battle_rewards、thin_drops、seize、file_battle
- 本人對本人：spar_power、spar_mirror
- 打一場的主流程：squad_encounter（第二輪第 98 批）
- 模組層的名字：TollFacts、LOW_HP_RATIO、FIGHT_LEFT、FIGHT_CHANGED、FIGHT_GONE_LINES（engine 照名字 import 回 FIGHT_GONE_LINES、LOW_HP_RATIO）

哪些經 ctx（手冊第十五節「換掉的才打得到」；tests/core/boundary_tables.py 的 COMBAT_VIA_CTX 守）：
- 被測試、腳本換掉的 8 個 Game 方法（judged、lose_silver、battle_rewards、seize、battle_power、battle_scores、spar_power、fight_request），模組裡互叫碰到它們的都寫 ctx._x：
  battle_scores → ctx._battle_power、checked_fight → ctx.fight_request、squad_encounter → ctx._judged、ctx._lose_silver、ctx._battle_rewards、ctx._seize。
  其餘 2 個（battle_scores、spar_power）模組裡沒有人互叫，都經包的 ctx._x，打得到。模組裡其他互叫直接叫函式（不多跳一層）。
- 包的委派（CORE_DELEGATE_CALLERS）：battle_marks → _escort_carry、_seal_bare；battle_gear → _duel_cut；seize → _seize_chance；
  squad_encounter → _drill、_sortie_rewards、train_trend_push、duel_on、_order_credit、_fs_after_win、_opp_on_win。
- 留在 Game 上的：state、content、world、rng、client、options、_draft、_fight、_last_wear、_loot_scale、_gate_scale、_drop_scale、_drills_with；
  別的核心檔經 ctx：push_trend、_push_progress（pushing）、publish（事件）。
  judged、file_battle 會寫 ctx._fight、ctx._last_wear：那是 Game 的欄位，不是這裡的模組變數。

squad_encounter（打一場的主流程，第二輪第 98 批從 Game 收進來，Game 留 _squad_encounter 一行委派）逐行照抄，擲骰與呼叫的先後一行都沒動，只換兩個名字：
sortie.on → territory.on（features/sortie/rules.py 的 on 整個函式就是 return territory.on(content)，tests、tianxia、scripts 沒有人換掉這兩個，是同一件事）；
sortie.PROLOGUE_FIGHT → PROLOGUE_FIGHT（字搬進 core/services.py，出陣包留的名字是同一個物件；engine 留的那個第 99 批拿掉）。事件 win 的發布點跟著搬，位置不動。

名字的綁法照搬之前的 engine：engine 拿名字的（add_rumor、front_of、game_day、season_one、PLAYER、drill_share）這裡也拿名字，engine 叫模組屬性的（team、encounter、materials、
treasures……）這裡也叫模組屬性——測試換掉的東西兩邊打得到的一樣。各有自己一份亂數的（lose_silver、tier3、thin_drops、play_rounds）種子字串一個字不動，
不碰 Game.rng；battle_rewards、fight_with 的 ctx.rng 是 Game 上那一顆。engine 在 `from .core import event_check` 之後才 import 這一份
（這裡 import 的模組那時都已經載入，載入順序不變）。同 event_check 不進 MODULES、不進 FEATURES；這裡不 import 包。

改這一份要跑的測試：
- scripts/test_for.py：這個檔在 CORE_SERVICES。hunk 落在函式、類別、常數上 → 名字的功能群＋這個檔的底（檔名有 battle、encounter、fight、rounds、tactics、team、engine 的，
  量到 36 個檔）＋邊界測試；函式以外（import、這段說明、模組層）或指名了卻沒有差 → 核心測試＋煙霧。互叫經 ctx 的（battle_scores → ctx._battle_power、checked_fight →
  ctx.fight_request）不會往上算（_core_refs 只看 ast.Name），那兩個都有底蓋著。
- 寫到這些名字、可是檔名不在底裡的只拿它當準備動作，留給閘門（why 寫幾個檔），要當場驗直接給檔名（寫到 _squad_encounter 的 test_fronts、test_characters、test_contract_core、test_journal、test_front_lines、test_push、test_opportunities_two 也是）。tests/season、tests/core/test_engine.py 的 slow 留閘門（要看加 --slow）。
- same_behavior：compare --tracks aftermath（這一批開的一軌：等判讀時選項沒了、經驗換心得、落敗保銀兩、掉落打折、寶物多掉、戰力快照），其餘經 events、sortie、train、story、
  roam、strip、tavern、battle、muster、progress、ring、bout、crossblade、figact、stamina。走不到的 4 行（fight_request 的序章雪恥、沒滿級卻換心得、三階發素材失敗）寫在那一軌的說明。
  squad_encounter 的序章標題那一行經 redress 一軌（第 98 批開的；其餘經 aftermath、train、roam、strip）。
- 反方向（第 36 批認定第 1 條）：這裡 import 的 24 個模組（第 98 批多 atlas、territory）都是核心或共用層，test_for.pick 在搬之前、之後挑的一樣，沒有少挑到的，不必另外跑。
"""
from __future__ import annotations

import random
from dataclasses import dataclass
from typing import TYPE_CHECKING

from . import battle_base as battle_instance
from . import features as features_core
from .services import PROLOGUE_FIGHT, drill_share
from .. import (
    armor, atlas, attrset, battlelog, conquest, encounter, fight_llm, gender, materials, mounts, ranger, renown, rise, roster, rounds, styles, tactics,
    team, terrain, territory, traits, treasures, weapons,
)
from .. import prologue as prologue_rules
from ..models import Squad
from ..rules import add_rumor, front_of, game_day, season_one
from ..state import PLAYER

if TYPE_CHECKING:
    from ..engine import Game  # noqa: F401  ctx 就是 Game（第一階）


@dataclass(frozen=True)
class TollFacts:
    """寫功效演出句要知道的氣血的事（_take_toll 與劇情戰量好、_play_rounds 讀；武學與成長設計 13.6：只在功效真的改到結果時才演）。"""

    wounded: bool = False  # 開打前氣血就低於上限（厚才有用：它把氣血係數的下限拉高，滿血時沒有東西可拉；內傷讓「滿血」的上蓋低於上限，也算）
    low_hp: bool = False  # 開打前氣血低到「見底」（剩 LOW_HP_RATIO 以下，含）：厚那句「氣血見底」才挑得到
    healed: tuple[str, ...] = ()  # 真的回了血（有一行「氣血 +N」）的功效掛點：win_heal（吸取）、heal_after（回春）；劇情戰不回血
    # 下面三個是功效演出句後面括號裡的數字（FB-084）：跟戰報上的「氣血 -N」「氣血 +N」「內傷 +N」是同一批算的
    saved: int = 0  # 化勁這一場少扣的氣血（team.toll_saved）
    spared: int = 0  # 不動這一場免掉的內傷（team.toll_saved）
    gained: tuple[tuple[str, int], ...] = ()  # 回血的功效掛點 → 回了多少氣血（「氣血 +N」那一行的 N），順序同 healed


LOW_HP_RATIO = 0.3  # 開打前氣血剩上限的三成以下（含）算「氣血見底」：厚的那一句「氣血見底，……硬撐」（battlelog.LOW_HP_MARKS）才挑得到

# 等模型判讀的時候選項沒了（另一個分頁把人帶走、事件被了結、體力花光）：這一仗不打，回這一句話代替一句看不出所以然的「無法這麼做」
FIGHT_LEFT = "你離開了，這一仗沒打成。"
FIGHT_CHANGED = "情勢變了，這一仗沒打成。"
FIGHT_GONE_LINES = (FIGHT_LEFT, FIGHT_CHANGED)


# ── 大場面：鎖外請模型判讀（武學與成長設計 8.3、計畫三 Task 2） ──

def is_big(ctx, squad: Squad) -> bool:
    """大場面：對手標了頭目、是大勢人物本人（figures 的 squad），或難度到 big_fight_difficulty（武學與成長設計 8.3）。
    只看對手本身：遊歷遇上自己陣營的隊伍是操練、不打架，那是遊歷那一條路自己擋（出陣包 train_actions.train_squad、train_option）；
    劇情戰從來不操練（_event_battle 不看陣營），黃巾的人打黃巾的頭目照樣是大場面（Task 2 審查修正 1）。"""
    return styles.is_big(ctx.content, squad)


def fight_squad(ctx, option_id: str) -> Squad | None:
    """這個選項按下去會打哪一路（遊歷、挑戰大勢人物本人、劇情戰的戰鬥選項）；不會打仗是 None。
    隨口應對（choice:free）不是數字，不是仗。"""
    s, c = ctx.state, ctx.content
    kind, _, arg = option_id.partition(":")
    # act 子動詞的主人說這一下打哪一路（Verb.squad，全部拆包第 17 批多開的一格）：出陣包——遊歷、出陣那一格（約戰開著不打仗、遇上自己人
    # 是操練，不打架）；大勢人物包——挑戰本人（Verb.tail_squad，第 57 批：難度照他此刻的聲威與江湖水漲）；不打仗、沒有主人照舊往下
    owned = features_core.act_squad(ctx, arg) if kind == "act" else None
    if owned is not None:
        return owned
    if kind == "choice" and arg.isdecimal() and s.pending_event:
        choices = c.events[s.pending_event].choices
        combat = choices[int(arg)].combat if int(arg) < len(choices) else None
        return story_squad(ctx, c.squads[combat]) if combat else None
    return None


def fight_request(ctx, option_id: str) -> fight_llm.FightRequest | None:
    """大場面的 A 段（server.prepare_fight 在行動鎖內、很快地呼叫）：這個選項按下去會打一場大場面，就回傳送模型判讀的單子；
    不會（不是大場面、按不下去、自己陣營的操練、這個角色不叫模型——伺服器假人的 client 是 None）就是 None，伺服器在
    同一次拿鎖裡直接做完（計畫三 G14）。C 段進鎖重驗也呼叫它（_checked_fight），要一模一樣才採用。
    只讀、不改狀態，也不推進戰鬥（理由同 dialogue_request）。先看是不是大場面、再排選單：一般的仗不多排一次選單。"""
    if ctx.client is None:
        return None
    squad = fight_squad(ctx, option_id)
    if squad is None or not is_big(ctx, squad):
        return None
    if prologue_rules.fight_tier(ctx.state, ctx.content) is not None:
        return None  # 序章雪恥那一場勝負是寫好的：不叫模型判讀、不排佇列（斷眉難度再高、標了頭目也一樣）
    option = {o.id: o for o in ctx.options(odds=False, tick=False)}.get(option_id)
    if option is None or not option.enabled:
        return None
    s = ctx.state
    theirs = f"{squad.name}（屬{squad.attribute or '不明'}，難度 {squad.difficulty:.0f}"
    theirs += styles.fight_line(ctx.content, styles.style_of(s, ctx.content, ctx.world, squad)) + "）"  # 一門打不遍
    return fight_llm.FightRequest(
        option_id=option_id, squad_id=squad.id, location=s.player.location, battle_seq=s.battle_seq,
        event=s.pending_event,
        # 本人那一行名號後面寫性別（女的寫「（女子）」，模型寫過程時稱呼跟著換；PM 2026-10-12），同伴照舊
        ours=[fight_llm.member_line(name + ("（女子）" if i == 0 and gender.female(s) else ""), arts)
              for i, (name, *arts) in enumerate(team.lineup(s, ctx.content, ctx.world))],
        theirs=theirs + (f"：{squad.desc}" if squad.desc else ""),  # 有來歷的對手多一句描述（設計 8.3「對手的描述」）
    )


def checked_fight(ctx, option_id: str, fight: fight_llm.PreparedFight | None) -> fight_llm.PreparedFight | None:
    """大場面 C 段的重驗（鎖內）：現在重算一張單子（fight_request），要跟鎖外判讀的那一張一模一樣才採用——同一個選項、
    同一路對手、同一個地點與事件、戰報流水號沒動（等模型的時候沒有打過別的仗）、雙方陣容一字不差（換了武學、帶的人，
    或對手的聲威被別人推動了，都算變了；Review Focus 3）。對不上就丟掉、照平常打（優勢 0）。"""
    if fight is None:
        return None
    return fight if ctx.fight_request(option_id) == fight.request else None


def fight_gone(ctx, fight: fight_llm.PreparedFight) -> str:
    """大場面 C 段：選項已經不在了。人不在備料時的地點了、或已經在路上就說「你離開了」；其他（事件被了結、體力花光……）
    認不出是哪一種變動，說得中性一點。備料（fight_request）一定是選項還按得下去才開單、而路上不開單，所以這裡只可能是等判讀的
    時候變的；步行、趕路出發之後 location 要到抵達才換（Journey 在路上時還是出發地），所以也要看 journey。"""
    player = ctx.state.player
    return FIGHT_LEFT if player.journey is not None or player.location != fight.request.location else FIGHT_CHANGED


def judged(ctx, squad: Squad) -> fight_llm.Judgment | None:
    """這一場有沒有鎖外判讀好的優勢：有、而且是同一路對手，就拿出來用掉——一次行動只用一次，同一次行動再打一場
    同一路也不會再吃一次（計畫三 G8）。"""
    fight = ctx._fight
    if fight is None or fight.request.squad_id != squad.id:
        return None
    ctx._fight = None
    return fight.judgment


def fight_with(ctx, squad: Squad, judged: fight_llm.Judgment | None, **kw) -> encounter.EncounterResult:
    """打一場單次判定（kw 照傳給 team.fight，挑戰本人的 difficulty）：有判讀就把優勢換成判定差距的平移
    （encounter.advantage_shift，照這一場真的用的難度、沒有功效的運氣範圍算；本人的功效改了運氣範圍時，單次判定裡會把它
    等比例縮放，推的百分點不變）；沒有是 0。優勢在這裡再夾一次 ±big_fight_swing 個百分點：
    fight_llm.judge 夾過了，但判讀不一定都經過它（之後的模型佇列也會交判讀進來），模型不能直接決定勝負（Task 2 審查修正 4）。"""
    shift = 0.0
    if judged is not None:
        swing = ctx.content.config.big_fight_swing
        shift = encounter.advantage_shift(squad.difficulty, max(-swing, min(swing, judged.advantage)))
    return team.fight(ctx.state, ctx.content, ctx.world, squad.id, ctx.rng, shift=shift, **kw)


def style_note(ctx, squad: Squad, result: encounter.EncounterResult) -> list[str]:
    """大場面對手的路數（styles，一門打不遍）在戰報裡含蓄的一句：打贏、用的剛好是他怕的那一路；或沒打贏、用的是他拿手對付的
    那一路。其他時候（不是大場面、第一季沒開、不相干的一路）什麼都不說。"""
    style = styles.style_of(ctx.state, ctx.content, ctx.world, squad)
    return styles.note(ctx.content, style, team.worn_attribute(ctx.state, ctx.content, ctx.world), result.tier)


def terrain_note(ctx) -> list[str]:
    """地利（武學隨地理環境）在戰報裡含蓄的一句：本人身上那兩門跟此地最濃的意境同一路或被它剋，或只有出戰同伴對上
    （terrain.note）；打贏打輸都寫，不寫倍數。開關關著、在路上、這裡沒有最濃的意境什麼都不說。"""
    strong = terrain.here(ctx.state, ctx.content)
    if strong is None:
        return []
    mine, mates = team.terrain_attributes(ctx.state, ctx.content, ctx.world)
    return terrain.note(ctx.content, strong, mine, mates)


def narrate(record, result: encounter.EncounterResult, judged: fight_llm.Judgment | None) -> None:
    """大場面的過程照結果挑一版：大勝、險勝是佔上風那一版，僵持、落敗是落下風那一版（計畫三 G15）。"""
    if judged is not None:
        record.narration = judged.winning if result.tier in team.WIN_TIERS else judged.losing


# ── 戰力快照：加入戰局那一刻存進 BattleParticipant 的 ──

def battle_power(ctx, *, seal: bool = True) -> float:
    """玩家自己目前的武學威力快照，加入戰鬥時存一份進 BattleParticipant.power，
    之後戰鬥結算的威力抵銷只讀這份快照，不會、也不能臨時去查任何人的角色資料
    （見 battle_instance.py::BattleParticipant 的欄位註解）。快照吃本人的加成（臂力、根骨，武學與成長設計 8.4）。
    同伴不進決戰（人物資質設計 14.5），這裡照舊只算本人。seal=False 不含玉璽碎片的戰力（奪璽單挑、江湖水漲；team.player_boost）。"""
    arts = team.team_arts(ctx.state, ctx.content, ctx.world)
    return encounter.member_power(
        ctx.state.player.member, arts, boost=team.player_boost(ctx.state, ctx.content, ctx.world, seal=seal),
    )


def battle_scores(ctx, mounted: bool = True, *, seal: bool = True) -> dict[str, float]:
    """加入戰局時的每招份量快照（戰鬥系統 3.4）：實力看武學威力（_battle_power），適性看身上武學與內功的屬性；
    騎著馬時強攻、奇襲再乘（1＋騎兵）（裝備四欄 5.9，_battle_mount），帶著部下再乘（1＋部下）（_battle_troops）。
    mounted=False 不算馬也不算部下：單人頭目戰用同一份份量，騎兵與部下只在全服決戰（設計 2.1；PM 2026-10-12）。只有加入戰局的那個玩家自己的 Game 能算（排程的 Game.for_world 玩家是空白的，
    不能在 world_tick 裡呼叫）。seal 見 _battle_power。"""
    p = ctx.state.player
    outer = team.player_art(ctx.state, ctx.content, ctx.world, p.member.wugong_id)
    inner = team.player_art(ctx.state, ctx.content, ctx.world, p.member.neigong_id)
    return battle_instance.move_scores(
        ctx.content.config.battle, ctx._battle_power(seal=seal),
        outer.attribute if outer else None, inner.attribute if inner else None, role=battle_role(ctx),
        cavalry=battle_mount(ctx)[1] if mounted else 0.0, troops=battle_troops(ctx)[1] if mounted else 0.0,
    )


def battle_role(ctx) -> str:
    """進場的職位（試玩回饋 2026-10-08）：本人最突出的屬性（battle_instance.role_for）。真人、散人臨時投效、假人都走這裡。"""
    if attrset.on(ctx.content, ctx.state.world):  # 五項屬性的季：照新的五項比（舊的四項有上限曲線，上限不同會偏向悟性）
        stats = {old: attrset.value(ctx.state, ctx.content, new) for old, new in ctx.content.config.attributes.v2.legacy.items()}
        return battle_instance.role_for(stats, team.COMBAT_STATS)
    stats = team.member_stats(ctx.state, ctx.content, ctx.world, team.PLAYER)
    return battle_instance.role_for(stats, team.COMBAT_STATS)


def battle_mount(ctx) -> tuple[str, float]:
    """加入決戰那一刻騎的馬（裝備四欄 5.9）：（馬名, 騎兵加成）；沒騎馬、坐騎關著是 ("", 0.0)。跟份量一起快照進
    BattleParticipant（mount、cavalry），之後換馬、馬餓了都不影響這一場。只在玩家自己的路徑呼叫（同 _battle_scores）。"""
    item = mounts.riding(ctx.state, ctx.content)
    bonus = mounts.cavalry(ctx.state, ctx.content)
    return (mounts.name_of(item), bonus) if item is not None and bonus > 0 else ("", 0.0)


def battle_troops(ctx) -> tuple[str, float]:
    """加入決戰那一刻帶的部下（PM 2026-10-12）：（「兩名持矛鄉勇」, 每名 Config.follower.battle_per 加起來）；沒有部下
    （第一季關著、還沒晉升）是 ("", 0.0)。跟份量一起快照進 BattleParticipant（troops、troop_bonus）。"""
    rows = team.follower_rows(ctx.state, ctx.content)
    if not rows:
        return "", 0.0
    return team.troop_names([f for _, f in rows]), len(rows) * ctx.content.config.follower.battle_per


def battle_gear(ctx) -> dict:
    """快照進 BattleParticipant 的坐騎、部下與防具減損（join_faction／auto_assign_latecomer 的 mount、cavalry、troops、troop_bonus、cut）。
    cut 是奪璽單挑吃防具用的（鐵匠鋪與合成流程 3.9，照坐騎的先例在加入決戰那一刻抄）；決戰本身不吃。"""
    horse, cavalry = battle_mount(ctx)
    troops, bonus = battle_troops(ctx)
    return {"mount": horse, "cavalry": cavalry, "troops": troops, "troop_bonus": bonus, "cut": ctx._duel_cut()}


def battle_marks(ctx) -> dict:
    """快照進 BattleParticipant 的「這一季叛投過」與「新手期」（玉璽碎片設計 4.6：挑挑戰者只讀快照），
    與稱號（名聲 2.5、4.5：本場戰功、論功那一句寫；名望名動一方起、善惡第 1 段起，開關關著是空的）。"""
    marks = {"turncoat": ctx.state.player.defected, "newbie": roster.newbie(ctx.state, ctx.content),
             "kit": team.self_side(ctx.state, ctx.content, ctx.world, mounted=True, troops=True),  # 本命戰法（第二批）
             "renown": renown.titles(ctx.state, ctx.content, fame_from=2),
             "escort": ctx._escort_carry()}  # 隨你上陣的歷史武將（歷史武將同行第五節）
    bare = ctx._seal_bare()
    if bare is not None:  # 玉璽碎片改版：只有戴著碎片才多這一鍵（沒碎片、改版關著時這一包一個字不變）
        marks["seal_bare"] = bare
    card = team.pvp_card(ctx.state, ctx.content, ctx.world)
    if card is not None:  # 五項屬性的季才多這一鍵（奪璽單挑照對手重算）；舊的季一個字不變
        marks["card"] = card
    return marks


def battle_road(ctx) -> str:
    """加入戰局時快照的武學屬性（決戰的隊伍多樣性，一門打不遍）：只有第一季開著時才記，關著時是空的、不算一路。"""
    if not season_one(ctx.content, ctx.state.world):
        return ""
    return team.worn_attribute(ctx.state, ctx.content, ctx.world) or ""


def battle_neili_cap(ctx) -> float:
    """決戰的氣血池上限：決戰的池子不吃螭首（玉璽碎片設計 7.1：決戰一個字都不改）。"""
    _, cap = team.member_neili(
        ctx.content, ctx.state.player.member, team.con_of(ctx.state, ctx.content, ctx.world, PLAYER), plain=True,
        season=ctx.state.world,
    )
    return cap


# ── 操練的帳與立功 ──

def drill_gains(ctx, squad: Squad, share: float | None = None, source: str = "hold", echo: bool = True) -> list[str]:
    """跟這一路一起操練拿的：對手心得與經驗的 share（預設 drill_reward_share；不給銀兩、素材）；經驗本人與帶著的同伴都拿（FB-002）。
    操練（_drill）與出陣的守（_sortie_hold）、守勢行動（_duty）共用；一類一顆開著時守、守勢行動給全額（_hold_share）。
    source（growth.exp_source）：這幾樣都不打仗（hold，PM 2026-10-25 第 5 件）；減法季自家營寨跟同袍比劃算仗（camp_spar）。
    echo：「心得 +N」那一行要不要也放進回傳的訊息。江湖紀錄的標籤本來就由草稿（_draft.changes）記一顆、訊息那一行在敘事裡收掉；
    出門一趟的比劃（_outing_fight）自己有「得：」那一行，兩邊都有就被 explore_actions.outing_ledger 加成兩倍、後面還多一則單獨的訊息
    （FB-830），所以它傳 False：只由草稿記。沒有草稿時（直接叫的）照樣放進訊息，帳才不會漏掉這一筆。"""
    s, c = ctx.state, ctx.content
    p = s.player
    share = c.config.drill_reward_share if share is None else share
    xinde, exp = drill_share(squad.reward_xinde, share), drill_share(squad.exp, share)
    msgs: list[str] = []
    if xinde:
        p.stats["xinde"] = p.stats.get("xinde", 0) + xinde
        xinde_line = f"心得 +{xinde}"
        if echo or ctx._draft is None:
            msgs.append(xinde_line)
        if ctx._draft is not None:
            if echo:
                ctx._draft.hide(xinde_line)
            ctx._draft.changes.append(xinde_line)
    keep = team.player_exp(s, c, exp, source)[0]  # 減法季三道閘：不是仗的 45 級以後換心得
    gained = team.maxed_xinde(s, c, exp, source)  # 滿級：本人的經驗照 5 換 1 換成心得（3.5），同伴照拿經驗
    if gained:
        msgs.append(team.xinde_line(c, p.member, gained))
    msgs += team.add_team_exp(s, c, ctx.world, exp, source)
    if ctx._draft is not None and exp > 0:
        ctx._draft.changes += exp_changes(ctx, exp, keep, gained)
    return msgs


def exp_changes(ctx, exp: int, keep: int, gained: int) -> list[str]:
    """操練這一類（不畫戰報的）經驗寫進江湖紀錄得失的那幾筆：滿級寫「心得 +N」、照常寫「經驗 +N（每人）」（同以前）；
    減法季 45 級的閘換了一截心得時，寫換到的心得與本人真的加的經驗（同伴照拿全額，不寫「每人」）。"""
    if team.maxed(ctx.content, ctx.state.player.member):
        return [f"心得 +{gained}"]
    if keep == exp:
        return [f"經驗 +{exp}（每人）"]
    return ([f"心得 +{gained}"] if gained else []) + ([f"經驗 +{keep}"] if keep else [])


def famed_news(ctx, place: str, foe: str, tier: str) -> None:
    """名聲 4.5：天下聞名的人打完大場面（大勢人物本人、劇情裡的頭目、難度 100 以上；單人頭目戰不算），不論勝負，天下大事點名一句；
    一個遊戲日最多 famed_news_per_day 則（不能讓一個人一直打就洗掉別人的消息）。"""
    s, c = ctx.state, ctx.content
    if renown.famed_news_due(s, c, game_day(c, s.world)):
        add_rumor(s, renown.NEWS_BIG.format(name=s.player.name, place=place, foe=foe, tier=tier), content=c, layer="world")


def deed_fame(ctx, kind: str) -> list[str]:
    """立功給名望（名聲設計 3.1）：RenownTuning.deeds 的那一項；deed_fame 關著、寫 0 的不給；序章不給。"""
    c = ctx.content
    n = c.config.renown.deeds.get(kind, 0) if renown.on(c, "deed_fame") else 0
    if n <= 0 or prologue_rules.active(ctx.state, c):
        return []
    return renown.gain(ctx.state, c, "fame", n)


def record_exp(ctx, record, exp: int, source: str = "battle") -> list[str]:
    """這一場本人的經驗寫進戰報（record.exp）：已經滿級時照 5 換 1 換成心得（team.maxed_xinde，3.5），戰報的得失寫心得、
    不寫經驗，回江湖紀錄那一句；沒滿級照舊寫經驗、回空的。經驗本身照舊交給 grant_team_exp／add_exp（滿級的本人不加，同伴照拿）。
    source（growth.exp_source）：減法季三道閘開著時不是仗的經驗過了 45 級那一截也換心得（戰報寫真的加的經驗，回 CAPPED_XINDE 那一句）；
    仗的經驗照舊。"""
    gained = team.maxed_xinde(ctx.state, ctx.content, exp, source)
    if not team.maxed(ctx.content, ctx.state.player.member):
        record.exp = team.player_exp(ctx.state, ctx.content, exp, source)[0]
        if not gained:
            return []
        record.xinde = (record.xinde or 0) + gained
        return [team.CAPPED_XINDE.format(n=gained), f"心得 +{gained}"]
    record.exp = 0
    record.xinde = (record.xinde or 0) + gained
    # 那一句之外另回「心得 +N」：江湖紀錄那一則的心得跟戰報得失對得上，「剛剛」卡片底下不多一顆「心得 -N」（FB-451）
    return [team.MAXED_XINDE.format(n=gained), f"心得 +{gained}"] if gained else []


# ── 收場：落敗失銀、氣血、回合演出、獎勵、頓悟的契機、歸檔 ──

def lose_silver(ctx, record) -> list[str]:
    """落敗失落一成銀兩（遊歷、探索野怪、挑戰本人共用），記在戰報上。騎著馬有機會策馬脫身、保住這一成（裝備四欄 5.11）：
    只保銀兩，氣血、內傷、戰報結果照舊是落敗；擲骰用自己的亂數（「脫身|季數|名號|戰報流水號」：戰報流水號每季從頭算，少了季數
    每一季第 N 場的結果都一樣），不動 Game.rng，整季測試與量表的基準不位移。沒有銀兩可丟（一成是 0）就不擲。
    帶著金角（玉璽碎片改版，treasures.amount 的 keep_silver）落敗不失銀兩，寫一句 treasures.KEEP_SILVER（截殺、設伏、混戰、
    買兇的殺手各有自己的扣法，不走這裡，照舊）。"""
    p = ctx.state.player
    loss = p.stats["silver"] // 10
    if loss and treasures.amount(ctx.state, ctx.content, "keep_silver") > 0:  # 金角（玉璽碎片改版，PM 五之一 3）：落敗不失銀兩
        line = treasures.KEEP_SILVER.format(shard=p.heirloom.name if p.heirloom is not None else "")
        record.notes.append(line)
        return [line]  # 保住了就不擲策馬脫身（那一份亂數是自己的，不擲不會讓別的擲骰位移）
    chance = mounts.escape(ctx.state, ctx.content)
    seed = f"脫身|{ctx.world.get_season_number()}|{p.name}|{record.id}"
    if loss and chance > 0 and random.Random(seed).random() < chance:
        record.notes.append(mounts.ESCAPED_LOSS)
        return [mounts.ESCAPED_LOSS]
    p.stats["silver"] -= loss
    record.silver = -loss
    return [f"銀兩 -{loss}"] if loss else []


def player_hp_and_cap(ctx) -> tuple[float, float]:
    """本人此刻的氣血與上限（上限吃根骨：con_of 認 key，所以傳 PLAYER，不傳 Member）。"""
    return team.member_neili(
        ctx.content, ctx.state.player.member, team.con_of(ctx.state, ctx.content, ctx.world, PLAYER), season=ctx.state.world,
    )


def player_hp(ctx) -> float:
    return player_hp_and_cap(ctx)[0]


def hp_facts(ctx, healed: tuple[str, ...] = ()) -> TollFacts:
    """此刻的氣血在寫功效演出句看來是什麼樣子（開打前量；劇情戰不扣氣血，開打前就是整場的樣子）。"""
    now, cap = player_hp_and_cap(ctx)
    return TollFacts(wounded=now < cap, low_hp=now <= LOW_HP_RATIO * cap, healed=healed)


def take_toll(ctx, tier: str, *, wild: bool = False, clash: tactics.Clash | None = None, squad: Squad | None = None,
               ) -> tuple[list[str], int, TollFacts]:
    """照結果扣這一場的氣血（team.take_encounter_toll），回傳（訊息, 本人真的掉了多少氣血, 寫演出句要的事實）。掉的量緊貼著
    扣氣血的前後量（計畫三 G4）：打贏升級會讓上限變高，開打前量的話回合裡寫的跟戰報「氣血 -N」對不上。四捨五入跟訊息的
    「:.0f」是同一個數（兩者都對同一個浮點數做銀行家捨入）。
    扣完之後本人身上的吸取（打贏）與回春（不論勝負）才回氣血（武學與成長設計 13.2、13.4）：回的那一行「氣血 +N」接在
    訊息後面、一起寫進戰報；掉的量在回血之前量，回合裡寫的「你氣血 -N」照舊加得起來。劇情戰不走這裡（不扣氣血，也就不回）。
    事實（TollFacts）是 _play_rounds 寫功效的演出句用的：開打前氣血是不是低於上限（厚），哪幾個回血的功效真的回了血
    （沒回到 1 點、沒有「氣血 +N」那一行就不算）。
    clash 是這一場一回合一回合打的樣子（tactics.Clash）：對手沒打到你的回合（定身、打空、打到自己、化影）照比例少扣，
    本命戰法回的與自扣的氣血（Clash.hp：本人與同伴）在最後改。"""
    before, cap = player_hp_and_cap(ctx)
    share = 1 - clash.blocked_share() if clash is not None else 1.0
    saved, spared = team.toll_saved(ctx.state, ctx.content, ctx.world, tier, wild=wild, share=share, squad=squad)  # 扣之前量：化勁、不動這一場改了多少
    toll = team.take_encounter_toll(ctx.state, ctx.content, ctx.world, tier, wild=wild, share=share, squad=squad)
    hp_lost = round(before - player_hp(ctx))  # 回血之前量：回合裡寫的扣血不受吸取與回春影響
    healed: list[str] = []  # 吸取、回春以前在這裡打完回血；本命戰法第三批起在回合裡回（Clash.hp）
    gained: list[tuple[str, int]] = []
    for key, fraction in (clash.hp.items() if clash is not None else ()):  # 本命戰法（tactics.py）回的、自扣的
        toll += team.shift_hp(ctx.state, ctx.content, ctx.world, key, fraction)
    return toll, hp_lost, TollFacts(
        wounded=before < cap, low_hp=before <= LOW_HP_RATIO * cap, healed=tuple(healed),
        saved=saved, spared=spared, gained=tuple(gained),
    )


def play_rounds(
    ctx, record, squad: Squad, tier: str, hp_lost: int | None, facts: TollFacts | None = None, clash: tactics.Clash | None = None,
) -> None:
    """照結果演出回合寫進戰報（武學與成長設計 8.2）。hp_lost 是這一場本人真的扣掉的氣血（_take_toll），回合裡寫的
    「你氣血 -N」加起來剛好等於它；None 是這一場本來就不扣氣血（劇情戰），對手的出手不寫數字（計畫三 G5）。
    亂數是自己一份、用「名號｜戰報流水號」當種子（計畫三 G3）：不碰 Game.rng，接下來的擲骰不會位移，
    同一筆戰報每次演出來都一樣。
    輸了（含僵持）卻一滴氣血都沒掉（本來就見底，內傷照樣累積）時，跟劇情戰一樣不寫打中沒有：每一下都寫「被你閃開了」，
    讀起來是對方沒碰到你、你卻輸了、損失裡還有內傷（最後審查 Minor 2）；贏了沒掉血（打得漂亮）寫閃開是通的，不動。
    帶【先手】的人回合裡一定先出手、不看身法（13.2）；功效的演出句寫進 trait_before／trait_after（13.6，trait_lines），
    護命的那一句寫進 notes 最前面（跟閃避的那一句同一個位置）。facts 是 _take_toll 量好的（劇情戰不給，氣血的功效就不演）。
    clash 是 team.fight 一回合一回合打的那一場（tactics.Clash，Joy 2026-10-15「全部改回合制」）：回合數、兩邊出的招、氣勢、
    對手打沒打到你都照它，本命戰法的句子排在它發動的那一回合前面；大場面有模型寫的那一段話時，戰法的句子接在 trait_after。
    沒有 clash 的（切磋、截殺、序章寫好結果的那一場）照舊照結果拆。"""
    s, c, p = ctx.state, ctx.content, ctx.state.player
    if hp_lost == 0 and tier not in team.WIN_TIERS:
        hp_lost = None
    rng = random.Random(f"{p.name}|{record.id}")
    lo = traits.loadout(s, c, ctx.world)
    foe = rounds.Foe(name=squad.name, attribute=squad.attribute, agility=rounds.foe_agility(squad.difficulty))
    our_agility = float(team.v1_stat(s, c, "agi"))
    fighters = team.fighters(s, c, ctx.world)
    if clash is not None:
        played = rounds.from_clash(clash, fighters, foe, our_agility, hp_lost, rng)
    else:
        played = rounds.play(tier, fighters, foe, our_agility, hp_lost, rng)
    record.rounds = battlelog.round_lines(c, played, rng)
    record.trait_before, record.trait_after = trait_lines(ctx, lo, record, squad, hp_lost, facts or TollFacts(), rng)
    if record.narration and clash is not None:  # 大場面：回合換成模型的那一段話，戰法的句子接在後面
        record.trait_after += [line for turn in clash.turns for line in turn.lines]


def trait_say(ctx, lo: traits.Loadout, name: str, squad: Squad, rng: random.Random, low_hp: bool = True) -> str:
    """一句功效的演出：本人、帶這個功效的那一門（lo.source，層數最多的）、對手的名字填進 S1 的句子。"""
    return battlelog.trait_line(
        ctx.content, name, ctx.state.player.name, lo.source.get(name, ""), squad.name, rng, low_hp=low_hp,
    )


def trait_lines(
    ctx, lo: traits.Loadout, record, squad: Squad, hp_lost: int | None, facts: TollFacts, rng: random.Random,
) -> tuple[list[str], list[str]]:
    """（開打前, 之後）的功效演出句。只在功效真的改到結果時才演（13.6）：開打前的四個一般功效與連環、借力一帶就算
    （它們改的是判定本身）；化勁、不動要這一場真的掉了氣血；厚要開打前氣血低於上限（它拉高的氣血係數下限這一場真的起了作用，
    見底、一滴氣血都沒得扣、或是不扣氣血的劇情戰也算；「氣血見底」那一句只在氣血剩三成以下才挑，Task 4 審查 M3）；
    乘勝要打贏、而且對手隊伍有東西可以多給（看 squad.exp、squad.reward_xinde：劇情戰先演回合、後發獎勵，戰報上的欄位這時還是 0，
    Task 4 審查 M2），悟招要打贏；吸取、回春要真的回了血（有「氣血 +N」，F10）；輕身只在遊歷。護命的那一句在 _play_rounds
    另外寫進 notes。"""
    names = {t.hook: t.name for t in ctx.content.traits.general}

    def say(name: str, low_hp: bool = True, note: str = "") -> str:
        """演出句；note 是這一場改了多少（FB-084，「（少扣了 12 點氣血）」），沒有數字可寫的功效不給。"""
        return trait_say(ctx, lo, name, squad, rng, low_hp=low_hp) + note

    # 本命戰法第三批起，其餘的功效在回合裡發動（tactics.py，句子在回合裡）；這裡只剩打完才算的兩個：化勁少扣的氣血、厚的氣血係數下限
    after: list[str] = []
    if hp_lost and lo.layers.get("toll_cut"):
        after.append(say(names["toll_cut"], note=f"（少扣了 {facts.saved} 點氣血）" if facts.saved > 0 else ""))
    if lo.layers.get("condition_floor") and facts.wounded:
        after.append(say(names["condition_floor"], low_hp=facts.low_hp))
    return [], after


def story_squad(ctx, squad: Squad) -> Squad:
    """劇情戰的對手：大場面（is_big）照江湖水漲浮上來（全隊威力 × big_scale，不看打贏幾次：劇情戰多半一次性）；
    其餘、序章照內容寫的。勝算（_choice_label）、備料（_fight_squad）、打起來（_event_battle）都照這一份。"""
    s, c = ctx.state, ctx.content
    if not rise.on(c, s.world) or not is_big(ctx, squad) or prologue_rules.active(s, c):
        return squad
    level = rise.big(c, squad.difficulty, team.power_vs(s, c, ctx.world, squad, fresh=True, terrain=False, seal=False))  # 地利、碎片不浮
    return squad if level == squad.difficulty else squad.model_copy(update={"difficulty": round(level, 1)})


def tier3(ctx, squad: Squad, record, chance: float, tag: str, source: str) -> list[str]:
    """三階素材的新來源（兵器設計 4.9；打造第二批）：擲 chance，中了照對手隊伍的屬性給一個三階素材（materials.tier3_pick），
    寫進這一場戰報的「得失」與江湖紀錄。自己一份亂數（「三階|季數|名號|戰報流水號|tag」；流水號每季從 1 起所以要季數，同
    treasures.challenge_drop），不碰 Game.rng：整季測試與量表的亂數序列不位移（FB-129）。序章不掉。
    source 寫在得失那一格的括號裡（挑戰本人、大場面；跟預設表掉的同一種合成一格，FB-147）。"""
    if chance <= 0 or prologue_rules.active(ctx.state, ctx.content):
        return []
    seed = f"三階|{ctx.world.get_season_number()}|{ctx.state.player.name}|{record.id}|{tag}"
    if random.Random(seed).random() >= chance:
        return []
    mid = materials.tier3_pick(ctx.content, squad.attribute, seed)
    line = materials.grant(ctx.state, ctx.content, mid) if mid is not None else None
    if not line:
        return []
    materials.add_cell(record.materials, ctx.content, mid, 1, source=source)
    return [materials.extra_line(ctx.content, mid, 1, source)]


def battle_rewards(ctx, squad: Squad, record, max_tier: int | None = None) -> list[str]:
    p = ctx.state.player
    msgs = []
    scale = ctx._loot_scale  # 探索包遭遇那一場（城裡的地痞）才不是 1
    gate = ctx._gate_scale  # 減法季三道閘（遭遇拍那一場才不是 1）：經驗、心得、銀兩一起乘（乘 1 一個位元都不動）
    silver_won = round(squad.reward_silver * scale * gate)
    if silver_won:
        p.stats["silver"] += silver_won
        record.silver = silver_won
        msgs.append(f"銀兩 +{silver_won}")
    # 寶物「打贏的心得／經驗」（裝備四欄 6.2）；兩種數字不同，拆成兩個倍數。乘勝、悟招以前多給獎勵，本命戰法第三批起改成回合裡的戰法
    more_xinde = 1 + treasures.amount(ctx.state, ctx.content, "win_xinde_pct")
    more_exp = 1 + treasures.amount(ctx.state, ctx.content, "win_exp_pct")
    xinde = round(squad.reward_xinde * more_xinde * scale * gate)
    if xinde:
        p.stats["xinde"] = p.stats.get("xinde", 0) + xinde
        record.xinde = xinde
        msgs.append(f"心得 +{xinde}")
    if not prologue_rules.active(ctx.state, ctx.content):  # 序章不掉素材（新手引導計畫一）
        got: list[str] = []  # 這一場掉到的素材（寶物「多掉一個素材」從這裡挑）
        if max_tier is None and record.kind in ("train", "wild"):  # 領地爭奪：剛易手的中立地，駐軍只掉一階（翻地與爭搶，冷卻期高階回饋暫停）
            max_tier = conquest.drop_cap(ctx.state.world, ctx.content, ctx.state.player.location)
        drops = materials.roll_squad_drops(squad, ctx.content, ctx.rng, max_tier=max_tier)  # 挑戰本人丁 (c) 才給 max_tier
        if ctx._drop_scale < 1:  # 減法季探索一顆的遭遇拍（城裡的地痞、三道閘）：掉的素材打折，用自己的亂數（不碰 Game.rng）
            drops = thin_drops(ctx, drops, record)
        for material_id, count in drops:
            line = materials.grant(ctx.state, ctx.content, material_id, count)
            if line:
                got.append(material_id)
                materials.add_cell(record.materials, ctx.content, material_id, count)  # 同一種合成一格（FB-140）
                msgs.append(line)
        # 大場面對手的掉落表加三階（兵器設計 4.9）：另擲一次 big_tier3（自己的亂數）；大勢人物本人那支隊伍的那一個在 _challenge，不重複擲；
        # 探索野怪不算大場面（同大場面判讀：_squad_encounter 對野怪不問模型；CLAUDE.md「大場面」那一條）
        figure_squads = {fig.squad for fig in ctx.content.figures.values()}
        if record.kind != "wild" and is_big(ctx, squad) and squad.id not in figure_squads:
            msgs += tier3(ctx, squad, record, ctx.content.config.forge_secrets.big_tier3, "大場面", materials.BIG_SOURCE)
        if record.kind in ("train", "wild"):  # 兵器掉落與寶物多掉的素材（兵器設計 4.8、裝備四欄 6.2）：只有遊歷與探索野怪；劇情戰、挑戰本人（都是 kind=event）不掉
            extra = treasures.extra_drop(ctx.state, ctx.content, got, ctx.world.get_season_number(), record.id)  # 自己的亂數
            line = materials.grant(ctx.state, ctx.content, extra) if extra is not None else None
            if line:  # 照實多寫那一個：戰報的得失、江湖紀錄（設計 6.2）；跟掉到的同一種合成一格、寫是寶物多給的（FB-140）
                source = ctx.state.player.treasure.name if ctx.state.player.treasure is not None else "寶物"
                materials.add_cell(record.materials, ctx.content, extra, 1, source=source)
                msgs.append(materials.extra_line(ctx.content, extra, 1, source))
            weapon, dropped_lines = weapons.drop(ctx.state, ctx.content, ctx.rng)
            if weapon is not None:
                record.materials.append(weapons.GAIN_LINE.format(name=weapon.name))
                msgs += dropped_lines
    # 經驗本來就是每人拿一樣多（FB-002），乘勝與寶物整隊一起乘；散人的遊俠名號每一階再多一成（ranger.exp_factor，陣營的人是 1）
    factor = ranger.exp_factor(ctx.state, ctx.content)
    exp = round(squad.exp * more_exp * factor * gate)
    exp_from = "encounter" if record.kind == "wild" else "battle"  # 都是仗（growth.BATTLE_KINDS）：減法季 45 級以後照算
    msgs += record_exp(ctx, record, exp, exp_from)
    levels, record.levelups = team.grant_team_exp(ctx.state, ctx.content, ctx.world, exp, exp_from)  # 每人都拿（FB-002）
    record.notes += levels  # 完整的句子留著（戰報頁、江湖紀錄）；戰鬥卡片畫 levelups 那一行簡短的（FB-074）
    why = renown.ranger_exp_note(ctx.state, ctx.content, factor)  # 名聲 6.3：散人的經驗加成說出原因
    record.notes += why
    return msgs + levels + why


def thin_drops(ctx, drops, record) -> list[tuple[str, int]]:
    """遭遇拍那一場掉的素材打 _drop_scale 折（減法季探索一顆：城裡的地痞、三道閘）：每一種的數量乘倍數，零頭照機率進位；
    亂數是自己的（「出門掉落|季數|名號|戰報流水號」），不碰 Game.rng。打到 0 的那一種不給。"""
    rng = random.Random(f"出門掉落|{ctx.world.get_season_number()}|{ctx.state.player.name}|{record.id}")
    out = []
    for material_id, count in drops:
        kept = int(count * ctx._drop_scale + rng.random())
        if kept > 0:
            out.append((material_id, kept))
    return out


def seize(ctx, record, draw: bool = False) -> list[str]:
    """絕學的契機（方案 C，cultivation.seize）：打贏了（險勝以上）、序章外，照這一場的難度比擲一次頓悟。
    draw：僵持也算（挑戰大勢人物本人，企劃者 2026-10-16），難度比照打贏的算法。
    說出來的話也記進這一場戰報的敘事（戰鬥卡片「結果」那一段）。"""
    tiers = (*team.WIN_TIERS, "僵持") if draw else team.WIN_TIERS
    if record.tier not in tiers or record.our_power <= 0 or prologue_rules.active(ctx.state, ctx.content):
        return []
    msgs = ctx._seize_chance(record.difficulty / record.our_power)  # 留原位：第 26 批（頓悟的契機在單打服務收尾、三處叫、野怪與僵持也算，不是懸賞那一下；修練包的查詢服務）
    record.notes += msgs
    return msgs


def file_battle(ctx, record, wear: bool | None = None, armor_wear: bool | None = None, team_exp: bool = True) -> str:
    """歸檔一場戰報。wear：這一場要不要磨兵器（兵器設計 3.4）；None＝照戰報類型，劇情戰（kind=event）不磨，
    挑戰本人雖然也是 event，由 _challenge 明說要磨。armor_wear：要不要磨防具（裝備四欄設計 4.5）；None＝照 armor.wears
    （遊歷、探索野怪、截殺自己這一邊落敗才磨；切磋、頭目戰、劇情戰不磨），挑戰本人由 _challenge 明說要磨。全服決戰不走這裡。
    兩樣的提醒合在 _last_wear（兵器先、防具後），進戰鬥卡片也進江湖紀錄（防具照兵器的做法；設計第九節「戰報不寫防具」指的是
    不每一場寫一句省了多少，這一句只在低於 edge_warn 時出現一次）。截殺輸的一方先扣血（_raid_spoils）、後磨，
    所以那一場用的是磨之前的耐久（同兵器的時序）。team_exp：草稿的得失補「經驗 +N（每人）」（整隊拿經驗的仗）；
    切磋只有本人拿、經驗自己寫在訊息裡（FB-244），不補。"""
    ctx._last_wear = []
    if (record.kind != "event") if wear is None else wear:
        ctx._last_wear += weapons.wear(ctx.state, ctx.content, record.tier)
    if armor.wears(record.kind, record.tier) if armor_wear is None else armor_wear:
        ctx._last_wear += armor.wear(ctx.state, ctx.content, record.tier)
    record.notes += ctx._last_wear
    battlelog.add_record(ctx.state, record)
    ctx.state.battle_card = record.id
    line = battlelog.summary_line(record)
    if ctx._draft is not None:
        ctx._draft.outcome(battlelog.outcome_text(record), line)
        ctx._draft.battle_id = record.id
        ctx._draft.notes += ctx._last_wear
        if record.exp and team_exp:
            ctx._draft.changes.append(f"經驗 +{record.exp}（每人）")
    return line


# ── 打一場的主流程（第二輪第 98 批從 Game 收進來：逐行照抄，擲骰與呼叫的先後一行都沒動） ──

def squad_encounter(ctx, squad_id: str, wild: bool = False, as_sortie: bool = False) -> list[str]:
    """遭遇一支敵方隊伍：單次判定，勝得對手獎勵，落敗失落一成銀兩；自己陣營的隊伍改成操練（見 _drill）。

    wild：探索時撞上的野怪（探索三選一設計 4.2）——扣氣血打折（`wild_neili_loss_factor`，內傷照比例）、
    打贏**不推大勢**（遊歷推大勢的量已經讓黃巾早早稱霸，探索不能再加碼）；獎勵、掉落、落敗的
    一成銀兩都照常。戰後事件本來就只在 _train 裡接，野怪不走那裡。遊歷不帶這個旗標，一點都不變。
    野怪是當下擲出來的，不問模型、也不吃判讀（武學與成長設計 8.3）；遊歷的大場面吃鎖外的判讀（_judged）。
    as_sortie：出陣的攻（出陣探索與地盤設計 2.2、2.4）——戰報類型 sortie、給自己的照 _sortie_rewards（三成、不給銀兩掉落）、
    不推線，推那一塊的進度（_push_progress）。"""
    s, c = ctx.state, ctx.content
    p = s.player
    loc = c.locations[p.location]
    squad = c.squads[squad_id]
    if ctx._drills_with(squad):
        return ctx._drill(squad)  # 遇上自家隊伍改操練：操練是出陣包的（第 17 批），打不打在這個單打服務裡定
    scripted = prologue_rules.fight_tier(s, c)  # 序章雪恥那一場：結果照寫好的，不吃模型的判讀
    judged = None if wild or scripted is not None else ctx._judged(squad)
    result = fight_with(ctx, squad, judged, tier=scripted)
    record = battlelog.new_record(s, c, ctx.world, squad, result, "wild" if wild else "sortie" if as_sortie else "train")
    if prologue_rules.active(s, c) and territory.on(c):  # 戰報不寫舊名「遊歷」（新手引導重做）
        record.label = PROLOGUE_FIGHT
    if scripted is None:
        record.notes += style_note(ctx, squad, result) + terrain_note(ctx)
    narrate(record, result, judged)
    msgs: list[str] = []
    if result.tier in team.WIN_TIERS:
        rewards = ctx._sortie_rewards(squad, record) if as_sortie else ctx._battle_rewards(squad, record)  # 留原位：第 26 批（打贏的獎勵是出陣包與核心二選一、接在 msgs 最前面不進 extra，不在懸賞那一個發布點上）
        msgs += rewards
        extra: list[str] = []
        if not wild and not prologue_rules.active(s, c):  # 序章打贏不推大勢、不抽伏筆、不記軍令
            if not as_sortie:  # 出陣不推線（領地爭奪：推那一塊的進度，下面 _push_progress）
                for trend_id, delta in ctx.train_trend_push(loc.id).items():  # 換算過的線，照舊交給 T3 的 push_trend  # 留原位：第 26 批（推大勢夾在記功、地盤進度之前，結果交給 push_trend，不在發布點上）
                    extra += ctx.push_trend(trend_id, delta, source="train")
            credit: list[str] | None = None
            # 領地爭奪：出陣攻打贏推這一塊的進度、不推線（設計 3.7）；約戰開著時這裡只剩截糧（減法季批 3b：進度只在約戰結算動）
            if as_sortie and not ctx.duel_on():  # 留原位：第 26 批（約戰開著與否是查詢，決定記功與推進度走哪一支，不是事件）
                # 軍令照推之前的清單記（FB-608：推滿易手的那一下，推完那一塊已經是自家的、在冷卻，不在攻的清單上）；那一句照舊排在後面
                credit = ctx._order_credit(
                    kind="win", location=loc.id, front=front_of(c, loc.id), squad=squad.id, squad_faction=squad.faction,
                )
                extra += ctx._push_progress(loc.id, conquest.sortie_nominal(c, loc.id, "attack"), "sortie", "attack")
            region = atlas.region_of(c, p.location)  # 官銀（伏筆，濃縮版內容表 4.0）：只有遊歷打贏才擲
            extra += ctx._fs_after_win(squad, region.id if region is not None else None)
            extra += credit if credit is not None else ctx._order_credit(  # 軍令（計畫 T6）：攻城看戰線與敵方陣營，截糧看地點與運糧隊
                kind="win", location=loc.id, front=front_of(c, loc.id), squad=squad.id, squad_faction=squad.faction,
            )
            extra += ctx._opp_on_win(front_of(c, loc.id), squad.faction)  # 三路並進（正式版乙二）
            extra += ctx.publish("win", loc.id, squad.id)  # 懸賞榜的討伐（事件 win，第 26 批）
            if as_sortie:  # 名聲 3.1：出陣攻打贏 +1（遊歷、探索野怪不給）
                extra += deed_fame(ctx, "sortie")
        changes, notes = battlelog.split_changes(extra, for_record=True)
        record.changes += changes
        record.notes += notes
        msgs += extra
    elif result.tier == "落敗":
        msgs += ctx._lose_silver(record)
    toll, hp_lost, facts = take_toll(ctx, result.tier, wild=wild, clash=result.clash, squad=squad)
    record.changes += toll
    msgs += toll
    play_rounds(ctx, record, squad, result.tier, hp_lost, facts, clash=result.clash)
    msgs += ctx._seize(record)
    msgs.insert(0, file_battle(ctx, record))
    if squad.desc:  # 有來歷的對手（運糧隊）多一句描述，接在戰鬥那一行後面
        msgs.insert(1, f"（{squad.name}：{squad.desc}）")
    if not wild and is_big(ctx, squad):  # 名聲 4.5：天下聞名打大場面點名
        famed_news(ctx, loc.name, squad.name, result.tier)
    return msgs

# ── 本人對本人（切磋、截殺、買兇的殺手） ──

def spar_power(who: Game, against: Game, *, seal: bool = True) -> float:
    """這個人切磋時的威力：只算本人（同伴、部下不上場），照對手身上那一門武學的屬性算相剋，吃自己的氣血係數與加成。
    seal=False 不含玉璽碎片的戰力（買兇的殺手照它浮上來，同江湖水漲）。"""
    s, c, w = who.state, who.content, who.world
    with team.facing_player(c, s, against.state, against.world):  # 五項屬性的季：照對手本人的五項對抗（他的統御擋你的武力）
        members, conditions, boosts = team._fighters(s, c, w, seal=seal)
    return encounter.member_power(
        members[0], team.team_arts(s, c, w), team.worn_attribute(against.state, c, against.world), conditions[0], boosts[0],
    )


def spar_mirror(result: encounter.EncounterResult, power: float) -> encounter.EncounterResult:
    """從另一邊看同一場：他贏就是你輸，他輸了你贏（差距夠大算大勝，門檻照你自己的威力當難度），平手照舊平手。"""
    if result.tier in team.WIN_TIERS:
        tier = "落敗"
    elif result.tier in team.DRAW_TIERS:
        tier = result.tier
    else:
        big = dict(encounter.tier_thresholds(result.our_power))["大勝"]  # 你的難度是他的威力
        tier = "大勝" if -result.margin >= big else "險勝"
    return result.model_copy(update={"tier": tier, "margin": -result.margin, "our_power": power, "difficulty": result.our_power})
