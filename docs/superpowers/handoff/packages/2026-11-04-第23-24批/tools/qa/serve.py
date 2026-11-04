"""工作包說明：這是第 12 批（頭目戰、擂台）QA 用的，留著當範本。
環境變數：QA_DIR（暫存資料夾，放 repo 外面；底下要有 HEAD、BASE 兩份工作樹）、QA_PORTS（預設 8161,8162）、QA_HOST（預設 qachk）。
要換成你這一批的：flow()、帳號名單、/__qa/peek 讀的欄位。用法看工作包的「共用-環境與做法.md」第六節。"""
"""單挑包第 1 批（全部拆包第 12 批：頭目戰、擂台、場邊事件）QA 的伺服器外殼（照 qa-sortie1/s/serve.py、b8-chk/s/serve.py、b22-chk/s/serve.py 改）：
QA_ROOT（BASE 或 HEAD 工作樹）的 server.py 照常起，兩版一模一樣：
  1. 時鐘凍住：time.time 與 server._monotonic 讀 CLOCK（從 QA_T0 起），只在 POST /__qa/clock {"t"|"dt"} 時往前推。
  2. 亂數凍住：每次進行動鎖（server._locked）把 game.rng 與全域 random 重設成 SEED＋int(假時鐘)；沒給種子的 random.Random() 用固定種子。
  3. 世界排程執行緒不開；戰記的背景執行緒不開；旁白改寫的那一輪什麼都不做；玉璽密鹽固定；註冊次數不限。
     場邊那一句的鎖外重寫（arena-crowd 執行緒）照開：/__qa/idle 等它停了再打下一步。
  4. /__qa/admin 建管理者；/__qa/edit 在行動鎖裡改存檔（只改給的那幾格）；/__qa/peek 讀單挑包認領的那幾格；/__qa/ladder 讀季上的擂台；
     /__qa/tweak 換記憶體裡的設定（兩台同一步換）；/__qa/force 探索一顆接下來幾下抽到的類別（同 same_behavior 的 draws）。
模型網址指到 127.0.0.1:9（叫不到，照固定段收），不碰 11434。"""
import contextlib
import os
import random
import sys
import threading
import time
import types
from pathlib import Path

root = Path(os.environ["QA_ROOT"]).resolve()
sys.path.insert(0, str(root))
os.chdir(root)
CLOCK = [float(os.environ["QA_T0"])]
time.time = lambda: CLOCK[0]
_orig_init = random.Random.__init__


def _seeded(self, x=None):
    _orig_init(self, 424242 if x is None else x)


random.Random.__init__ = _seeded
random.seed(0)

import server  # noqa: E402
from fastapi import Body  # noqa: E402

server.CONTENT.config.ollama_url = "http://127.0.0.1:9"
server.start_scheduler = lambda interval: None
server.narration_round = lambda clock=None: None
server._monotonic = lambda: CLOCK[0]
server.REGISTER_LIMIT = 10 ** 6
from tianxia import seal as _seal  # noqa: E402

_seal.secrets = types.SimpleNamespace(token_hex=lambda n=16: "5a" * n)

_orig_start_tales = server.start_tales


def _start_tales(config, client=None):
    """同 server.start_tales 建 TALES 與 TALES_CLIENT，只是不開背景執行緒。"""
    real_thread = threading.Thread

    class _NoStart(real_thread):
        def start(self):  # noqa: D401
            return None

    threading.Thread = _NoStart
    try:
        return _orig_start_tales(config, client)
    finally:
        threading.Thread = real_thread


server.start_tales = _start_tales
_orig_boards_now = server.boards_now


def _boards_now(game, clock=None):
    """整張榜的快取照真的 time.monotonic 過期：每次清掉重掃（同 same_behavior 的 begin），兩台才不會因為跑得快慢讀到不同份。"""
    server.BOARDS_CACHE.clear()
    return _orig_boards_now(game)


server.boards_now = _boards_now
SEED = 20261104
_orig_locked = server._locked


@contextlib.contextmanager
def _locked(game):
    with _orig_locked(game):
        seed = SEED + int(CLOCK[0])
        game.rng.seed(seed)
        random.seed(seed)
        yield


server._locked = _locked
C = server.CONTENT
TRANSIENT = ("battle-tales", "event-flavor", "letter", "yuedan", "xingshi", "arena-crowd", "tavern-chatter", "zhuan-")

# 探索一顆接下來幾下抽到的類別（/__qa/force；用完了照真的抽）
from tianxia import explore_one as _explore_one  # noqa: E402

FORCED: list = []
_real_draw = _explore_one.draw


def _draw(rng, weights, *, last_choice=None):
    if FORCED:
        return FORCED.pop(0)
    return _real_draw(rng, weights, last_choice=last_choice)


_explore_one.draw = _draw


@server.app.post("/__qa/clock")
def _qa_clock(body: dict = Body(...)):
    if "t" in body:
        CLOCK[0] = float(body["t"])
    if "dt" in body:
        CLOCK[0] += float(body["dt"])
    return {"t": CLOCK[0]}


@server.app.get("/__qa/idle")
def _qa_idle():
    busy = sorted(t.name for t in threading.enumerate() if t.is_alive() and t.name.startswith(TRANSIENT))
    return {"busy": busy, "tale_running": server.TALE_RUNNING}


@server.app.get("/__qa/where")
def _qa_where():
    import importlib.util

    import tianxia.duel as d

    return {"bout": importlib.util.find_spec("tianxia.features.bout") is not None, "duel": d.__name__,
            "duel_file": Path(d.__file__).name}


