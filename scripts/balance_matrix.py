"""平衡總表：屬性配法 × 身手（武學、意境、秘方、頓悟神品、兵器、防具、玉璽碎片），用真的擂台規則互打。

企劃者 2026-11-04「武學、寶物、裝備，全部的極端可能性都要計算在平衡系統裡」「有也沒關係，但是要在我們的控制範圍內」
「先確保我們舊的武學效果不會因為新的屬性點而亂套」。檢查清單在 docs/guide/量表與教訓.md「量平衡與試玩的教訓」。

每個人都是真的 Game 物件：五項照配法長、送點照配法給；身手照 KITS 組（真的內容武學、真的自創絕學與意境、真的神器原品、
真的玉璽碎片）。對打走擂台：arena_actions.arena_side 快照、faced 照對方重算、tactics.open_bout 本命戰法、
arena_rules.exchange_full 一回合一回合打到 verdict。兩邊都照分身的出招法（roll_next 的權重）出招，甲挑乙、乙挑甲各打一半。

印三張表：
1. 同一套身手，不同配法互打（每一套身手各一張）：看有沒有配法壓倒性贏或輸；
2. 每一套身手裡贏面最高的配法：看有沒有「特別適配」的身手配屬性；
3. 身手互打（配法都用均衡）：看裝備、武學的極端差多少。

用法：python scripts/balance_matrix.py [--level 30] [--n 200] [--kits ...] [--builds ...] [--json out.json]
"""
from __future__ import annotations

import argparse
import io
import json
import os
import random
import statistics
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("TIANXIA_DB", str(Path(tempfile.mkdtemp(prefix="bal-")) / "t.db"))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from tianxia import tactics, team  # noqa: E402
from tianxia.content import load_content  # noqa: E402
from tianxia.engine import Game  # noqa: E402
from tianxia.equipment import Equipment  # noqa: E402
from tianxia.features.bout import arena_actions  # noqa: E402
from tianxia.features.bout import arena_rules as arena  # noqa: E402
from tianxia.martial_arts import MAX_LEVEL, Insight, MartialArt  # noqa: E402
from tianxia.models import MOVES  # noqa: E402
from tianxia.sqlite_world import open_world  # noqa: E402
from tianxia.state import ArenaFight, InsightFx  # noqa: E402

WIN = {"大勝", "險勝"}

# 配法：名字 → (配比, 送點全給哪一項)。全某項＝那一項 4（上限）、另一項 3、其餘 1
BUILDS = {
    "全武力": ({"str": 4, "lead": 1, "int": 1, "spd": 3, "cha": 1}, "str"),
    "全統御": ({"str": 3, "lead": 4, "int": 1, "spd": 1, "cha": 1}, "lead"),
    "全悟性": ({"str": 1, "lead": 1, "int": 4, "spd": 1, "cha": 3}, "int"),
    "悟性武力": ({"str": 3, "lead": 1, "int": 4, "spd": 1, "cha": 1}, "int"),
    "全身法": ({"str": 3, "lead": 1, "int": 1, "spd": 4, "cha": 1}, "spd"),
    "全魅力": ({"str": 1, "lead": 1, "int": 3, "spd": 1, "cha": 4}, "cha"),
    "武將": ("warrior", "str"),
    "均衡": ("balanced", None),
}

