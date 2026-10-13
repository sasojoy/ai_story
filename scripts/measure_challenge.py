"""挑戰大勢人物每季都有的量表（docs/superpowers/specs/2026-10-11-挑戰大勢人物每季都有-design.md 第十一節；只量不改）。

兩種跑法：
- --mode server（預設）：伺服器假人整季。每一季在自己的暫存資料庫跑 scripts/sim_server_bots.py 的 run_season（照設定本身跑，
  14 天的預設設定第一季規則關著），只在記憶體裡包幾個函式記下每一場挑戰、每天的聲威、誰哪一天退場、掉落、頓悟，不改 repo 的程式。
  時間倍率預設 1、假人每 --tick（預設 120）秒動一次；--tick 20 是線上速度（慢六倍）。
- --mode season-bot：整季機器人（bot.play_season），observe 每一步把 game.now 推到跟賽季時間對得上（不然打贏之後的閉門不見
  永遠不會過）。

對照（設計第十一節）：--regen N、--cap N（Config.figure_prestige_regen／figure_daily_loss_cap）、--outcome a|c（a：在記憶體裡
讓退場的龍頭人物照常出手、不記 out_flag）、--no-challenge（緊急開關關掉：就是改之前的 14 天季）、--no-huangjin-end（拿掉黃巾聲勢
80 收季，輸出第一行寫明）、--players N（伺服器人數上限 server_max_players）、--profile weekend（週末設定當基準）。

數字照實印，不為了量表調參數；要調由企劃者定。「挑戰佔的收入」是佔打仗收入（每一場戰報記的心得、經驗）的比例，不含事件、閉關。
"""
from __future__ import annotations

import argparse
import io
import statistics
import sys
import tempfile
from collections import Counter, defaultdict
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from tianxia import cultivation, database, figures, insight_llm, treasures  # noqa: E402
from tianxia import world as world_mod  # noqa: E402
from tianxia.bot_runner import BotRunner  # noqa: E402
from tianxia.content import load_content  # noqa: E402
from tianxia.engine import Game  # noqa: E402
from tianxia.martial_arts import QUALITIES  # noqa: E402

DAY = 86400.0
MASTERED = QUALITIES[-1]  # 絕學
FACTION_NAMES = {"guan": "官軍", "huang": "黃巾", "haoqiang": "豪強", None: "散人"}


class ChallengeTally:
    """一季的紀錄：每一場挑戰、每天結束時每位人物的聲威、退場、三階與寶物（照來源）、頓悟、打仗收入。只記不改。"""

    def __init__(self) -> None:
        self.fights: list[dict] = []  # day、fid、faction、tier、xinde、exp、strong
        self.retired: dict[str, float] = {}
        self.prestige: dict[int, dict[str, int]] = {}  # 第幾天 → 人物 → 聲威（那一天最後看到的）
        self.tier3: Counter = Counter()  # （陣營, 來源）→ 個數；來源：first（預設表，第一次打贏）、guaranteed（保證那一個）
        self.treasures: Counter = Counter()  # 陣營 → 件數
        self.seizes: list[tuple[float, str]] = []  # （第幾天, 哪一種仗）
        self.battle_income: Counter = Counter()  # （陣營, xinde／exp）→ 打仗收入合計（含挑戰）

    def fight(self, day: float, fid: str, faction: str | None, tier: str, xinde: int, exp: int, strong: bool) -> None:
        self.fights.append({"day": day, "fid": fid, "faction": faction, "tier": tier, "xinde": xinde, "exp": exp, "strong": strong})

    def report(self, content) -> dict:
        won = [f for f in self.fights if f["tier"] in ("大勝", "險勝")]
        by_faction: dict[str, dict] = defaultdict(lambda: {"挑戰": 0, "打贏": 0, "心得": 0, "經驗": 0})
        for f in self.fights:
            row = by_faction[FACTION_NAMES.get(f["faction"], f["faction"])]
            row["挑戰"] += 1
            if f["tier"] in ("大勝", "險勝"):
                row["打贏"] += 1
                row["心得"] += f["xinde"]
                row["經驗"] += f["exp"]
        for (faction, source), n in self.tier3.items():
            by_faction[FACTION_NAMES.get(faction, faction)][f"三階・{'第一次的預設表' if source == 'first' else '保證'}"] = n
        for faction, n in self.treasures.items():
            by_faction[FACTION_NAMES.get(faction, faction)]["寶物"] = n
        share = {}
        for key in ("xinde", "exp"):
            total = sum(n for (_, k), n in self.battle_income.items() if k == key)
            mine = sum(f[key] for f in won)
            share["心得" if key == "xinde" else "經驗"] = round(mine / total, 2) if total else None
        days = sorted(self.prestige)
        low = {
            figures.name_of(content, fid): min(self.prestige[d][fid] for d in days if fid in self.prestige[d])
            for fid in content.figures if any(fid in self.prestige[d] for d in days)
        }
        return {
            "挑戰": len(self.fights), "打贏": len(won), "僵持": sum(f["tier"] == "僵持" for f in self.fights),
            "分陣營": dict(by_faction),
            "退場": {figures.name_of(content, fid): round(day, 1) for fid, day in sorted(self.retired.items(), key=lambda kv: kv[1])},
            "聲威最低": low,
            "挑戰佔打仗收入": share,
            "強弱人物場數": {"強": sum(f["strong"] for f in self.fights), "弱": sum(not f["strong"] for f in self.fights)},
            "頓悟": [(round(day, 1), kind) for day, kind in self.seizes],
        }


