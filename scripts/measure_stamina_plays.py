"""後期體力玩法第一批的效能（PM 2026-10-16：「每段比對多少埋伏、每一步多少負載、寫資料庫幾次、二十人以上同時在線」；只量不改）。

正式內容、週末設定、一個暫存資料庫。--per-side 個官軍、同樣多個黃巾（真的 Game，存進角色表）；黃巾的前 --ambushes 個在設得了伏的路段上設伏
（照路段輪流排，一段可能不只一個），官軍在那幾段路上來回走（疾行，一下就走完一段；步行補算的路徑相同）。量：
1. 路過一段路時查埋伏的那一下（Game._ambush_check）：沒有埋伏的路段、有埋伏但不是敵人、真的打一場，各幾微秒；
2. 一個人一步（同步＋走一段）要多久、寫幾筆資料庫（INSERT／UPDATE／DELETE 句數，set_trace_callback 數的）：關掉設伏、有埋伏但沒中、中伏打一場；
3. 一輪（全部的人各走一步，像伺服器在一把行動鎖底下一個一個做）總共多久，跟關掉設伏比；
4. 地盤重算（territory.update）有工事、沒工事各多久；屯糧開集結（works.on_muster）多久。
--rounds 輪，印中位數與 p95。"""
from __future__ import annotations

import argparse
import io
import random
import statistics
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tianxia import ambush, database, territory, works  # noqa: E402
from tianxia import world as world_mod  # noqa: E402
from tianxia.characters import CharacterStore  # noqa: E402
from tianxia.content import load_content  # noqa: E402
from tianxia.engine import Game  # noqa: E402
from tianxia.sqlite_world import open_world  # noqa: E402


class Writes:
    """數這段時間資料庫寫了幾句（INSERT／UPDATE／DELETE），與寫進去的字數（角色 JSON 的大小）。"""

    def __init__(self, store):
        self.n = 0
        self.conn = store.db._thread().conn
        self.conn.set_trace_callback(self._see)

    def _see(self, sql: str) -> None:
        head = sql.lstrip()[:6].upper()
        if head in ("INSERT", "UPDATE", "DELETE"):
            self.n += 1

    def take(self) -> int:
        n, self.n = self.n, 0
        return n


def _pct(xs: list[float], q: float) -> float:
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(q * len(xs)))] if xs else 0.0


def _ms(xs: list[float]) -> str:
    return f"中位 {statistics.median(xs) * 1000:.2f} ms・p95 {_pct(xs, 0.95) * 1000:.2f} ms" if xs else "—"


def _us(xs: list[float]) -> str:
    return f"中位 {statistics.median(xs) * 1e6:.1f} µs・p95 {_pct(xs, 0.95) * 1e6:.1f} µs" if xs else "—"


