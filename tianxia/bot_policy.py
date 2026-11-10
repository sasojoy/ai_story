"""伺服器假人的行為（伺服器假人設計第七節）：照陣營目標替選項打分數，強度旋鈕決定多常挑最高分。

只透過 engine.Game 的公開行動（choose／practice／heal／forge／cultivate…）做事，跟真人按按鈕走同一條
路；不接 LLM（呼叫端把 game.client 設成 None）；例外是首創配方的取名與絕學定名，在鎖外由 bot_runner 做
（見 tend_arts、apply_job）。全服戰鬥裡假人是一般參戰者，每回合從固定戰法裡挑，不寫自由文字。
"""
from __future__ import annotations

import random

from . import allied
from .features.bout import arena_rules as arena
from . import bot
from .features.cultivation import cultivation
from .features.bout import duel_rules as duel
from . import library, naming
from .features.explore import outing_rules as outing
from . import rules, server_bots
from .features.companions import stances
from . import team
from .bot import allocate_points, can_practise, wants_heal
from .core import battle_base as battle_instance
from .core import features as features_core
from .engine import FREE_TEXT_OPTION, Game, Option
# 決戰（battle:）的分數搬進決戰包的 bots.py（全部拆包第 7 批；score 先問那一包）：這兩個名字照舊在這裡（tests/bots/test_bot_policy.py、
# tests/season/test_real_content.py 直接叫，同一個函式、同一個數）
from .features.battle.bots import JOIN_BATTLE_SCORE, battle_score as _battle_score  # noqa: F401
from .features.bounties.bots import takeable as _takeable  # noqa: F401  懸賞榜上有沒有揭得下的：全部拆包第 60 批搬進懸賞榜包（tests 讀 bot_policy._takeable，同一個函式）
from .features.smithy import bots as smithy_bots  # 過渡：_smith_want 的一行委派（全部拆包第 41 批）
from .features.sortie.bots import DUTY_SCORE, TRAIN_SCORE, duel_play  # noqa: F401  約戰卡上的事：全部拆包第 60 批搬進出陣包（take_turn 與 tests 讀這個名字）；兩個分數第二輪第 89 批
from .features.tavern import bots as tavern_bots  # 舊模組 → 包：_tavern 的本體（全部拆包第 60 批）
from .features.travel import bots as travel_bots  # 舊模組 → 包：move: 的分數（全部拆包第 47 批）  # 過渡：掛鉤沒有 profile（第 47 批 PM 認定第 2 條）
from .features.peers.bots import (  # noqa: F401  打招呼、名帖的回法與比例：全部拆包第 37 批搬進玩家互動包（tests 讀 bot_policy.answer_call、REPLY_MIN_SECONDS）
    GREET_REPLY_SHARE, MINGTIE_ACCEPT_SHARE, MINGTIE_REJECT_SHARE, MINGTIE_SEND_CHANCE, REPLY_MIN_SECONDS, REPLY_SPREAD_SECONDS,
    TRAVEL_ACCEPT_SHARE, TRAVEL_REJECT_SHARE, _hand_card, _make_card, _roll, answer_call,
    INVITE_YES, RAID_CHANCE, RAID_ODDS, _answer_invite, _raid, answer_discuss,  # 切磋、論武、截殺：全部拆包第 38 批搬進玩家互動包（測試讀 bot_policy._answer_invite、_raid；_answer_discuss 的薄層叫 answer_discuss）
    _answer_discuss,  # 論武包成取名單：第二輪第 101 批
)
# 別包也讀的、包自己讀的第二輪第 89 批搬走了（bot_base 與各包的 bots.py；包不再跳回這個檔）。舊名留著，同一批物件：這個檔自己照舊叫（score、_stamina_play、_toward_*……），測試與腳本讀；
# 要換掉那幾個函式的換新位置那一份，換這裡打不到。_TURN 不留這個名字（只有 bot_base 那一份）。每包的按法第二輪第 101 批也搬走了（舊名同一批物件）；讀者留在這個檔的（take_turn 讀 _stamina_play、_sense……）換這裡打得到，
# 讀者搬走的（_stamina_play 讀 PLAY_CHANCE）要換新位置那一份。tend_arts、look_after、take_turn 留在這裡：同時排幾包的事，包不准 import 包
from . import bot_base
from .bot_base import (  # noqa: F401
    BOUNTY_SCORE, ORDER_SCORE, PRACTICE_SCORE, SORTIE_WIN, SORTIE_WIN_FLOOR, TREND_WEIGHT,
    _bounty_here, _cannot_push, _crippled, _duel_value, _goals, _outmatched, _side, _sortie_win, _train_value, _turn_cached,
    NO_NAME, DiscussJob, EpiphanyJob, ForgeJob, MasterJob, NamingSlot, SenseJob, next_hop,  # 第二輪第 101 批
)
from .features.battle.bots import _staying_for_the_battle, _toward_battle  # noqa: F401
from .features.craft.bots import _forge  # noqa: F401
from .features.cultivation.bots import LEARN_ROOM, LEARN_SILVER_RESERVE, _learn_here, _master, _too_dear  # noqa: F401
from .features.explore.bots import ACT_SCORES, NEED_MATERIAL_SCORE, OUTING_SCORE  # noqa: F401
from .features.faction.bots import _toward_faction  # noqa: F401
from .features.figure_acts.bots import CHALLENGE_ODDS, CHALLENGE_SCORE, STRIKE_ODDS  # noqa: F401
from .features.sense.bots import _god_name, _sense  # noqa: F401
from .features.smithy.bots import DIVINE_NAME_CHANCE, _name_originals  # noqa: F401
from .features.stamina_plays.bots import PLAY_CHANCE, PLAY_STAMINA, _stamina_play  # noqa: F401
from .features.travel.bots import (  # noqa: F401
    AWAY_MOVE_SCORE, BOUNTY_MOVE_SCORE, CLINIC_MOVE_SCORE, CLINIC_URGENT_SCORE, FOCUS_MOVE_SCORE, HOME_MOVE_SCORE, ORDER_MOVE_SCORE, SUMMONS_MOVE_SCORE, TRAIN_MOVE_SCORE,
    _bounty_hop, _clinic_score, _focus_hop, _front_hop, _front_locations, _home, _losing_front, _order_hop, _order_hop_now, _summons_hop,
)
from .models import MOVES, Effect
from .state import BotProfile

