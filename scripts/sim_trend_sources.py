"""黃巾聲勢的來源分析（地圖擴充第 4 步，2026-10-03）：用伺服器假人的整季模擬（scripts/sim_server_bots.py 的
run_season）跑幾季，把每一筆黃巾聲勢的實際變動記下來源（操練、真打贏、事件、虛擬玩家）與陣營，
另外數各陣營操練與真打的次數、聲勢的最高與最低點。還能試三種調法（只在這支腳本裡換掉引擎的函式，
不改程式）：
  --variant zero   操練不推大勢
  --variant half   操練推的量減半
  --cap N          每個角色每遊戲日只有頭 N 次歷練（真打或操練）推大勢
執行：.venv/Scripts/python.exe scripts/sim_trend_sources.py --seasons 4 [--variant zero|half] [--cap 3]
結果與結論見 docs/superpowers/rulings/2026-10-03-第4步平衡模擬.md。
"""
from __future__ import annotations

import argparse
import inspect
import io
import sys
import tempfile
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import sim_server_bots as sim  # noqa: E402
from tianxia import engine, rules  # noqa: E402
from tianxia import world as worldmod  # noqa: E402
from tianxia.content import load_content  # noqa: E402

TREND = "huangjin"
TRAINING = ("_drill", "_squad_encounter")


def _caller(names: tuple[str, ...], depth: int) -> str | None:
    """呼叫堆疊裡最近的一個在 names 裡的函式名稱（只看 depth 層）。"""
    return next((fr.function for fr in inspect.stack()[2:depth] if fr.function in names), None)


def main() -> None:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--seasons", type=int, default=4)
    ap.add_argument("--variant", choices=("none", "zero", "half"), default="none")
    ap.add_argument("--cap", type=int, default=0)
    args = ap.parse_args()

    season = {"n": 0}
    sources: dict[int, Counter] = defaultdict(Counter)
    actions: dict[int, Counter] = defaultdict(Counter)
    trajectory: dict[int, list[tuple[float, int]]] = defaultdict(list)

    original_change = rules.change_trend

    def change_trend(state, content, trend_id, delta, reveal=True):
        before = state.world.trends.get(trend_id, 0)
        out = original_change(state, content, trend_id, delta, reveal)
        after = state.world.trends.get(trend_id, 0)
        if trend_id == TREND:
            trajectory[season["n"]].append((state.world.time / 86400, after))
            if after != before:
                kind = {"_drill": "操練", "_squad_encounter": "真打贏", "sim_tick": "虛擬玩家", "apply_effect": "事件"}.get(
                    _caller(("_drill", "_squad_encounter", "sim_tick", "apply_effect"), 9), "其他")
                game = next((fr.frame.f_locals["self"] for fr in inspect.stack()[1:10]
                             if isinstance(fr.frame.f_locals.get("self"), engine.Game)), None)
                faction = (game.state.player.faction or "散人") if game is not None else "—"
                sources[season["n"]][(kind, faction)] += after - before
        return out

    rules.change_trend = engine.change_trend = worldmod.change_trend = change_trend

    original_push = engine.Game._train_push
    pushes_today: Counter = Counter()

    def train_push(self, trend_id, delta):
        value = original_push(self, trend_id, delta)
        training = _caller(TRAINING, 4)
        if training is None or trend_id != TREND:
            return value  # 假人評估地點時也會呼叫，只有真的歷練才算
        if training == "_drill" and args.variant == "zero":
            return 0
        if training == "_drill" and args.variant == "half":
            value = int(value / 2)
        if args.cap:
            key = (season["n"], self.state.player.name, int(self.state.world.time // 86400))
            if pushes_today[key] >= args.cap:
                return 0
            pushes_today[key] += 1
        return value

    engine.Game._train_push = train_push

    original_drill, original_encounter = engine.Game._drill, engine.Game._squad_encounter

    def drill(self, squad):
        actions[season["n"]][("操練", self.state.player.faction)] += 1
        return original_drill(self, squad)

    def encounter(self, squad_id, wild=False):
        squad = self.content.squads[squad_id]
        if not (squad.faction is not None and squad.faction == self.state.player.faction):
            kind = "野怪" if wild else "真打"  # 野怪：探索三選一撞上的，不推大勢
            actions[season["n"]][(kind, self.state.player.faction)] += 1
        return original_encounter(self, squad_id, wild=wild)

    engine.Game._drill, engine.Game._squad_encounter = drill, encounter

    content = load_content(ROOT / "content")
    for n in range(1, args.seasons + 1):
        season["n"] = n
        workdir = Path(tempfile.mkdtemp())  # SQLite 檔在 Windows 上還被占用時刪不掉，留給系統清
        result = sim.run_season(content, workdir, seed=n, tick=60.0)
        print(f"第 {n} 季：第 {result['day']:.2f} 天收季，{result['ending']}，大勢 {result['trends']}，"
              f"陣營 {result['factions']}，決戰開打 {result['battle_day']}")
        top = sorted(sources[n].items(), key=lambda kv: -abs(kv[1]))[:5]
        print("    聲勢來源：", "、".join(f"{kind}/{faction} {value:+d}" for (kind, faction), value in top))
        print("    歷練次數：", dict(actions[n]))
        points = trajectory[n]
        if points:
            high = max(points, key=lambda p: p[1])
            low = min(points, key=lambda p: p[1])
            print(f"    聲勢最高 {high[1]}（第 {high[0]:.1f} 天）、最低 {low[1]}（第 {low[0]:.1f} 天）")


if __name__ == "__main__":
    main()