def run(args) -> None:
    content = load_content(ROOT / "content", profile="weekend")
    cfg = content.config
    cfg.auto_open_first_season = True
    cfg.road_sight_chance = 0.0
    cfg.train_event_chance = 0.0
    segs = sorted({ambush.key(a, b) for a, loc in content.locations.items() for b in loc.connections if ambush.road_ok(content, a, b)})
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        store = open_world(Path(tmp) / "t.db")
        try:
            store.open_season(content, 0.0)
            chars = CharacterStore(store.db)
            now = 1000.0

            def make(name, faction, at):
                g = Game.new(content, name, rng=random.Random(name), world=store)
                p = g.state.player
                p.faction, p.location = faction, at
                p.tutorial_step = len(content.tutorial.steps)
                p.joined_at = -1e9
                p.stamina = 250
                p.stats["silver"] = 200
                p.materials = {m.id: 3 for m in list(content.materials.values())[:6]}
                g.now = now
                chars.save(g.state)
                return g

            # 黃巾的前 --ambushes 個設伏：照路段輪流排（從路段的一頭往另一頭）
            owners = []
            for i in range(args.per_side):
                seg = segs[i % len(segs)]
                a, b = seg.split("|")
                g = make(f"黃{i}", "huang", a)
                if i < args.ambushes:
                    g.sync(now)
                    msgs = g.choose(f"ambush:set:{b}")
                    assert g.state.player.ambush is not None, msgs
                    chars.save(g.state)
                owners.append(g)
            walkers = []
            for i in range(args.per_side):
                seg = segs[i % len(segs)]
                a, b = seg.split("|")
                make(f"官{i}", "guan", b)
                walkers.append((f"官{i}", a, b))
            w = store.get_season()
            per_seg = [len(v) for v in w.ambushes.values()]
            print(f"設得了伏的路段 {len(segs)} 段；設下的埋伏 {sum(per_seg)} 處，分在 {len(per_seg)} 段，一段最多 {max(per_seg, default=0)} 處")
            print(f"在線 {args.per_side * 2} 人（官軍 {args.per_side} 個在走、黃巾 {args.per_side} 個，其中 {args.ambushes} 個在設伏）")

            # 1. 查埋伏的那一下
            probe = Game(content, chars.load("官0"), random.Random(0), store)
            probe.state.world = store.get_season()
            empty = next(s for s in segs if s not in probe.state.world.ambushes) if len(per_seg) < len(segs) else None
            t_empty, t_friend = [], []
            for _ in range(2000):
                a, b = ("zhuo_militia_hall", "zhuo_county") if empty is None else empty.split("|")
                t0 = time.perf_counter()
                probe._ambush_check(a, b, probe.state.world.time)
                t_empty.append(time.perf_counter() - t0)
            friend = Game(content, chars.load("黃1"), random.Random(0), store) if args.per_side > 1 else None
            if friend is not None:
                friend.state.world = store.get_season()
                a, b = segs[0].split("|")
                for _ in range(500):
                    t0 = time.perf_counter()
                    friend._ambush_check(a, b, friend.state.world.time)
                    t_friend.append(time.perf_counter() - t0)
            print(f"1. 查一段路：沒有埋伏 {_us(t_empty)}；有埋伏但是自己人 {_us(t_friend)}（照設伏那一刻的陣營篩掉，不讀伏兵的存檔）")

            d = next(b for b in content.battles.values() if b.timetable_event)
            writes = Writes(store)
            store.mutate_season(lambda s: s.supply.update({d.factions[0].id: 40, d.factions[1].id: 25}))
            writes.take()
            t0 = time.perf_counter()
            world_mod._open_claimed(store, content, now, lambda vehicle: (d, 50))
            print(f"0. 屯糧開集結（含開一場決戰）{(time.perf_counter() - t0) * 1000:.2f} ms、寫資料庫 {writes.take()} 句；起點 {store.get_battle().trend_start}")
            # 2、3. 一步與一輪
            step = {"off": [], "miss": [], "fight": []}
            wrote = {"off": [], "miss": [], "fight": []}
            rounds_on, rounds_off = [], []
            fights = 0
            for r in range(args.rounds):
                for mode in ("off", "on"):
                    cfg.ambush.enabled = mode == "on"
                    t_round = 0.0
                    for name, a, b in walkers:
                        with store.action_lock():
                            t0 = time.perf_counter()
                            g = Game(content, chars.load(name), random.Random(f"{name}|{r}"), store)
                            g.sync(now)
                            here = g.state.player.location
                            dest = a if here == b else b
                            before = len(g.state.battles)
                            g.travel(dest, "dash")
                            chars.save(g.state)
                            dt = time.perf_counter() - t0
                        t_round += dt
                        fought = len(g.state.battles) > before
                        fights += fought and mode == "on"
                        kind = "off" if mode == "off" else "fight" if fought else "miss"
                        step[kind].append(dt)
                        wrote[kind].append(writes.take())
                        g.state.player.stamina = 250
                        chars.save(g.state)
                        writes.take()
                    (rounds_on if mode == "on" else rounds_off).append(t_round)
                now += cfg.raid.shield_seconds + cfg.ambush.pair_cooldown_seconds + 1  # 下一輪冷卻過了，照樣中伏
                with store.action_lock():
                    store.mutate_season(lambda s: setattr(s, "time", s.time + cfg.ambush.pair_cooldown_seconds + 1))
                    for g in owners:  # 被打退、到時刻的伏兵再設一次（量的是一直有埋伏的情形）
                        if int(g.state.player.name[1:]) >= args.ambushes:
                            continue
                        g2 = Game(content, chars.load(g.state.player.name), random.Random(0), store)
                        g2.sync(now)
                        if g2.state.player.ambush is None:
                            g2.state.player.stamina = 250
                            seg = segs[int(g.state.player.name[1:]) % len(segs)]
                            g2.state.player.location = seg.split("|")[0]
                            g2.choose(f"ambush:set:{seg.split('|')[1]}")
                            chars.save(g2.state)
                    writes.take()
            cfg.ambush.enabled = True
            print(f"2. 一個人一步（同步＋疾行一段＋存檔）：關掉設伏 {_ms(step['off'])}；有埋伏沒中 {_ms(step['miss'])}；中伏打一場 {_ms(step['fight'])}")
            for kind, label in (("off", "關掉設伏"), ("miss", "沒中"), ("fight", "中伏")):
                if wrote[kind]:
                    print(f"   寫資料庫（{label}）：中位 {statistics.median(wrote[kind]):.0f} 句、最多 {max(wrote[kind])} 句")
            print(f"3. 一輪 {len(walkers)} 個人各走一步：關掉設伏 {_ms(rounds_off)}；開著 {_ms(rounds_on)}（{args.rounds} 輪共中伏 {fights} 次）")

            # 4. 地盤與屯糧
            season = store.get_season()
            territory.update(season, content)
            t_plain = []
            for _ in range(200):
                t0 = time.perf_counter()
                territory.update(season, content)
                t_plain.append(time.perf_counter() - t0)
            from tianxia.state import Fort  # noqa: PLC0415

            for loc_id, side in season.territory.tug.items():
                season.territory.forts[loc_id] = Fort(side=side, level=80, at=season.time)
            t_fort = []
            for _ in range(200):
                t0 = time.perf_counter()
                territory.update(season, content)
                t_fort.append(time.perf_counter() - t0)
            print(f"4. 地盤重算：沒有工事 {_us(t_plain)}；每一處都有工事 {_us(t_fort)}")
        finally:
            database.close_all()


def main(argv=None) -> None:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-side", type=int, default=20)
    ap.add_argument("--ambushes", type=int, default=10)
    ap.add_argument("--rounds", type=int, default=5)
    run(ap.parse_args(argv))


if __name__ == "__main__":
    main()
