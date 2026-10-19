"""經驗節奏量表（正式季整合 8.2、3.4；只量不改）：「最認真」的人第幾天到第 30、40、50 級，經驗從哪裡來。

照伺服器的做法推時間：每隔 --step 現實分鐘 Game.sync(now) 一次（體力照回、新手期照算、季的事照推），把體力用到不夠下一下為止；
包住 team.add_exp 記本人每一筆經驗是哪一種行動給的。

「最認真」：體力不浪費、出陣次數用滿；其餘照「每點體力換最多經驗」挑——
- 新規則（一類一顆，--rules new）：練功，在每點體力換最多經驗的那一處（那一處的練功對手 × 本人勝率，每一個現實日開頭重挑一次）。
- 現在的規則（--rules old）：同一處按找素材（城外 encounter_chance 撞上那一場，現在唯一的經驗來源）。
- 出陣（有陣營的人）：每天的次數用在按得下去、一下期望經驗最多的那一處。
- 每次同步先配點、拿心得練成身上兩門、在醫館療傷（bot.allocate_points、bot.spend_xinde，同整季機器人）：不練的話威力不長，後段每一下的經驗
  跟著等級越來越不夠看。不合成、不修練（那要體力，體力全給經驗）。
- 內傷到氣血上限的 bot.CLINIC_AT 就站到最近的醫館療傷（clinic.nearest，同整季機器人的門檻）：不療的話內傷疊滿、氣血見底，後段一場都打不贏。
簡化（照實寫在輸出裡）：換地點直接站過去、不算路上的時間與體力；不挑戰本人、不上擂台、不接懸賞；事件一律按第一個按得下去的選項；
頭目戰照架勢出招（同假人）。吃丹（--pills）每個現實日照上限吃，體力不夠一顆的量時才吃。

用法：
  .venv/Scripts/python.exe scripts/measure_exp_pace.py --profile weekend --rules old new
  .venv/Scripts/python.exe scripts/measure_exp_pace.py --profile 14 --rules old new --days 14
  .venv/Scripts/python.exe scripts/measure_exp_pace.py --profile season21 --rules new --days 21 --pills 0 5
--late 0.1 0.12：只換這一份設定的 late_exp_step 再量（校曲線用）。
每一行多印練功的「每點體力換幾經驗」（練功拿到的經驗 ÷ 花在練功的體力，勝率算在裡面）與常去的練功點（第 8 批：各陣營的練功點一樣好）。"""
from __future__ import annotations

import argparse
import io
import random
import sys
import tempfile
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tianxia import bot, bot_policy, clinic, database, encounter, explore_modes, team  # noqa: E402
from tianxia.content import load_content  # noqa: E402
from tianxia.engine import Game  # noqa: E402
from tianxia.sqlite_world import open_world  # noqa: E402

DAY = 86400.0
T0 = 1_792_339_200.0  # 2026-10-19 週一 00:00（台灣）：開季那一刻
SIDES = {"官軍": "guan", "黃巾": "huang", "豪強": "haoqiang", "散人": None}
PRACTICE = explore_modes.option_id(explore_modes.PRACTICE)
GATHER = explore_modes.option_id(explore_modes.GATHER)


class Ledger:
    """包住 team.add_exp：本人的每一筆經驗記在此刻在做的那一種行動（source）底下。"""

    def __init__(self, name: str) -> None:
        self.name, self.source, self.by = name, "其他", Counter()
        self._orig = team.add_exp

    def __enter__(self):
        def spy(content, member, amount, name):
            if name == self.name and amount > 0 and member.level < content.config.max_level:
                self.by[self.source] += amount
            return self._orig(content, member, amount, name)

        team.add_exp = spy
        return self

    def __exit__(self, *exc) -> None:
        team.add_exp = self._orig


def _win_rate(game: Game, squad, runs: int = 40) -> float:
    power = team.power_vs(game.state, game.content, game.world, squad, fresh=True)
    rng = random.Random(7)
    return sum(encounter.resolve_encounter(power, squad.difficulty, rng).tier in team.WIN_TIERS for _ in range(runs)) / runs


