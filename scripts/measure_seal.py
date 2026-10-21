"""玉璽碎片的量表（docs/superpowers/specs/2026-10-11-玉璽碎片-design.md 15.2；計畫 2026-10-12-玉璽-1-核心.md Task 12）：只量不改。

跑真的程式（包住 scripts/sim_season_one.py::run_season，攔下 seal.on_muster、Game._seal_settle、seal_duel.finish 記數字），印：
- 每季：現世沒有、哪一片、得主的戰功名次；
- 每次璽動：持有者那一方四檔、挑得出幾個合格的挑戰者、單挑每回合氣勢、結果、單挑係數、再擲中沒中；
- 一季易手幾次、隱沒幾片；新角色快照的份量比；季末碎片在真人、假人手上各幾片；持有者所在陣營的大勝比例；
- 一季被捲進璽動幾成、一季易手幾成，與照一輪（7 ÷ 現世率 季）換算的全服單挑場數與易手次數。
參數：--decisive-week（改提前收季的週次）、--force-stir（每場都璽動：stir_chance 1、一季上限拿掉，量「一次璽動之後」的條件分布）、
--holders N（假人一建好就把前 N 片記到前 N 個假人名下，since_season 0：不然第一季沒有人持有、量不到璽動）。
--duel-mc：只跑單挑，掃份量比 0.5～3、在場與代打四種組合、放手一搏（成功率 30～70；不搏、每回合搏、一場最多兩次），報 E[g]（單挑係數的期望）。
每個種子給一份量表用的密鹽（「measure-種子」）：沒有密鹽時碎片的擲骰只看天機與季別，每個種子擲出一樣的結果。
數字照實報，不為了量表調參數。
玉璽二：--mandate-mc 數七片湊齊要幾季（純蒙地卡羅，照 --emerge-rate）；--mandate 把每一季直接蓋成天命之季（開季那一刻；--holders N 片記到
假人名下、--sunk M 片隱沒），量三場必定璽動、單挑、易手、喚回、天命之爭的起點與結果、結局。

領地爭奪第三批 B（計畫 Task 15，設計 4.8）：--mandate-mc 加上 --hide H --find F --explores N [N …] --own-share S [--own-scale X]
就改量「碎片藏在中立地、探索撿到」的節奏：每季現世率＝H×（1−（1−F）^（N×（1−S））×（1−min(1,F×X)）^（N×S））——開季先擲 H 有沒有一片
藏著，之後藏碎片的那一塊一季被探索 N 次，其中 S 的比例是那一塊此刻歸你的陣營（機率 ×X），只要撿到一次就現世；再數七片湊齊要幾季
（同上）。沒給的參數讀 Config.seal.cache（hide_chance／find_chance／own_scale）；N 預設 150 300 600 1000、S 預設 0.5。N 是一個外部的
假設（一塊中立地一季被探索幾次）：量表算得出的只是「N 是多少時落在 16～20 季」。

執行：.venv/Scripts/python.exe scripts/measure_seal.py --seeds 1 2 3 [--factions 5 5 5] [--force-stir --holders 7] [--duel-mc]
      [--mandate --holders 5 --sunk 2] [--mandate-mc --emerge-rate 0.35 0.2]
      [--mandate-mc --hide 0.4 --find 0.005 --explores 150 300 600 1000 --own-share 0.5]
輸出只有數字與陣營，不列名號。
"""
from __future__ import annotations

import argparse
import contextlib
import io
import random
import statistics
import sys
import tempfile
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from tianxia import battle_instance, database, seal, seal_duel, timetable  # noqa: E402
from tianxia.bot_runner import BotRunner  # noqa: E402
from tianxia.characters import open_characters  # noqa: E402
from tianxia.content import load_content as _load_content  # noqa: E402
from tianxia.content import profile_line  # noqa: E402
from tianxia.engine import Game  # noqa: E402
from tianxia.models import MOVES, Content  # noqa: E402
from tianxia.sqlite_world import SqliteWorldStore, open_world  # noqa: E402
from tianxia.world_state import SealDuel, SealSide  # noqa: E402

import sim_season_one  # noqa: E402

