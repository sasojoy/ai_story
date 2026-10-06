"""武學與成長計畫六 Task 5：功效的平衡（設計 13.7）——找出人人必選或沒人要的功效。只量、不改數字、不擋上線。

1. 單一功效值多少：本人第 L 級（10／30，每升一級給一點屬性，照 臂力、根骨、身法、悟性、博聞 的順序配到頂）、兩門中品第十成
   （外功屬實、內功屬柔：不同屬性、也不相剋，沒有內外搭配的加減），對遊歷與探索的每一支隊伍，每個一般功效「三格都是它、中品
   （4.5 層）」對「沒有功效」：勝率、大勝率、一場平均扣的氣血與內傷（佔氣血上限的百分點）的平均差。氣血與內傷照
   team.take_encounter_toll 的算法：化勁少扣、不動不留內傷、身法減損耗、根骨減內傷、落敗有身法閃避的機會（護命先收、不擲閃避）。
   勝率照 team.estimate 的算法（不含閃避與護命；固定種子，場數用 --runs，預設 400：場數多一點才看得出幾個百分點的差，
   而且每個功效用同一串運氣，差距不是亂數雜訊）。厚另外量「半血起手」與「兩成血起手」；特別功效除了勝率，另外用它自己的單位
   寫（乘勝／悟招：每場多拿的心得與經驗；吸取／回春：每場回的氣血；輕身：每趟遊歷省的體力；護命：落敗改成僵持的比例）。
2. 整季：整季機器人（真實 content/，五個 seed）。每一場戰報的功效句（trait_before／trait_after／notes 裡的護命）數到哪些功效
   真的起了作用（整季每一場都數，不只最近 20 場），每一場打完時身上兩門帶著哪些功效（含「合成的武學帶的」另外算一份：基礎武學
   開局就帶厚與化勁，那是送的不是選的），季末身上帶哪些、整季「從來沒人帶」的、「幾乎每一場都帶」的。

企劃者已定九成勝率可以接受（設計 8.4），這裡不拿勝率偏移當門檻；看的是「誰都會選」或「誰都不選」的功效。
用法：.venv/Scripts/python.exe scripts/measure_traits.py [--seeds 1 2 3 4 5] [--runs 400] [--no-season]
"""
from __future__ import annotations

import argparse
import atexit
import io
import os
import random
import shutil
import statistics
import sys
import tempfile
from collections import Counter
from pathlib import Path
from unittest import mock

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
TMP = Path(tempfile.mkdtemp(prefix="measure_traits_"))
os.environ["TIANXIA_DB"] = str(TMP / "unused.db")  # 別開到 worktree 的 saves/tianxia.db

from tianxia import bot, database, encounter, team, traits  # noqa: E402
from tianxia.content import load_content  # noqa: E402
from tianxia.martial_arts import content_art, with_quality  # noqa: E402
from tianxia.ollama_client import OllamaClient  # noqa: E402
from tianxia.sqlite_world import open_world  # noqa: E402
from tianxia.state import Member  # noqa: E402


def _cleanup() -> None:
    """結束時清掉暫存的資料庫檔：先關掉所有連線（Windows 上開著的檔刪不掉）。"""
    database.close_all()
    shutil.rmtree(TMP, ignore_errors=True)


atexit.register(_cleanup)

LEVELS = (10, 30)
LAYERS = 3 * 1.5  # 三格同一個、中品
POINT_ORDER = ("str", "con", "agi", "wis", "lore")  # 屬性點照這個順序配到頂（臂力、根骨管威力與氣血，先配）
WOUNDED_STARTS = (0.5, 0.2)  # 厚另外量的起手氣血（佔上限）


# ── 參考角色 ──────────────────────────────────────────────


def stats_at(content, level):
    """第 L 級：開局五項都是基準 5，每升一級給 stat_points_per_level 點，照 POINT_ORDER 配到 stat_cap。"""
    cfg = content.config
    stats = dict.fromkeys(team.COMBAT_STATS, float(team.BASE_STAT))
    points = (level - 1) * cfg.stat_points_per_level
    for key in POINT_ORDER:
        add = min(points, cfg.stat_cap - stats[key])
        stats[key] += add
        points -= add
    return stats