REWARD_STATS = ("str", "agi", "con", "wis", "silver", "fame", "xinde")  # 博聞不在內：它只靠升級的點數增加，事件不給
# 召見（計畫 T5）：一季一次、演完才晉升帶部下，到了就應召、沒到就往那裡走，都比軍令優先
SUMMONS_SCORE = 50.0
PRACTICE_CHANCE = 0.2  # 每次行動順便練成一門的機率（付得起心得才練，見 look_after；不是每次行動都練）
FORGE_CHANCE = 0.25  # 每一輪合成一爐的機會（有東西可合、體力有餘時才擲）【預設】
CULTIVATE_CHANCE = 0.2  # 每一輪修練一次的機會（體力有 bot.CULTIVATE_RESERVE、有東西可修時才擲）【預設】
# （截殺的 RAID_CHANCE、RAID_ODDS 與切磋、論武的 INVITE_YES 搬進玩家互動包 features/peers/bots.py，全部拆包第 38 批；上面 import 回來）
SMITH_SCORE = BOUNTY_SCORE  # 鐵匠鋪：跟揭懸賞一樣急，兵器配不上是白白少一截威力
# 人在城鎮、身上湊得出一爐又付得起（bot.forge_ready）時「進鐵匠鋪」再多這麼多（FB-144，PM 2026-10-13）：不加的話假人路過城鎮那幾輪
# 多半挑了遊歷、趕路，一整季一爐都沒打。照 SMITH_SCORE 再加一份（合起來 16）：高過一般的遊歷、往軍令與懸賞走的那一步，
# 低過軍令本身（ORDER_SCORE 30：替軍令遊歷、接糧車）——不然手上帶著糧草的假人會先把糧草下爐，不去接糧車
FORGE_SCORE = SMITH_SCORE
MARKET_SCORE = SMITH_SCORE  # （同 features/gear/bots.py 的 MARKET_SCORE，8.0）馬市（裝備四欄設計第九節）：趕路疾行省體力，跟鐵匠鋪一樣急；真人會騎馬，假人也要
MASTER_TRIES = 5  # 定名時模型的名字用不了，字表最多另組幾個


