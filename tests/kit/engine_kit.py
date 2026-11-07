"""tests/core/test_engine.py 拆走的測試與留下的測試共用的小工具（全部拆包第 61 批，只搬位置、不改內容）。"""
import random
from unittest import mock
from conftest import at, install_season_one, walk_to
from tianxia import atlas, battle_instance, companion_agent, fight_llm
from tianxia.engine import Game
from tianxia.martial_arts import generate_from_name
from tianxia.models import Effect, Location

HOUR = 3600
DAY = 86400


def ids(game):
    return [o.id for o in game.options()]


# ── 讀檔清理（武學與成長計畫 T10）──────────────────────────


def _reload(game, content, world):
    return Game(content, game.state, rng=random.Random(0), world=world).state.player


def _a_fused_art(world, name="旋風腿"):
    """全服登記一門合成的武學（修練、定名都要它存在於全服）。"""
    art = generate_from_name(name, "武學", name).model_copy(update={"origin": "fused", "insight": "feng", "creator": "舊檔"})
    assert world.claim_skill_name(art)
    return art


# ── 深度對話（companion_agent.py 的引擎接線）────────────────


FAKE_TURN = companion_agent.CompanionTurn(
    narrative="他點了點頭。", options=["閒聊幾句", "就此告辭"], option_tags=["尋常寒暄", "尋常寒暄"],
)


# ── 練功、療傷 ───────────────────────────────────────────


def _wear(game, wugong: str | None = None, neigong: str | None = None):
    """直接把內容裡的武學配到身上（第一成）：自創已經作廢，測試要「先有一門功夫」就這樣借。"""
    member = game.state.player.member
    if wugong:
        member.wugong_id, member.wugong_level = wugong, 1
    if neigong:
        member.neigong_id, member.neigong_level = neigong, 1


def _practice_step_game(game, worn: dict[str, int]):
    """把引導換成「第 1 步＝鍛鍊」（fixture 的引導沒有這一步，照 _install_* 的慣例直接裝進內容），
    身上先配好 worn（種類 → 熟練度），並給足心得（練成要花心得，這裡驗的是引導不是價錢）。回傳（引導步驟的獎勵銀兩）。"""
    from tianxia.models import Effect, TutorialGoal, TutorialStep

    for kind, level in worn.items():
        _wear(game, **{"neigong" if kind == "內功" else "wugong": "breath" if kind == "內功" else "fist"})
        slot = "neigong" if kind == "內功" else "wugong"
        setattr(game.state.player.member, f"{slot}_level", level)
    game.state.player.stats["xinde"] = 100
    reward = 10
    game.content.tutorial.steps = [
        TutorialStep(
            id="t4_practice", text="先修練。", done_when=TutorialGoal(action="practice"),
            reward=Effect(stats={"silver": reward}),
        ),
        TutorialStep(id="t5_next", text="出城。", done_when=TutorialGoal(action="move")),
    ]
    game.state.player.tutorial_step = 0
    return reward


def _wugong_step_game(game, worn: dict[str, int]):
    """把引導換成「看地圖 → 身上要有一門武學（has_wugong）→ 出城」；身上先配好 worn（種類 → 熟練度），引導停在
    看地圖那一步。回傳 has_wugong 那一步的獎勵銀兩。正式內容的 t4_practice 已經改成看「練功」這個動作
    （開局就送了武學，has_wugong 一開始就成立，教不到練成），這裡留著測 has_wugong 這種條件本身。"""
    from tianxia.models import Effect, TutorialGoal, TutorialStep

    for kind, level in worn.items():
        _wear(game, **{"neigong" if kind == "內功" else "wugong": "breath" if kind == "內功" else "fist"})
        setattr(game.state.player.member, f"{'neigong' if kind == '內功' else 'wugong'}_level", level)
    reward = 10
    game.content.tutorial.steps = [
        TutorialStep(id="t2_map", text="看地圖。", done_when=TutorialGoal(action="view_map")),
        TutorialStep(
            id="t4_practice", text="先修練。", done_when=TutorialGoal(has_wugong=True),
            reward=Effect(stats={"silver": reward}),
        ),
        TutorialStep(id="t5_next", text="出城。", done_when=TutorialGoal(action="move")),
    ]
    game.state.player.tutorial_step = 0
    return reward


def _legacy_hurry(game, dest):
    """拿掉趕路（企劃者 2026-10-12）之前以趕路出發、還在路上的那一趟：選單與地圖都不再給趕路，直接從 _depart 出發。"""
    return game._depart(atlas.way_to(game.state, game.content, dest), "hurry")


# ── 全服即時多人戰鬥（設計討論：集結選陣營→逐幕逐回合鎖步）──────────