def reference(content, level):
    """（外功, 內功, 屬性, 加成）：兩門中品、第十成。回傳每支隊伍的威力用 power_vs。"""
    outer = with_quality(content_art("量武學", "量武學", "武學", "實", "下品"), "中品")
    inner = with_quality(content_art("量內功", "量內功", "內功", "柔", "下品"), "中品")
    stats = stats_at(content, level)
    boost = encounter.Boost(outer=team.stat_bonus(content, stats["str"]), inner=team.stat_bonus(content, stats["con"]))
    return outer, inner, stats, boost


def power_vs(content, level, squad, condition=1.0):
    outer, inner, _, boost = reference(content, level)
    member = Member(wugong_id=outer.id, neigong_id=inner.id, wugong_level=10, neigong_level=10, level=level)
    arts = {outer.id: outer, inner.id: inner}
    return encounter.member_power(member, arts, squad.attribute, condition=condition, boost=boost)


def hit_squads(content):
    """遊歷與探索遇得到的每一支隊伍：地點的 enemies。"""
    return [content.squads[s] for s in sorted({s for loc in content.locations.values() for s in loc.enemies})]


# ── 一場仗的各項期望 ──────────────────────────────────────


def tier_counts(power, squad, mods, runs):
    rng = random.Random(team.ESTIMATE_SEED)
    return Counter(encounter.resolve_encounter(power, squad.difficulty, rng, mods=mods).tier for _ in range(runs))


def outcome(content, stats, power, squad, lo, runs):
    """這支隊伍打 runs 場的各項：（勝率 %, 大勝率 %, 氣血 %, 內傷 %, 落敗改僵持 %）。氣血與內傷是佔上限的百分點。
    結果出來之後：護命把落敗改成僵持（不擲閃避）；沒有護命時落敗有身法閃避的機會。每一種結果的氣血損耗照
    team.take_encounter_toll（encounter_neili_loss × 化勁 × 身法）、內傷是損耗的 injury_share × 根骨 × 不動。"""
    cfg = content.config
    mods = team.trait_mods(content, lo)
    counts = tier_counts(power, squad, mods, runs)
    wins = sum(counts[t] for t in team.WIN_TIERS)
    guard = "no_loss" in lo.specials
    dodge = min(1.0, max(0.0, (stats["agi"] - team.BASE_STAT) * cfg.dodge_per_point))
    keep = 1 - traits.amount(content, lo, "toll_cut")
    agi_factor = max(0.0, 1 - team.stat_bonus(content, stats["agi"]))
    con_factor = max(0.0, 1 - team.stat_bonus(content, stats["con"]))
    injury_factor = 0.0 if "no_injury" in lo.specials else 1.0
    after = lo.specials["heal_after"].amount if "heal_after" in lo.specials else 0.0
    absorb = traits.amount(content, lo, "win_heal")

    def loss(tier):
        return cfg.encounter_neili_loss.get(tier, 0.0) * keep * agi_factor

    def net(tier):
        """扣完之後吸取（打贏）與回春（不論勝負）回氣血；從滿血起手時最多回到扣掉的那麼多（不會回到上限以上）。"""
        heal = after + (absorb if tier in team.WIN_TIERS else 0.0)
        return max(0.0, loss(tier) - heal)

    hp = hurt = saved = 0.0
    for tier, n in counts.items():
        share = n / runs
        if tier == encounter.FALLBACK_TIER:
            if guard:
                chances = {"僵持": 1.0}
                saved += share
            else:
                chances = {"僵持": dodge, tier: 1 - dodge}
        else:
            chances = {tier: 1.0}
        for final, chance in chances.items():
            hp += share * chance * net(final)
            hurt += share * chance * loss(final) * cfg.injury_share * con_factor * injury_factor
    return 100 * wins / runs, 100 * counts["大勝"] / runs, 100 * hp, 100 * hurt, 100 * saved