def take_turn(game: Game, profile: BotProfile, rng: random.Random, slot: NamingSlot | None = None) -> list[str]:
    """做一個動作（外加不受強度影響的照顧動作、武學的事）；沒有能做的事（例如體力不夠）就什麼都不做，回傳空清單。
    在路上的假人這一輪跳過，連照顧動作都不做（地圖擴充設計 3.4）。
    slot 是這一輪的取名名額（見 NamingSlot）：武學的事開出要取名的單時放進 slot.job，這一輪就只做到那裡。"""
    game.options(odds=False)  # 每一輪先替全服戰鬥追趕一次時間（集結截止、回合逾時），跟真人的畫面刷新一樣；在路上、趕路的假人也不例外
    if game.state.player.journey is not None:
        return []
    if game.state.player.god_naming is not None:
        return _god_name(game, rng, slot)  # 頓悟取名的時候選單上只有取名（同真人）
    look_after(game, rng)
    msgs = tend_arts(game, rng, slot)
    if slot is not None and slot.job is not None:
        return msgs  # 這一輪在爐前等名字，不做別的（不然體力可能花掉，C 段開不成）
    s = game.state
    if s.player.sensing is not None:
        return msgs + _sense(game, rng, slot)
    if s.player.duel is not None:
        return msgs + game.choose(f"duel:{duel_move(game, rng)}")
    if s.player.arena is not None:
        return msgs + game.choose(f"arena:{duel_move(game, rng, s.player.arena)}")
    if s.player.pending_companion:
        return msgs + game.choose("talk:leave")
    discussed = _answer_discuss(game, rng, slot)
    if discussed is not None:
        return msgs + discussed
    answer = _answer_invite(game, rng)
    if answer is not None:
        return msgs + game.choose(answer)
    answer = answer_call(game, profile)
    if answer is not None:
        return msgs + game.choose(answer)
    if s.player.tagalong is not None:
        return msgs  # 答應了跟人結伴同行：在原地等他動身，不自己走開
    rally = _toward_battle(game)
    if rally is not None:
        return msgs + rally
    raided = _raid(game, rng)
    if raided is not None:
        return msgs + raided
    handed = _hand_card(game, rng)
    if handed is not None:
        return msgs + handed
    played = _stamina_play(game, rng)
    if played is not None:
        return msgs + played
    drank = _tavern(game, rng)
    if drank is not None:
        return msgs + drank
    staged = _arena(game, rng)
    if staged is not None:
        msgs = msgs + staged
        if s.player.arena is not None:  # 開打了：這一輪就是這一場；只報名、更新分身不花體力，照常做別的
            return msgs
    dueled = duel_play(game, profile, rng)  # 出陣約戰（減法季批 3b）：應對面的約戰、同袍的同去
    if dueled is not None:
        return msgs + dueled
    options = [  # road: 開頭的是路上的選項：假人不改道、不做路上小事（路上設計 3.5）
        o for o in game.options(odds=False, tick=False)
        if o.enabled and o.id not in ("act:rest", "act:halt", FREE_TEXT_OPTION)
        and not o.id.startswith(("road:", "defect:", "invite:", "errand:", "faction:lean:"))  # 叛投：假人不換陣營（計畫甲）；託付：假人不收（減法季批 6）；豪強改幫另一軍也不換
        # 邀請由上面的 _answer_invite 答，不交給打分數亂按
    ]
    enlist = [o for o in options if o.id.startswith("battle:enlist:")]
    options = [o for o in options if not o.id.startswith("battle:enlist:")]  # 臨時投效只照 bot.enlist_pick，不交給打分數（散人的假人不投效）
    if not options and not enlist:
        return msgs
    ids = [o.id for o in options]
    battle = game.battle_now()  # 有攻城戰時是自己看的那一場（領地爭奪第二批）
    if battle is not None and s.player.name not in battle.participants:
        join = next((i for i in ids if i.startswith("battle:join")), None) or bot.enlist_pick(game, [o.id for o in enlist])
        if join is not None:  # 集結時選單照常有別的事可做（FB-009）；假人一看到加入就加入，不交給強度旋鈕碰運氣；豪強投效人少的一軍
            return msgs + game.choose(join)
    elif battle is not None and battle.phase == "muster":
        # 已經參戰：不換邊（不分陣營的劇本集結時還看得到另一邊的加入），也不走出決戰的大區
        options = [o for o in _staying_for_the_battle(game, battle.battle_id, options) if not o.id.startswith("battle:join")]
        if not options:
            return msgs
        ids = [o.id for o in options]
    side = allied.pick_side(s.player.name, ids, game.world.roll_counts())
    if side is not None:  # 豪強分屬兩軍：投靠豪強、拜入曹氏莊院之後挑依附哪一軍，挑人少的那一邊（設計第十三節）
        return msgs + game.choose(side)
    if s.player.faction is None and profile.faction is not None and not s.pending_event \
            and not any(i.startswith("battle:") for i in ids):
        step = _toward_faction(game, profile.faction, ids)
        if step is not None:
            return msgs + game.choose(step)
    if outing.active(s) is not None and game.outing_can_go():  # 走一趟停在要選的事上、選完了：接著走（同真人）
        return msgs + game.outing_go() + bot.outing_say(game, rng)
    choice = pick(game, options, profile, rng)
    if choice == "act:explore" and outing.on(game.content, s):  # 走一趟開著：探索照真人一樣挑段數出發（bot.outing_segments）
        n = bot.outing_segments(game, rng)
        if n:
            return msgs + game.outing_go(n) + bot.outing_say(game, rng)
    # 約戰開著（減法季批 3b）：挑到出陣那一格（只是打開出陣前那張卡）換成真的貼一張、封好三招（bot.duel_go）
    return msgs + game.choose(bot.duel_go(game, choice, rng)) if choice else msgs