PRESENCES = ("both", "challenger", "holder", "none")  # 誰在場（另一邊交給代打）
PRESENT = {"both": ("challenger", "holder"), "challenger": ("challenger",), "holder": ("holder",), "none": ()}
MODES = ("none", "every", "cap2")  # 在場那一邊：不搏（出份量最高的招）、每回合搏（不管一場兩次的上限）、照上限前兩回合搏
HOLDER_SCORES = {"強攻": 60.0, "固守": 50.0, "奇襲": 40.0}  # 持有者固定的份量；挑戰者乘份量比
HOLDER_POWER = 100.0
SALT = "measure"
ROUND_SECONDS = 20.0


def load_content(root: Path, profile: str | None = "weekend") -> Content:
    """照 sim_season_one 的載法：週末設定（"none" 是不帶設定覆寫檔的十四天季）、第一季開著（run_season 自己再設一次）。"""
    content = _load_content(root, profile=None if profile in (None, "none") else profile)
    content.config.season_one = True
    return content


def _side(name: str, scale: float) -> SealSide:
    return SealSide(name=name, power=HOLDER_POWER * scale, scores={m: v * scale for m, v in HOLDER_SCORES.items()},
                    hp=300.0, hp_cap=300.0)


def _best(side: SealSide) -> str:
    return max(MOVES, key=lambda m: (side.scores.get(m, 0.0), -MOVES.index(m)))


def one_duel(content: Content, n: int, ratio: float, presence: str, rate: int, mode: str) -> str:
    """跑一場單挑到收場，回挑戰者角度的結果（verdict）。不碰 Game、不碰資料庫；種子照流水號 n。"""
    cfg = content.config.seal
    d = SealDuel(id=f"mc{n}:chishou", shard="chishou", phase="active", starts_real=0.0, challenger=_side("挑戰者", ratio),
                 holder=_side("懷璽", 1.0), cap=cfg.cap, rounds=cfg.rounds)
    t = 0.0
    result = None
    while result is None:
        for who in PRESENT[presence]:
            getattr(d, who).last_seen = t  # 在場：這一回合開始前剛推過
        seal_duel.open_round(d, t, content, SALT, 0)
        for who in PRESENT[presence]:
            side = getattr(d, who)
            gamble = mode == "every" or (mode == "cap2" and side.gambles < cfg.gamble_cap)
            if gamble:
                seal_duel.submit(d, who, text="放手一搏", rate=rate)
            else:
                seal_duel.submit(d, who, move=_best(side))
        seal_duel.resolve(d, content, SALT, 0)
        result = seal_duel.verdict(d, content.config.duel)
        t += ROUND_SECONDS
    return result


def duel_mc(content: Content, ratios, trials: int, rates, modes, presences=PRESENCES) -> list[dict]:
    """每個（份量比, 在場組合, 成功率, 模式）跑 trials 場單挑；eg＝單挑係數（Config.seal.take_share[結果]）的平均。同樣的參數結果一樣。"""
    share = content.config.seal.take_share
    rows = []
    n = 0
    for ratio in ratios:
        for presence in presences:
            for rate in rates:
                for mode in modes:
                    total = 0.0
                    for _ in range(trials):
                        n += 1
                        total += share.get(one_duel(content, n, ratio, presence, rate, mode), 0.0)
                    rows.append({"ratio": ratio, "presence": presence, "rate": rate, "mode": mode, "eg": total / trials})
    return rows


PRESENCE_WORDS = {"both": "都在場", "challenger": "只有挑戰者", "holder": "只有持有者", "none": "都代打"}
MODE_WORDS = {"none": "不搏", "every": "每回合搏", "cap2": "最多兩次"}


def print_mc(rows: list[dict]) -> None:
    print("份量比\t在場\t成功率\t放手一搏\tE[g]")
    for r in rows:
        print(f"{r['ratio']:g}\t{PRESENCE_WORDS.get(r['presence'], r['presence'])}\t{r['rate']}\t"
              f"{MODE_WORDS.get(r['mode'], r['mode'])}\t{r['eg']:.3f}")