def _three_moves_options(*sides):
    """每一邊的三招：<陣營>_strong／_hold／_raid，寫 move 與陣營（決戰改版一）。"""
    from tianxia.models import MOVES, BattleOption

    codes = {"強攻": "strong", "固守": "hold", "奇襲": "raid"}
    return [BattleOption(text=f"{s}{m}", tag=f"{s}_{codes[m]}", faction=s, move=m) for s in sides for m in MOVES]


def _install_battle_def(content):
    from tianxia.models import BattleAct, BattleDef, BattleFaction, BattleOutcome

    definition = BattleDef(
        id="t1", name="測試決戰",
        factions=[BattleFaction(id="guan", name="官軍"), BattleFaction(id="huang", name="黃巾")],
        acts=[BattleAct(id="a1", title="初探", text="雙方試探。", goal="推動戰局", options=_three_moves_options("guan", "huang"))],
        outcomes=[BattleOutcome(faction="guan", title="官軍大勝", text="官軍獲勝。")],
        muster_seconds=600, round_seconds=120,
        rounds_per_act=1,  # 一幕一回合：第一回合結算完就看戰局收場（保底結果沒有門檻，一定是官軍大勝）
    )
    content.battles[definition.id] = definition
    return definition


def _install_three_move_battle(content):
    """三招的決戰（戰鬥系統 3.4）：一幕三回合，兩邊各有強攻、固守、奇襲。"""
    from tianxia.models import MOVES, BattleAct, BattleDef, BattleFaction, BattleOption, BattleOutcome

    codes = {"強攻": "strong", "固守": "hold", "奇襲": "raid"}
    definition = BattleDef(
        id="t3", name="三招決戰",
        factions=[BattleFaction(id="guan", name="官軍"), BattleFaction(id="huang", name="黃巾")],
        acts=[BattleAct(
            id="a1", title="對陣", text="兩軍對陣。", goal="推動戰局",
            options=[BattleOption(text=f"{s}{m}", tag=f"{s}_{codes[m]}", faction=s, move=m)
                     for s in ("guan", "huang") for m in MOVES],
        )],
        outcomes=[BattleOutcome(faction="guan", title="收場", text="戰罷。")],
        muster_seconds=600, round_seconds=120, rounds_per_act=3,
    )
    content.battles[definition.id] = definition
    return definition


def _open_three_move_battle(game):
    """開一場三招的仗、本人加入官軍、集結時間撥到過去，進到開打。"""
    definition = _install_three_move_battle(game.content)
    game.content.config.admins = [game.state.player.name]
    game.now = 0.0
    game.admin_start_battle(definition.id, now=0.0)
    game._battle_choose("join:guan")
    game.world.mutate_battle(lambda b: setattr(b, "muster_deadline_real", -1.0))
    game._run_battle_tick(definition)
    return game.world.get_battle(), definition


def _strip_scores(game, name=None):
    """把這個人在戰局上的份量快照拿掉：模擬上線前就在決戰裡的人（舊資料沒有 scores）。"""
    name = name or game.state.player.name
    game.world.mutate_battle(lambda b: b.participants[name].scores.clear())
    assert game.world.get_battle().participants[name].scores == {}


def _install_factions(content):
    from tianxia.models import FactionDef

    content.scenario.factions = [
        FactionDef(id="guan", name="官軍", join_at=["town"]),
        FactionDef(id="huang", name="黃巾"),
        FactionDef(id="haoqiang", name="地方豪強"),
    ]


# ── 地方豪強在決戰臨時投效兩軍之一（Joy 2026-10-13「豪強在大決戰還是要加入某一陣營，主軸還是官兵跟黃巾」）──


def _as_warlord(game):
    """本人是地方豪強；開一場三招決戰（只有官軍、黃巾兩軍）。"""
    _install_factions(game.content)
    game.state.player.faction = "haoqiang"
    return _install_three_move_battle(game.content)


def _warlord_in_battle(game, side="guan"):
    """豪強本人臨時投效 side、集結撥到過去、開打；回傳 (這一場, 定義)。"""
    definition = _as_warlord(game)
    game.content.config.admins = [game.state.player.name]
    game.now = 0.0
    game.admin_start_battle(definition.id, now=0.0)
    game._battle_choose(f"enlist:{side}")
    game.world.mutate_battle(lambda b: setattr(b, "muster_deadline_real", -1.0))
    game._run_battle_tick(definition)
    return game.world.get_battle(), definition


# ── 決戰的結果送到每個參戰者手上（FB-027：下次同步時補）──────────────


def _three_round_showdown(content, trend_delta=None):
    """劇本分陣營、一幕三回合（整場 3 回合；穩紮穩打只推 1，不會提前收場），保底結果官軍大勝。"""
    _install_factions(content)
    definition = _install_battle_def(content)
    definition.rounds_per_act = 3
    definition.outcomes[0] = definition.outcomes[0].model_copy(update={"trend_delta": trend_delta or {"kou": -20}})
    return definition