# 出陣約戰（減法季批 3b-3）：應對面的約戰、同袍的同去（duel_play、ANSWER_AFTER、ANSWER_POWER_FLOOR、JOIN_CHANCE）搬進出陣包 features/sortie/bots.py，全部拆包第 60 批；上面 import 回來


ORDER_FOLLOW = 0.6  # 決戰有將令時照令出招的機會（真人也不見得都聽）


def battle_move(game: Game, profile: BotProfile, rng: random.Random) -> list[str]:
    """決戰這一回合出一招（bot_runner.battle_tick 用；Joy 2026-10-13「機器人是不是都不會第一時間選擇行動」）：只看選單上的
    battle:act:，照 pick 一樣打分數挑（不寫放手一搏）。這一回合已經出過、或選單上沒有可出的招，就什麼都不做。"""
    options = [o for o in game.options(odds=False) if o.enabled and o.id.startswith("battle:act:")]
    if not options:
        return []
    ordered = [o for o in options if battle_instance.ORDER_MARK in o.label]  # 龍頭上陣：有將令時多半照令出招
    if ordered and rng.random() < ORDER_FOLLOW:
        return game.choose(ordered[0].id)
    choice = pick(game, options, profile, rng)
    return game.choose(choice) if choice else []


# 擂台（tianxia/arena.py）：還沒報名、有武學就報名；分身比此刻弱了 ARENA_REFRESH 以上就更新；今天還有次數時每一輪 ARENA_CHANCE 的機會
# 挑一場，挑挑得了的人裡身手最弱的（同樣弱挑名次高的）。挑擂不花體力，哪裡都能挑。
ARENA_CHANCE = 0.05
ARENA_REFRESH = 0.15


def _arena(game: Game, rng: random.Random) -> list[str] | None:
    """擂台的事（報名、更新分身、挑一場），走真人同一串選單：打開擂台、按那一顆、還開著就返回。這一輪不做是 None。
    選單上沒有「擂台」（擂台關著、序章、手上有事）時不擲骰。"""
    s = game.state
    if "act:arena" not in {o.id for o in game.options(odds=False, tick=False) if o.enabled}:
        return None
    power = game.arena_power()
    if power <= 0:
        return None
    mine = arena.entry_of(s.world, s.player.name)
    refresh = mine is None or power > mine.power * (1 + ARENA_REFRESH)
    if not refresh and (game.arena_left() <= 0 or rng.random() >= ARENA_CHANCE):
        return None
    msgs = game.choose("act:arena")
    if refresh:
        msgs += game.choose("arena:join")
    else:
        fights = [o.id for o in game.options(odds=False, tick=False) if o.enabled and o.id.startswith("arena:fight:")]
        if fights:
            pick = min(fights, key=lambda oid: (s.world.arena[oid.removeprefix("arena:fight:")].power,
                                                s.world.arena[oid.removeprefix("arena:fight:")].rank))
            msgs += game.choose(pick)
    if s.player.picking_arena:
        msgs += game.choose("arena:back")
    return msgs


