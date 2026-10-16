"""合成的深度量表（合成與意境改法定案，企劃者 2026-10-16；tianxia/depth.py）。只量、不改數字。

1. 整季機器人（真實 content/，每個種子一個機器人一季）：
   - 全服這一季登記的合成武學：第幾代的各幾門、一門幾層功效（屬性清單的長度）。
   - 合出來的意境：幾重的各幾個、圓融佔幾成。
   - 季末機器人手上的武學：代數、層數、品質、功效強度（見下）。
2. 功效強度對照本命：一門武學的功效強度＝每一個一般功效「這一門自己的數字 ÷ 那個功效的上限」加起來（品質倍數照算，
   跟 traits.card_line 同一套），特別功效另算一個 0.5。本命武學照內容（三個功效、絕學）；另外照規則排幾門「理想的」：
   一脈相承三代、每代融圓融到頂的意境，上品與絕學各一門。
用法：python scripts/measure_depth.py --seeds 1 2 3 4 5 [--profile weekend]
"""
from __future__ import annotations

import argparse
import atexit
import io
import os
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
TMP = Path(tempfile.mkdtemp(prefix="measure_depth_"))
os.environ["TIANXIA_DB"] = str(TMP / "unused.db")  # 別開到 worktree 的 saves/tianxia.db

from tianxia import bot, database, depth, library, naming, team, traits  # noqa: E402
from tianxia.content import load_content  # noqa: E402
from tianxia.martial_arts import MartialArt, content_art, with_quality  # noqa: E402
from tianxia.ollama_client import OllamaClient  # noqa: E402
from tianxia.sqlite_world import open_world  # noqa: E402

SPECIAL_WEIGHT = 0.5


def _cleanup() -> None:
    database.close_all()
    shutil.rmtree(TMP, ignore_errors=True)


atexit.register(_cleanup)


def strength(content, art: MartialArt) -> float:
    """功效強度：每個一般功效「數字 ÷ 上限」加起來，特別功效另加 SPECIAL_WEIGHT。"""
    mult, mine, total = traits.multiplier(content, art.quality), traits.traits_of(art), 0.0
    for attribute in dict.fromkeys(mine):
        trait = traits.general(content, attribute)
        total += min(trait.cap, trait.per_layer * mine.count(attribute) * mult) / trait.cap
    return total + (SPECIAL_WEIGHT if art.special else 0.0)


def signature_arts(content) -> list[MartialArt]:
    out = []
    for character in content.characters.values():
        for skill_id in (character.starting_wugong, character.starting_neigong):
            s = content.skills.get(skill_id) if skill_id else None
            if s is not None:
                out.append(content_art(skill_id, s.name, s.kind, s.attribute, s.quality, special=s.special, traits=s.traits))
    return out


def ideal(content, quality: str) -> MartialArt:
    """規則上排得出來最強的第三代：底是基礎武學（一層）；第 g 代融一個 g 重、圓融的意境（一重一層、二重三層、三重四層），
    三代各挑一個屬性（8×8×8 種都試），取功效強度最高的那一門，再帶一個特別功效。"""
    import itertools

    cfg = content.config.fusion_depth
    best, top = None, -1.0
    attrs = [t.attribute for t in content.traits.general]
    for base_attr in ("剛", "柔", "快", "慢"):
        for seq in itertools.product(attrs, repeat=cfg.max_gen):
            art = content_art("底", "底", "武學", base_attr, "下品")
            for rank, attribute in enumerate(seq, 1):
                layers = max(1, rank + (cfg.harmony_bonus if rank > 1 else 0))
                art = art.model_copy(update={"traits": depth.fuse_traits(content, art, attribute, layers), "attribute": attribute})
            art = with_quality(art.model_copy(update={"special": "lianhuan"}), quality)
            value = strength(content, art)
            if value > top:
                best, top = art, value
    return best