# 身手。arts：內容武學 id（wugong, neigong），或自創絕學 [(kind, attribute, cells)]，cell＝{"attr", "gens":{名:層}, "special", "god"}
KITS = {
    "下品": {"arts": ("xingwu_dao", "xingwu_lianqi")},
    "上品": {"arts": ("buqu_dao", "yanghao_jue")},
    "絕學": {"arts": ("guanyu_wugong", "dongzhuo_neigong")},
    "秘方神器": {  # 10/27 的 A：連環、借力兩個秘方特效＋隕星刀
        "created": [("武學", "陽", [{"attr": "快", "gens": {"先手": 1}, "special": "連環"}, {"attr": "陽", "gens": {"朝陽": 2}},
                                    {"attr": "陽", "gens": {"乘勝": 2}}]),
                    ("內功", "陽", [{"attr": "快", "gens": {"掠影": 1}, "special": "借力"}, {"attr": "虛", "gens": {"料敵": 2}},
                                    {"attr": "虛", "gens": {"險": 1}}])],
        "weapon": "wd_fallen_star"},
    "頓悟神品": {  # 10/27 的 C：實變神品＋隕星刀
        "created": [("武學", "陽", [{"attr": "快", "gens": {"先手": 1}}, {"attr": "陽", "gens": {"朝陽": 2}}, {"attr": "陽", "gens": {"乘勝": 2}}]),
                    ("內功", "陽", [{"god": "實變神品"}, {"attr": "虛", "gens": {"料敵": 2}}, {"attr": "虛", "gens": {"險": 1}}])],
        "weapon": "wd_fallen_star"},
    "護命回春": {  # 吃氣血的那一路（偏統御）：護命、回春＋化勁、鐵壁、厚
        "created": [("武學", "柔", [{"attr": "柔", "gens": {"化勁": 2}, "special": "護命"}, {"attr": "實", "gens": {"鐵壁": 2}},
                                    {"attr": "實", "gens": {"厚": 2}}]),
                    ("內功", "實", [{"attr": "柔", "gens": {"回瀾": 2}, "special": "回春"}, {"attr": "實", "gens": {"厚": 2}},
                                    {"attr": "慢", "gens": {"守拙": 2}}])],
        "weapon": "wd_fallen_star"},
    "輕身先手": {  # 吃身法的那一路：輕身、先手、掠影（身法高的先手）
        "created": [("武學", "快", [{"attr": "快", "gens": {"先手": 2}, "special": "輕身"}, {"attr": "快", "gens": {"掠影": 2}},
                                    {"attr": "虛", "gens": {"險": 2}}]),
                    ("內功", "快", [{"attr": "快", "gens": {"掠影": 2}, "special": "連環"}, {"attr": "虛", "gens": {"料敵": 2}},
                                    {"attr": "快", "gens": {"先手": 2}}])],
        "weapon": "wd_dark_crystal"},
    "悟招破甲": {  # 吃悟性（內功份量）的那一路：悟招＋破甲、沉勁
        "created": [("武學", "剛", [{"attr": "剛", "gens": {"破甲": 2}, "special": "悟招"}, {"attr": "剛", "gens": {"沉勁": 2}},
                                    {"attr": "陰", "gens": {"陰勁": 2}}]),
                    ("內功", "陰", [{"attr": "陰", "gens": {"吸取": 2}, "special": "借力"}, {"attr": "剛", "gens": {"沉勁": 2}},
                                    {"attr": "陰", "gens": {"陰勁": 2}}])],
        "weapon": "wd_fallen_star"},
}
EXTRAS = {"＋神器防具": {"armor": True}, "＋玉璽碎片": {"seal": True}}