# 酒肆：每一輪 TAVERN_CHANCE 的機會進去問一件事、問完出門（本體與 TAVERN_RESERVE、TAVERN_ASKS 搬進酒肆包 features/tavern/bots.py，全部拆包第 60 批；機會留在這裡，叫的那一下才讀，測試換的是這個屬性）
TAVERN_CHANCE = 0.03


def _tavern(game: Game, rng: random.Random) -> list[str] | None:
    """進酒肆問一件事、出門；這一輪不做是 None。選單上沒有「酒肆」時不擲骰。"""
    return tavern_bots.visit(game, rng, TAVERN_CHANCE)


GROWTH_SCORE = 100.0  # 開季準備卡上照名號那一套配比（只剩這幾顆可按）
TEACH_PER_TICK = 3  # 假人一輪最多傳幾下功（真人也是一下一下按的）


def look_after(game: Game, rng: random.Random) -> None:
    """照顧動作（不受強度旋鈕影響）：升級的屬性點先配掉（只走 Game.allocate_stat，跟真人一樣）；有內傷先療傷；馬餓了就餵；裝備庫裡有更好的寶物、更快的馬就換上；身上的兩門（開局送的基礎武學）偶爾練成一成，付得起心得才練；
    心得多出來的傳給同伴、部下（bot.teach，一輪最多 TEACH_PER_TICK 下）。
    合成、修練、學藝、改練、熔煉、定名在 tend_arts。"""
    allocate_points(game, rng)
    _make_card(game)  # 名帖（不擲亂數）
    bot.check_in(game)  # 每日簽到（21 天季，正式季整合 8.1；不擲亂數，四階照名號＋季數的種子挑）
    bot.take_pill(game)  # 體力見底、手上有回體丹就吃一顆（內測贈送，真人假人一樣拿到）
    if wants_heal(game):
        game.heal()
    bot.feed_mount(game)  # 馬餓了就餵（不受強度旋鈕影響，不擲亂數）
    bot.wear_better(game)  # 換上更好的寶物、更快的馬（不受強度旋鈕影響，不擲亂數）
    for kind in ("內功", "武學"):
        if can_practise(game, kind) and rng.random() < PRACTICE_CHANCE:
            game.practice(kind)
    bot.teach(game, TEACH_PER_TICK)  # 傳功門下：心得多出來就傳給同伴、部下（不擲亂數）
    bot.trade_at_smith(game)  # 素材與經濟（計畫 B5）：人在鐵匠鋪就升階、賣多的（不擲亂數；不為了它進鐵匠鋪）
    bot.donate_spare(game)  # 人在自家大本營就捐多的素材（不擲亂數；不為了它繞路）
    voice_stance(game)  # 人物心意（減法季批 6）：每天照名號雜湊的機會直接記一筆（不擲 rng；關著什麼都不做）


def voice_stance(game: Game) -> bool:
    """假人挑心意（減法季整合設計 5.4、5.7；企劃者 2026-10-24 第 5 件）：每天 Config.jianfa.bot_stance_chance 的機會（照名號＋今天的雜湊，
    stances.bot_pick），直接記一筆（Game.voice_stance：一人一天一筆、到門檻、貢獻都跟真人說話那一輪同一條），不說話、不寫字、不寫紀錄。
    人物挑自己這一邊的，心意照名號＋人物的雜湊（同一個假人一直勸同一種）。同一天每一輪都擲到同一個結果，記過就不再記。回有沒有記。"""
    pick = stances.bot_pick(game.state, game.content)
    return pick is not None and game.voice_stance(*pick)


