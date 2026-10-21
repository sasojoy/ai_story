"""口訣與秘方、天時地利的量表（PM 2026-10-10 派工）。只量、不改數字。

整季機器人（bot.play_season，真實 content/），每個種子跑三次、各自一個資料庫：
- 隨機：整季機器人照舊隨機合（不讀口訣），看一季偶然撞中幾條秘方；
- 解口訣：聽過某條秘方的任何一句口訣，之後手上湊得出那一爐就去合（假設玩家讀得懂口訣：量的是「線索給得夠不夠、材料湊不湊得到」）；
- 全知：一開季就知道這一季的秘方，湊得出就合（上限：一季下來材料湊不湊得到）。
模型一律不連（同 measure_forge）：整季機器人跟人物說不上話，所以「人物順口版」的口訣量不到，只有說書與殘譜兩個來源。

印每個種子、每一邊：合中幾條（這一季幾條裡）、聽到幾句口訣（說書／殘譜）、合成幾爐（武學＋武學、意境＋意境）。
最後一行是各欄的平均。（武學重構之後合成不擲品質、沒有天時地利，那幾欄拿掉了。）

鑄器（打造隱藏配方第一批；設計第十二節第 1、2、4 項）：同一季另印一行——摸到幾條隱藏配方（這一季幾條裡，照「兵／甲＋階」分）、
聽到幾句鑄器口訣（說書／鐵匠／殘譜）、這一季打了幾爐（兵器加防具）、其中幾件名器。解口訣與全知兩邊照鑄譜去湊那一爐（聽過那一條的
任何一句、或一開季就知道，手上湊得出就打；包住 `smithing.forge_plan`／`armor_plan`），隨機那一邊照舊。每個種子三邊印完再印一行
『三邊合起來』（每個機器人獨佔一個資料庫，合起來當全服的粗估）。
打造第二批起另印神器原品、仿品幾把，與一季拿到幾個三階（新來源另計）。

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
from collections import Counter
from pathlib import Path
from unittest import mock

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
TMP = Path(tempfile.mkdtemp(prefix="measure_secrets_"))
os.environ["TIANXIA_DB"] = str(TMP / "unused.db")  # 別開到 worktree 的 saves/tianxia.db

from tianxia import bot, database, forge_secrets, fusion, insights, library, materials, naming, secret_recipes, smithing, team  # noqa: E402
from tianxia.content import load_content  # noqa: E402
from tianxia.ollama_client import OllamaClient  # noqa: E402
from tianxia.sqlite_world import open_world  # noqa: E402

SIDES = ("隨機", "解口訣", "全知")
GROUP_WORDS = {
    "weapon:1": "兵一階", "weapon:2": "兵二階", "weapon:3": "兵三階", "armor:1": "甲一階", "armor:2": "甲二階", "armor:3": "甲三階",
    "weapon:divine": "兵神器", "armor:divine": "甲神器",
}


def _forge_order(state, content, recipe):
    """手上湊得出這條隱藏配方的那一爐（主料、輔料照形狀挑背包裡的；主輔同一種要兩個），打不成是 None。"""
    held = {mid: n for mid, n in state.player.materials.items() if n > 0 and mid in content.materials}
    kind = recipe.kind if recipe.slot == "weapon" else smithing.ARMOR_KIND
    for main in [mid for mid in held if forge_secrets.fits(recipe.main, content.materials[mid])]:
        for aux in [mid for mid in held if forge_secrets.fits(recipe.aux, content.materials[mid])]:
            if (main != aux or held[main] >= 2) and smithing.forge_problem(state, content, kind, main, aux) is None:
                return kind, main, aux
    return None


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
        self.forges = 0  # 真的合成了幾爐（武學＋武學、意境＋意境）


def measure(seed: int, profile: str | None, side: str) -> dict:
    content = load_content(ROOT / "content", profile=profile)
    world = open_world(TMP / f"{side}{seed}.db")
    tally = Tally()
    original_pick_forge, original_blend, original_merge = bot.pick_forge, fusion.blend, fusion.merge
    forged = {"爐": 0, "名器": 0, "原品": 0, "仿品": 0}
    tier3 = {"全部": 0, "新來源": 0}
    original_forge_plan, original_armor_plan, original_forge = smithing.forge_plan, smithing.armor_plan, smithing.forge

    def steer(slot, original):
        """解口訣、全知：鑄譜上聽過（全知不必）還沒打中的隱藏配方，手上湊得出就先打那一爐；其餘照整季機器人原本的挑法。
        配方照這一季的章挑（forge_secrets.active 帶季，FB-270）；拆了片的神器配方三片都聽過才算「聽過」（鑄譜上那一行完整了）。"""
        def plan(state, content_, world_, art):
            if side != "隨機":
                tianji = world_.read().tianji
                book = forge_secrets.manual(state, tianji)
                for recipe in forge_secrets.active(content_, tianji, state.world):
                    known = book.heard.get(recipe.id) or len(book.pieces.get(recipe.id, [])) == len(forge_secrets.PIECES)
                    if recipe.slot != slot or recipe.id in book.solved or (side == "解口訣" and not known):
                        continue
                    order = _forge_order(state, content_, recipe)
                    if order is not None:
                        return order
            return original(state, content_, world_, art)
        return plan

    def counted_forge(*args, **kwargs):
        item, msgs = original_forge(*args, **kwargs)
        if item is not None:
            forged["爐"] += 1
            forged["名器"] += item.secret is not None and not item.original and item.copy_of is None
            forged["原品"] += item.original
            forged["仿品"] += item.copy_of is not None
        return item, msgs

    real_grant, real_pick = materials.grant, materials.tier3_pick

    def counted_grant(state, content_, material_id, count=1):
        """一季拿到幾個三階（不論來源：掉落表、新來源、事件、路上）。"""
        line = real_grant(state, content_, material_id, count)
        if line and content_.materials[material_id].tier == 3:
            tier3["全部"] += count
        return line

    def counted_pick(*args, **kwargs):
        """三階的新來源（Game._tier3 擲中了才挑）：挑戰本人與大場面另擲的那幾個。"""
        mid = real_pick(*args, **kwargs)
        tier3["新來源"] += mid is not None
        return mid

    def counted(original):
        """數真的合成了幾爐：回傳的東西不是 None 才算（被拒絕的不算）。"""
        def wrapped(*args, **kwargs):
            made, msgs = original(*args, **kwargs)
            tally.forges += made is not None
            return made, msgs
        return wrapped

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
            mock.patch.object(fusion, "blend", counted(original_blend)), mock.patch.object(fusion, "merge", counted(original_merge)), \
            mock.patch.object(smithing, "forge_plan", steer("weapon", original_forge_plan)), \
            mock.patch.object(smithing, "armor_plan", steer("armor", original_armor_plan)), mock.patch.object(smithing, "forge", counted_forge), \
            mock.patch.object(materials, "grant", counted_grant), mock.patch.object(materials, "tier3_pick", counted_pick):
        game = bot.play_season(content, seed, world=world)
    tianji = secret_recipes.tianji_of(game.world)
    book = secret_recipes.manual(game.state, tianji)
    heard = [i for idx in book.heard.values() for i in idx]
    fbook = forge_secrets.manual(game.state, tianji)
    fheard = [i for idx in fbook.heard.values() for i in idx]
    pieces = sum(len(got) for got in fbook.pieces.values())  # 拆了片的季聽到的神器線索片子（FB-270；不分來源）
    return {
        "合中": len(book.solved), "這一季": len(secret_recipes.active(content, tianji)),
        "說書": heard.count(secret_recipes.TALE), "殘譜": heard.count(secret_recipes.SCRAP),
        "爐": tally.forges,
        "哪幾條": ",".join(book.solved),
        "鑄器摸到": len(fbook.solved), "鑄器這一季": len(forge_secrets.active(content, tianji, game.state.world)),  # 照季的章（FB-270）
        "鑄器組": Counter(forge_secrets.group_of(content.forge_secrets[rid]) for rid in fbook.solved),
        "鑄說書": fheard.count(forge_secrets.TALE), "鑄鐵匠": fheard.count(forge_secrets.SMITH), "鑄殘譜": fheard.count(forge_secrets.SCRAP),
        "鑄片": pieces,
        "打造": forged["爐"], "名器": forged["名器"], "鑄器哪幾條": set(fbook.solved),
        "原品": forged["原品"], "仿品": forged["仿品"], "三階": tier3["全部"], "三階新": tier3["新來源"],
    }


def _fmt(row: dict) -> str:
    return f"合中 {row['合中']}/{row['這一季']}　口訣 說書 {row['說書']}・殘譜 {row['殘譜']}　爐 {row['爐']}　{row['哪幾條']}"


def _fmt_forge(row: dict) -> str:
    groups = "・".join(f"{GROUP_WORDS.get(g, g)} {n}" for g, n in sorted(row["鑄器組"].items())) or "—"
    share = f"{row['名器'] / row['打造'] * 100:.0f}%" if row["打造"] else "—"
    return (f"鑄器：摸到 {row['鑄器摸到']}/{row['鑄器這一季']}（{groups}）　口訣 說書 {row['鑄說書']}・鐵匠 {row['鑄鐵匠']}・殘譜 {row['鑄殘譜']}"
            f"・神器片子 {row['鑄片']}"
            f"　打造 {row['打造']} 爐、名器 {row['名器']}（{share}）　神器 原品 {row['原品']}・仿品 {row['仿品']}"
            f"　三階 {row['三階']}（新來源 {row['三階新']}）")


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
            print(f"種子 {seed} {side} {_fmt_forge(row)}", flush=True)
        seed_rows = [rows[side][-1] for side in SIDES]
        union = set().union(*(r["鑄器哪幾條"] for r in seed_rows))
        print(f"種子 {seed} 三邊合起來：鑄器摸到 {len(union)}/{seed_rows[0]['鑄器這一季']}", flush=True)
    for side, side_rows in rows.items():
        mean = lambda k: statistics.mean(r[k] for r in side_rows)  # noqa: E731
        print(
            f"{side}平均：合中 {mean('合中'):.1f}/{mean('這一季'):.0f}　口訣 說書 {mean('說書'):.1f}・殘譜 {mean('殘譜'):.1f}"
            f"　爐 {mean('爐'):.0f}"
        )
        print(
            f"{side}平均 鑄器：摸到 {mean('鑄器摸到'):.1f}/{mean('鑄器這一季'):.0f}　口訣 說書 {mean('鑄說書'):.1f}・鐵匠 {mean('鑄鐵匠'):.1f}"
            f"・殘譜 {mean('鑄殘譜'):.1f}・神器片子 {mean('鑄片'):.1f}　打造 {mean('打造'):.1f} 爐、名器 {mean('名器'):.1f}"
            f"　神器 原品 {mean('原品'):.1f}・仿品 {mean('仿品'):.1f}　三階 {mean('三階'):.1f}（新來源 {mean('三階新'):.1f}）"
        )


if __name__ == "__main__":
    main()
