"""Staging helpers for the throwaway servers, called from /__qa/py: same code on both sides.

No imports at the top: this file has to load on old commits too (reproductions), so anything newer goes through getattr inside the function that wants it.
"""
import importlib


def _insight_fx():
    return importlib.import_module("tianxia.insight_fx")


def _state():
    return importlib.import_module("tianxia.state")


def skills_by_kind(content):
    out = {}
    for k, v in content.skills.items():
        kind = getattr(v, "kind", None) or getattr(v, "type", None) or getattr(v, "category", None)
        out.setdefault(str(kind), []).append(k)
    return out


def rich(chars, content, name, loc, level=30, gear=False):
    """gear: also the mount, the treasure and a full rack (wave B's walk stood on them; wave C's did not)."""
    Equipment, InsightFx = _state().Equipment, _state().InsightFx
    st = chars.load(name)
    p = st.player
    p.location, p.journey = loc, None
    st.pending_event = None
    p.stamina = 200
    p.joined_at = -1e9
    p.stats.update(str=12, agi=10, con=9, wis=8, lore=6, silver=88888, good=130, evil=0, fame=260, xinde=900)
    p.member.level, p.member.exp = level, 0
    p.stat_points = 6
    p.materials = {k: 9 for k in content.materials}
    p.weapon = Equipment(id="兵:1", name="寒鐵厚背刀", kind="刀", attribute="剛", tier=2, quality="中品", edge=80, tempers=1)
    p.armor = Equipment(id="甲:2", slot="armor", name="鎖子甲", attribute="柔", tier=2, quality="上品", edge=60)
    if gear:
        steeds, tre = list(content.gear.steeds), list(content.gear.treasures)
        p.mount = Equipment(id="騎:3", slot="mount", name=content.gear.steeds[steeds[0]].name, tier=1, quality="下品", edge=70, template=steeds[0])
        p.treasure = Equipment(id="寶:4", slot="treasure", name=content.gear.treasures[tre[0]].name, template=tre[0])
        p.rack = [
            Equipment(id="兵:5", name="短劍", kind="劍", attribute="快", tier=1, quality="下品", edge=100),
            Equipment(id="兵:6", name="虎頭槍", kind="槍", attribute="剛", tier=3, quality="上品", edge=35, tempers=2),
            Equipment(id="甲:7", slot="armor", name="皮甲", attribute="慢", tier=1, quality="下品", edge=20),
            Equipment(id="騎:8", slot="mount", name=content.gear.steeds[steeds[-1]].name, tier=2, quality="中品", edge=90, template=steeds[-1]),
            Equipment(id="寶:9", slot="treasure", name=content.gear.treasures[tre[1]].name, template=tre[1]),
        ]
    p.weapon_serial = 10
    p.arts = ["shouyi_jian", "shusheng_jian", "youxia_jian", "xingwu_dao", "yanghao_jue", "taiping_daoyin"]
    p.art_levels = {"shouyi_jian": 3, "shusheng_jian": 7, "yanghao_jue": 2}
    p.insights = ["feng", "huo", "shui", "shan", "haoran"]
    q = _insight_fx().QUALITIES
    p.insight_fx = {i: InsightFx(quality=q[min(n, len(q) - 1)], general={}) for n, i in enumerate(p.insights)}
    chars.save(st)
    return {"silver": p.stats["silver"], "level": level}


def place(chars, name, loc, **fields):
    st = chars.load(name)
    p = st.player
    p.location, p.journey = loc, None
    st.pending_event = None
    for k, v in fields.items():
        setattr(p, k, v)
    chars.save(st)
    return loc


def two_copies(chars, content, world, name):
    """feng and feng~2: one trait at layer 1 on each and a second trait on one, so merged cells are part lit."""
    fx, InsightFx = _insight_fx(), _state().InsightFx
    st = chars.load(name)
    p = st.player
    ins = content.insights["feng"]
    attribute = ins.attribute
    pool = fx.generals(content, attribute)
    a, b = pool[0], pool[1] if len(pool) > 1 else pool[0]
    p.insights = [i for i in p.insights if i not in ("feng", "feng~2")] + ["feng", "feng~2"]
    q = fx.QUALITIES
    p.insight_fx["feng"] = InsightFx(quality=q[1], general={a.key: 1})
    p.insight_fx["feng~2"] = InsightFx(quality=q[2], general={a.key: 1, b.key: 1})
    chars.save(st)
    return {"attribute": attribute, "traits": [a.key, b.key], "pool": len(pool)}