def tend_arts(game: Game, rng: random.Random, slot: NamingSlot | None = None) -> list[str]:
    """假人的武學（修練頁與煉製頁上的事），每一輪主要行動之前做；只走 Game 的公開行動，跟真人按按鈕一樣：
    1. 練成絕學、輪到自己定名：請模型另取新名字（企劃者 2026-10-06：不沿用原名），輪得到就開單交給假人程式、這一輪到此為止；
       輪不到先不定（見 _master）；
    1b. 手上有還沒定名的神器原品：每一輪 DIVINE_NAME_CHANCE 的機會按「沿用譜名」（見 _name_originals）；
    2. 這裡教、自己同一種還沒有這個屬性的，學一門（見 _learn_here）；
    3. 庫滿了熔最弱的一門；
    4. 手上有兩個以上意境、體力有餘時，FORGE_CHANCE 的機會合一爐（挑法同整季機器人；首創的要叫模型，見 _forge）；
    5. 功法庫裡有更強的就改練；
    6. 體力有餘、有東西可修時，CULTIVATE_CHANCE 的機會修練一次（衝絕學、手上有破境丹就服）。
    亂數只在真的有事可做時才擲（有東西可合才擲合成的機會、有東西可修才擲修練的機會、有神器原品等著定名才擲定名的機會）：什麼武學都沒有的假人一次都不擲。
    注意：正式內容開局送兩門基礎武學，所以真的假人從第一輪起就有東西可合、每一輪都擲一次合成的機會
    （假人程式共用的亂數順序因此跟加這個之前不一樣）。"""
    state, content, world = game.state, game.content, game.world
    p = state.player
    msgs: list[str] = []
    if p.naming is not None:
        _master(game, slot)
        if slot is not None and slot.job is not None:
            return msgs  # 這個名在等模型：別的等定完名再說
    msgs += _name_originals(game, rng)
    msgs += _learn_here(game)
    if library.full(state, content):
        bot.melt_the_weakest(game)
    msgs += bot.infuse_spare(game)  # 意境合成改版：同一路的凡、佳化進最深的一份（不擲亂數；改版沒開什麼都不做）
    if len(p.insights) >= 2 and p.stamina >= bot.FORGE_RESERVE and rng.random() < FORGE_CHANCE:
        plan = bot.pick_forge(game, rng)
        if plan is not None:
            msgs += _forge(game, plan, slot)
            if slot is not None and slot.job is not None:
                return msgs  # 這一爐在等名字：改練與修練等開完爐再說
    bot.create_art(game, rng)  # 武學重構：心得多出來就自創一門（假人不叫模型：意分照預設、名字照退路字表）
    bot.switch_to_the_strongest(game)
    bot.slot_insights(game)  # 悟到的意境裝進身上兩門的空槽（不擲亂數）
    if p.stamina >= bot.CULTIVATE_RESERVE:
        ready = [  # 服丹或花心得強行衝關（bot.break_way）；兩樣都不行的只能等契機
            a for a in bot.worn_first(game)
            if bot.break_way(game, a) and cultivation.cultivate_problem(state, content, world, a, **bot.break_way(game, a)) is None
        ]
        if ready and rng.random() < CULTIVATE_CHANCE:
            msgs += game.cultivate(ready[0], **bot.break_way(game, ready[0]))
    return msgs