def averaged(content, level, squads, lo, runs, condition_for=None):
    """對每一支隊伍的平均（condition_for：本人此刻的氣血係數，給厚的半血起手用）。"""
    outer, inner, stats, boost = reference(content, level)
    cap = team.neili_cap(content, level, stats["con"])
    rows = []
    for squad in squads:
        power = power_vs(content, level, squad, condition=condition_for(lo) if condition_for else 1.0)
        rows.append(outcome(content, stats, power, squad, lo, runs))
    return [statistics.mean(col) for col in zip(*rows)], cap


def hp_share_condition(content, start):
    """起手氣血佔上限 start 時的氣血係數（厚把下限拉高，見 team.team_conditions）。"""
    def condition(lo):
        floor = encounter.CONDITION_FLOOR + traits.amount(content, lo, "condition_floor")
        return encounter.condition_of(start, 1.0, floor=floor)

    return condition


def reward_note(content, sp, squads, win_rate):
    """特別功效在勝率之外的作用，用它自己的單位（每一場平均）。"""
    gain = statistics.mean(max(sq.reward_xinde, 0) for sq in squads)
    exp = statistics.mean(max(sq.exp, 0) for sq in squads)
    if sp.hook == "win_xinde":
        return f"每場多 {sp.amount * win_rate / 100:.1f} 心得（打贏才有，勝率 {win_rate:.0f}%，一場平均給 {gain:.1f}）"
    if sp.hook == "heal_after":
        return f"每場回氣血上限的 {sp.amount:.0%}（不論勝負；扣的氣血回得到才算）"
    if sp.hook == "train_stamina":
        return f"每趟遊歷少花 {int(sp.amount)} 體力（{content.config.action_cost['train']} → {content.config.action_cost['train'] - int(sp.amount)}，省 {sp.amount / content.config.action_cost['train']:.0%}）"
    if sp.hook == "no_loss":
        return "落敗一律改判僵持（結果欄的「落敗改僵持」）"
    if sp.hook == "no_injury":
        return "一場的氣血全算輕傷（內傷欄）"
    if sp.hook == "double_luck":
        return "每場擲兩次運氣取好的（勝率與大勝率）"
    if sp.hook == "power_from_difficulty":
        return f"威力加上對手強度的 {sp.amount:.0%}（勝率與大勝率；對手越強加越多）"
    return sp.desc


def single_traits(content, runs):
    squads = hit_squads(content)
    print(f"一、單一功效（三格同一個、中品＝{LAYERS:g} 層；對 {len(squads)} 支遊歷與探索遇得到的隊伍平均，每個功效 {runs} 場；與「沒有功效」的差）")
    print("    欄位：勝率 ／ 大勝率 ／ 一場扣的氣血 ／ 一場累積的內傷（後兩欄是佔氣血上限的百分點，負的是少扣）／ 落敗改成僵持")
    for level in LEVELS:
        outer, inner, stats, boost = reference(content, level)
        none = traits.Loadout()
        base, cap = averaged(content, level, squads, none, runs)
        print(f"  第 {level} 級（臂力 {stats['str']:g}、根骨 {stats['con']:g}、身法 {stats['agi']:g}；氣血上限 {cap:g}）"
              f"：沒有功效時 勝率 {base[0]:.1f}%、大勝 {base[1]:.1f}%、一場扣氣血 {base[2]:.2f}%、內傷 {base[3]:.2f}%")
        for trait in content.traits.general:
            lo = traits.Loadout(layers={trait.hook: LAYERS})
            got, _ = averaged(content, level, squads, lo, runs)
            line = delta_line(f"〔{trait.name}〕", got, base) + f"　（數字 {traits.amount(content, lo, trait.hook):.0%}）"
            extra = ""
            if trait.hook == "win_reward":
                extra = f"；平均每場多拿 {traits.amount(content, lo, 'win_reward') * got[0] / 100:.0%} 的心得與經驗（只有打贏那幾場多拿，勝率 {got[0]:.0f}%）"
            elif trait.hook == "win_heal":
                heal = traits.amount(content, lo, "win_heal")
                extra = f"；打贏回氣血上限的 {heal:.0%}（一場打贏只扣 5%～15%，所以打贏的那幾場等於沒扣；氣血欄已經扣掉回的量）"
            print("    " + line + extra)
            if trait.hook == "condition_floor":
                for start in WOUNDED_STARTS:
                    cond = hp_share_condition(content, start)
                    base_w, _ = averaged(content, level, squads, none, runs, condition_for=cond)
                    got_w, _ = averaged(content, level, squads, lo, runs, condition_for=cond)
                    print("      " + delta_line(f"〔厚〕起手剩 {start:.0%} 氣血", got_w, base_w)
                          + f"　（沒有厚時這個起手就只有 勝率 {base_w[0]:.1f}%）")
        for sp in content.traits.special:
            lo = traits.Loadout(specials={sp.hook: sp})
            got, _ = averaged(content, level, squads, lo, runs)
            print("    " + delta_line(f"〔{sp.name}〕", got, base) + "　" + reward_note(content, sp, squads, got[0]))