class Kit:
    def __init__(self, content):
        self.c = content
        self.gen = {t.name: (t.id or t.key) for t in content.traits.general} if content.traits else {}
        self.special = {t.name: t.id for t in content.traits.special}
        self.god = {g.name: g for g in content.traits.god}
        self.n = 0

    def _insight(self, s, cell) -> str:
        self.n += 1
        iid = f"悟:{self.n}"
        p = s.player
        p.own_insights[iid] = Insight(id=iid, name=f"悟{self.n}", attribute=cell.get("attr", "快"),
                                      secret_special=self.special[cell["special"]] if cell.get("special") else None)
        p.insights.append(iid)
        if cell.get("god"):
            g = self.god[cell["god"]]
            p.insight_fx[iid] = InsightFx(quality="上品", general={g.general: 3}, grand=g.id)
        else:
            p.insight_fx[iid] = InsightFx(quality="上品", general={self.gen[k]: v for k, v in cell["gens"].items()})
        return iid

    def _created(self, g: Game, kind: str, attribute: str, cells) -> None:
        s = g.state
        self.n += 1
        name = f"{s.player.name}{kind}{self.n}"
        colors = [[cell.get("attr", attribute)] for cell in cells]
        art = MartialArt(id=name, name=name, kind=kind, quality="上品", attribute=attribute, base_power=40, top_power=100,
                         origin="created", creator=s.player.name, creator_shown=s.player.name,
                         affinity=list(dict.fromkeys([attribute] + [c[0] for c in colors])), slot_colors=colors,
                         weapon="刀" if kind == "武學" else None, method="吐納" if kind == "內功" else None,
                         move_fire="透", move_rare=True, move_stance="出招" if kind == "武學" else "起手")
        g.world.claim_skill_name(art)
        s.player.art_quality[name] = "絕學"
        m = s.player.member
        if kind == "內功":
            m.neigong_id, m.neigong_level = name, MAX_LEVEL
        else:
            m.wugong_id, m.wugong_level = name, MAX_LEVEL
        s.player.art_slots[name] = [self._insight(s, cell) for cell in cells]

    def apply(self, g: Game, spec: dict, extras: dict) -> None:
        s, m = g.state, g.state.player.member
        if "arts" in spec:
            m.wugong_id, m.neigong_id = spec["arts"]
            m.wugong_level = m.neigong_level = MAX_LEVEL
        for kind, attribute, cells in spec.get("created", []):
            self._created(g, kind, attribute, cells)
        if spec.get("weapon"):
            sec = self.c.forge_secrets[spec["weapon"]]
            s.player.weapon = Equipment(id="兵:9", name=sec.name, kind=sec.kind, attribute=sec.main.attribute, tier=4,
                                        quality="上品", original=True, secret=sec.id, bound_art=m.wugong_id)
        if extras.get("armor"):
            sec = next(x for x in self.c.forge_secrets.values() if x.slot == "armor" and getattr(x, "divine", False))
            s.player.armor = Equipment(id="甲:9", name=sec.name, kind=sec.kind or "袍", attribute=sec.main.attribute, tier=4,
                                       quality="上品", original=True, secret=sec.id, slot="armor")
        if extras.get("seal"):
            shard = next(iter(self.c.seal))
            s.player.heirloom = Equipment(id="璽:1", name=self.c.seal[shard].name, kind="寶物", attribute="", tier=4,
                                          quality="上品", template=shard, slot="treasure", heirloom=True)