def _mastered(state) -> int:
    return sum(q == MASTERED for q in state.player.art_quality.values())


def _tier3(game) -> int:
    mats = game.content.materials
    return sum(n for mid, n in game.state.player.materials.items() if n > 0 and mid in mats and mats[mid].tier == 3)


def instrument(tally: ChallengeTally, outcome: str) -> list:
    """包函式（只在記憶體裡）：回傳要 start／stop 的 patch 清單。"""
    real_challenge, real_rewards, real_figure_tier3 = Game._challenge, Game._battle_rewards, Game._figure_tier3
    real_drop, real_seize, real_engine_seize = treasures.challenge_drop, cultivation.seize, Game._seize
    real_tick = BotRunner.tick
    kind_now: list[str] = []

    def challenge(self, fid):
        p = self.state.player
        before = figures.state_of(self.state, self.content, fid)
        strong = before.prestige * 2 >= self.content.figures[fid].start_prestige
        held, guaranteed_before = _tier3(self), sum(p.tier3_drops.values())
        msgs = real_challenge(self, fid)
        record = self.state.battles[0]
        day = self.state.world.time / DAY
        tally.fight(day, fid, p.faction, record.tier, record.xinde, record.exp, strong)
        guaranteed = sum(p.tier3_drops.values()) - guaranteed_before
        if guaranteed:
            tally.tier3[(p.faction, "guaranteed")] += guaranteed
        if _tier3(self) - held - guaranteed > 0:
            tally.tier3[(p.faction, "first")] += _tier3(self) - held - guaranteed
        if figures.is_out(self.state, fid) and fid not in tally.retired:
            tally.retired[fid] = day
        return msgs

    def rewards(self, squad, record, max_tier=None):
        msgs = real_rewards(self, squad, record, max_tier=max_tier)
        tally.battle_income[(self.state.player.faction, "xinde")] += record.xinde
        tally.battle_income[(self.state.player.faction, "exp")] += record.exp
        return msgs

    def drop(state, content, figure, season, record_id):
        item, lines = real_drop(state, content, figure, season, record_id)
        if item is not None:
            tally.treasures[state.player.faction] += 1
        return item, lines

    def engine_seize(self, record):
        kind_now.append("挑戰本人" if record.event.startswith("挑戰") else record.kind)
        try:
            return real_engine_seize(self, record)
        finally:
            kind_now.pop()

    def seize(state, content, world, ratio, rng):
        before = _mastered(state)
        msgs = real_seize(state, content, world, ratio, rng)
        if _mastered(state) > before:
            tally.seizes.append((state.world.time / DAY, kind_now[-1] if kind_now else "決戰"))
        return msgs

    def tick(self):
        report = real_tick(self)
        season = self.world.get_season()
        vehicle = world_mod._season_vehicle(self.content, season)
        tally.prestige[int(season.time // DAY)] = {
            fid: figures.state_of(vehicle, self.content, fid).prestige for fid in self.content.figures
            if figures.state_of(vehicle, self.content, fid).status == "active"
        }
        return report

    patches = [
        mock.patch.object(Game, "_challenge", challenge), mock.patch.object(Game, "_battle_rewards", rewards),
        mock.patch.object(treasures, "challenge_drop", drop), mock.patch.object(Game, "_seize", engine_seize),
        mock.patch.object(cultivation, "seize", seize), mock.patch.object(BotRunner, "tick", tick),
        mock.patch.object(insight_llm, "name", lambda *a, **k: (None, "", "")),  # 假的 client 不叫取名（FB-130 的繞法）
    ]
    del real_figure_tier3
    if outcome == "a":  # 丙 (a)：退場的龍頭人物照常出手（out_flag 另外在內容裡拿掉）
        patches.append(mock.patch.object(figures, "leader_out", lambda *a, **k: False))
    return patches


def configure(content, args) -> list[str]:
    """照參數在記憶體裡改設定與內容；回傳要印在第一行的說明。"""
    cfg, notes = content.config, []
    cfg.time_scale = args.time_scale
    cfg.bot_tick_seconds = args.tick
    if args.regen is not None:
        cfg.figure_prestige_regen = args.regen
    if args.cap is not None:
        cfg.figure_daily_loss_cap = args.cap
    if args.players is not None:
        cfg.server_max_players = args.players
    if args.no_challenge:
        cfg.figure_challenge_every_season = False
        notes.append("緊急開關關著（改之前的 14 天季）")
    if args.outcome == "a":
        for fid, fig in list(content.figures.items()):
            content.figures[fid] = fig.model_copy(update={"out_flag": None})
        notes.append("丙 (a)：退場的龍頭人物照常出手、不記 out_flag")
    if args.no_huangjin_end:
        content.scenario.thresholds = [
            th.model_copy(update={"ends_season": False}) if th.id == "huangjin_80" else th for th in content.scenario.thresholds
        ]
        notes.append("記憶體裡拿掉了黃巾聲勢 80 收季")
    return notes


def run_server(args, seed: int) -> dict:
    import sim_server_bots as sim
    content = load_content(ROOT / "content", profile=None if args.profile == "none" else args.profile)
    configure(content, args)
    tally = ChallengeTally()
    patches = instrument(tally, args.outcome)
    for p in patches:
        p.start()
    try:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            try:
                res = sim.run_season(content, Path(tmp), seed=seed, tick=args.tick)
            finally:
                database.close_all()
    finally:
        for p in reversed(patches):
            p.stop()
    out = tally.report(content)
    out.update({"收季": round(res["day"], 2), "結局": res["ending"], "黃巾聲勢季末": res["trends"].get("huangjin"),
                "陣營人數": res["factions"]})
    return out


def run_season_bot(args, seed: int) -> dict:
    from tianxia import bot
    content = load_content(ROOT / "content", profile=None if args.profile == "none" else args.profile)
    configure(content, args)
    tally = ChallengeTally()
    patches = instrument(tally, args.outcome)

    def observe(game) -> None:
        game.now = game.state.world.time  # 閉門不見看現實時間：跟賽季時間對得上（time_scale 1）

    for p in patches:
        p.start()
    try:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            from tianxia.sqlite_world import open_world
            store = open_world(Path(tmp) / "t.db")
            try:
                game = bot.play_season(content, seed, observe=observe, world=store)
            finally:
                database.close_all()
    finally:
        for p in reversed(patches):
            p.stop()
    out = tally.report(content)
    out["三階身上"] = _tier3(game)
    return out


def main(argv: list[str] | None = None) -> None:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("server", "season-bot"), default="server")
    parser.add_argument("--seeds", type=int, nargs="+", default=[1, 2, 3])
    parser.add_argument("--profile", default="none", help="none＝預設設定（14 天）；weekend＝週末設定")
    parser.add_argument("--regen", type=float, default=None)
    parser.add_argument("--cap", type=int, default=None)
    parser.add_argument("--outcome", choices=("a", "c"), default="c")
    parser.add_argument("--no-challenge", action="store_true")
    parser.add_argument("--no-huangjin-end", action="store_true")
    parser.add_argument("--players", type=int, default=None)
    parser.add_argument("--tick", type=float, default=120.0)
    parser.add_argument("--time-scale", type=float, default=1.0)
    args = parser.parse_args(argv)
    probe = load_content(ROOT / "content", profile=None if args.profile == "none" else args.profile)
    notes = configure(probe, args)
    print(f"設定：{args.profile}　mode {args.mode}　regen {probe.config.figure_prestige_regen:g}　cap {probe.config.figure_daily_loss_cap}"
          f"　outcome {args.outcome}　players {probe.config.server_max_players}　tick {args.tick:g}　time_scale {args.time_scale:g}"
          + ("　｜" + "；".join(notes) if notes else ""), flush=True)
    rows = []
    for seed in args.seeds:
        row = (run_server if args.mode == "server" else run_season_bot)(args, seed)
        rows.append(row)
        print(f"種子 {seed}：{row}", flush=True)
    if len(rows) > 1:
        print("平均：挑戰 {:.1f}・打贏 {:.1f}・僵持 {:.1f}・退場 {:.1f} 位・頓悟 {:.1f}".format(
            statistics.mean(r["挑戰"] for r in rows), statistics.mean(r["打贏"] for r in rows),
            statistics.mean(r["僵持"] for r in rows), statistics.mean(len(r["退場"]) for r in rows),
            statistics.mean(len(r["頓悟"]) for r in rows)), flush=True)


if __name__ == "__main__":
    main()