def mandate_mc(emerge_rate: float, trials: int = 4000, seed: int = 0) -> dict:
    """天命之季多久來一次（玉璽二）：每季最多現世一片、機率 emerge_rate，數到七片都現世過要幾季（下一季就是天命之季）。
    只用 random.Random(seed)：同樣的參數結果一樣。回 rate、mean、p10、p50、p90（季）與 cycle（一輪＝湊齊＋天命之季一季）。"""
    if emerge_rate <= 0:  # 永遠湊不齊（find 是 0 之類）：不跑，免得無窮迴圈
        return {"rate": emerge_rate, "mean": float("inf"), "p10": float("inf"), "p50": float("inf"), "p90": float("inf"), "cycle": float("inf")}
    rng = random.Random(seed)
    counts = []
    for _ in range(trials):
        seasons = got = 0
        while got < 7:
            seasons += 1
            got += rng.random() < emerge_rate
        counts.append(seasons)
    counts.sort()
    mean = round(sum(counts) / len(counts), 1)

    def pick(q: float) -> int:
        return counts[min(len(counts) - 1, int(q * len(counts)))]

    return {"rate": emerge_rate, "mean": mean, "p10": pick(0.1), "p50": pick(0.5), "p90": pick(0.9), "cycle": round(mean + 1, 1)}


def season_rate(hide: float, find: float, explores: int, own_share: float = 0.0, own_scale: float = 1.5) -> float:
    """領地爭奪的季，一季裡有一片現世的機率（Task 15）：開季先擲 hide 有沒有一片藏著，之後藏碎片的那一塊一季被探索 explores 次，
    其中 own_share 的比例是那一塊此刻歸你的陣營（每一下 find×own_scale，夾在 1 以下），其餘每一下 find；一次都沒撿到的機率是兩段相乘，
    撿到至少一次就現世。find 是 1、explores 是 1 時就等於 hide（舊的「每季現世率」）。"""
    own = min(1.0, find * own_scale)
    miss = (1.0 - find) ** (explores * (1.0 - own_share)) * (1.0 - own) ** (explores * own_share)
    return hide * (1.0 - miss)


def cache_rows(hide: float, find: float, explores: list[int], own_share: float, own_scale: float, trials: int = 4000, seed: int = 0) -> list[dict]:
    """每個 explores 一列：mandate_mc 的那幾格加上 explores、p_find（有藏的季裡撿到的機率）、hide、find。"""
    rows = []
    for n in explores:
        rate = season_rate(hide, find, n, own_share, own_scale)
        row = mandate_mc(rate, trials, seed)
        row.update(explores=n, p_find=(rate / hide if hide else 0.0), hide=hide, find=find, own_share=own_share, own_scale=own_scale)
        rows.append(row)
    return rows


def print_cache_mc(rows: list[dict]) -> None:
    print("碎片藏在中立地、探索撿到（每季現世率 → 七片湊齊要幾季；一輪＝湊齊＋天命之季一季）")
    for r in rows:
        mean = "永遠湊不齊" if r["mean"] == float("inf") else f"平均 {r['mean']} 季（p10 {r['p10']}、中位 {r['p50']}、p90 {r['p90']}），一輪約 {r['cycle']} 季"
        print(f"  藏 {r['hide']:.2f}、每下 {r['find']:.4f}（自家 ×{r['own_scale']:g}、自家佔 {r['own_share']:.0%}）、藏處一季探索 {r['explores']} 次："
              f"藏著時撿到 {r['p_find']:.0%}，每季現世 {r['rate']:.3f}，{mean}")


def print_mandate_mc(rows: list[dict]) -> None:
    print("天命之季多久來一次（每季現世率 → 七片湊齊要幾季；一輪＝湊齊＋天命之季一季）")
    for r in rows:
        print(f"  現世率 {r['rate']:.2f}：平均 {r['mean']} 季（p10 {r['p10']}、中位 {r['p50']}、p90 {r['p90']}），一輪約 {r['cycle']} 季")


def mandate_lines(rows: list[dict]) -> list[str]:
    """天命之季那幾季的分布：天命之爭的結果（「官軍大勝」……「天命未定」「沒開成」）、結局、平均璽動／單挑／易手／喚回。"""
    got = [r["mandate"] for r in rows if r.get("mandate")]
    if not got:
        return []
    results: dict[str, int] = {}
    endings: dict[str, int] = {}
    for m in got:
        results[m.get("result") or "沒開成"] = results.get(m.get("result") or "沒開成", 0) + 1
        endings[m.get("ending") or "—"] = endings.get(m.get("ending") or "—", 0) + 1
    n = len(got)
    return [
        f"天命之季 {n} 季：天命之爭 {'、'.join(f'{k} {v}' for k, v in results.items())}；結局 {'、'.join(f'{k} {v}' for k, v in endings.items())}",
        f"平均每季璽動 {sum(len(r['stirs']) for r in rows) / n:.1f}、單挑 {sum(len(r['duels']) for r in rows) / n:.1f}、"
        f"易手 {sum(r['takes'] for r in rows) / n:.2f}、喚回 {sum(m.get('recalls', 0) for m in got) / n:.1f}",
    ]


