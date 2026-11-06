"""same_behavior 一軌一檔：carve（這一檔登記 carve）。"""
from __future__ import annotations

import hashlib
import os
import random
from pathlib import Path

from sb.harness import ADMIN, CLOCK, STEP, emit, register_track
from sb.tracks.relic import RelicScenario

# ═══════════════════════════ carve：玉璽二軌（全部拆包第 28 批「玉璽二」，dev/seal-2） ═══════════════════════════
# 玉璽一軌（relic）沒走到的：七種獨門行動（/api/do/seal_use，七片各一種，含目標不對、同一片再按一次）、碎片卡（/api/main 的 seal.act）、
# 單挑卡與背景輪詢（status.seal_duel、seal_watch）、單挑每一回合的出招（/api/choose 的 seal:<招>：不認得的招、已出招的灰鈕、對手也出了就結算）、
# 放手一搏（/api/do/seal_text：鎖外三段式，假模型連不上、評 DEFAULT_FREE_TEXT_SUCCESS_RATE）、管理者的 seal_fix（單挑前、單挑中）、
# 管理頁的玉璽一組（admin_seal_choices，指定後的樣子）、假人在單挑裡（選單上 seal: 一顆都不按，被代打）。
# 半舊半新切在單挑第一回合：一方（應長庚）出了招、另一方（卓遠岑）還沒——新程式接手後對方才出招、結算。
# 計畫 docs/superpowers/plans/2026-11-06-玉璽包-第2批.md。角色與名字都是原創的（PM 11/04）。


