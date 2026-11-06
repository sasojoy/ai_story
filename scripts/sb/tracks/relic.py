"""same_behavior 一軌一檔：relic（這一檔登記 relic）。"""
from __future__ import annotations

import hashlib
import os
import random
from pathlib import Path

from sb.harness import ADMIN, CLOCK, CLOCK0, STEP, db_text, emit, register_track
from sb.tracks.explore import _explore_rules
from sb.tracks.herald import HeraldScenario

# ═══════════════════════════ relic：玉璽一軌（全部拆包第 27 批「玉璽一」，dev/seal-1） ═══════════════════════════
# 碎片的季流程：開季藏一片（世界層 open 的 seal.cache）、管理者的「現在藏一片」、探索撿碎片（事件 outing 的 seal 那一格：擲中、沒擲中、
# 剛易手冷卻、手上已有一片）、撿到之後的補送（傳承那一格的抄本、紀錄、行狀）、玉璽這一下擲中（持有者在場、強制璽動、開標了璽動的時刻表
# 決戰：同一下屯糧、龍頭上陣也有動作——世界層 muster 的 front、works、seal、generals 四格）、決戰收場（事件 battle_end 的 seal 那一格）、
# 離線的人同步補送、隱沒判斷、換季（世界層 retire：隱沒、沒收場的奪璽單挑記成未分勝負；next：天命之季的章、天命之季不藏）、天命之季的
# 喚回與天命之爭（份量加權、定天命）、散去、管理者的 seal_mandate（now、next、cancel）、/api/main 的江湖史七格與碎片卡、管理頁的玉璽一組。
# 計畫 docs/superpowers/plans/2026-11-07-玉璽包-第1批.md。這一段整塊是這一批的：接在檔尾、最後一行登記（register_track），PM 合的時候
# 不跟別人的行穿插。角色的名字都是原創的（PM 11/04）。
# 固定密鹽（PM 認定）：same_behavior 走 TestClient、不經 server.main／run_bots.main，seal.ensure_salt 從沒叫到，別的軌的密鹽都是空字串、
# 兩份程式一樣。這一軌只在開季前寫一個固定的非空密鹽（tianxia-qa 引擎驗收那一條）；子行程另外把 seal.secrets.token_hex 換成回固定值
# （以防有路徑走到 ensure_salt）。既有的軌一個字不動。

RELIC_SALT = "古玉藏鋒"  # 固定的非空密鹽：碎片的每一份亂數（藏、撿、璽動、挑人、回不回來）都照它
RELIC_TOKEN = "relic" + "0" * 27  # seal.secrets.token_hex 換成回這一個