CLOSE_RATIOS = (0.7, 0.9, 1.0, 1.3, 2.0)  # 對手難度是我方威力的幾倍：從打得贏到打不贏（2 倍是「怎麼打都輸」：護命只在這種仗才有用）


def close_fights(content, runs):
    """三、勢均力敵的仗：對手難度＝我方威力的 0.7／0.9／1.0／1.3 倍（沒有屬性相剋）——真正的隊伍大多遠比本人弱（勝率九成以上），
    功效的價值在這種仗才看得出來。每個功效四個難度各一欄：勝率差（百分點）／氣血差（佔上限的百分點，負的是少扣）。"""
    from types import SimpleNamespace

    print("三、勢均力敵的仗（對手難度＝我方威力的 " + "／".join(f"{r:g}" for r in CLOSE_RATIOS)
          + " 倍；每格：勝率差 ／ 氣血差（佔上限的百分點）；護命再加 落敗改僵持 的差；第 30 級）")
    level = LEVELS[-1]
    stats = reference(content, level)[2]
    power = power_vs(content, level, SimpleNamespace(attribute=None))
    squads = [SimpleNamespace(difficulty=power * r, attribute=None) for r in CLOSE_RATIOS]
    base = [outcome(content, stats, power, sq, traits.Loadout(), runs) for sq in squads]
    print("  沒有功效：" + "　".join(f"{r:g} 倍 勝率 {b[0]:.0f}% 氣血 {b[2]:.1f}%" for r, b in zip(CLOSE_RATIOS, base)))
    rows = [(f"〔{t.name}〕", traits.Loadout(layers={t.hook: LAYERS})) for t in content.traits.general]
    rows += [(f"〔{sp.name}〕", traits.Loadout(specials={sp.hook: sp})) for sp in content.traits.special]
    for label, lo in rows:
        cells = []
        for sq, b in zip(squads, base):
            got = outcome(content, stats, power, sq, lo, runs)
            cells.append(f"{got[0] - b[0]:+5.1f} ／ {got[2] - b[2]:+5.2f}" + (f" ／ 改僵持 {got[4] - b[4]:+.0f}" if "no_loss" in lo.specials else ""))
        print(f"  {label}　" + "　│　".join(cells))


def delta_line(label, got, base):
    d = [g - b for g, b in zip(got, base)]
    return f"{label}　勝率 {d[0]:+.1f}　大勝 {d[1]:+.1f}　氣血 {d[2]:+.2f}　內傷 {d[3]:+.2f}　落敗改僵持 {d[4]:+.1f}"


# ── 整季 ────────────────────────────────────────────────