def measure_season(content: Content, seed: int, factions, hours: float, force_stir: bool, holders: int, tick: float = 60.0,
                   mandate: bool = False, sunk: int = 0) -> dict:
    """包 sim_season_one.run_season 跑一季，攔下現世、璽動、單挑的數字。回 summary 用的那幾個鍵。
    mandate：開季那一刻把這一季蓋成天命之季（玉璽二；sorted(content.seal) 第 holders 片起的 sunk 片先改成隱沒），另外記天命之爭的
    起點偏移、各方握幾片、結果、喚回幾片、結局（row["mandate"]）。"""
    cfg = content.config.seal
    if force_stir:
        cfg.stir_chance, cfg.season_stir_cap = 1.0, 99
    row: dict = {"emerged": None, "emerge_rank": None, "emerge_rolled": 0, "stirs": [], "duels": [], "takes": 0, "sunk": 0,
                 "holders": {"真人": 0, "假人": 0}, "fresh_ratio": [], "holder_big_wins": []}
    current: dict = {"tier": None, "eligible": 0}
    edges: dict[str, list[float]] = {}
    assigned: list[str] = []
    real_settle, real_tier, real_finish, real_resolve = Game._seal_settle, seal.tier_for, seal_duel.finish, seal_duel.resolve
    real_challengers, real_spectators, real_add = Game._seal_challengers, Game._seal_spectators, BotRunner._add_bot
    real_open, real_shift, real_mandate = SqliteWorldStore.open_season, seal.lean_shift, Game._mandate_settle
    tuning = content.config.battle
    info: dict = {}

    def tier_for(holder_side, winner, margin):
        current["tier"] = real_tier(holder_side, winner, margin)
        return current["tier"]

    def challengers(self, *args, **kwargs):
        rows = real_challengers(self, *args, **kwargs)
        current["eligible"] += len(rows)
        return rows

    def spectators(self, *args, **kwargs):
        rows = real_spectators(self, *args, **kwargs)
        current["eligible"] += len(rows)
        return rows

    def settle(self, battle, definition, result):
        current["tier"], current["eligible"] = None, 0
        # 沒走到挑挑戰者的原因（同 Game._seal_settle 的兩道擋）：兩軍都沒人還能打（保底），或那一片此刻已經不在持有者手上
        deserted = seal.deserted(battle, definition)
        holder_now = self.world.seal_state().registry.shards.get(battle.seal_shard or "")
        real_settle(self, battle, definition, result)
        if battle.seal_shard:
            moved = holder_now is None or seal.key(holder_now.holder) != seal.key(battle.seal_holder)
            tier = current["tier"] or ("保底" if deserted else "易主過" if moved else "未判")
            row["stirs"].append({"tier": tier, "eligible": current["eligible"]})
            row["holder_big_wins"].append(1 if tier == "大勝" else 0)
        if battle.seal_emerge:
            row["emerge_rolled"] += 1
            reg = self.world.seal_state().registry
            got = next((e for e in reg.history if e.kind == "emerge" and e.record == battle.record_id), None)
            if got is not None:
                side = str(result.get("side") or "")
                names = [p.name for p, _ in battle_instance.merit_ranking(battle, tuning, side)]
                row["emerged"] = content.seal[got.shard].name
                row["emerge_rank"] = names.index(got.holder) + 1 if got.holder in names else None

    def resolve(duel, *args, **kwargs):
        line = real_resolve(duel, *args, **kwargs)
        edges.setdefault(duel.id, [50.0]).append(round(duel.edge, 1))
        return line

    def finish(shared, duel, content_, result, now):
        event = real_finish(shared, duel, content_, result, now)
        taken = event.kind == "take"
        row["duels"].append({"verdict": result or "沒打完", "share": cfg.take_share.get(result or "", 0.0), "taken": taken,
                             "edges": edges.get(duel.id, [50.0])})
        row["takes"] += 1 if taken else 0
        if duel.holder.fresh:
            mine = battle_instance.strength(tuning, duel.holder.power)
            row["fresh_ratio"].append(round(battle_instance.strength(tuning, duel.challenger.power) / max(1.0, mine), 2))
        return event

    def add_bot(self, faction_id, season, bots, now, state=None):
        out = real_add(self, faction_id, season, bots, now, state=state)
        if len(assigned) < holders and out:
            name = out[-1].player.name
            shard_id = sorted(content.seal)[len(assigned)]
            assigned.append(name)

            def _give(st):
                reg = seal.filled(st.seal, content)
                reg.shards[shard_id].state, reg.shards[shard_id].holder, reg.shards[shard_id].since_season = "held", name, 0

            self.world.mutate(_give)
        return out

    def open_season(self, content_, now):
        ok = real_open(self, content_, now)
        if ok:
            def _stamp(st):
                reg = seal.filled(st.seal, content)
                for shard_id in sorted(content.seal)[holders:holders + sunk]:
                    reg.shards[shard_id].state, reg.shards[shard_id].emerged_round = "sunk", reg.round
                seal.stamp_mandate(st, content, timetable.default_time(seal.mandate_event(content), content, st.season))

            self.mutate(_stamp)
        return ok

    def lean_shift(lean, definition, cfg_):
        info["shift"] = real_shift(lean, definition, cfg_)
        info["lean"] = seal.lean_text(lean, definition)
        return info["shift"]

    def mandate_settle(self, winner, record, battle_name):
        real_mandate(self, winner, record, battle_name)
        battle = self.world.get_battle()
        margin = battle.outcome_margin if battle is not None else ""
        info["result"] = f"{timetable.SIDE_NAMES.get(winner, winner)}{margin}" if winner else "天命未定"

    targets = dict(zip(sim_season_one.SIDES, factions))
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "seal.db"
        try:
            # 每個種子一份量表用的密鹽：沒有密鹽時碎片的擲骰只看天機與季別，五個種子擲出一模一樣的現世與璽動；照種子給就各自不同、重跑一樣
            open_world(db_path).mutate(lambda st: setattr(st.seal, "salt", f"measure-{seed}"))
            with contextlib.ExitStack() as stack:
                for target, name, value in (
                    (seal, "tier_for", tier_for), (Game, "_seal_settle", settle), (Game, "_seal_challengers", challengers),
                    (Game, "_seal_spectators", spectators), (seal_duel, "finish", finish), (seal_duel, "resolve", resolve),
                    (BotRunner, "_add_bot", add_bot),
                ):
                    stack.enter_context(mock.patch.object(target, name, value))
                if mandate:  # 天命之季（玉璽二）：開季那一刻蓋章，攔起點偏移與定天命
                    stack.enter_context(mock.patch.object(SqliteWorldStore, "open_season", open_season))
                    stack.enter_context(mock.patch.object(seal, "lean_shift", lean_shift))
                    stack.enter_context(mock.patch.object(Game, "_mandate_settle", mandate_settle))
                result = sim_season_one.run_season(content, db_path, seed, targets, hours, tick)
            world, characters = open_world(db_path), open_characters(db_path)
            view = world.seal_state()
            for shard in view.registry.shards.values():
                if shard.state == "held" and shard.holder:
                    state = characters.load(shard.holder)
                    row["holders"]["假人" if state is not None and state.player.bot is not None else "真人"] += 1
            row["sunk"] = sum(1 for e in view.registry.history if e.kind == "sink")
            row["ending"] = result["ending"]
            if mandate:
                info["recalls"] = sum(1 for e in view.registry.history if e.kind == "recall")
                info["ending"] = result["ending"]
                row["mandate"] = info
        finally:
            database.close_all()  # 不先關連線，Windows 刪不掉暫存資料夾
    return row