def divine_recipe(chars, content, world, name):
    """Materials and a place to forge the first of one of this season's divine recipes; the flow forges it through the server's own route. None when none is left."""
    fs = importlib.import_module("tianxia.forge_secrets")
    season = world.get_season()
    tianji = world.tianji()
    st = chars.load(name)
    p = st.player
    p.location, p.journey = "wan_city", None
    st.pending_event = None
    p.stats["silver"] = 88888
    for recipe in fs.active(content, tianji, season):
        if not recipe.divine or recipe.kind is None or world.lookup_gear_find(fs.key(recipe)) is not None:
            continue
        mains = [k for k, m in content.materials.items() if fs.fits(recipe.main, m)]
        auxes = [k for k, m in content.materials.items() if fs.fits(recipe.aux, m)]
        pair = next(((m, x) for m in mains for x in auxes if fs.match(content, tianji, recipe.slot, recipe.kind, m, x, season) is recipe), None)
        if pair is None:
            continue
        p.materials[pair[0]] = 9
        p.materials[pair[1]] = 9
        chars.save(st)
        return {"kind": recipe.kind, "main": pair[0], "aux": pair[1], "pattern": recipe.name}
    return None


def persuade_errand(chars, content, name, figure, errand):
    """A persuade errand on the character, who then stands at its target (the way the errand tests give one). None if the errand is not in this content."""
    errands = importlib.import_module("tianxia.errands")
    st = chars.load(name)
    st.player.affinities[figure] = 50
    errands.give(st, content, figure, errand)
    if not st.player.errands:
        return None
    e = st.player.errands[-1]
    st.player.location, st.player.journey = e.target, None
    st.pending_event = None
    chars.save(st)
    return {"id": e.id, "target": e.target}


def _wallet(world):
    return importlib.import_module("tianxia.wallet").Wallet(world.db)


def _owner(name):
    return importlib.import_module("tianxia.characters").name_key(name)


def give_ingots(world, now, names, amount):
    w = _wallet(world)
    for n in names:
        w.post(_owner(n), amount, "grant", f"qa-{n}-{now}", time=now)
    return True


def look_order(world, content, name, look_name, now, made=False):
    """A custom look ordered by this character: still waiting for its pictures (it can be withdrawn), or made (it can go on the market). The sixteen sheets are not drawn, the row is only marked."""
    orders = importlib.import_module("tianxia.features.looks.orders")
    w = _wallet(world)
    pid, said = orders.place(content, w, _owner(name), look_name, "一身青衫的少年俠客", f"qa-{look_name}", now=now, day=1, season=world.get_season().number if hasattr(world.get_season(), "number") else 1)
    if pid is None:
        return {"pid": None, "said": said}
    if made:
        w.update_data(pid, status=orders.MADE, look_id=orders.look_id(pid))
    return {"pid": pid, "look": orders.look_id(pid)}


def mvp_now(world, name, move="qa", move_name="試招"):
    """The round that just settled has this one as its best: picked by hand, a real one takes a gamble that came through with a move on, and the model is on a dead port here."""
    BattleMvp = importlib.import_module("tianxia.core.battle_base").BattleMvp

    def fn(b):
        p = b.participants[name]
        b.mvps.append(BattleMvp(round=b.round_number, name=name, faction=p.faction, move=move, move_name=move_name))
    world.mutate_battle(fn)
    return True


def chiefs(world):
    b = world.get_battle()
    return None if b is None else [[c.fid, c.name, c.faction, c.rank, round(c.neili), round(c.neili_cap), c.fallen_round, c.felled_by] for c in b.commanders]


def chief_pct(world, faction, rank, pct):
    def fn(b):
        c = next(c for c in b.commanders if c.faction == faction and c.rank == rank)
        c.neili = c.neili_cap * pct / 100
    world.mutate_battle(fn)
    return chiefs(world)


def chief_fall(world, faction, rank, by):
    def fn(b):
        c = next(c for c in b.commanders if c.faction == faction and c.rank == rank)
        c.neili = 0.0
        c.fallen_round = b.round_number
        c.felled_by = by
    world.mutate_battle(fn)
    return chiefs(world)


def knock_out(world, name):
    def fn(b):
        p = b.participants[name]
        p.neili = 0.0
        p.eliminated = True
    world.mutate_battle(fn)
    return 1


def battle_brief(world):
    b = world.get_battle()
    if b is None:
        return None
    return {"id": b.battle_id, "phase": b.phase, "round": b.round_number, "parts": list(b.participants), "opened": b.round.opened_real if b.round else None, "muster": b.muster_deadline_real}