def make(content, kit: Kit, build: str, kit_name: str, level: int, seq: list[int]) -> Game:
    seq[0] += 1
    world = open_world(Path(tempfile.mkdtemp(prefix="bal-")) / "t.db")
    g = Game.new(content, f"甲{seq[0]}", rng=random.Random(seq[0]), world=world)
    g.client = None
    p = g.state.player
    p.member.level = level
    split, bonus = BUILDS[build]
    if isinstance(split, dict):
        p.growth_preset, p.growth_custom = "custom", dict(split)
    else:
        p.growth_preset = split
    cfg = content.config.attributes.v2
    pts = (level // cfg.bonus_every) * cfg.bonus_points
    p.attr_alloc = {bonus: pts} if bonus else {k: pts // len(cfg.keys) for k in cfg.keys}
    base, _, extra = kit_name.partition("＋")
    kit.apply(g, KITS[base], EXTRAS.get("＋" + extra, {}) if extra else {})
    return g


def fight(a: Game, b: Game, rng: random.Random) -> str:
    """a 挑 b（b 是分身）打一場，回 a 那一邊的結果。兩邊都照分身的出招法出招。"""
    c = a.content
    me, foe = arena_actions.arena_side(a), arena_actions.arena_side(b)
    f = ArenaFight(id=1, foe_key="b", me=me, foe=foe, rounds=c.config.arena.rounds, edge=c.config.duel.start)
    arena_actions.faced(c, f.me, f.foe)
    f.bout = tactics.open_bout(team.self_side(a.state, c, a.world), team.self_side(b.state, c, b.world), "你", b.state.player.name,
                               pvp=True)
    cfg = c.config.arena
    while True:
        arena.roll_next(f, rng, cfg, c.config.duel)
        values = [max(0.0, f.me.scores.get(m, 0.0)) for m in MOVES]
        top = max(values) or 1.0
        move = rng.choices(MOVES, weights=[(v / top) ** cfg.proxy_power for v in values])[0]
        banned = tactics.locks(f.bout).no_moves
        if move in banned:
            move = next((m for m in MOVES if m not in banned), move)
        arena.exchange_full(f, move, c, rng, rng)
        f.round += 1
        tier = arena.verdict(f, c.config.duel)
        if tier is not None:
            return tier


def share(a: Game, b: Game, n: int, seed: int) -> float:
    """a 對 b 的贏面：a 挑 b 一半、b 挑 a 一半（a 守時，b 落敗就算 a 贏）。"""
    rng = random.Random(seed)
    won = 0
    for i in range(n):
        if i % 2 == 0:
            won += fight(a, b, rng) in WIN
        else:
            won += fight(b, a, rng) == "落敗"
    return won / n


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--level", type=int, default=30)
    ap.add_argument("--n", type=int, default=200)
    ap.add_argument("--kits", nargs="*", default=None)
    ap.add_argument("--builds", nargs="*", default=None)
    ap.add_argument("--json")
    ap.add_argument("--int-outer", type=float, default=None, help="試草稿：悟性也管外功（對他的悟性），上限這麼多")
    ap.add_argument("--str-cap", type=float, default=None, help="試草稿：武力管外功的上限")
    ap.add_argument("--neigong-div", type=float, default=None, help="試：內功份量的除數（encounter.NEIGONG_BONUS_DIVISOR，現在 100；越小內功越重）")
    ap.add_argument("--power-cap", type=float, default=None, help="試：份量的威力上限（battle.power_cap，現在 400）")
    args = ap.parse_args()
    c = load_content(ROOT / "content", profile="season21")
    c.config.attributes.v2.enabled = True
    c.config.auto_open_first_season = True
    if args.int_outer:
        from tianxia.models import AttrEffect
        c.config.attributes.v2.effects.append(AttrEffect(attr="int", hook="outer", curve="contest", cap=args.int_outer, scale=40, origin=50))
    if args.str_cap is not None:
        for row in c.config.attributes.v2.effects:
            if row.attr == "str" and row.hook == "outer":
                row.cap = args.str_cap
    if args.neigong_div:
        from tianxia import encounter
        encounter.NEIGONG_BONUS_DIVISOR = args.neigong_div
    if args.power_cap:
        c.config.battle.power_cap = args.power_cap
    kit = Kit(c)
    seq = [0]
    builds = args.builds or list(BUILDS)
    kits = args.kits or list(KITS) + ["秘方神器＋神器防具", "秘方神器＋玉璽碎片"]
    games = {(k, b): make(c, kit, b, k, args.level, seq) for k in kits for b in builds}
    out = {"level": args.level, "n": args.n, "per_kit": {}, "kits": {}}
    print(f"第 {args.level} 級；每一對 {args.n} 場（甲挑乙、乙挑甲各半）；格子是列的人贏的機會")
    for k in kits:
        rows = {}
        for a in builds:
            rows[a] = {b: share(games[(k, a)], games[(k, b)], args.n, hash((k, a, b)) & 0xffffff) for b in builds}
        out["per_kit"][k] = rows
        power = {b: round(arena_actions.arena_side(games[(k, b)]).power) for b in builds}
        print(f"\n【{k}】威力（對平均人） " + "、".join(f"{b}{v}" for b, v in power.items()))
        print("".ljust(8) + "".join(b.ljust(7) for b in builds) + "平均")
        for a in builds:
            vals = [rows[a][b] for b in builds if b != a]
            print(a.ljust(8) + "".join(f"{rows[a][b]:.0%}".ljust(8) for b in builds) + f"{statistics.mean(vals):.0%}")
    print("\n身手互打（配法都是均衡）")
    print("".ljust(12) + "".join(k[:6].ljust(9) for k in kits))
    for k1 in kits:
        row = {k2: share(games[(k1, "均衡")], games[(k2, "均衡")], args.n, hash((k1, k2)) & 0xffffff) for k2 in kits}
        out["kits"][k1] = row
        print(k1[:10].ljust(12) + "".join(f"{row[k2]:.0%}".ljust(10) for k2 in kits))
    if args.json:
        Path(args.json).write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