def summary(seed: int, row: dict) -> str:
    """一個種子一行：「種子 1：現世 雲篆（戰功第 2）　璽動 1（大敗×1，合格 3）　單挑 1（險勝，係數 0.6，未易手）　易手 0　隱沒 0
    真人 1／假人 0　新角色份量比 3.1　持有者那一方大勝 1／2」。"""
    emerged = row.get("emerged")
    rank = row.get("emerge_rank")
    head = f"現世 {emerged}（戰功第 {rank}）" if emerged and rank else f"現世 {emerged}" if emerged else "現世 無"
    stirs = row.get("stirs", [])
    tiers: dict[str, int] = {}
    for s in stirs:
        tiers[s["tier"]] = tiers.get(s["tier"], 0) + 1
    stir = f"璽動 {len(stirs)}"
    if stirs:
        stir += f"（{'、'.join(f'{t}×{n}' for t, n in tiers.items())}，合格 {'、'.join(str(s['eligible']) for s in stirs)}）"
    duels = row.get("duels", [])
    duel = f"單挑 {len(duels)}"
    if duels:
        duel += "（" + "；".join(f"{d['verdict']}，係數 {d['share']:g}，{'易手' if d['taken'] else '未易手'}" for d in duels) + "）"
    fresh = row.get("fresh_ratio") or []
    fresh_text = f"新角色份量比 {'、'.join(f'{x:g}' for x in fresh)}" if fresh else "新角色份量比 無"
    wins = row.get("holder_big_wins") or []
    hold = row.get("holders", {})
    text = (f"種子 {seed}：{head}　{stir}　{duel}　易手 {row.get('takes', 0)}　隱沒 {row.get('sunk', 0)}　"
            f"真人 {hold.get('真人', 0)}／假人 {hold.get('假人', 0)}　{fresh_text}　持有者那一方大勝 {sum(wins)}／{len(wins)}")
    m = row.get("mandate")
    if m:
        text += (f"　天命之爭 {m.get('result') or '沒開成'}（起點偏 {m.get('shift', 0):+d}，{m.get('lean', '—')}）"
                 f"　喚回 {m.get('recalls', 0)}　結局 {m.get('ending') or '—'}")
    return text