def _best_spot(game: Game, press: str) -> str:
    """每點體力換最多經驗的那一處：那一處練功（找素材撞上）打的那一路的經驗 × 本人勝率。press 那一顆在那裡要按得下去；
    舊規則（找素材）城鎮不撞仗，不算。"""
    c, p = game.content, game.state.player
    here, best, value = p.location, p.location, -1.0
    for loc in c.locations.values():
        if loc.prologue_only or (press == GATHER and explore_modes.is_town(c, loc)):
            continue
        foe = game._gather_foe(loc)
        if foe is None or foe.exp <= 0:
            continue
        p.location = loc.id
        if not any(o.id == press and o.enabled for o in game.options(odds=False)):
            continue
        v = foe.exp * _win_rate(game, foe)
        if v > value:
            best, value = loc.id, v
    p.location = here
    return best


def _sortie_spot(game: Game) -> str | None:
    """出陣按得下去、一下期望經驗最多的那一處（沒有出陣是 None）：攻照對手經驗 × 本人勝率（最強的那一路當對手，同鈕上的勝算），
    守與攪局照拿誰的數字（Game._sortie_host，不打、一定拿到）。出陣只給對手的三成（drill_reward_share），各處一樣，不影響挑哪一處。"""
    c, p = game.content, game.state.player
    here, best, value = p.location, None, -1.0
    for loc in c.locations.values():
        if loc.prologue_only:
            continue
        p.location = loc.id
        if not any(o.id == "act:train" and o.enabled for o in game.options(odds=False)):
            continue
        mode = game.sortie_mode()
        if mode == "attack":
            foes = [c.squads[sid] for sid in game._sortie_foes(loc) if sid in c.squads]
            v = min((f.exp * _win_rate(game, f) for f in foes), default=0.0) if foes else 0.0
        else:
            host = game._sortie_host(loc, mode)
            v = float(host.exp) if host is not None else 0.0
        if v > value:
            best, value = loc.id, v
    p.location = here
    return best


def _settle(game: Game, ledger: Ledger, rng: random.Random) -> bool:
    """眼前有事件、頭目戰、有所感就先了結（回 True）。"""
    s = game.state
    if s.player.duel is not None:
        ledger.source = "頭目戰"
        game.choose(f"duel:{bot_policy.duel_move(game, rng)}")
        return True
    if s.player.sensing is not None:
        game.choose(next(o.id for o in game.options(odds=False) if o.enabled))
        return True
    if s.pending_event or s.player.pending_companion:
        ledger.source = "事件"
        opts = [o for o in game.options(odds=False) if o.enabled]
        pick = next((o for o in opts if o.id.startswith("choice:")), None) or next((o for o in opts if o.id == "talk:leave"), opts[0])
        game.choose(pick.id)
        return True
    return False


def _heal(game: Game) -> None:
    """內傷到 bot.CLINIC_AT 就站到最近的醫館療傷（付得起多少治多少，同修練頁的療傷鈕）。"""
    if bot.injury_share(game) < bot.CLINIC_AT or not bot.can_pay_clinic(game):
        return
    route = clinic.nearest(game.state, game.content)
    if route is not None:
        game.state.player.location = route.path[-1]
        game.heal()


def _spend(game: Game, ledger: Ledger, rules: str, spot: str, rng: random.Random) -> int:
    """把體力用掉；回按了幾下練功（找素材）。"""
    p = game.state.player
    presses = 0
    for _ in range(400):
        if _settle(game, ledger, rng):
            continue
        sortie = _sortie_spot(game) if game.sorties_left() > 0 else None
        if sortie is not None:
            p.location = sortie
            ids = {o.id for o in game.options(odds=False) if o.enabled}
            if "act:train" in ids:
                ledger.source = "出陣"
                game.choose("act:train")
                continue
        p.location = spot
        ids = {o.id for o in game.options(odds=False) if o.enabled}
        press = PRACTICE if rules == "new" else GATHER
        if press not in ids:
            return presses
        ledger.source = "練功" if rules == "new" else "找素材"
        game.choose(press)
        presses += 1
    return presses


