"""same_behavior 一軌一檔：switchboard（這一檔登記 switchboard）。"""
from __future__ import annotations

import hashlib
import json
import random
from pathlib import Path

from sb.base import Scenario
from sb.harness import ADMIN, CLOCK, STEP, emit, new_ops, register_track

# ═══════════════════════════ 動作表一軌（全部拆包第 68 批：伺服器分包一）═══════════════════════════


# 三張動作表的每一個 op → body 的鍵（順序照表；寫死在這裡：表搬去哪、合起來的順序變不變，這裡都不跟著變）
SWITCH_MAIN = {
    "seclude": ("hours",), "smith_forge": ("kind", "main", "aux"), "smith_sell": ("material", "count"), "smith_upgrade": ("attribute", "tier"), "smith_furnace": (),
    "donate": ("material", "count"), "tavern": ("op", "target", "text"), "anonymous": ("value",), "gender": ("value",), "story_seen": (),
    "letter_read": ("id",), "letter_decline": ("id",), "hints_off": ("value",), "skip_tutorial": (), "view_map": (), "view_orders": (), "view_tab": ("tab",),
    "guide_ack": (), "allocate": ("stat",), "growth": ("preset", "split"), "newbie_drifter": (), "pill": (), "checkin": ("attribute",), "conquest_letter": ("loc",),
    "seal_use": ("target", "side"), "sortie_go": ("moves",), "sortie_answer": ("id", "moves"), "sortie_join": ("id",), "outing": ("n",),
}
SWITCH_ADMIN = {
    "outing_erase": ("id",), "open_season": (), "end_season": (), "next_season": (), "pause_clock": (), "resume_clock": (), "fast_forward": ("hours",),
    "start_battle": ("id",), "fire": ("id",), "push_trend": ("id", "amount"), "schedule": ("id", "at"), "jump_next": (), "set_trend": ("id", "value"),
    "resolve_event": ("id", "key"), "clear_lock": ("id",), "cancel_battle": (), "revive_figure": ("id",), "issue_orders": (), "rotate_seats": (),
    "start_showdown": ("id",), "summon": ("name",), "give_opportunity": ("name", "id"), "give_fragment": ("name", "id"), "seal_emerge": ("id",), "seal_stir": ("id",),
    "seal_assign": ("id", "name", "state"), "seal_duel": ("id", "name", "factor"), "seal_fix": ("take",), "seal_cancel": (), "seal_sink_check": (), "seal_mandate": ("when",),
    "mingtie_remove": ("name", "version"), "mingtie_restore": ("name", "version"),
}
SWITCH_MENXIA = {
    "practice": ("kind",), "heal": (), "forge": ("art", "insights"), "switch": ("art",), "slot": ("art", "insight", "index"), "unslot": ("art", "insight"),
    "create_begin": ("kind", "form"), "create_pose": ("pose",), "create_back": ("to",), "create_name": ("name", "move"), "create_cancel": (), "create_reroll": (),
    "ascend_dismiss": (), "cultivate": ("art", "use_legend"), "melt": ("art",), "melt_insight": ("insight",), "melt_many": ("arts", "insights"), "name": ("name",),
    "name_divine": ("weapon", "name", "keep"), "bind_art": ("weapon", "art"), "join": ("person",), "leave": ("person",), "release": ("person",), "wield": ("weapon",),
    "dismantle": ("weapon",), "feed": (), "repair_item": ("item", "weapon"), "temper_item": ("item", "weapon"), "dismantle_many": ("items",), "chuangong": ("person", "what"),
}
# 換位置的那 20 個管理者工具（暫停中照做 paused_ok 是表的一部分，一個一個打；留在殼的那 13 個一個字沒動）
SWITCH_TOOLS = (
    "outing_erase", "start_battle", "cancel_battle", "revive_figure", "issue_orders", "rotate_seats", "start_showdown", "summon", "give_opportunity", "give_fragment",
    "seal_emerge", "seal_stir", "seal_assign", "seal_duel", "seal_fix", "seal_cancel", "seal_sink_check", "seal_mandate", "mingtie_remove", "mingtie_restore",
)
SWITCH_JUNK = (None, -3, True, "長" * 90, ["甲"], {"鍵": 1})  # 型別不對、負的、太長：每一格的轉型與預設值都在這幾樣上分得出來
SWITCH_MORE = {  # 只有這樣送才走得到的那一條（清單、布林只認 True、切字數、夾下限）
    "seclude": ({"hours": 3},),
    "smith_sell": ({"material": "rou_1", "count": 0},),
    "smith_upgrade": ({"attribute": "剛", "tier": 2},),
    "donate": ({"items": [{"material": "rou_1", "count": 2}, {"count": 3}, "壞的"]}, {"items": "不是清單"}, {"material": "rou_1", "count": 3}),
    "tavern": ({"op": "news"}, {"op": "wall", "text": "長" * 60}, {"op": "seek", "target": "長" * 30}),
    "growth": ({"preset": "custom", "split": {"str": 1}},),
    "checkin": ({"attribute": "剛柔快慢"},),
    "seal_use": ({"target": "長" * 50, "side": "長" * 30},),
    "sortie_go": ({"moves": "強攻、固守，奇襲,再一招,又一招,第六招,第七招"},),
    "sortie_answer": ({"id": "長" * 100, "moves": "強攻,固守,奇襲"},),
    "sortie_join": ({"id": "長" * 100},),
    "outing": ({"n": 3},),
    "practice": ({"kind": "內功"},),
    "slot": ({"art": "a", "insight": "b", "index": 2}, {"art": "a", "insight": "b", "index": -2}),
    "melt_many": ({"arts": ["a", 1, None], "insights": ["b"]},),
    "dismantle_many": ({"items": ["兵:1", 5, None]},),
    "repair_item": ({"weapon": "兵:9"},),
    "temper_item": ({"weapon": "兵:9"},),
    "create_name": ({"name": "名", "move": "長" * 60},),
    "cultivate": ({"art": "a", "use_legend": "true"},),
    "name_divine": ({"weapon": "兵:1", "keep": "true"}, {"weapon": "兵:1", "keep": True}),
    "chuangong": ({"person": "player", "what": "str"},),
    "join": ({"person": "player"},),  # 名冊上的人（其他都在名冊那一關就回了，碰不到表上那一條）
    "leave": ({"person": "player"},),
    "release": ({"person": "player"},),
    "seal_duel": ({"id": "x", "name": "y", "factor": "壞"},),
    "seal_fix": ({"take": "true"},),
    "seal_assign": ({"id": "x", "name": "y"},),
}
SWITCH_SPIES = {  # 表上的 lambda 最後叫到的那一支（包裡的函式；Game 的委派與搬過去之後的表都經過模組的屬性叫它）：它收到什麼一個字一個字記下來
    "tianxia.features.seclusion.actions": ("seclude",),
    "tianxia.features.smithy.forge_actions": ("smith_forge", "smith_furnace"),
    "tianxia.features.smithy.trade_actions": ("smith_sell", "smith_upgrade"),
    "tianxia.features.smithy.divine_actions": ("name_divine", "bind_art"),
    "tianxia.features.smithy.gear_actions": ("repair_item", "temper_item"),
    "tianxia.features.outlets.donate_actions": ("donate", "donate_items"),
    "tianxia.features.tavern.actions": ("tavern_do",),
    "tianxia.features.story.actions": ("story_seen",),
    "tianxia.features.companions.actions": ("read_letter", "decline_letter", "add_to_team", "remove_from_team", "release_companion"),
    "tianxia.features.guide.actions": ("set_hints_off", "skip_tutorial", "view_map", "view_orders", "view_tab", "guide_ack", "newbie_drifter"),
    "tianxia.features.cultivation.actions": ("allocate_stat", "practice", "switch_art", "slot_insight", "unslot_insight", "ascend_dismiss", "cultivate", "melt_art",
                                             "melt_insight", "melt_many", "name_mastered", "chuangong"),
    "tianxia.features.checkin.actions": ("check_in",),
    "tianxia.features.territory_acts.letter_actions": ("conquest_letter",),
    "tianxia.features.seal.card": ("use",),
    "tianxia.features.seal.admin": ("emerge", "stir", "assign", "duel", "fix", "cancel", "sink_check", "mandate"),
    "tianxia.features.sortie.duel_actions": ("sortie_go", "sortie_answer", "sortie_join"),
    "tianxia.features.explore.outing_actions": ("outing_go", "admin_erase_inscription"),
    "tianxia.features.battle.admin": ("admin_start_battle", "admin_cancel_battle", "admin_start_showdown"),
    "tianxia.features.figure_acts.admin_actions": ("revive_figure",),
    "tianxia.features.military.admin_actions": ("issue_orders", "rotate_seats", "summon"),
    "tianxia.features.military.opp_actions": ("give_opportunity",),
    "tianxia.features.military.fs_actions": ("give_fragment",),
    "tianxia.features.peers.mingtie_actions": ("admin_remove", "admin_restore"),
    "tianxia.features.craft.actions": ("begin", "pose", "back", "name", "cancel", "reroll"),
    "tianxia.features.gear.bench_actions": ("wield_weapon", "dismantle_weapon", "feed_mount", "dismantle_many"),
}