class CarveScenario(RelicScenario):
    """玉璽二軌（--track carve，自己一個資料庫）。借 relic 的 setup、seat（固定密鹽、七片、角色與陣營）；單挑的節奏在記憶體裡縮短
    （兩半各自的行程在 __init__ 裡一樣縮）：下戰書 120 秒、一回合最多等 3000 秒（後半開頭的登入要走十步，單挑不能在那幾步裡自己走完）、在場看
    900 秒，qa_tools 開著（管理者不必有決戰就能開單挑）。"""

    BOT_SEATS = ["執璽丙", "挑璽丁"]  # 第一個是持璽的假人、第二個是來挑的假人
    PHASES_FIRST = ["setup", "seat", "uses", "hang", "first_move", "halt"]
    PHASES_SECOND = ["wake", "rounds", "gamble", "finish_up", "bot_duel", "last_views"]

    def __init__(self, root: Path, profile: str, db: Path):
        super().__init__(root, profile, db)
        cfg = self.c.config.seal
        cfg.qa_tools, cfg.muster_seconds, cfg.round_seconds, cfg.presence_window = True, 120.0, 3000.0, 900.0

    # ── 小工具 ──

    def card_of(self, who: str) -> dict:
        data = self.main(who)
        main = data.get("main", data) if isinstance(data, dict) else {}
        status = main.get("status") if isinstance(main, dict) else None
        return (status or {}).get("seal") or {}

    def seal_moves(self, who: str) -> list[str]:
        return [i for i, o in self.ids(self.main(who)).items() if i.startswith("seal:") and o.get("enabled")]

    # ── 前半 ──

    def uses(self) -> None:
        """七片各由藺秋禾拿一次（管理者指定），每一片：不認得的目標、照碎片卡上第一個能選的目標按、再按一次（次數與間隔）。"""
        for n, shard in enumerate(sorted(self.c.seal)):
            self.do(ADMIN, "seal_assign", {"id": shard, "name": self.WORKER, "state": "held"})
            act = self.card_of(self.WORKER).get("act") or {}
            rows = act.get("targets") or []
            row = next((r for r in rows if not r.get("why")), rows[0] if rows else None)
            sides = act.get("sides") or []
            side = (sides[0].get("id", "") if isinstance(sides[0], dict) else str(sides[0])) if sides else ""
            target = row.get("id", "") if row else ""
            emit(f"獨門行動 第 {n} 片", [shard, act.get("kind"), act.get("ok"), act.get("why"), act.get("left"), target, side, len(rows)])
            self.do(self.WORKER, "seal_use", {"target": "沒有這個目標", "side": "沒有這一軍"})
            self.do(self.WORKER, "seal_use", {"target": target, "side": side})
            self.do(self.WORKER, "seal_use", {"target": target, "side": side})
            self.card_of(self.WORKER)
            self.relic_view(f"第 {n} 片起用之後")
            self.do(ADMIN, "seal_assign", {"id": shard, "name": "", "state": "hidden"})  # 收回（一人一片，下一片才指定得上）
        self.do(ADMIN, "seal_assign", {"id": sorted(self.c.seal)[-1], "name": "", "state": "held"})  # 空名字：看它怎麼擋
        self.call(ADMIN, "GET", "/api/admin")

    def hang(self) -> None:
        """管理者把第一片記到應長庚名下、對卓遠岑開單挑；單挑前後各按一次「定結果」（沒有單挑、有單挑）。"""
        shard = sorted(self.c.seal)[0]
        self.do(ADMIN, "seal_assign", {"id": shard, "name": self.KEEPER, "state": "held"})
        self.do(ADMIN, "seal_fix", {"take": True})
        self.do(ADMIN, "seal_duel", {"id": shard, "name": self.FOE, "factor": 1.0})
        self.do(ADMIN, "seal_fix", {"take": False})
        self.call(ADMIN, "GET", "/api/admin")
        for who in (self.KEEPER, self.FOE):
            self.card_of(who)
        self.relic_view("單挑掛起來")

    def first_move(self) -> None:
        """下戰書的時間過了（開打）：兩個人都在場；應長庚先出一招（不認得的招、真的一招、已出招再按一次），卓遠岑還沒。"""
        STEP[0] += 3
        for who in (self.KEEPER, self.FOE):
            emit(f"{who} 此刻的招", self.seal_moves(who))
        mine = self.seal_moves(self.KEEPER)
        self.choose(self.KEEPER, "seal:沒有這一招")
        if mine:
            self.choose(self.KEEPER, mine[0])
            self.choose(self.KEEPER, mine[0])
        self.card_of(self.KEEPER)
        self.card_of(self.FOE)

    def halt(self) -> None:
        for who in (self.KEEPER, self.FOE):
            self.relic_me(who, "前半停在這裡")
        self.relic_view("前半停在這裡")

    # ── 後半 ──

    def wake(self) -> None:
        self.login_all()
        for who in (self.FOE, self.KEEPER):
            emit(f"{who} 接手之後的招", self.seal_moves(who))

    def rounds(self) -> None:
        """卓遠岑出招（結算第一回合），之後兩邊輪流出招兩回合（第二回合應長庚搶先、第三回合卓遠岑搶先；挑第幾個可選的招輪著換）。"""
        for n in range(3):
            order = (self.FOE, self.KEEPER) if n % 2 == 0 else (self.KEEPER, self.FOE)
            for k, who in enumerate(order):
                moves = self.seal_moves(who)
                if moves:
                    self.choose(who, moves[(n + k) % len(moves)])
            STEP[0] += 5
            self.card_of(self.KEEPER)
            self.relic_view(f"出招第 {n + 1} 輪之後")

    def gamble(self) -> None:
        """放手一搏：空字串、太長、真的一句（假模型評不到、用預設）、同一回合再搏、第三次搏（一場最多兩次）。"""
        for who in (self.FOE, self.KEEPER):
            self.do(who, "seal_text", {"text": ""})
            self.do(who, "seal_text", {"text": "劍出如電，直取咽喉"})
            self.do(who, "seal_text", {"text": "再搏一次"})
            STEP[0] += 5
            self.card_of(who)
        self.do(self.FOE, "seal_text", {"text": "第三次搏"})
        self.relic_view("放手一搏之後")

    def finish_up(self) -> None:
        """單挑推到收場（兩邊各看，缺的招代打），雙方看戰報與紀錄。"""
        self.duel_out((self.KEEPER, self.FOE))
        for who in (self.KEEPER, self.FOE):
            self.main(who)
            self.relic_me(who, "單挑收場之後")
        self.relic_view("單挑收場")

    def bot_duel(self) -> None:
        """假人在單挑裡：執璽丙持第二片、挑璽丁來挑（管理者開）；BotRunner 跑幾輪（選單上的 seal: 一顆都不按，單挑由代打走完）。"""
        from tianxia import server_bots
        from tianxia.bot_runner import BotRunner
        from tianxia.engine import Game
        from tianxia.state import BotProfile

        shard = sorted(self.c.seal)[1]
        season = self.world.get_season_number()
        for i, name in enumerate(self.BOT_SEATS):
            self.begin()
            g = Game.new(self.c, name, rng=random.Random(i), world=self.world, graduated=True)
            p = g.state.player
            p.bot = BotProfile(personality="普通", seed=91 + i, faction="guan" if i == 0 else "huang", season_number=season)
            g.client = None
            g.sync(CLOCK[0])
            for _ in range(6):
                first = next((o.id for o in g.options(odds=False) if o.id.startswith("choice:") and o.enabled), None)
                if first is None:
                    break
                g.choose(first)
            p.faction, p.location, p.journey = p.bot.faction, self.hub(), None
            p.visited.add(self.hub())
            p.tutorial_step = len(self.c.tutorial.steps)
            p.joined_at = -1.0e9
            p.stamina = float(self.c.config.stamina_max)
            self.chars.save(g.state)
        self.do(ADMIN, "seal_assign", {"id": shard, "name": self.BOT_SEATS[0], "state": "held"})
        self.do(ADMIN, "seal_duel", {"id": shard, "name": self.BOT_SEATS[1], "factor": 1.0})
        runner = BotRunner(self.c, self.world, self.chars, rng=random.Random(47), clock=lambda: CLOCK[0])
        tick, online = self.c.config.bot_tick_seconds, server_bots.is_online
        seeds = {91, 92}
        self.c.config.bot_tick_seconds = 10 ** 6
        server_bots.is_online = lambda profile, now: profile.seed in seeds or online(profile, now)
        try:
            for _ in range(int(os.environ.get("SB_CARVE_TICKS", "6"))):
                STEP[0] += 3
                self.begin()
                report = runner.tick()
                emit("假人一輪", [report.acted, report.added, report.skipped, report.failed])
        finally:
            self.c.config.bot_tick_seconds, server_bots.is_online = tick, online
        for name in self.BOT_SEATS:
            s = self.chars.load(name)
            emit(f"假人 {name}", {"seal_seen": s.player.seal_seen, "journal": [[e.title, list(e.lines)[:3]] for e in s.journal[:4]],
                                  "state": hashlib.sha256(s.model_dump_json().encode("utf-8")).hexdigest()})
        self.relic_view("假人單挑之後")
        self.duel_out((self.KEEPER, self.FOE))

    def last_views(self) -> None:
        self.call(ADMIN, "GET", "/api/admin")
        for who in (self.KEEPER, self.FOE, self.WORKER, self.RIVAL):
            self.card_of(who)
            self.relic_me(who, "最後")
        self.relic_view("最後")


# 改一個字（selftest）：選單上一招的回話（Game._seal_act；搬之前在 engine.py，搬進包之後在 tianxia/features/seal/duel_actions.py
# 〔計畫 2.1 的檔名；搬的人照實際的檔名改第 1 項〕），first_move 那一段抓到
register_track("carve", CarveScenario, (("tianxia/engine.py", "tianxia/features/seal/duel_actions.py"),
                                       ('out.append(f"你出了{move}。")', 'out.append(f"你出了{move}！")')), "week7")