def apply_job(game: Game, job: ForgeJob | MasterJob | SenseJob | DiscussJob | EpiphanyJob, proposed) -> list[str]:
    """C 段（bot_runner 在鎖內、重讀角色之後呼叫）：
    - 首創的爐：交給 Game.forge(proposed=...) 整個重驗再登記（等名字的時候配方被別人登記了，照查到的給、不收第二次）。
      取新名字的單（沒有候選）要是沒有過得了過濾的名字（模型沒取到、或這時重驗過不了），這一爐不開、不收費：
      Game.forge 會走字表名字搶下首創，那正是看得出是假人的樣子（真人在模型掛掉時走字表，假人不行）。
      挑一個的單（有候選）沒挑到照常開，由規則挑，不產生新名字；
    - 絕學定名：還輪到這一門才定。模型的名字先過一次完整的過濾（naming.recheck），跟原名一樣、過不了、或定的時候
      被用掉了，就用退路字表另組（salt 從 0 起），最多 MASTER_TRIES 個，一定跟原名不同。都定不成就留著，下次再來。"""
    state, content, world = game.state, game.content, game.world
    if isinstance(job, EpiphanyJob):  # 頓悟取名：proposed 是模型給的名字清單；一個都沒拿到不交回（等下一次輪到再請模型），不用字表搶
        return game.epiphany_names(job.request, list(proposed)) if proposed else []
    if isinstance(job, DiscussJob):  # 論武：同首創的爐，取新名字卻沒有名字可用就不答（不用字表名字搶首創）
        if not job.request.choices and naming.recheck(content, proposed, world.is_character_name)[0] is None:
            return []
        return game.peer_act(job.sender, "discuss", {"arg": f"yes:{job.item}", "proposed": proposed})
    if isinstance(job, SenseJob):  # 取不到名字照樣交回：私有意境走退路字表，不記首悟（Game._sense_apply 只記模型取的）
        return game.sense_draw(job.request, proposed)
    if isinstance(job, ForgeJob):
        if not job.request.choices and naming.recheck(content, proposed, world.is_character_name)[0] is None:
            return []  # 取新名字的那一爐沒有名字可用：不開，不用字表名字搶下首創（見下面的說明）
        return game.forge(None, list(job.insight_ids), proposed=proposed)
    if state.player.naming != job.art_id:
        return []
    old = team.resolve_art(job.art_id, content, world)
    if old is None:
        return []
    name, _ = naming.recheck(content, proposed, world.is_character_name)
    candidates = ([name] if name else []) + [
        naming.fallback_name(content, f"定名|{job.art_id}", old.kind, salt=i) for i in range(MASTER_TRIES)
    ]
    for candidate in candidates:
        if candidate == old.name:
            continue
        msgs = game.name_mastered(candidate)
        if state.player.naming is None:
            return msgs
    return []


def pick(game: Game, options: list[Option], profile: BotProfile, rng: random.Random) -> str | None:
    """以強度旋鈕的機率挑最高分的選項（同分隨機），否則從假人會選的選項裡隨便挑。選邊鈕（豪強分屬兩軍）照 allied.pick_side、不打分數。"""
    side = allied.pick_side(game.state.player.name, [o.id for o in options if o.enabled], game.world.roll_counts())
    if side is not None:
        return side
    with bot_base.turn_cache():
        scored = [(score(game, o, profile), o.id) for o in options]
    scored = [(value, option_id) for value, option_id in scored if value is not None]
    if not scored:
        return None
    if rng.random() < server_bots.strength(game.content.config, profile):
        best = max(value for value, _ in scored)
        return rng.choice([option_id for value, option_id in scored if value == best])
    return rng.choice([option_id for _, option_id in scored])


# 頭目戰：假人照看到的架勢出剋它的那一招的機會（其餘亂出）。真人也是看架勢出招，架勢有三成是虛招（DuelTuning.tell_truth）
DUEL_READ = 0.6


def duel_move(game: Game, rng: random.Random, fight=None) -> str:
    """頭目戰（或擂台，fight 給 ArenaFight）的一招：不寫放手一搏（假人不寫自由文字）、不抽身、不認輸。整季機器人（bot.pick）是隨機挑選單上的招。"""
    answer = duel.answer_to(fight if fight is not None else game.state.player.duel)
    return answer if answer is not None and rng.random() < DUEL_READ else rng.choice(MOVES)