class RelicScenario(HeraldScenario):
    """玉璽一軌（全部拆包第 27 批；--track relic，自己一個資料庫）。借 herald 的小工具（showdown、spot、join、seal_live、factions_on）。
    **前半停在五件寫到一半的事**：開季藏好一片、聞岫川在那一塊探索過還沒擲中；時刻表決戰集結中、集結那一刻擲了璽動（應長庚懷中那一片）、
    還沒收場；符靜淵下線之後才被記上一片（全服登記有他還沒補的那一筆）；下一季天命之季的章按下了（mandate_pending）、天命之爭還沒打；
    一場奪璽單挑掛在下戰書（記憶體裡把 muster_seconds 拉長，整段跑不完）。
    後半：新程式接著——補送（登入那一下）、取消掛著的單挑、璽動那一場打到收場（挑出挑戰者、單挑推到收場）、假人（BotRunner 兩個：一個從
    藏處那一塊開跑〔記憶體裡把撿到的機率壓成 0〕、一個是退隱的持璽假人，照 bot_return_chance 與密鹽擲回不回來）、聞岫川撿到、隱沒判斷、
    換季、天命之季的璽動與喚回、天命之爭、散去、管理者的 seal_mandate、江湖史與管理頁、整季機器人（另一個資料庫）、再收一季（蓋了章沒打成：
    天命未定；記憶體裡關掉碎片，沒收場的單挑留到換季記成未分勝負）。
    測試內容沒有 content/seal.json：記憶體裡借正式內容的七片（兩份程式同一步借），沒有領地爭奪、時刻表、天命之爭的那幾支照打、寫「沒有」。"""

    HUNTER, KEEPER, FOE, WORKER, ABSENT, RIVAL, SPARE = "聞岫川", "應長庚", "卓遠岑", "藺秋禾", "符靜淵", "季聽瀾", "江未晞"
    LOST = "隱名客"  # 沒有角色的名號：管理者把一片記到他名下、缺席記滿，下一次換季隱沒
    LONE = HUNTER  # herald 的 wild_spot 拿這一位問野地的對手（這一軌沒有 herald 的嚴暮帆）
    PLAYERS = {HUNTER: "guan", KEEPER: "guan", FOE: "huang", WORKER: "guan", ABSENT: "guan", RIVAL: "huang", SPARE: "guan"}
    NEWBIE = "乍到者"
    BOT_SEATS = ["尋璽丁", "璽歸客"]  # 第一個站在藏處那一塊、第二個是退隱的持璽假人
    PHASES_FIRST = ["setup", "seat", "cache", "tries", "absent", "stock", "muster", "mandate_mark", "duel_hang", "half"]
    PHASES_SECOND = ["resume", "fight", "bots", "find", "sink_mark", "turn", "absent_back", "recall_fight", "mandate_fight", "mandate_end",
                     "mandate_tools", "views", "play_bot", "season"]

    def __init__(self, root: Path, profile: str, db: Path):
        super().__init__(root, profile, db)
        from tianxia import seal

        seal.secrets.token_hex = lambda nbytes=None: RELIC_TOKEN  # 以防有路徑走到 ensure_salt（server.main、run_bots.main 才叫）
        self.borrowed = False
        if not self.c.seal:  # 測試內容沒有七片：借正式內容的（記憶體裡；兩半各自的行程都在這裡借，同一份）
            from tianxia.content import load_content

            self.c.seal = load_content(root / "content").seal
            self.borrowed = True

    # ── 小工具 ──

    def picks(self) -> tuple[str | None, list[str]]:
        """（藏著或撿到的那一片, 其餘照 id 排）：應長庚拿其餘的第一片、符靜淵第二片、退隱的持璽假人第三片、隱名客第四片。照登記算，兩半一樣。"""
        reg = self.world.seal_state().registry
        x = reg.cache.shard if reg.cache is not None else next((s.id for s in reg.shards.values() if s.holder == self.HUNTER), None)
        return x, [s for s in sorted(self.c.seal) if s != x]

    def quiet(self, who: str, url: str = "/api/main"):
        """打一次 GET，只寫回應的雜湊（迴圈裡每一下都整份寫的話輸出太大）；回 JSON。"""
        self.begin()
        r = self.clients[who].get(url)
        emit(f"{who} GET {url}（雜湊）", [r.status_code, hashlib.sha256(r.content).hexdigest()[:16]])
        return r.json() if r.status_code == 200 else {}

    def relic_view(self, tag: str) -> None:
        view = self.world.seal_state()
        reg = view.registry
        w = self.world.get_season()
        b = self.world.get_battle()
        emit(f"玉璽 {tag}", {
            "shards": {k: [v.state, v.holder, v.since_season, v.stirred_season, v.absent, v.emerged_round] for k, v in sorted(reg.shards.items())},
            "cache": None if reg.cache is None else reg.cache.model_dump(mode="json"),
            "reg": [reg.seq, reg.round, reg.emerge_season, reg.force_emerge, reg.force_stir, reg.mandate_season, reg.mandate_pending,
                    reg.opened_real, reg.last_showdown, reg.last_showdown_dueled, reg.salt == RELIC_SALT],
            "history": [[e.seq, e.season, e.kind, e.shard, e.holder, e.other, e.result, e.text] for e in reg.history[-8:]],
            "duels": [[d.id, d.shard, d.holder.name, d.challenger.name] for d in view.duels],
            "season": [view.season, w.mandate, w.mandate_result, w.ended],
            "battle": None if b is None else {
                "id": b.battle_id, "phase": b.phase, "round": b.round_number, "trend": [b.trend, b.trend_start],
                "seal": [b.seal_shard, b.seal_holder, b.seal_holder_side, b.seal_emerge, dict(sorted(b.seal_lean.items()))],
                "supply": dict(sorted(b.supply_lean.items())), "front": b.front_note is not None,
                "chiefs": [getattr(x, "name", "") for x in b.commanders], "outcome": b.outcome_title, "notes": list(b.seal_notes),
                "who": {n: [p.faction, p.acted_rounds, round(sum(p.scores.values()), 1), p.seal_bare is not None, p.eliminated, p.away]
                        for n, p in sorted(b.participants.items())}},
            "rumors": [r.text for r in w.rumors][-5:], "chronicle": [r.text for r in w.chronicle][-4:]})

    def relic_me(self, who: str, tag: str) -> None:
        state = self.chars.load(who)
        if state is None:
            emit(f"{who} {tag}（沒有這個人）", None)
            return
        p = state.player
        emit(f"{who} {tag}", {
            "loc": p.location, "faction": p.faction, "seal_seen": p.seal_seen, "explore_seq": p.explore_seq,
            "heirloom": None if p.heirloom is None else [p.heirloom.id, p.heirloom.name], "cap_scale": p.member.cap_scale,
            "annals": [a.model_dump(mode="json") for a in p.annals[-2:]],
            "battles": [[r.kind, r.event, r.opponent, r.tier, list(r.notes)[:4], list(r.changes)[:3]] for r in state.battles[:2]],
            "journal": [[e.title, e.tag, list(e.lines)[:6]] for e in state.journal[:3]]})

    def base_of(self, side: str) -> str:
        from tianxia import territory

        try:
            bases = territory.bases(self.c)
        except Exception:  # noqa: BLE001
            bases = {}
        return next((loc for loc, owner in sorted(bases.items()) if owner == side), self.hub())

    def cooling(self, loc: str, on: bool) -> None:
        """那一塊記成剛易手（冷卻中）或還原：只在領地爭奪的季（測試內容沒有，寫「沒有」）。"""
        from tianxia import conquest
        from tianxia.state import BlockFight

        if not conquest.on(self.c, self.world.get_season()) or loc not in conquest.blocks(self.c):
            emit("剛易手冷卻：這一季沒有領地爭奪或那裡不是區塊", None)
            return

        def fn(s) -> None:
            if s.conquest is None:
                conquest.update(s, self.c)
            fight = s.conquest.fights.setdefault(loc, BlockFight())
            fight.flipped_at = s.time if on else None

        self.world.mutate_season(fn)
        emit(f"{loc} 剛易手冷卻中", conquest.cooling(self.world.get_season(), self.c, loc))

    def cancel_natural(self) -> None:
        """照時刻表自己開了的那一場先取消（管理者「取消決戰」），才開得了要的那一場。"""
        b = self.world.get_battle()
        if b is not None and b.phase != "ended":
            emit("自己開了的那一場", [b.battle_id, b.phase])
            self.do(ADMIN, "cancel_battle")

    def fight_out(self, names: tuple[str, ...], tag: str, limit: int = 60) -> None:
        """那一場打到收場：每一下名單上的人各看一次選單（只寫雜湊），按得到 battle:act: 就照選單上第一顆出手；都按不到就把時鐘往前推。"""
        n = acted = 0
        b = self.world.get_battle()
        while n < limit:
            b = self.world.get_battle()
            if b is None or b.phase == "ended":
                break
            moved = False
            for who in names:
                if self.chars.load(who) is None:
                    continue
                opts = self.ids(self.quiet(who))
                pick = next((i for i, o in opts.items() if i.startswith("battle:act:") and o.get("enabled")), None)
                if pick is not None:
                    self.choose(who, pick)
                    acted += 1
                    moved = True
            if not moved:
                STEP[0] += 5
            n += 1
        b = self.world.get_battle()
        emit(f"{tag} 推了幾下", [n, acted, None if b is None else [b.phase, b.outcome_title]])

    def duel_out(self, names: tuple[str, ...], limit: int = 60) -> None:
        """奪璽單挑照時間推到收場（雙方各自同步；出招照代打）：每一下名單上的人各看一次（只寫雜湊），時鐘往前推。"""
        n = 0
        while n < limit and self.world.seal_state().duels:
            for who in names:
                self.quiet(who)
            STEP[0] += 2
            n += 1
        emit("奪璽單挑推了幾下", [n, [d.id for d in self.world.seal_state().duels]])

    # ── 前半 ──

    def setup(self) -> None:
        """同 Scenario.setup，只多一件：開季之前寫固定的密鹽（開季那一刻就照它擲藏不藏）。"""
        from tianxia.accounts import AccountStore
        from tianxia.engine import Game

        store = AccountStore(self.world.db)
        self.passwords[ADMIN] = "pw-admin-123456"
        with self.world.db.transaction():
            store.register(self.login_of(ADMIN), self.passwords[ADMIN])
            game = Game.new(self.c, ADMIN, world=self.world)
            self.chars.save(game.state)
            store.bind_character(self.login_of(ADMIN), ADMIN)
        self.world.mutate(lambda st: setattr(st.seal, "salt", RELIC_SALT))
        emit("借了正式內容的七片", self.borrowed)
        self.clients[ADMIN] = self.TestClient(self.server.app)
        self.call(ADMIN, "POST", "/api/login", {"login": self.login_of(ADMIN), "password": self.passwords[ADMIN]})
        self.do(ADMIN, "open_season")
        for who in [self.NEWBIE, *self.PLAYERS]:
            self.clients[who] = self.TestClient(self.server.app)
            self.passwords[who] = "pw-" + self.login_of(who)
            self.call(who, "POST", "/api/register", {"login": self.login_of(who), "password": self.passwords[who],
                                                    "again": self.passwords[who]})
            self.call(who, "POST", "/api/character", {"name": who, "gender": "男"})
        for who in self.PLAYERS:
            self.do(who, "skip_tutorial")
            self.settle_choices(who)

    def seat(self) -> None:
        for who in self.PLAYERS:
            self.place(who, self.hub(), self.side(who))
        for who in self.PLAYERS:
            self.main(who)
        self.relic_view("開季之後")  # 世界層 open 的 seal.cache：開季照固定密鹽擲 hide_chance

    def cache(self) -> None:
        """管理者「強制現世」：領地爭奪的季是「現在藏一片」（不存在的那一片、現在藏、已經藏著）；沒有領地爭奪的季是下一場標了現世的必定現世。"""
        self.do(ADMIN, "seal_emerge", {"id": "沒有這一片"})
        self.do(ADMIN, "seal_emerge", {"id": ""})
        self.do(ADMIN, "seal_emerge", {"id": ""})
        self.call(ADMIN, "GET", "/api/admin")  # 管理頁的玉璽一組（hide：只給有沒有、不給藏在哪）
        self.relic_view("強制現世之後")

    def tries(self) -> None:
        """探索走到藏處：手上已有一片（應長庚，機率開到 1 也不擲）、剛易手冷卻中（機率開到 1 也不擲）、照原本的機率擲（沒擲中）。"""
        x, rest = self.picks()
        reg = self.world.seal_state().registry
        where = reg.cache.loc if reg.cache is not None else (self.wild_spot() or self.hub())
        emit("藏著的那一片與地方", [x, reg.cache.loc if reg.cache is not None else None, where])
        self.do(ADMIN, "seal_assign", {"id": rest[0], "name": self.KEEPER, "state": "held"})
        self.do(ADMIN, "seal_assign", {"id": rest[0], "name": self.KEEPER, "state": "看不懂"})  # 看不懂要怎麼改
        explore_one = _explore_rules()
        for who in (self.KEEPER, self.HUNTER):
            self.place(who, where)
        with self.tweak(self.c.config.seal.cache, find_chance=1.0), self.draws(explore_one.MATERIAL):
            self.explore(self.KEEPER)
        self.relic_me(self.KEEPER, "手上已有一片、探索到藏處")
        self.cooling(where, True)
        with self.tweak(self.c.config.seal.cache, find_chance=1.0), self.draws(explore_one.MATERIAL):
            self.explore(self.HUNTER)
        self.cooling(where, False)
        self.relic_me(self.HUNTER, "冷卻中探索到藏處")
        with self.draws(explore_one.MATERIAL):
            self.explore(self.HUNTER)
        self.relic_me(self.HUNTER, "照原本的機率擲過")
        self.relic_view("探索過還沒擲中")

    def absent(self) -> None:
        """符靜淵最後一次同步之後，管理者才把一片記到他名下：登記多一筆 assign、他還沒補。"""
        x, rest = self.picks()
        self.main(self.ABSENT)
        self.relic_me(self.ABSENT, "下線之前")
        self.do(ADMIN, "seal_assign", {"id": rest[1], "name": self.ABSENT, "state": "held"})
        self.relic_view("下線的人名下多一片")

    def stock(self) -> None:
        """屯糧（三種設定的預設關著：記憶體裡開到下一段開完集結）：藺秋禾在官軍的大本營屯兩下。"""
        self.stock_was = self.c.config.stockpile.enabled
        self.c.config.stockpile.enabled = True
        base = self.base_of("guan")
        self.place(self.WORKER, base)
        for _ in range(2):
            self.edit(self.WORKER, lambda p: setattr(p, "stamina", float(self.c.config.stamina_max)))
            self.choose(self.WORKER, "works:stockpile")
        emit("屯量", dict(sorted(self.world.get_season().supply.items())))

    def muster(self) -> None:
        """玉璽這一下擲中（第 25 批認定第 3 條）：持有者應長庚站在那一場的大區、管理者強制璽動他那一片，開標了璽動的時刻表決戰——
        同一下起點（front）、屯糧（works）、璽動（seal）、龍頭上陣（generals）四格都有動作；兩軍各有人加入。"""
        try:
            which = self.showdown() if self.seal_live() else None
            emit("開哪一場", which)
            if which is None:
                emit("集結：這份內容沒有玉璽或那一場", None)
                return
            x, rest = self.picks()
            spot = self.spot(which)
            self.cancel_natural()
            self.place(self.KEEPER, spot)
            self.main(self.KEEPER)
            self.do(ADMIN, "seal_stir", {"id": rest[0]})
            self.do(ADMIN, "start_showdown", {"id": which})
        finally:
            self.c.config.stockpile.enabled = self.stock_was
        self.relic_view("開集結那一刻")
        for who in (self.KEEPER, self.FOE, self.HUNTER):
            self.place(who, spot)
            self.join(who)
        self.relic_view("集結中")

    def mandate_mark(self) -> None:
        """管理者的 seal_mandate：沒有要收回的、下一季蓋章、收回、看不懂，最後再按「下一季」（前半停在章按下了、天命之爭還沒打）。"""
        for when in ("cancel", "next", "cancel", "看不懂", "next"):
            self.do(ADMIN, "seal_mandate", {"when": when})
        self.call(ADMIN, "GET", "/api/admin")
        self.relic_view("下一季的章")

    def duel_hang(self) -> None:
        """掛一場奪璽單挑（QA 工具；記憶體裡開 qa_tools、下戰書拉到很久）：符靜淵那一片、季聽瀾挑。"""
        x, rest = self.picks()
        with self.tweak(self.c.config.seal, qa_tools=True, muster_seconds=1.0e7):
            self.do(ADMIN, "seal_duel", {"id": rest[1], "name": self.RIVAL, "factor": 1.0})
        self.relic_view("掛著的單挑")

    def half(self) -> None:
        for who in (self.HUNTER, self.KEEPER, self.RIVAL):
            self.relic_me(who, "前半停在這裡")
        self.relic_view("前半停在這裡")

    # ── 後半 ──

    def resume(self) -> None:
        self.login_all()  # 符靜淵也在這裡登入：他那一筆由新程式補送
        self.relic_me(self.ABSENT, "接手登入之後")
        for who in (self.HUNTER, self.KEEPER):
            self.main(who)

    def bots(self) -> None:
        """假人：BotRunner 兩個——尋璽丁（官軍）每一輪之前不在路上就站回藏處那一塊（記憶體裡把撿到的機率壓成 0：擲照擲、撿不到，留給聞岫川；
        season21 它在藏處探索到，week7 它一開跑就上路去別處、8 輪沒在藏處探索）；璽歸客是退隱的
        持璽假人（管理者記一片到他名下），每季開季後第一次補人照 bot_return_chance 與密鹽擲回不回來。"""
        from collections import Counter

        from tianxia import server_bots
        from tianxia.bot_runner import BotRunner
        from tianxia.engine import Game
        from tianxia.state import BotProfile

        reg = self.world.seal_state().registry
        spot = reg.cache.loc if reg.cache is not None else (self.wild_spot() or self.hub())
        on = self.factions_on()
        season = self.world.get_season_number()
        for i, name in enumerate(self.BOT_SEATS):
            self.begin()
            g = Game.new(self.c, name, rng=random.Random(i), world=self.world, graduated=True)
            p = g.state.player
            retired = i == 1
            p.bot = BotProfile(personality="普通", seed=71 + i, faction=None if retired or not on else "guan",
                               season_number=season - 1 if retired else season)
            g.client = None
            g.sync(CLOCK[0])
            for _ in range(6):
                first = next((o.id for o in g.options(odds=False) if o.id.startswith("choice:") and o.enabled), None)
                if first is None:
                    break
                g.choose(first)
            p.faction, p.location, p.journey = p.bot.faction, spot, None
            p.visited.add(spot)
            p.tutorial_step = len(self.c.tutorial.steps)
            p.joined_at = -1.0e9
            p.stamina = float(self.c.config.stamina_max)
            self.chars.save(g.state)
        x, rest = self.picks()
        self.do(ADMIN, "seal_assign", {"id": rest[2], "name": self.BOT_SEATS[1], "state": "held"})
        runner = BotRunner(self.c, self.world, self.chars, rng=random.Random(43), clock=lambda: CLOCK[0])
        tick, online = self.c.config.bot_tick_seconds, server_bots.is_online
        seeds = {71 + i for i in range(len(self.BOT_SEATS))}
        self.c.config.bot_tick_seconds = 10 ** 6
        server_bots.is_online = lambda profile, now: profile.seed in seeds or online(profile, now)
        totals = Counter()

        def pin(p) -> None:  # 尋璽丁不在路上就站回藏處那一塊（不然它會走開，探索不到藏處）
            if p.journey is None:
                p.location = spot
                p.visited.add(spot)

        try:
            with self.tweak(self.c.config.seal.cache, find_chance=0.0):
                for _ in range(int(os.environ.get("SB_RELIC_TICKS", "8"))):
                    self.edit(self.BOT_SEATS[0], pin)
                    STEP[0] += 4
                    self.begin()
                    report = runner.tick()
                    totals.update(acted=report.acted, added=report.added, skipped=report.skipped, failed=report.failed, online=report.online)
        finally:
            self.c.config.bot_tick_seconds, server_bots.is_online = tick, online
        emit("假人 一輪一輪", dict(sorted(totals.items())))
        for name in self.BOT_SEATS:
            s = self.chars.load(name)
            profile = s.player.bot
            emit(f"假人 {name}", {"loc": s.player.location, "faction": s.player.faction, "explore_seq": s.player.explore_seq,
                                  "active": server_bots.active(profile, self.world.get_season_number()) if profile else None,
                                  "heirloom": None if s.player.heirloom is None else s.player.heirloom.id, "seal_seen": s.player.seal_seen,
                                  "journal": [[e.title, list(e.lines)[:3]] for e in s.journal[:4]],
                                  "state": hashlib.sha256(s.model_dump_json().encode("utf-8")).hexdigest()})
        self.relic_view("假人之後")

    def find(self) -> None:
        """聞岫川在藏處擲中（機率開到 1）：撿到、傳承那一格的抄本、紀錄、行狀；接著管理者再按「現在藏一片」：一季一片。"""
        reg = self.world.seal_state().registry
        if reg.cache is None:
            emit("撿到：這一季沒有藏著的碎片", None)
        else:
            self.place(self.HUNTER, reg.cache.loc)
            explore_one = _explore_rules()
            with self.tweak(self.c.config.seal.cache, find_chance=1.0), self.draws(explore_one.MATERIAL):
                self.explore(self.HUNTER)
        self.relic_me(self.HUNTER, "擲中之後")
        self.do(ADMIN, "seal_emerge", {"id": ""})
        self.relic_view("撿到之後")

    def fight(self) -> None:
        """前半掛著的那一場單挑由新程式取消（記成未分勝負、只寫天下大事）；璽動那一場打到收場（事件 battle_end：大勢不打或挑出挑戰者）；
        挑出了就把那一場單挑照時間推到收場（雙方補送戰報與紀錄）。"""
        self.do(ADMIN, "seal_cancel")
        self.relic_me(self.ABSENT, "掛著的單挑取消之後")
        names = (self.KEEPER, self.FOE, self.HUNTER)
        self.fight_out(names, "璽動那一場")
        self.relic_view("璽動那一場收場")
        self.duel_out(names + (self.RIVAL,))
        for who in names:
            self.main(who)
            self.relic_me(who, "收場之後")
        self.relic_view("收場的單挑之後")

    def sink_mark(self) -> None:
        """隱沒判斷：先看一次（沒有要隱沒的）；管理者把一片記到沒有角色的隱名客名下、缺席記到差一季，再看一次（下一次換季會隱沒）。"""
        x, rest = self.picks()
        self.do(ADMIN, "seal_sink_check")
        self.do(ADMIN, "seal_assign", {"id": rest[3], "name": self.LOST, "state": "held"})
        need = self.c.config.seal.sink_seasons - 1

        def fn(st) -> None:
            shard = st.seal.shards.get(rest[3])
            if shard is not None:
                shard.absent = need

        self.world.mutate(fn)
        self.do(ADMIN, "seal_sink_check")
        self.relic_view("隱沒判斷之後")

    def turn(self) -> None:
        """換季（世界層 retire、next）：收季、休季時看隱沒判斷、開下一季——隱沒（碎片開著才判）、天命之季的章（前半按下的「下一季」）、
        天命之季不藏。"""
        self.do(ADMIN, "end_season")
        self.relic_view("收季之後")
        self.do(ADMIN, "seal_sink_check")
        self.do(ADMIN, "next_season")
        self.relic_view("換季之後")

    def absent_back(self) -> None:
        """下一季：符靜淵與季聽瀾同步，補到換季時記成未分勝負的那一筆。"""
        for who in (self.ABSENT, self.RIVAL, self.KEEPER, self.HUNTER):
            self.main(who)
            self.relic_me(who, "換季之後同步")

    def recall_fight(self) -> None:
        """天命之季的璽動那一場（每場必定牽動一片、標了 seal 的前兩場收場時喚回一片隱沒的）：開集結、兩軍各兩個手上沒有碎片的人加入
        （贏的那一軍挑走一個去單挑之後還剩一個能被喚回）、打到收場；挑出了單挑就推到收場。"""
        from tianxia import seal

        which = self.showdown() if self.seal_live() else None
        emit("天命之季的璽動那一場", [which, which in seal.recall_events(self.c) if which else None])
        if which is None:
            return
        spot = self.spot(which)
        names = (self.KEEPER, self.FOE, self.HUNTER, self.RIVAL, self.WORKER, self.SPARE)
        for who in names:  # 換季之後第一次同步才換成新角色：同步之後照原本的陣營重新站好
            self.main(who)
            self.place(who, spot, self.side(who))
            self.main(who)
        b = self.world.get_battle()
        if b is not None and b.phase == "muster" and b.battle_id == which:  # 照時刻表自己開了的就是這一場（season21）：不取消、接著打
            emit("自己開了的就是這一場", [b.battle_id, b.phase])
        else:
            self.cancel_natural()
            self.do(ADMIN, "start_showdown", {"id": which})
        for who in names:
            self.join(who)
        self.relic_view("天命之季的璽動集結中")
        self.fight_out(names, "天命之季的璽動")
        self.duel_out(names)
        self.relic_view("天命之季的璽動收場")

    def mandate_fight(self) -> None:
        """天命之爭：開集結（起點照兩軍各握幾片偏）、懷璽的人加入（份量 × holder_weight）、打到收場定天命；懷璽的人補到合璽之人那一句。"""
        from tianxia import seal

        event = seal.mandate_event(self.c)
        emit("天命之爭", None if event is None else event.id)
        if event is None or not self.seal_live():
            return
        battle = seal.mandate_battle(self.c)
        spot = self.spot(battle.id) if battle is not None else None
        self.cancel_natural()
        self.do(ADMIN, "start_showdown", {"id": event.id})
        names = (self.KEEPER, self.HUNTER, self.FOE, self.RIVAL)
        for who in names:
            self.place(who, spot, self.side(who))
            self.join(who)
        self.relic_view("天命之爭集結中")
        self.fight_out(names, "天命之爭")
        self.relic_view("天命之爭收場")
        for who in names:
            self.main(who)
            self.relic_me(who, "天命之爭之後")

    def mandate_end(self) -> None:
        """天命之季收季（天命結局或天命未定）、開下一季（散去：七片回到未現世、懷璽的人補一句、抄本清掉）。"""
        self.do(ADMIN, "end_season")
        self.relic_view("天命之季收季")
        self.do(ADMIN, "next_season")
        self.relic_view("散去之後")
        for who in (self.KEEPER, self.HUNTER):
            self.main(who)
            self.relic_me(who, "散去之後")

    def mandate_tools(self) -> None:
        """管理者的 seal_mandate 其餘幾支：沒有要收回的、下一季、收回、這一季立刻蓋、再按這一季（已經是天命之季）；天命之季不藏。"""
        for when in ("cancel", "next", "cancel", "now", "now"):
            self.do(ADMIN, "seal_mandate", {"when": when})
        self.do(ADMIN, "seal_emerge", {"id": ""})
        self.relic_view("這一季蓋章之後")

    def views(self) -> None:
        """/api/main（江湖史七格、碎片卡、奪璽卡）與管理頁的玉璽一組。"""
        self.main(self.HUNTER)
        self.main(self.ABSENT)
        self.call(ADMIN, "GET", "/api/admin")

    def play_bot(self) -> None:
        """整季機器人（bot.play_season）：自己一個資料庫（這一軌的資料庫旁邊），開季前寫同一個密鹽；第一步沒藏就現在藏一片，還藏著的
        每一步把它站回藏處（不在路上時），這份內容撿到的機率開到 0.3（記憶體裡）。測試內容沒有領地爭奪，寫「沒有」。"""
        from collections import Counter

        if self.profile == "test":
            emit("整季機器人：測試內容沒有領地爭奪、時刻表與天命之爭", None)
            return
        from tianxia import bot, seal
        from tianxia.content import load_content
        from tianxia.sqlite_world import open_world

        path = self.db.with_name(self.db.stem + "-play.db")
        for suffix in ("", "-wal", "-shm", "-push.sqlite"):
            p = Path(str(path) + suffix)
            if p.exists():
                p.unlink()
        content = load_content(self.root / "content", profile=self.profile)
        content.config.seal.cache.find_chance = 0.3
        world = open_world(path)
        world.mutate(lambda st: setattr(st.seal, "salt", RELIC_SALT))
        seen = {"placed": False}

        def observe(g) -> None:
            g.now += 60.0
            if g.state.world.ended:
                return
            if not seen["placed"]:
                seen["placed"] = True

                def hide(st) -> None:
                    reg = seal.filled(st.seal, content)
                    if reg.cache is None:
                        reg.cache = seal.hide(reg, content, st.season_number, st.tianji, seal.hide_spots(content, st.season), force=True)

                g.world.mutate(hide)
            cache = seal.live_cache(g.world.seal_state().registry, g.world.get_season_number())
            p = g.state.player
            if cache is not None and p.journey is None:  # 還藏著就每一步站回藏處（撿到之後照它自己走）
                p.location = cache.loc
                p.visited.add(cache.loc)

        game = bot.play_season(content, seed=7, max_steps=int(os.environ.get("SB_RELIC_PLAY_STEPS", "200")), world=world, now=CLOCK0,
                               observe=observe)
        reg = world.seal_state().registry
        emit("整季機器人 玉璽", {"shards": {k: [v.state, v.holder] for k, v in sorted(reg.shards.items())},
                                "cache": None if reg.cache is None else reg.cache.model_dump(mode="json"),
                                "history": [[e.kind, e.shard, e.holder] for e in reg.history],
                                "me": [game.state.player.explore_seq, game.state.player.seal_seen,
                                       None if game.state.player.heirloom is None else game.state.player.heirloom.id]})
        emit("整季機器人 紀錄標題", dict(sorted(Counter(e.title for e in game.state.journal).items())))
        emit("整季機器人 存檔", hashlib.sha256(game.state.model_dump_json().encode("utf-8")).hexdigest())
        emit("整季機器人 資料庫", hashlib.sha256(db_text(path).encode("utf-8")).hexdigest())

    def season(self) -> None:
        """再收一季：這一季蓋了章、天命之爭沒打成（天命未定）。收季之前掛一場下戰書的單挑，接著主機關掉碎片（記憶體裡，收季與開下一季
        這兩下）：單挑推不動、留到換季，世界層 retire 記成未分勝負；散去不看開關、隱沒看開關。開下一季之後兩人同步補到那一筆。"""
        x, rest = self.picks()
        for who in (self.HUNTER, self.RIVAL):
            self.place(who, self.hub(), self.side(who))
        self.do(ADMIN, "seal_assign", {"id": rest[0], "name": self.HUNTER, "state": "held"})
        with self.tweak(self.c.config.seal, qa_tools=True, muster_seconds=1.0e7):
            self.do(ADMIN, "seal_duel", {"id": rest[0], "name": self.RIVAL, "factor": 0.5})
        self.relic_view("收季之前掛著的單挑")
        with self.tweak(self.c.config.seal, enabled=False):
            self.do(ADMIN, "end_season")
            self.relic_view("蓋了章沒打成的收季")
            self.do(ADMIN, "next_season")
            self.relic_view("關著碎片換季之後")
        for who in (self.HUNTER, self.RIVAL):
            self.main(who)
            self.relic_me(who, "最後一季同步")
        self.relic_view("最後一季")


# 改一個字（selftest）：管理者收回「下一季」的天命之季章那一句（Game.admin_seal_mandate；搬之前在 engine.py，搬進包之後在
# tianxia/features/seal/admin.py〔計畫 1.1 的檔名；搬的人照實際的檔名改第 1 項〕），week7 mandate_mark 那一段抓到
register_track("relic", RelicScenario, (("tianxia/engine.py", "tianxia/features/seal/admin.py"),
                                       ("換季時照樣會蓋）。", "換季時照樣會蓋）！")), "week7")