@server.app.post("/__qa/admin")
def _qa_admin(body: dict = Body(...)):
    from tianxia.accounts import AccountStore
    from tianxia.engine import Game

    world = server.open_world()
    chars = server.open_characters()
    store = AccountStore(world.db)
    with world.db.transaction():
        store.register(body["login"], body["password"])
        game = Game.new(C, body["name"], world=world)
        chars.save(game.state)
        store.bind_character(body["login"], body["name"])
    return {"ok": True}


def _walk(path):
    obj = C.config
    parts = path.split(".")
    for p in parts[:-1]:
        obj = getattr(obj, p)
    return obj, parts[-1]


@server.app.post("/__qa/tweak")
def _qa_tweak(body: dict = Body(...)):
    obj, key = _walk(body["path"])
    old = getattr(obj, key)
    setattr(obj, key, body["value"])
    return {"path": body["path"], "old": old, "new": getattr(obj, key)}


@server.app.post("/__qa/force")
def _qa_force(body: dict = Body(...)):
    FORCED[:] = [getattr(_explore_one, k) for k in body.get("draws") or []]
    return {"forced": list(FORCED)}


@server.app.post("/__qa/edit")
def _qa_edit(body: dict = Body(...)):
    """只改給的那幾格：loc（站過去、journey 清掉）、stamina_full、veteran（過新手期）、set（player 欄位）、stats、
    learn（[武學 id, 成]：沒有武學先學、武學內功練到那一成）、armor（穿一件甲）、duel_edge／arena_edge（打到一半那一場的氣勢）。"""
    from tianxia import rules
    from tianxia.state import Equipment

    world = server.open_world()
    chars = server.open_characters()
    with world.action_lock():
        st = chars.load(body["name"])
        p = st.player
        loc = body.get("loc")
        if loc:
            p.location, p.journey = loc, None
            p.visited.add(loc)
        if body.get("stamina_full"):
            p.stamina = float(C.config.stamina_max)
        if body.get("veteran"):
            p.joined_at = -1.0e9
        for k, v in (body.get("set") or {}).items():
            setattr(p, k, v)
        for k, v in (body.get("stats") or {}).items():
            p.stats[k] = v
        if body.get("learn"):
            skill, level = body["learn"]
            if p.member.wugong_id is None:
                rules.learn_skill(st, C, skill)
            if level:
                p.member.wugong_level, p.member.neigong_level = level, level
        if body.get("armor"):
            p.armor = Equipment(**body["armor"])
        if "duel_edge" in body and p.duel is not None:
            p.duel.edge = float(body["duel_edge"])
        if "arena_edge" in body and p.arena is not None:
            p.arena.edge = float(body["arena_edge"])
        chars.save(st)
        return {"ok": True, "loc": p.location, "wugong": p.member.wugong_id, "armor": None if p.armor is None else p.armor.edge,
                "duel": None if p.duel is None else p.duel.edge, "arena": None if p.arena is None else p.arena.edge}


def _dump(x):
    return None if x is None else x.model_dump(mode="json")


@server.app.post("/__qa/peek")
def _qa_peek(body: dict = Body(...)):
    """單挑包認領的十個欄位，加上氣血、內傷、銀兩、心得、名望、破境丹、防具、最新一份戰報與江湖紀錄的標題（同 same_behavior 的 BoutScenario.me）。"""
    st = server.open_characters().load(body["name"])
    if st is None:
        return {"missing": True}
    p = st.player
    return {
        "loc": p.location, "faction": p.faction, "stamina": p.stamina,
        "duel": _dump(p.duel), "duel_tally": dict(sorted(p.duel_tally.items())), "duel_last": list(p.duel_last),
        "arena": _dump(p.arena), "arena_last": _dump(p.arena_last), "picking_arena": p.picking_arena, "arena_day": p.arena_day,
        "arena_today": p.arena_today, "arena_crowd_seen": dict(sorted(p.arena_crowd_seen.items())),
        "arena_crowd_note": _dump(p.arena_crowd_note), "neili": p.member.neili, "injury": p.member.injury,
        "silver": p.stats.get("silver", 0), "xinde": p.stats.get("xinde", 0), "fame": p.stats.get("fame", 0),
        "legend": p.legend_items, "armor": _dump(p.armor), "battle": _dump(st.battles[-1]) if st.battles else None,
        "battles": len(st.battles), "journal": [e.title for e in st.journal[:4]], "wugong": [p.member.wugong_id, p.member.wugong_level],
    }


@server.app.get("/__qa/ladder")
def _qa_ladder():
    world = server.open_world()
    w = world.get_season()
    return {"entries": {k: e.model_dump(mode="json") for k, e in sorted(w.arena.items())}, "pairs": dict(sorted(w.arena_pairs.items())),
            "seq": w.arena_seq, "closed": w.arena_closed, "day": w.arena_day, "season": world.get_season_number(),
            "phase": world.season_phase(), "time": w.time}


@server.app.get("/__qa/info")
def _qa_info():
    from tianxia.characters import name_key

    return {"time_scale": C.config.time_scale, "cooldown": C.config.duel.cooldown_seconds, "pair_cd": C.config.arena.pair_cooldown_seconds,
            "per_day": C.config.arena.per_day, "keys": {n: name_key(n) for n in ("驗收官", "程聽松", "范映雪", "柯遠帆", "鍾離岫")},
            "bosses": sorted(b.id + "@" + ",".join(sorted(b.locations)) for b in C.duels.values())}


server.main(["--port", os.environ["QA_PORT"]])