def season(content, seeds):
    print("四、整季（真實內容、整季機器人；每一場都數）")
    names = [t.name for t in content.traits.general] + [t.name for t in content.traits.special]
    hook_name = {t.hook: t.name for t in content.traits.general} | {t.hook: t.name for t in content.traits.special}
    fired, worn, worn_fused, season_end = Counter(), Counter(), Counter(), Counter()
    totals = Counter()
    by_attribute = Counter()
    for seed in seeds:
        world = open_world(TMP / f"seed{seed}.db")
        seen = {"seq": 0}

        def observe(game, seen=seen):
            now = game.state.battle_seq
            if now == seen["seq"]:
                return
            new = game.state.battles[: max(0, now - seen["seq"])]
            seen["seq"] = now
            lo = traits.loadout(game.state, game.content, game.world)
            carried = {t.hook: t.name for t in game.content.traits.general if lo.layers.get(t.hook)}
            fused = set()
            for skill_id in (game.state.player.member.wugong_id, game.state.player.member.neigong_id):
                art = team.player_art(game.state, game.content, game.world, skill_id)
                if art is not None and art.origin == "fused":
                    fused |= {traits.general(game.content, a).name for a in traits.traits_of(art)}
                    if art.special:
                        fused.add(traits.special(game.content, art.special).name)
            carried_names = set(carried.values()) | {sp.name for sp in lo.specials.values()}
            for record in new:
                totals["戰鬥"] += 1
                totals["打贏"] += record.tier in team.WIN_TIERS
                totals["護命改判"] += bool(record.guarded)
                lines = record.trait_before + record.trait_after + [n for n in record.notes if n.startswith(("〔"))]
                for line in lines:
                    fired[line[1:line.index("〕")]] += 1
                worn.update(carried_names)
                worn_fused.update(fused)

        with mock.patch.object(OllamaClient, "chat_structured", side_effect=RuntimeError), \
                mock.patch.object(OllamaClient, "chat_text", side_effect=RuntimeError):
            game = bot.play_season(content, seed, world=world, observe=observe)
        arts = []
        for skill_id in (game.state.player.member.wugong_id, game.state.player.member.neigong_id):
            art = team.player_art(game.state, content, world, skill_id)
            if art is None:
                continue
            arts.append(f"【{art.name}】{art.quality}・屬{art.attribute}・{'、'.join(traits.general(content, a).name for a in traits.traits_of(art))}"
                        + (f"・〔{traits.special(content, art.special).name}〕" if art.special else ""))
            season_end.update(traits.general(content, a).name for a in traits.traits_of(art))
            if art.special:
                season_end[traits.special(content, art.special).name] += 1
        for item in game.state.player.arts:
            art = team.player_art(game.state, content, world, item)
            if art is not None:
                by_attribute[art.attribute] += 1
        print(f"  seed {seed}：第 {game.state.player.member.level} 級；季末身上 " + "　".join(arts))
    fights = max(1, totals["戰鬥"])
    print(f"  共 {totals['戰鬥']} 場、打贏 {totals['打贏']} 場（{100 * totals['打贏'] / fights:.0f}%）、護命改判 {totals['護命改判']} 場")
    print("  每一功效：起作用的場次（佔全部戰鬥）／打完時身上帶著的場次（其中合成的武學帶的）／季末帶的 seed 數")
    for name in names:
        print(f"    〔{name}〕起作用 {fired[name]}（{100 * fired[name] / fights:.0f}%）　身上帶 {worn[name]}（{100 * worn[name] / fights:.0f}%，"
              f"合成的 {worn_fused[name]}＝{100 * worn_fused[name] / fights:.0f}%）　季末 {season_end[name]}")
    print("  從來沒人帶（整季沒有一場帶著）：" + ("、".join(n for n in names if not worn[n]) or "無"))
    print("  幾乎每一場都帶（≥ 90% 的戰鬥）：" + ("、".join(n for n in names if worn[n] >= 0.9 * fights) or "無")
          + "（厚、化勁來自開局送的基礎武學，不是選的；看「合成的」那一欄才是機器人選出來的）")
    print("  合成的武學從來沒帶過：" + ("、".join(n for n in names if not worn_fused[n]) or "無"))
    if by_attribute:
        print("  季末功法庫與身上合成武學的屬性分布：" + "、".join(f"{a} {n}" for a, n in by_attribute.most_common()))
    unused = [name for hook, name in hook_name.items() if name not in fired and name in names]
    print("  整季一次都沒起作用：" + ("、".join(unused) or "無"))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seeds", type=int, nargs="+", default=[1, 2, 3, 4, 5])
    parser.add_argument("--runs", type=int, default=400, help="單一功效每支隊伍模擬幾場（預設 400）")
    parser.add_argument("--no-season", action="store_true", help="只量單一功效，不跑整季")
    args = parser.parse_args()
    content = load_content(ROOT / "content")
    single_traits(content, args.runs)
    close_fights(content, args.runs)
    if not args.no_season:
        season(content, args.seeds)


if __name__ == "__main__":
    main()