def score(game: Game, option: Option, profile: BotProfile) -> float | None:
    """選項的分數；None＝假人不會選（別的陣營的投靠、叛投、閒聊或求見大勢人物、只會被擋在門外的交友、投靠的確認畫面另外處理）。"""
    kind, _, arg = option.id.partition(":")
    # （defect：假人不叛投〔計畫甲〕；sect：假人不拜門派；faction: 原本落到最後的 None。全部拆包第 35 批搬進陣營包的 bots.py，下面 features_core.bot_pick 問它）
    # （ambush、works：設伏、屯糧由 take_turn 的 _stamina_play 做，不交給打分數；全部拆包第 39 批換成體力玩法包的 bots.py，下面 features_core.bot_pick 問到；
    # 護衛、犒軍、探望 aid: 同理，假人沒有要按的，bot_pick 照預設回 None，全部拆包第 31 批）
    if kind == "move":  # 往哪裡走：移動包的分數要 profile（測試傳的不一定是 game.state.player.bot），所以在掛鉤之前直接問（全部拆包第 47 批）
        return travel_bots.score(game, option, profile)
    owned, value = features_core.bot_pick(game, option)  # 搬成包的功能：假人看到這一顆怎麼按問那一包（開發規範手冊 3.8；宴客 feast:）
    if owned:
        return value
    if kind == "growth":  # 開季準備卡挑配比：照名號那一套（bot.growth_key），其餘不按
        return GROWTH_SCORE if arg == bot.growth_key(game) else None
    # （opp：機緣，假人不做，正式版乙一；全部拆包第 34 批搬進 features/military/bots.py，上面的 features_core.bot_pick 問它。對話裡的 talk:opp: 由人物情誼包的 bots.py 回 None）
    # 決戰（battle:）搬進功能包：假人的分數在 features/battle/bots.py，上面的 features_core.bot_pick 問它（全部拆包第 7 批）
    # 奪璽單挑（seal:）搬進功能包：假人一律被代打，分數在 features/seal/bots.py，上面的 features_core.bot_pick 問它（全部拆包第 28 批）
    # 頭目戰（duel:）、擂台（arena:）搬進功能包：假人的分數在 features/bout/bots.py，上面的 features_core.bot_pick 問它（全部拆包第 12 批）
    if kind == "choice":
        event = game.content.events[game.state.pending_event]
        effect = event.choices[int(arg)].effect
        moved = rules.resolve_trends(game.content, game.state.world, effect.trend, game.state.player.location)
        return effect_score(effect, _goals(game, profile), moved)
    # 對話（talk:、parley:）搬進功能包：假人只按告辭，分數在 features/companions/bots.py，上面的 features_core.bot_pick 問它（全部拆包第 20 批）
    # 懸賞榜（bounty:）搬進功能包：假人的分數在 features/bounties/bots.py，上面的 features_core.bot_pick 問它（全部拆包第 45 批）
    # 鐵匠鋪（smith:）搬進功能包：假人的分數在 features/smithy/bots.py，上面的 features_core.bot_pick 問它（全部拆包第 41 批）
    # 酒肆（tavern:）搬進功能包：假人的分數在 features/tavern/bots.py，上面的 features_core.bot_pick 問它（主動搬六包第 10 批）
    # 馬市（market:）搬進功能包：假人的分數在 features/gear/bots.py，上面的 features_core.bot_pick 問它（全部拆包第 42 批）
    # 求見（call:）搬進功能包：假人只按返回，分數在 features/socialize/bots.py，上面的 features_core.bot_pick 問它（全部拆包第 21 批）
    # 往哪裡走（move:）搬進功能包：分數在 features/travel/bots.py，上面 features_core.bot_pick 之前那一行問它（要 profile，掛鉤沒有；全部拆包第 47 批）
    if kind == "act":  # act:<子動詞>：分數問那一格的主人（Verb.bot、tail_bot，全部拆包第 60 批）；只有醫館療傷沒有主人（第 57 批第四節）
        if arg == "heal":  # 醫館療傷：look_after 已經先療了，萬一還在選單上（照顧動作沒輪到）付得起就按
            return _clinic_score(game) if wants_heal(game) else None
        owned, value = features_core.act_score(game, arg, profile)
        return value if owned else ACT_SCORES.get(arg, 0.0)
    # 打點那一間店（dadian:）、軍需官那一串（donate:）搬進功能包：假人只會離開，分數在 features/outlets/bots.py，上面的 features_core.bot_pick 問它（全部拆包第 43 批）
    return None


def effect_score(effect: Effect, goals: dict[str, int], trend: dict[str, int] | None = None) -> float:
    """選項效果的分數：把大勢往陣營想要的方向推，一點抵十分；能力、心得、銀兩、名望等獎勵每點 0.1 分。
    trend 是照 rules.resolve_trends 換過鍵的推動（front 換成所在戰線）；不給就照效果原本寫的。"""
    pushes = effect.trend if trend is None else trend
    push = sum(goals.get(trend_id, 0) * delta for trend_id, delta in pushes.items())
    reward = sum(max(0, effect.stats.get(key, 0)) for key in REWARD_STATS)
    return TREND_WEIGHT * push + reward / 10


def _smith_want(game: Game) -> str | None:
    """此刻在鐵匠鋪最該按的那一顆（本體在鐵匠鋪包的 bots.want；tests 讀這個名字）。"""
    return smithy_bots.want(game)