def _fighter(content, game, name, faction):
    """跟沈浪同一個全服世界的另一位玩家（自己的一份 Game），已經投靠 faction。"""
    other = Game.new(content, name, rng=random.Random(1), world=game.world)
    other.state.player.faction = faction
    return other


def _fight_to_the_end(game, definition, now):
    """沈浪每回合自己出手，其他還在場上的人逾時由系統代選，一路打到收場；回傳收場那一刻的時間。"""
    for _ in range(100):  # 選項不對時不會有人收場：失敗，不要永遠轉下去
        with at(game, now):
            game.options()  # 推進：集結關閉，或上一回合逾時、代選、結算
            battle = game.world.get_battle()
            if battle.phase == "ended":
                return now
            if game.state.player.name not in battle.round.pending_actions:
                game.choose("battle:act:guan_hold")
        now = game.world.get_battle().round.opened_real + definition.round_seconds
    raise AssertionError("打了 100 回合還沒收場")


# ── 決戰要人在那個大區才打得到（地圖擴充設計第六節）──────────────


def _south_cave(content, game):
    """寶洞搬進南區（夾具的三個地點本來都在北區）並打開。"""
    content.locations["cave"].y = 170
    game.state.world.flags.add("cave_open")


def _joined_a_battle_in_the_north(content, game):
    """測試北區的一場決戰，沈浪在集結時站官軍；南區另有寶洞（_south_cave）可去。回傳那一場的定義。"""
    definition = _install_battle_def(content)
    definition.region = "north"
    _south_cave(content, game)
    game.world.start_battle(definition, now=0.0)
    with at(game, 0.0):
        game.choose("battle:join:guan")
    return definition


# ── 自訂行動輸入框（設計討論：魯莽該是玩家自己想出來的招，不是固定選單）────────


def _install_battle_def_with_free_text(content):
    from tianxia.models import BattleAct, BattleDef, BattleFaction, BattleOption, BattleOutcome

    definition = BattleDef(
        id="t2", name="測試決戰（自訂行動）",
        factions=[BattleFaction(id="guan", name="官軍"), BattleFaction(id="huang", name="黃巾")],
        acts=[
            BattleAct(
                id="a1", title="初探", text="雙方試探。", goal="推動戰局",
                options=_three_moves_options("guan") + [
                    BattleOption(text="放手一搏（20字內）", tag="reckless", faction="guan", free_text=True),
                ] + _three_moves_options("huang"),
            ),
        ],
        outcomes=[BattleOutcome(faction="guan", title="官軍大勝", text="官軍獲勝。")],
        muster_seconds=600, round_seconds=120,
        rounds_per_act=1,  # 一幕一回合，同 _install_battle_def
    )
    content.battles[definition.id] = definition
    return definition


def _join_and_open(content, game, definition):
    game.world.start_battle(definition, now=0.0)
    with at(game, 0.0):
        game.choose("battle:join:guan")
        game.world.mutate_battle(
            lambda b: battle_instance.join_faction(b, "機器人", "huang", neili_cap=100.0, is_bot=True)
        )
    after_muster = definition.muster_seconds + 1
    with at(game, after_muster):
        game._battle_status()
    return after_muster


# ── 管理者觸發（伺服器假人計畫 Task 8）────────────────────────


def _admin(content, game):
    content.config.admins = [game.state.player.name]
    return game


# ── 大場面請模型判讀（武學與成長設計 8.3、計畫三 Task 2）──────────────────────

JUDGMENT = fight_llm.Judgment(advantage=15, winning="佔上風的過程。", losing="落下風的過程。")
ACCOUNTS = (JUDGMENT.winning, JUDGMENT.losing)


def _boss_at_the_lake(game):
    game.content.locations["lake"].enemies = ["boss"]
    walk_to(game, "lake")
    game.state.player.member.wugong_id = "basic_fist"


def _judged(request, judgment=JUDGMENT):
    return fight_llm.PreparedFight(request=request, judgment=judgment)

def _training_factions(content):
    from tianxia.models import FactionDef

    content.scenario.factions = [
        FactionDef(id="guan", name="官軍", join_at=["town"], goals={"kou": -1}),
        FactionDef(id="huang", name="黃巾", join_at=["lake"], goals={"kou": 1}),
        FactionDef(id="haoqiang", name="地方豪強"),
    ]


def _figure(content, fame=0):
    ch = content.characters["mate"]
    ch.deep_interaction = True
    ch.audience_fame = fame
    return ch


def _prepared(game, option_id, turn=FAKE_TURN):
    req = game.dialogue_request(option_id)
    return companion_agent.PreparedTurn(req.option_id, req.companion_id, req.player_action, turn)