def round_up(rows: list[dict], content: Content, emerge_default: float = 0.35) -> list[str]:
    """平均與換算（照實寫算式）：現世率、璽動之後開單挑的比例、單挑之後易手的比例；換成正式的 stir_chance 時一片一季被捲進幾成、
    易手幾成；一輪（7 ÷ 現世率 季）全服單挑幾場、易手幾次（每季被捲進的次數照全服上限 season_stir_cap 夾）。
    content 要給沒被 --force-stir 改過的那一份（換算照正式的機率與上限）。"""
    cfg = content.config.seal
    seasons = len(rows)
    emerged = sum(1 for r in rows if r.get("emerged"))
    rolled = sum(r.get("emerge_rolled", 0) for r in rows)
    stirs = sum(len(r["stirs"]) for r in rows)
    duels = sum(len(r["duels"]) for r in rows)
    takes = sum(r["takes"] for r in rows)
    marked = sum(1 for e in content.timetable if e.seal)
    emerge_rate = emerged / seasons if seasons and emerged else emerge_default
    p_duel = duels / stirs if stirs else 0.0
    p_take = takes / duels if duels else 0.0
    involve = 1 - (1 - cfg.stir_chance) ** marked  # 一片一季（標了 seal 的決戰 marked 場，每場 stir_chance）
    per_round = round(7 / emerge_rate) if emerge_rate else 0
    held_avg = 3.5  # 一輪裡平均有幾片有主（從 0 片長到 7 片，取一半；假設）
    season_stirs = min(cfg.season_stir_cap, held_avg * involve)
    lines = [
        f"季數 {seasons}：現世 {emerged} 季（標 emerge 的決戰擲中現世 {rolled} 場）；璽動 {stirs} 次、開單挑 {duels} 場、易手 {takes} 次",
        f"璽動之後開單挑的比例 {p_duel:.2f}；單挑之後易手的比例 {p_take:.2f}",
        f"換成 {cfg.stir_chance:.0%}：一片一季被捲進 {involve:.1%}、易手 {involve * p_duel * p_take:.1%}（標了 seal 的決戰 {marked} 場）",
        f"一輪 {per_round} 季（7 ÷ 現世率 {emerge_rate:.2f}）：每季約 {season_stirs:.2f} 次璽動（平均 {held_avg:g} 片有主、上限 {cfg.season_stir_cap}），"
        f"全服單挑約 {per_round * season_stirs * p_duel:.1f} 場、易手約 {per_round * season_stirs * p_duel * p_take:.1f} 次",
    ]
    return lines


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seeds", type=int, nargs="+", default=[1, 2, 3])
    parser.add_argument("--factions", type=int, nargs=3, default=[5, 5, 5], metavar=("GUAN", "HUANG", "HAOQIANG"))
    parser.add_argument("--hours", type=float, default=60.0)
    parser.add_argument("--tick", type=float, default=60.0)
    parser.add_argument("--profile", default="weekend")
    parser.add_argument("--decisive-week", type=int, default=None)
    parser.add_argument("--force-stir", action="store_true")
    parser.add_argument("--holders", type=int, default=0)
    parser.add_argument("--duel-mc", action="store_true")
    parser.add_argument("--trials", type=int, default=400)
    parser.add_argument("--mandate", action="store_true")
    parser.add_argument("--sunk", type=int, default=0)
    parser.add_argument("--mandate-mc", action="store_true")
    parser.add_argument("--emerge-rate", type=float, nargs="+", default=[0.35, 0.2])
    # 領地爭奪第三批 B：碎片藏在中立地、探索撿到（--mandate-mc 底下；沒給的讀 Config.seal.cache）
    parser.add_argument("--hide", type=float, default=None, help="開季這一季有沒有一片藏著的機率（hide_chance）")
    parser.add_argument("--find", type=float, default=None, help="在藏處每探索一下撿到的機率（find_chance）")
    parser.add_argument("--explores", type=int, nargs="+", default=None, help="藏碎片的那一塊一季被探索幾次（外部假設；預設 150 300 600 1000）")
    parser.add_argument("--own-share", type=float, default=None, help="那些探索裡，藏處歸探索者自己陣營的比例（預設 0.5）")
    parser.add_argument("--own-scale", type=float, default=None, help="歸自己陣營時的倍數（own_scale）")
    return parser


