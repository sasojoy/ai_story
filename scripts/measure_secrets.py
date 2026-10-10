"""口訣與秘方、天時地利的量表（PM 2026-10-10 派工）。只量、不改數字。

整季機器人（bot.play_season，真實 content/），每個種子跑三次、各自一個資料庫：
- 隨機：整季機器人照舊隨機合（不讀口訣），看一季偶然撞中幾條秘方；
- 解口訣：聽過某條秘方的任何一句口訣，之後手上湊得出那一爐就去合（假設玩家讀得懂口訣：量的是「線索給得夠不夠、材料湊不湊得到」）；
- 全知：一開季就知道這一季的秘方，湊得出就合（上限：一季下來材料湊不湊得到）。
模型一律不連（同 measure_forge）：整季機器人跟人物說不上話，所以「人物順口版」的口訣量不到，只有說書與殘譜兩個來源。

印每個種子、每一邊：合中幾條（這一季幾條裡）、聽到幾句口訣（說書／殘譜）、合成幾爐、天時地利讓上品機率平均多幾個百分點
（每一爐照實際的機率與把天時地利的權重歸零的機率相減）、碰到天時地利的爐占幾成、秘方那幾爐與一般那幾爐擲到上品的比例。
最後一行是各欄的平均。

用法：.venv/Scripts/python.exe scripts/measure_secrets.py --seeds 1 2 3 4 5 [--profile weekend]
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
from pathlib import Path
from unittest import mock

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
TMP = Path(tempfile.mkdtemp(prefix="measure_secrets_"))
os.environ["TIANXIA_DB"] = str(TMP / "unused.db")  # 別開到 worktree 的 saves/tianxia.db

from tianxia import bot, database, fusion, insights, library, naming, secret_recipes, team  # noqa: E402
from tianxia.content import load_content  # noqa: E402
from tianxia.ollama_client import OllamaClient  # noqa: E402
from tianxia.sqlite_world import open_world  # noqa: E402

SIDES = ("隨機", "解口訣", "全知")
SETTING_KEYS = ("terrain", "night_match", "night_clash", "battlefield", "calm")


def _cleanup() -> None:
    database.close_all()
    shutil.rmtree(TMP, ignore_errors=True)


atexit.register(_cleanup)


def _plans(game, recipe):
    """手上湊得出這條秘方的每一爐（只挑合得了的）。"""
    s, c, w = game.state, game.content, game.world
    arts = library.owned_arts(s)
    held = [i for i in s.player.insights if not insights.is_own(i)]
    resolved = {i: insights.resolve(i, c, w, s) for i in held}
    if recipe.kind == "fuse":
        for art_id in arts:
            art = team.player_art(s, c, w, art_id)
            for i in held:
                if art is not None and secret_recipes.match_fuse(s, c, w, art_id, art, resolved[i]) is recipe \
                        and fusion.fuse_problem(s, c, w, art_id, i) is None:
                    yield bot.ForgePlan(art_id, (i,), None)
    elif recipe.kind == "merge":
        for a in held:
            for b in held:
                if secret_recipes.match_merge(c, w, resolved[a], resolved[b]) is recipe and fusion.merge_problem(s, c, w, a, b) is None:
                    yield bot.ForgePlan(None, (a, b), None)
    else:
        for a in arts:
            for b in arts:
                art_a, art_b = team.player_art(s, c, w, a), team.player_art(s, c, w, b)
                if a < b and art_a is not None and art_b is not None \
                        and secret_recipes.match_blend(s, c, w, a, art_a, b, art_b) is recipe \
                        and fusion.blend_problem(s, c, w, a, b) is None:
                    yield bot.ForgePlan(a, (), b)


def _prep(game, recipe):
    """手上還湊不出、但差一步的：缺的那門武學（屬性、種類）拿手上同種類的武學融一個那個屬性的意境先合出來
    （讀懂口訣的玩家會這樣走）。只看武學＋意境、武學＋武學；意境要自己去悟，這裡不替它跑。"""
    s, c, w = game.state, game.content, game.world
    if recipe.kind == "merge":
        return
    arts = library.owned_arts(s)
    wanted = [recipe.art] if recipe.kind == "fuse" else list(recipe.arts)
    for pattern in wanted:
        have = False
        for a in arts:
            art = team.player_art(s, c, w, a)
            if art is not None and secret_recipes.art_fits(pattern, art, s.player.art_quality.get(a, art.quality)):
                have = True
        if have or pattern.attribute is None or pattern.min_quality not in (None, "下品"):
            continue
        for a in arts:
            art = team.player_art(s, c, w, a)
            if art is None or (pattern.kind is not None and art.kind != pattern.kind):
                continue
            for i in s.player.insights:
                insight = insights.resolve(i, c, w, s)
                if insight is not None and insight.attribute == pattern.attribute and pattern.lean in (None, insight.lean) \
                        and fusion.fuse_problem(s, c, w, a, i) is None:
                    yield bot.ForgePlan(a, (i,), None)


class Tally:
    def __init__(self) -> None:
        self.pending: tuple[float, float, bool] | None = None
        self.uplift: list[float] = []  # 每一爐：天時地利讓上品多幾個百分點
        self.touched = 0  # 碰到天時地利的爐
        self.secret_top: list[bool] = []  # 秘方那幾爐擲到上品
        self.plain_top: list[bool] = []


def measure(seed: int, profile: str | None, side: str) -> dict:
    content = load_content(ROOT / "content", profile=profile)
    world = open_world(TMP / f"{side}{seed}.db")
    tally = Tally()
    original_pick_forge, fuse_odds, blend_odds, roll_quality = bot.pick_forge, fusion.fuse_odds, fusion.blend_odds, fusion.roll_quality
    rule = content.config.fuse_quality

    def bare(fn, *args, **kwargs):
        saved = {k: getattr(rule, k) for k in SETTING_KEYS}
        for k in SETTING_KEYS:
            setattr(rule, k, 0)
        try:
            return fn(*args, **kwargs)
        finally:
            for k, v in saved.items():
                setattr(rule, k, v)

    def stash(fn):
        def wrapped(*args, **kwargs):
            odds = fn(*args, **kwargs)
            plain = bare(fn, *args, **kwargs)
            tally.pending = (odds.odds["上品"], plain.odds["上品"], bool(kwargs.get("secret")))
            return odds
        return wrapped

    def rolled(odds, rng):
        quality = roll_quality(odds, rng)
        if tally.pending is not None and rng is not None:
            top, plain, secret = tally.pending
            tally.uplift.append(top - plain)
            tally.touched += top != plain
            (tally.secret_top if secret else tally.plain_top).append(quality == "上品")
        tally.pending = None
        return quality

    def pick_forge(game, rng, *args, **kwargs):
        if side != "隨機" and game.state.player.stamina >= bot.FORGE_RESERVE:
            tianji = secret_recipes.tianji_of(game.world)
            book = secret_recipes.manual(game.state, tianji)
            for recipe in secret_recipes.active(game.content, tianji):
                if recipe.id in book.solved or (side == "解口訣" and not book.heard.get(recipe.id)):
                    continue
                plan = next(_plans(game, recipe), None) or next(_prep(game, recipe), None)
                if plan is not None:
                    return plan
        return original_pick_forge(game, rng, *args, **kwargs)

    def refuse(*args, **kwargs):
        raise RuntimeError("量測不連模型")

    with mock.patch.object(naming, "propose", lambda *a, **k: (None, "")), \
            mock.patch.object(naming, "pick", lambda *a, **k: (None, "")), \
            mock.patch.object(OllamaClient, "chat_structured", refuse), mock.patch.object(OllamaClient, "chat_text", refuse), \
            mock.patch("requests.post", refuse), mock.patch("requests.get", refuse), \
            mock.patch.object(bot, "pick_forge", pick_forge), \
            mock.patch.object(fusion, "fuse_odds", stash(fuse_odds)), mock.patch.object(fusion, "blend_odds", stash(blend_odds)), \
            mock.patch.object(fusion, "roll_quality", rolled):
        game = bot.play_season(content, seed, world=world)
    tianji = secret_recipes.tianji_of(game.world)
    book = secret_recipes.manual(game.state, tianji)
    heard = [i for idx in book.heard.values() for i in idx]
    forges = len(tally.uplift)
    return {
        "合中": len(book.solved), "這一季": len(secret_recipes.active(content, tianji)),
        "說書": heard.count(secret_recipes.TALE), "殘譜": heard.count(secret_recipes.SCRAP),
        "爐": forges,
        "天時地利": statistics.mean(tally.uplift) if tally.uplift else 0.0,
        "碰到": tally.touched / forges if forges else 0.0,
        "秘方上品": statistics.mean(tally.secret_top) if tally.secret_top else None,
        "一般上品": statistics.mean(tally.plain_top) if tally.plain_top else None,
        "秘方爐": len(tally.secret_top),
        "哪幾條": ",".join(book.solved),
    }


def _fmt(row: dict) -> str:
    pct = lambda v: "—" if v is None else f"{v * 100:.0f}%"  # noqa: E731
    return (
        f"合中 {row['合中']}/{row['這一季']}　口訣 說書 {row['說書']}・殘譜 {row['殘譜']}　爐 {row['爐']}"
        f"　天時地利 +{row['天時地利']:.1f} 點（碰到 {pct(row['碰到'])}）"
        f"　上品 秘方 {pct(row['秘方上品'])}（{row['秘方爐']} 爐）・一般 {pct(row['一般上品'])}　{row['哪幾條']}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--seeds", type=int, nargs="+", default=[1, 2, 3])
    parser.add_argument("--profile", default="weekend")
    args = parser.parse_args()
    profile = None if args.profile in ("", "none", "default") else args.profile
    rows: dict[str, list[dict]] = {side: [] for side in SIDES}
    for seed in args.seeds:
        for side in SIDES:
            random.seed(seed)
            row = measure(seed, profile, side)
            rows[side].append(row)
            print(f"種子 {seed} {side}：{_fmt(row)}", flush=True)
    for side, side_rows in rows.items():
        mean = lambda k: statistics.mean(r[k] for r in side_rows)  # noqa: E731
        tops = [r["秘方上品"] for r in side_rows if r["秘方上品"] is not None]
        plain = [r["一般上品"] for r in side_rows if r["一般上品"] is not None]
        print(
            f"{side}平均：合中 {mean('合中'):.1f}/{mean('這一季'):.0f}　口訣 說書 {mean('說書'):.1f}・殘譜 {mean('殘譜'):.1f}"
            f"　爐 {mean('爐'):.0f}　天時地利 +{mean('天時地利'):.1f} 點（碰到 {mean('碰到') * 100:.0f}%）"
            f"　上品 秘方 {statistics.mean(tops) * 100 if tops else 0:.0f}%・一般 {statistics.mean(plain) * 100 if plain else 0:.0f}%"
        )


if __name__ == "__main__":
    main()