class SwitchboardScenario(Scenario):
    """三張動作表一軌（全部拆包第 68 批；--track switchboard，自己一個資料庫）。班底的名字都是原創（PM 11/04）。
    每一個 op 照表的順序打一次，對照的是「表怎麼把網頁送來的東西轉成參數、擋在哪裡」，所以：叫到包裡那一支時把它收到的參數逐字記下來（spy，
    Game 的委派與搬過去之後的表都經過模組的屬性叫它）；每打一下把人的存檔放回去（閉關、走一趟不擋住下一個 op）；回應只記狀態碼、回話與畫面的雜湊，整段才不會太大。

    前半（照段落順序）：setup 籌備中建人（test 設定開局就開季）；tables 三張表的鍵（順序算數）、管理者兩張表合起來的名字、暫停中照做與動到別人存檔的那兩張；
    strangers 沒登入每個 op 打一次（401）、跨表與不認得的 op（/api/do 沒登入 401、登入了 404；/api/menxia 一律先 404）；not_admin 玩家按每個管理者動作（400）；
    preparing 籌備中按每個玩家動作：checkin、name_divine、bind_art、join、leave、release 六個擋在 Game 委派的裝飾器上、包裡的函式不擋（這六支 spy 一次都沒響；test 把 Game._preparing 換成真）；
    opened 開季、過教學、兩軍擺到同一處；main_ops、menxia_ops 兩張表每一個 op：空的 body、六種壞值、SWITCH_MORE 那幾個（回話大多是拒絕，看的是轉型之後的參數）；
    half 寫到一半：墨衡自創起了手、貼了約戰（test 約戰關著，回「此刻無法」），管理者把季暫停——舊程式停在這裡。
    後半是重開的伺服器：resume 重新登入；paused 接手舊程式暫停的季：玩家動作照 PAUSE_OK_ACTIONS 分兩邊（其餘 400「賽季暫停中」）、換位置的 20 個管理者工具一律進得了引擎（引擎自己回「先按繼續」的也算）；
    unpaused 繼續、接著做舊程式寫到一半的：聞笛應戰、墨衡擺式成了（「此式偏剛」）、立名回「先立意」（立意是三段式、不在動作表）、擱下；
    core_ops 別軌都沒打到、留在殼裡的 8 個：匿名開關、性別（定了改不了那一句）、療傷（氣血無恙那一句）、推得動的大勢線、定戰況、排時間（test 沒有時刻表，回一句）、清鎖定、跳下一件；
    admin_ops 管理者表每一個 op（季的三顆除外）：空的 body、六種壞值；targets 動到別人存檔的 op 帶真的名字（_tell_tabs 第二個參數是那個名字；mingtie_restore、outing_erase 不在那張表，是空字串）；
    accounts 管理頁重設密碼那兩條（第二輪第 90 批補）：沒登入、玩家擋住，管理者搜帳號、重設（查無此人、太短、太長、照名號、照帳號），重設之後舊密碼登不進、舊的工作階段失效、臨時密碼登得進；
    bots 假人兩個若干輪（假人走 Game 的公開方法、不走動作表，這一段確定委派沒被動到；test 沒有輪到假人，online 0）；season 收季、休季每個玩家動作打一次、開下一季。
    管理頁（/api/admin、/api/admin/player）在 setup、opened、half、core_ops、admin_ops、season 的尾巴整份記下來（畫面逐字不變）。

    這一軌走不到的：動作成功的那一條大多在各包自己的軌（計畫第二節有表）；/api/do 在查表之前先接走的十一個 op（outing_say 到 persuade_text，不在表上，三段式是第 69 批）；真的瀏覽器（web/ 沒動）。"""

    PLAYERS = {"墨衡": "guan", "聞笛": "huang"}
    NEWBIE = "未央客"
    BOT_SEATS = ["衡甲", "衡乙"]
    MO, WEN = "墨衡", "聞笛"
    LOC = "runan_wilds"
    PHASES_FIRST = ["setup", "tables", "strangers", "not_admin", "preparing", "opened", "main_ops", "menxia_ops", "half"]
    PHASES_SECOND = ["resume", "paused", "unpaused", "core_ops", "admin_ops", "targets", "accounts", "bots", "season"]

    def __init__(self, root: Path, profile: str, db: Path):
        super().__init__(root, profile, db)
        import importlib

        self.spying = False
        for path, names in SWITCH_SPIES.items():
            module = importlib.import_module(path)
            for name in names:
                setattr(module, name, self._spy(path.rsplit(".", 2)[-2], name, getattr(module, name)))
        real_tell = self.server._tell_tabs

        def tell(game, also: str = "") -> None:
            if self.spying:
                emit("→ _tell_tabs", also)
            return real_tell(game, also)

        self.server._tell_tabs = tell

    def _spy(self, package: str, name: str, real):
        def spied(*args, **kwargs):
            if self.spying:
                emit(f"→ {package}.{name}", json.dumps([args[1:], kwargs], ensure_ascii=False, default=str))
            return real(*args, **kwargs)

        return spied

    # ── 小工具 ──

    def factions_on(self) -> bool:
        return {"guan", "huang"} <= {f.id for f in self.c.scenario.factions}

    def probe(self, who: str | None, path: str, body: dict | None = None, *, keep: bool = False) -> None:
        """打一支（who 是 None：沒登入的人）；回應只記狀態碼、回話與畫面的雜湊。keep 以外打完把這個人的存檔放回去（下一個 op 從同一個局面打）。"""
        saved = self.chars.load(who) if who and not keep else None
        self.begin()
        client = self.clients[who] if who else self.TestClient(self.server.app)
        self.spying = True
        try:
            r = client.post(path, json=body if body is not None else {})
            try:
                raw = r.json()
            except Exception:  # noqa: BLE001
                raw = r.text[:200]
            data = ({k: hashlib.sha256(json.dumps(v, ensure_ascii=False).encode("utf-8")).hexdigest()[:16] if k in ("main", "menxia") else v for k, v in raw.items()}
                    if isinstance(raw, dict) else raw)
            status = r.status_code
        except Exception as exc:  # noqa: BLE001  伺服器丟出來的例外（TestClient 照丟）：兩份程式要丟一樣的
            status, data = "例外", f"{type(exc).__name__}: {exc}"
        finally:
            self.spying = False
        emit(f"{who or '沒登入'} {path} {json.dumps(body, ensure_ascii=False) if body else ''} {status}", data)
        if saved is not None:
            with self.world.action_lock():
                self.chars.save(saved)

    def bodies(self, op: str, keys: tuple) -> list[dict]:
        junk = [{k: v for k in keys} for v in SWITCH_JUNK] if keys else []
        return [{}, *junk, *SWITCH_MORE.get(op, ())]

    def sweep(self, who: str, table: dict, prefix: str, *, keep: bool = False, full: bool = True, skip: tuple = ()) -> None:
        for op, keys in table.items():
            if op not in skip:
                for body in self.bodies(op, keys) if full else [{}]:
                    self.probe(who, f"{prefix}/{op}", body, keep=keep)

    def admin_page(self, tag: str) -> None:
        """管理頁的兩條（畫面逐字不變：整份記）。"""
        self.begin()
        r = self.clients[ADMIN].get("/api/admin")
        emit(f"管理頁 {tag} {r.status_code}", r.json())
        self.begin()
        r = self.clients[ADMIN].post("/api/admin/player", json={"name": self.MO})
        emit(f"管理頁查人 {tag} {r.status_code}", r.json())

    # ── 前半 ──

    def setup(self) -> None:
        """同 Scenario.setup，但不開季：籌備中建人（test 設定開局就開季）。"""
        from tianxia.accounts import AccountStore
        from tianxia.engine import Game

        store = AccountStore(self.world.db)
        self.passwords[ADMIN] = "pw-admin-123456"
        with self.world.db.transaction():
            store.register(self.login_of(ADMIN), self.passwords[ADMIN])
            game = Game.new(self.c, ADMIN, world=self.world)
            self.chars.save(game.state)
            store.bind_character(self.login_of(ADMIN), ADMIN)
        self.clients[ADMIN] = self.TestClient(self.server.app)
        self.call(ADMIN, "POST", "/api/login", {"login": self.login_of(ADMIN), "password": self.passwords[ADMIN]})
        for who in [self.NEWBIE, *self.PLAYERS]:
            self.clients[who] = self.TestClient(self.server.app)
            self.passwords[who] = "pw-" + self.login_of(who)
            self.call(who, "POST", "/api/register", {"login": self.login_of(who), "password": self.passwords[who], "again": self.passwords[who]})
            self.call(who, "POST", "/api/character", {"name": who, "gender": "男"})
        self.admin_page("籌備中")

    def tables(self) -> None:
        """表本身：MAIN、MENXIA 的鍵照順序（分包之後合起來的順序不變）；管理者那一張會拆到功能包的工具，合起來照名字排；還有這一軌沒列到的 op。"""
        s = self.server
        new = new_ops(s)  # compare --new（第 106 批）：新包帶來的 op 扣掉；沒帶參數時三個都是空的
        emit("MAIN_ACTIONS 的鍵", [op for op in s.MAIN_ACTIONS if op not in new["main"]])
        emit("MENXIA_ACTIONS 的鍵", [op for op in s.MENXIA_ACTIONS if op not in new["menxia"]])
        leftover = getattr(s, "ADMIN_ACTIONS", {})  # 第二輪第 90 批把殼的那一張搬進管理者包（base 還有、head 沒有；合起來的名字不變）
        admin = (set(leftover) | set(s.FEATURE_ADMIN_ACTIONS)) - new["admin"]
        emit("管理者動作（兩張表合起來）", sorted(admin))
        emit("暫停中照做", sorted(s.PAUSE_OK_ACTIONS))
        emit("動到別人的存檔", sorted(s.PLAYER_ADMIN_ACTIONS))
        emit("這一軌沒列到的 op", [sorted(set(s.MAIN_ACTIONS) - set(SWITCH_MAIN) - new["main"]), sorted(set(s.MENXIA_ACTIONS) - set(SWITCH_MENXIA) - new["menxia"]), sorted(set(leftover) - set(SWITCH_ADMIN))])

    def strangers(self) -> None:
        """沒登入：每一個 op 一下（功能包的管理者工具也要 401、不是 404）；跨表的、不認得的 op。"""
        self.sweep(None, SWITCH_MAIN, "/api/do", keep=True, full=False)
        self.sweep(None, SWITCH_ADMIN, "/api/do", keep=True, full=False)
        self.sweep(None, SWITCH_MENXIA, "/api/menxia", keep=True, full=False)
        for path in ("/api/do/沒有這個", "/api/do/wield", "/api/do/practice", "/api/menxia/沒有這個", "/api/menxia/seclude", "/api/menxia/summon"):
            self.probe(None, path)
            self.probe(self.MO, path)

    def not_admin(self) -> None:
        """玩家按每一個管理者動作：一律「只有管理者能這麼做」，季的三顆也一樣。"""
        self.sweep(self.MO, SWITCH_ADMIN, "/api/do", full=False)

    def preparing(self) -> None:
        """籌備中：每一個玩家動作按一下。六個擋在 Game 委派裝飾器上的（checkin、name_divine、bind_art、join、leave、release）搬過去要照樣擋。"""
        from tianxia.engine import Game

        real = Game._preparing
        if self.profile == "test":  # 測試內容開局就開季：換成真（同 SenseScenario.preparing）
            Game._preparing = lambda game: True
        try:
            self.sweep(self.MO, SWITCH_MAIN, "/api/do", full=False)
            self.sweep(self.MO, SWITCH_MENXIA, "/api/menxia", full=False)
            self.probe(self.MO, "/api/do/checkin", {"attribute": "剛"})
            for op in ("join", "leave", "release"):  # 名冊上的人（不帶 person 的那一下在名冊那一關就回了，碰不到裝飾器）
                self.probe(self.MO, f"/api/menxia/{op}", {"person": "player"})
            self.probe(self.MO, "/api/menxia/name_divine", {"weapon": "兵:1", "keep": True})
        finally:
            Game._preparing = real

    def opened(self) -> None:
        """開季、過教學、兩軍擺到同一處。"""
        self.do(ADMIN, "open_season")
        for who, side in self.PLAYERS.items():
            self.do(who, "skip_tutorial")
            self.settle_choices(who)
            self.place(who, self.LOC, side if self.factions_on() else None)
            self.main(who)
        self.main(self.NEWBIE)  # 開季準備卡先按掉（暫停中按不掉，重新登入那一下會卡住）
        self.main(ADMIN)
        self.admin_page("開季")

    def main_ops(self) -> None:
        self.sweep(self.MO, SWITCH_MAIN, "/api/do")

    def menxia_ops(self) -> None:
        self.sweep(self.MO, SWITCH_MENXIA, "/api/menxia")

    def half(self) -> None:
        """前半停在寫到一半：墨衡自創起了手、貼了一張約戰（窗還開著），管理者把季暫停；接手的程式要接得起來。"""
        self.edit(self.MO, lambda p: p.stats.__setitem__("xinde", 20000))
        self.call(self.MO, "POST", "/api/menxia/create_begin", {"kind": "武學", "form": "拳腳"})
        self.do(self.MO, "sortie_go", {"moves": "強攻,固守,奇襲"})
        self.do(ADMIN, "pause_clock")
        self.admin_page("暫停")

    # ── 後半 ──

    def resume(self) -> None:
        self.login_all()

    def paused(self) -> None:
        """接手舊程式暫停的季：玩家動作照 PAUSE_OK_ACTIONS 分兩邊，換位置的 20 個管理者工具都照做（paused_ok）。"""
        self.sweep(self.MO, SWITCH_MAIN, "/api/do", full=False)
        self.sweep(self.MO, SWITCH_MENXIA, "/api/menxia", full=False)
        for op in SWITCH_TOOLS:
            self.probe(ADMIN, f"/api/do/{op}", keep=True)

    def unpaused(self) -> None:
        """繼續，接著把舊程式寫到一半的做完：應戰（約戰關著的 test 回一句）、擺式、立名（回「先立意」）、擱下。"""
        from tianxia.features.craft import create

        self.do(ADMIN, "resume_clock")
        duels = sorted(self.world.sortie_duels().values(), key=lambda d: (d.opened_at, d.id))
        posted = next((d.id for d in reversed(duels) if d.attacker.name == self.MO), "s0-none")
        self.probe(self.WEN, "/api/do/sortie_answer", {"id": posted, "moves": "固守,固守,固守"}, keep=True)
        self.probe(self.MO, "/api/menxia/create_pose", {"pose": create.preset(self.c, "進擊")}, keep=True)
        self.probe(self.MO, "/api/menxia/create_name", {"name": "衡山一式", "move": "接雲式"}, keep=True)  # 立意是三段式、不在動作表：這一下回「先立意」
        self.probe(self.MO, "/api/menxia/create_cancel", keep=True)
        self.main(self.MO)

    def core_ops(self) -> None:
        """別軌都沒打到、留在殼裡的 8 個：匿名、性別、療傷、推大勢、定戰況、排時間、跳下一件、清鎖定。"""
        self.begin()
        page = self.clients[ADMIN].get("/api/admin").json()
        trend = next((t["id"] for t in page.get("trends") or []), "")  # 照這一季的規則推得動的第一條（黃巾聲勢是合成的，不列）
        rows = page.get("timetable") or []
        emit("推得動的大勢線、時刻表", [trend, rows])
        item = next((r["id"] for r in rows if r.get("schedulable")), "")  # 排得了時間的第一件（三場決戰與季末；測試內容沒有時刻表）
        self.probe(self.MO, "/api/do/anonymous", {"value": True}, keep=True)
        self.probe(self.MO, "/api/do/anonymous", {"value": False}, keep=True)
        self.probe(self.NEWBIE, "/api/do/gender", {"value": "女"}, keep=True)
        self.probe(self.MO, "/api/menxia/heal", keep=True)
        self.probe(ADMIN, "/api/do/push_trend", {"id": trend, "amount": 5}, keep=True)
        self.probe(ADMIN, "/api/do/set_trend", {"id": trend, "value": 40}, keep=True)
        self.probe(ADMIN, "/api/do/schedule", {"id": item, "at": CLOCK[0] + 7200.0}, keep=True)
        self.probe(ADMIN, "/api/do/clear_lock", {"id": item}, keep=True)
        self.probe(ADMIN, "/api/do/jump_next", keep=True)
        self.admin_page("救場之後")

    def admin_ops(self) -> None:
        """管理者表每一個 op：空的 body、六種壞值。季的三顆最後才按（season），暫停、繼續成對。"""
        self.sweep(ADMIN, SWITCH_ADMIN, "/api/do", keep=True, skip=("open_season", "end_season", "next_season"))
        self.probe(ADMIN, "/api/do/resume_clock", keep=True)
        self.admin_page("管理者動作之後")

    def targets(self) -> None:
        """動到別人存檔的四個 op 帶真的名字：_tell_tabs 第二個參數要是那個名字（PLAYER_ADMIN_ACTIONS）；其他管理者工具是空字串。"""
        self.probe(ADMIN, "/api/do/summon", {"name": self.MO}, keep=True)
        self.probe(ADMIN, "/api/do/give_opportunity", {"name": self.MO, "id": "沒有這個機緣"}, keep=True)
        self.probe(ADMIN, "/api/do/give_fragment", {"name": self.MO, "id": "沒有這個片段"}, keep=True)
        self.probe(ADMIN, "/api/do/mingtie_remove", {"name": self.MO, "version": 0}, keep=True)
        self.probe(ADMIN, "/api/do/mingtie_restore", {"name": self.MO, "version": 0}, keep=True)
        self.probe(ADMIN, "/api/do/outing_erase", {"name": self.MO, "id": 1}, keep=True)

    def accounts(self) -> None:
        """管理頁重設密碼那兩條（第二輪第 90 批補，之前沒有一軌打到）：不是管理者一律擋；管理者搜帳號（空的、名號、帳號不分大小寫、搜不到、壞值、萬用字元）、重設（查無此人、太短、太長、沒帶、照名號、照帳號）。
        重設之後那個帳號所有裝置都登出：舊的工作階段失效、舊密碼登不進、臨時密碼登得進。"""
        login = self.login_of(self.WEN)
        for who in (None, self.MO):
            self.probe(who, "/api/admin/accounts", {"q": login})
            self.probe(who, "/api/admin/reset_password", {"target": login, "temp": "temp-pass-1"})
        for q in ("", self.WEN, login.upper(), "沒有這個人", None, "%"):
            self.probe(ADMIN, "/api/admin/accounts", {"q": q}, keep=True)
        for body in ({"target": "沒有這個人", "temp": "temp-pass-1"}, {"target": login, "temp": "123"}, {"target": login, "temp": "長" * 200}, {},
                     {"target": self.WEN, "temp": "temp-pass-1"}, {"target": login, "temp": "temp-pass-2"}):
            self.probe(ADMIN, "/api/admin/reset_password", body, keep=True)
        self.main(self.WEN)
        self.call(self.WEN, "POST", "/api/login", {"login": login, "password": self.passwords[self.WEN]})
        self.passwords[self.WEN] = "temp-pass-2"
        self.relogin(self.WEN)
        self.main(self.WEN)

    def bots(self) -> None:
        """假人：BotRunner 兩個（官軍）若干輪。假人走 Game 的公開方法、不走動作表，這一段看的是委派沒被動到。"""
        from collections import Counter

        from tianxia import server_bots
        from tianxia.bot_runner import BotRunner
        from tianxia.engine import Game
        from tianxia.state import BotProfile

        on = self.factions_on()
        for i, name in enumerate(self.BOT_SEATS):
            self.begin()
            g = Game.new(self.c, name, rng=random.Random(i), world=self.world, graduated=True)
            p = g.state.player
            p.bot = BotProfile(personality="普通", seed=91 + i, faction="guan" if on else None, season_number=self.world.get_season_number())
            g.client = None
            g.sync(CLOCK[0])
            for _ in range(6):
                first = next((o.id for o in g.options(odds=False) if o.id.startswith("choice:") and o.enabled), None)
                if first is None:
                    break
                g.choose(first)
            p.faction, p.location, p.journey = p.bot.faction, self.c.scenario.start_location, None
            p.tutorial_step = len(self.c.tutorial.steps)
            p.joined_at = -1.0e9
            p.stamina = float(self.c.config.stamina_max)
            self.chars.save(g.state)
        runner = BotRunner(self.c, self.world, self.chars, rng=random.Random(53), clock=lambda: CLOCK[0])
        tick, online = self.c.config.bot_tick_seconds, server_bots.is_online
        seeds = {91 + i for i in range(len(self.BOT_SEATS))}
        self.c.config.bot_tick_seconds = 10 ** 6
        server_bots.is_online = lambda profile, now: profile.seed in seeds or online(profile, now)
        totals = Counter()
        try:
            for _ in range(6):
                STEP[0] += 4
                self.begin()
                report = runner.tick()
                totals.update(acted=report.acted, added=report.added, skipped=report.skipped, failed=report.failed, online=report.online)
        finally:
            self.c.config.bot_tick_seconds, server_bots.is_online = tick, online
        emit("假人 一輪一輪", dict(sorted(totals.items())))

    def season(self) -> None:
        """收季、休季每個玩家動作按一下、開下一季。"""
        self.do(ADMIN, "end_season")
        self.admin_page("休季")
        self.sweep(self.MO, SWITCH_MAIN, "/api/do", full=False)
        self.sweep(self.MO, SWITCH_MENXIA, "/api/menxia", full=False)
        self.do(ADMIN, "next_season")
        self.main(self.MO)
        self.admin_page("下一季")


# 改一個字（selftest）：閉關的預設時數（MAIN_ACTIONS["seclude"]：第 68 批搬進閉關包，搬進包的檔、殼兩處找）
register_track("switchboard", SwitchboardScenario, (("tianxia/features/seclusion/routes.py", "server.py"),
                                                    ('b.get("hours"), 8)', 'b.get("hours"), 6)')), "week7",
               covers=("admin", "battle", "bounties", "bout", "checkin", "companions", "craft", "cultivation", "explore", "faction",
                       "figure_acts", "gear", "guide", "heroines", "identity", "legacy", "looks", "mail", "mall", "military",
                       "outlets", "peers", "seal", "seclusion", "sense", "smithy", "socialize", "sortie", "stamina_plays", "story",
                       "tavern", "territory_acts", "travel", "zhuan"))