NEXT_TURN = companion_agent.CompanionTurn(
    narrative="他笑了笑。", options=["再聊聊", "起身告辭"], option_tags=["雪中送炭", "尋常寒暄"],
)


def _no_model():
    """讓任何一條「在鎖內生成」的路徑直接失敗，證明這輪用的是預先生成好的。"""
    return mock.patch.object(companion_agent, "_generate", side_effect=AssertionError("不該在鎖內生成"))


def _spy_battle_status(game):
    """記下每次 _battle_status 是用 tick=True 還是 tick=False 呼叫的。"""
    calls = []
    real = type(game)._battle_status

    def spy(self, tick=True):
        calls.append(tick)
        return real(self, tick=tick)

    return calls, mock.patch.object(type(game), "_battle_status", spy)


# ── 路上：改道與折返（路上設計第三節）──────────────────────────


def _add_field(content):
    """夾具只有一條線（小鎮—湖邊—寶洞）；在小鎮西邊加一塊田（一般路，3 分鐘），讓掉頭之後有別處可去。"""
    content.locations["field"] = Location(id="field", name="田野", description="一片田。", connections=["town"], x=0, y=100)
    content.locations["town"].connections.append("field")


def _partway(game, share=1 / 3):
    """從小鎮步行往湖邊（夾具 3 分鐘），把時間推到走了 share 成的那一刻；回傳這一趟。"""
    game.choose("move:lake")
    game.advance(180 * share)
    return game.state.player.journey


# ── 指名求見（兩位以上大勢人物的地點，企劃者 2026-10-03 決定）──────────


def _hall(content, game, mate_fame=0, scholar_fame=0):
    """把小鎮變成兩位大勢人物的地點：韓鐵、書生（recruit_at 本來就是小鎮）都開深度對話。小鎮有交友事件（拜師）；
    福緣設成已領，交友不會先送福緣。"""
    for cid, fame in (("mate", mate_fame), ("scholar", scholar_fame)):
        content.characters[cid].deep_interaction = True
        content.characters[cid].audience_fame = fame
    game.state.player.fortune = True


def _labels(game):
    return {o.id: (o.label, o.enabled) for o in game.options()}


# ── 求見一直都在，門檻不夠就打發（武學與成長設計 9.1）──────────


def _stand_by_one_figure(content, game, fame=30):
    """小鎮只剩韓鐵一位大勢人物（夾具裡其他人都沒開深度對話），名望門檻 fame；他有一句打發話。福緣設成已領。"""
    ch = _figure(content, fame=fame)
    ch.brush_off = ["閒雜人等退下。"]
    game.state.player.fortune = True
    return "mate"


# ── 三場大戲（計畫 T8）：照時刻表開集結、收場的結果餵給時刻表 ────────────────────


def _showdown_game(content, world, name="沈浪", faction="guan"):
    """第一季內容＋三筆時刻表決戰（北區打，小鎮就在北區）＋陣營；第 3、4 週的擲骰先記成跳過，戰線停在開季的數字
    （潁川 40、南陽 35），起點才算得準。回傳站在 faction 的 Game（現實時間 0）。"""
    from conftest import install_showdowns
    from tianxia.state import TimelineResult

    if not content.config.season_one:
        install_season_one(content)
        install_showdowns(content)
        _install_factions(content)
    game = Game.new(content, name, rng=random.Random(0), world=world)
    game.state.player.faction = faction
    game.now = 0.0
    skipped = {e: TimelineResult(key="skip", time=0.0) for e in ("zhangmancheng", "bocai")}
    game.world.mutate_season(lambda s: s.timeline.update({k: v for k, v in skipped.items() if k not in s.timeline}))
    game.state.world = game.world.get_season()
    return game


def _to_showdown(game, event_id: str, after: float = 1.0) -> list[str]:
    """把季推進到這件決戰排定的時間再過 after 世界秒（遊戲時間；現實時間 game.now 不動）。"""
    return game.advance(game.state.world.schedule[event_id] + after - game.state.world.time)


def _play_showdown(game, tag: str) -> None:
    """自己一個人參戰（集結時加入），集結截止後每回合都出 tag，一路打到收場。"""
    with at(game, game.now):
        game.choose(f"battle:join:{game.state.player.faction}")
    now = game.world.get_battle().muster_deadline_real
    for _ in range(100):  # 出的招不在選單上時 choose 會悄悄拒絕：以前這裡就永遠轉下去，現在是失敗
        if game.world.get_battle().phase == "ended":
            return
        with at(game, now):
            game.choose(f"battle:act:{tag}")
        now += 1
    raise AssertionError(f"打了 100 回合還沒收場：{tag} 大概不是這一邊的選項")