def run_one(profile: str | None, side: str, rules: str, pills: int, days: float, step_min: float, late: float | None,
            tmp: Path) -> dict:
    content = load_content(ROOT / "content", profile=profile)
    cfg = content.config
    cfg.precise_actions = rules == "new"
    if late is not None:
        cfg.late_exp_step = late
    cfg.road_sight_chance = 0.0
    store = open_world(tmp / f"{profile}-{side}-{rules}-{pills}-{late}.db")
    store.seed_first_season(content)
    store.open_season(content, T0)
    name = f"量{side}"
    game = Game.new(content, name, rng=random.Random(1), world=store)
    game.client = None
    game.sync(T0)
    p = game.state.player
    p.faction = SIDES[side]
    if p.faction == "haoqiang":
        p.ally = "guan"
    p.tutorial_step = len(content.tutorial.steps)
    p.stamina_pills = 10_000 if pills else 0
    rng = random.Random(2)
    reached: dict[int, float] = {}
    daily: list[int] = []
    powers: list[int] = []  # 每天結束時本人的武學威力（Game._battle_power）：練功挑得動多強的對手看它
    spots: Counter = Counter()  # 每一個現實日挑的練功點（地點・對手）
    presses = 0
    with Ledger(name) as ledger:
        press = PRACTICE if rules == "new" else GATHER
        now, spot, day_mark = T0, _best_spot(game, press), T0
        while now < T0 + days * DAY:
            game.sync(now)
            if now >= day_mark:
                spot, day_mark = _best_spot(game, press), day_mark + DAY
                foe = game._gather_foe(content.locations[spot])
                spots[f"{content.locations[spot].name}・{foe.name if foe else '—'}"] += 1
            _heal(game)
            bot.allocate_points(game, rng)  # 配點、練成（同整季機器人）
            bot.spend_xinde(game, rng)
            while pills and game.pills_left_today() and p.stamina <= cfg.stamina_max - cfg.stamina_pill_restore:
                game.take_stamina_pill(pill_only=True)
            presses += _spend(game, ledger, rules, spot, rng)
            for lv in (30, 40, 50):
                if lv not in reached and p.member.level >= lv:
                    reached[lv] = (now - T0) / DAY
            now += step_min * 60
            if now >= T0 + (len(daily) + 1) * DAY:
                daily.append(p.member.level)
                powers.append(round(game._battle_power()))
    database.close_all()
    source = "練功" if rules == "new" else "找素材"
    per = ledger.by[source] / (presses * cfg.action_cost["explore"]) if presses else 0.0
    return {"reached": reached, "daily": daily, "by": ledger.by, "level": p.member.level, "silver": p.stats.get("silver", 0),
            "late": cfg.late_exp_step, "per_stamina": per, "spots": spots, "powers": powers}


def main(argv=None) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", default="weekend", help="weekend｜season21｜14（14＝不帶設定檔的 14 天季）")
    ap.add_argument("--rules", nargs="+", default=["old", "new"], choices=["old", "new"])
    ap.add_argument("--sides", nargs="+", default=list(SIDES), choices=list(SIDES))
    ap.add_argument("--pills", nargs="+", type=int, default=[0], help="0＝不吃丹；其他數字＝每天照上限吃")
    ap.add_argument("--days", type=float, default=None, help="量幾個現實日（預設：週末 2.5、14 天 14、21 天 21）")
    ap.add_argument("--step", type=float, default=60.0, help="幾分鐘同步一次、把體力用掉")
    ap.add_argument("--late", nargs="+", type=float, default=[None], help="換 late_exp_step 再量")
    args = ap.parse_args(argv)
    profile = None if args.profile == "14" else args.profile
    days = args.days or {"weekend": 2.5, "season21": 21.0}.get(args.profile, 14.0)
    print(f"設定 {args.profile}；量 {days} 個現實日、每 {args.step:.0f} 分鐘同步一次。簡化：換地點直接站過去、不挑戰本人、"
          "不上擂台、不接懸賞、事件按第一個選項（見檔頭）。")
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        for late in args.late:
            for rules in args.rules:
                for pills in args.pills:
                    for side in args.sides:
                        r = run_one(profile, side, rules, pills, days, args.step, late, Path(tmp))
                        hit = "、".join(f"{lv} 級第 {d:.2f} 天" for lv, d in sorted(r["reached"].items())) or "沒到 30 級"
                        total = sum(r["by"].values()) or 1
                        src = "、".join(f"{k} {v * 100 / total:.0f}%" for k, v in r["by"].most_common())
                        print(f"[{'新' if rules == 'new' else '舊'}規則・加陡 {r['late']}・{'吃丹' if pills else '不吃丹'}] {side}："
                              f"{hit}；最後 {r['level']} 級、銀兩 {r['silver']}；經驗來源 {src}")
                        print(f"    每天結束時的等級：{r['daily']}")
                        print(f"    每天結束時的威力：{r['powers']}")
                        where = "、".join(f"{k} {v} 天" for k, v in r["spots"].most_common(3))
                        print(f"    {'練功' if rules == 'new' else '找素材'}每點體力 {r['per_stamina']:.2f} 經驗；常去的：{where}")


if __name__ == "__main__":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    main()