def cache_mode(args) -> bool:
    """--mandate-mc 底下有給任何一個「藏在中立地」的參數，就改量那一套。"""
    return any(x is not None for x in (args.hide, args.find, args.explores, args.own_share, args.own_scale))


def cache_args(args, content: Content) -> tuple[float, float, list[int], float, float]:
    """沒給的讀 Config.seal.cache（hide_chance、find_chance、own_scale）；N 與自家比例用預設。"""
    cfg = content.config.seal.cache
    return (cfg.hide_chance if args.hide is None else args.hide, cfg.find_chance if args.find is None else args.find,
            args.explores or [150, 300, 600, 1000], 0.5 if args.own_share is None else args.own_share,
            cfg.own_scale if args.own_scale is None else args.own_scale)


def main() -> None:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    args = build_parser().parse_args()
    content = load_content(ROOT / "content", args.profile)
    print(profile_line(content, None if args.profile == "none" else args.profile), flush=True)
    if args.duel_mc:
        print_mc(duel_mc(content, ratios=[0.5, 1.0, 1.5, 2.0, 3.0], trials=args.trials, rates=[30, 50, 70], modes=list(MODES)))
        return
    if args.mandate_mc and cache_mode(args):  # 領地爭奪的季：碎片藏在中立地、探索撿到（第三批 B）
        print_cache_mc(cache_rows(*cache_args(args, content)))
        return
    if args.mandate_mc:  # 天命之季多久來一次（玉璽二）
        print_mandate_mc([mandate_mc(r) for r in args.emerge_rate])
        return
    rows = []
    for seed in args.seeds:
        content = load_content(ROOT / "content", args.profile)
        if args.decisive_week is not None:
            content.config.decisive_from_week = args.decisive_week
        row = measure_season(content, seed, args.factions, args.hours, args.force_stir, args.holders, args.tick,
                             mandate=args.mandate, sunk=args.sunk)
        rows.append(row)
        print(summary(seed, row), flush=True)
    for line in round_up(rows, load_content(ROOT / "content", args.profile)):  # 換算照正式的機率與上限（不吃 --force-stir）
        print(line, flush=True)
    for line in mandate_lines(rows):  # 天命之季那幾季（--mandate，玉璽二）
        print(line, flush=True)


if __name__ == "__main__":
    main()