def measure(seed: int, profile: str | None, max_layers: int | None = None) -> dict:
    content = load_content(ROOT / "content", profile=profile)
    if max_layers:
        content.config.fusion_depth.max_layers = max_layers
    world = open_world(TMP / f"seed{seed}.db")

    def refuse(*a, **k):
        raise ConnectionError("量表不連模型")

    with mock.patch.object(OllamaClient, "chat_structured", refuse), mock.patch.object(OllamaClient, "chat_text", refuse), \
            mock.patch("requests.post", refuse), mock.patch("requests.get", refuse):
        game = bot.play_season(content, seed, world=world)
    arts = world.fused_arts()
    merged = world.merged_insights()
    own = [i for i in game.state.player.own_insights.values() if i.parents]
    held = [team.player_art(game.state, content, world, a) for a in library.owned_arts(game.state)]
    held = [a for a in held if a is not None and a.origin == "fused"]
    member = game.state.player.member
    worn = [team.player_art(game.state, content, world, a) for a in (member.wugong_id, member.neigong_id)]
    return {
        "gens": Counter(depth.gen_of(a, content, world) for a in arts),
        "layers": Counter(len(traits.traits_of(a)) for a in arts),
        "ranks": Counter(depth.rank_of(i, content, world, game.state) for i in merged + own),
        "moods": Counter(depth.harmony_of(i, content, world, game.state) for i in merged + own),
        "held": [(depth.gen_of(a, content, world), len(traits.traits_of(a)), a.quality, strength(content, a)) for a in held],
        "worn": [strength(content, a) for a in worn if a is not None],
        "forged": len(arts),
        "level": game.state.player.member.level,
        "third": [a.model_dump(mode="json") for a in arts if depth.gen_of(a, content, world) >= content.config.fusion_depth.max_gen],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seeds", type=int, nargs="+", default=[1, 2, 3, 4, 5])
    parser.add_argument("--profile", default="weekend")
    parser.add_argument("--max-layers", type=int, default=None, help="試別的一門最多幾層（只改這一次量的，不改設定）")
    parser.add_argument("--dump", help="把這幾季全服登記的第三代武學寫成 JSON（measure_tactics.py --depth 讀）")
    args = parser.parse_args()
    profile = None if args.profile == "none" else args.profile
    content = load_content(ROOT / "content", profile=profile)
    if args.max_layers:
        content.config.fusion_depth.max_layers = args.max_layers
    print(f"設定：{args.profile}，種子 {args.seeds}，一門最多 {content.config.fusion_depth.max_layers} 層")
    gens, layers, ranks, moods = Counter(), Counter(), Counter(), Counter()
    held, worn, third = [], [], []
    for seed in args.seeds:
        got = measure(seed, profile, args.max_layers)
        gens.update(got["gens"])
        layers.update(got["layers"])
        ranks.update(got["ranks"])
        moods.update(got["moods"])
        held += got["held"]
        worn += got["worn"]
        third += got["third"]
        print(f"種子 {seed}：登記 {got['forged']} 門、季末 {got['level']} 級；代數 {dict(sorted(got['gens'].items()))}、"
              f"意境重數 {dict(sorted(got['ranks'].items()))}")
    print()
    print("全服登記的合成武學：代數", dict(sorted(gens.items())), "層數", dict(sorted(layers.items())))
    total = sum(moods[m] for m in (depth.HARMONY, depth.DISCORD)) or 1
    print("合出來的意境：重數", dict(sorted(ranks.items())), f"圓融 {moods[depth.HARMONY]}／駁雜 {moods[depth.DISCORD]}"
          f"（圓融 {moods[depth.HARMONY] * 100 / total:.0f}%）")
    if held:
        by_gen: dict[int, list[float]] = {}
        for gen, _, _, value in held:
            by_gen.setdefault(gen, []).append(value)
        print("季末手上的合成武學：", "、".join(
            f"第{g}代 {len(v)} 門 強度中位 {statistics.median(v):.2f} 最高 {max(v):.2f}" for g, v in sorted(by_gen.items())))
        print("  品質：", dict(Counter(q for _, _, q, _ in held)))
    if worn:
        print(f"季末身上兩門的功效強度：中位 {statistics.median(worn):.2f}、最高 {max(worn):.2f}")
    if args.dump:
        import json
        Path(args.dump).write_text(json.dumps(third, ensure_ascii=False), encoding="utf-8")
        print(f"第三代 {len(third)} 門寫進 {args.dump}")
    print()
    sig = [strength(content, a) for a in signature_arts(content)]
    print(f"本命武學（{len(sig)} 門，絕學、內容寫的三個功效與特別功效）：功效強度 中位 {statistics.median(sig):.2f}、"
          f"最低 {min(sig):.2f}、最高 {max(sig):.2f}")
    for quality in ("中品", "上品", "絕學"):
        art = ideal(content, quality)
        print(f"排得出來最強的第三代（{quality}）：{len(art.traits)} 層 {''.join(art.traits)}、功效強度 {strength(content, art):.2f}")


if __name__ == "__main__":
    main()
