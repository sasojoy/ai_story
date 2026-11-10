"""The real server from one unpacked copy, for the web comparison: clock and random frozen, model on a dead port, one staging route.

usage: python -u serve.py <copy root> <port> <db file> [profile] [--outbox <file>]

Exit 3 when something this wrapper patches is gone (the code it patches moves around between waves; a patch that silently
stops applying would turn into noise on every run). gate.py turns that into its exit 2.

--outbox (batch 110): codes never go to the log (batch 208: only the notice line, LOG_LINE), so a round that reaches a code reads it here.
With the identity switch and fake_services both on, every fake SMS and mail is appended as one JSON line {"kind", "to", "text"};
otherwise one line says the outbox is off and nothing is touched.
"""
import importlib
import json
import os
import random
import sys
import threading
import time
import traceback
import types

OUTBOX = None
if "--outbox" in sys.argv:  # taken out first: the four places stay where they are
    _i = sys.argv.index("--outbox")
    OUTBOX = sys.argv[_i + 1]
    del sys.argv[_i:_i + 2]
ROOT, PORT, DB = sys.argv[1:4]
PROFILE = sys.argv[4] if len(sys.argv) > 4 else "season21"
sys.path.insert(0, ROOT)
os.chdir(ROOT)
os.environ["TIANXIA_DB"] = DB
os.environ["TIANXIA_PROFILE"] = PROFILE

CLOCK = {"now": 1793937600.0}
time.time = lambda: CLOCK["now"]

_init = random.Random.__init__


def _seeded(self, x=None):
    _init(self, 12345 if x is None else x)


random.Random.__init__ = _seeded
random.seed(0)

import server  # noqa: E402

# every name of server.py this file reaches for
PATCH_NAMES = ("CONTENT", "app", "main", "narration_round", "BOARDS_CACHE", "GAMES", "world_step", "WORLD_GAME", "_monotonic", "open_characters", "start_scheduler", "make_queue")
# the seal module draws its shard secrets from here; it has lived in two places
SEAL_MODULES = ("tianxia.features.seal.seal",)


def _seal_module():
    for name in SEAL_MODULES:
        try:
            module = importlib.import_module(name)
        except ImportError:
            continue
        if hasattr(module, "secrets"):
            return module
    return None


missing = [name for name in PATCH_NAMES if not hasattr(server, name)]
_seal = _seal_module()
if _seal is None:
    missing.append("secrets in " + " or ".join(SEAL_MODULES))
OUTBOX_SENDERS = ("sms", "mail")  # tianxia.features.identity.senders.FAKES.<name>.send, only reached for with --outbox


def _fakes():
    try:
        from tianxia.features.identity import senders
    except ImportError:
        return None
    fakes = getattr(senders, "FAKES", None)
    return fakes if fakes is not None and all(callable(getattr(getattr(fakes, k, None), "send", None)) for k in OUTBOX_SENDERS) else None


_FAKES = _fakes() if OUTBOX else None
if OUTBOX and _FAKES is None:
    missing.append("tianxia.features.identity.senders.FAKES " + ", ".join(f"{k}.send" for k in OUTBOX_SENDERS))
if missing:
    print("webqa: patch targets gone:", ", ".join(missing), flush=True)
    sys.exit(3)


def _to_outbox(kind, send):
    def wrapped(to, *rest):
        send(to, *rest)
        with open(OUTBOX, "a", encoding="utf-8") as f:
            f.write(json.dumps({"kind": kind, "to": to, "text": rest[-1]}, ensure_ascii=False) + "\n")
    return wrapped


if OUTBOX:
    _id = server.CONTENT.config.identity
    if _id.enabled and _id.fake_services:
        for _kind in OUTBOX_SENDERS:
            _sender = getattr(_FAKES, _kind)
            _sender.send = _to_outbox(_kind, _sender.send)
        print(f"webqa: outbox {OUTBOX}", flush=True)
    else:
        print("webqa: outbox off (identity off)", flush=True)

assert server.CONTENT.config.ollama_url == "http://127.0.0.1:9", server.CONTENT.config.ollama_url
# The 開場 layer (intro package) covers the whole page the first time a new character reaches the 城門口, and every walk
# account is new: it would sit over the clicks. The walk is about the game under it, so the layer stays off here.
if getattr(server.CONTENT.config, "intro", None) is not None:
    server.CONTENT.config.intro.enabled = False
server._monotonic = lambda: CLOCK["now"]
server.narration_round = lambda *a, **k: None
# The world only moves on requests. The scheduler ticks on the wall clock, so whether a tick lands before or after the walk's next
# request differs from side to side: wave D saw a xingshi essay written on one side only because of it.
server.start_scheduler = lambda interval: None
# The model queue has one slot and skips a writer when another holds it. The chronicle loop runs on the wall clock, so who got skipped differed from side
# to side, and a skipped essay goes back on the shelf with a retry 30 frozen seconds away: wave D saw one more line in the rumours on one side, six scenes long.
# With no queue every writer just calls the dead port and writes its fixed text.
server.make_queue = lambda config: None
_seal.secrets = types.SimpleNamespace(token_hex=lambda n=16: "ab" * n)

from fastapi import Body, Request  # noqa: E402
from fastapi.concurrency import run_in_threadpool  # noqa: E402

from tianxia.sqlite_world import open_world  # noqa: E402


# Writers a request kicks off and leaves running: the next request would see their work on one side and not on the other.
WRITERS = ("xingshi", "event-flavor", "battle-tales", "arena-crowd", "letter", "yuedan", "tavern-chatter", "guard-event")
WRITER_PREFIXES = ("zhuan-",)  # one thread a season: zhuan-1, zhuan-2


def _writers_done(seconds: float = 8.0) -> None:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline and any((t.name in WRITERS or t.name.startswith(WRITER_PREFIXES)) and t.is_alive() for t in threading.enumerate()):
        time.sleep(0.02)


@server.app.middleware("http")
async def _freeze_each_request(request: Request, call_next):
    random.seed(0)
    server.BOARDS_CACHE.clear()
    static = request.url.path.startswith("/static")
    if not static:
        server.GAMES.clear()
    response = await call_next(request)
    if not static:
        await run_in_threadpool(_writers_done)
    return response


_world_step = server.world_step


def _seeded_world_step(*a, **k):
    random.seed(0)
    if server.WORLD_GAME is not None:
        server.WORLD_GAME.rng = random.Random(1)
    return _world_step(*a, **k)


server.world_step = _seeded_world_step


@server.app.post("/__qa/py")
def qa_py(body: dict = Body(...)):
    g = {"server": server, "content": server.CONTENT, "chars": server.open_characters(), "world": open_world(DB), "CLOCK": CLOCK, "out": None}
    try:
        import stage_lib

        g["stage"] = importlib.reload(stage_lib)
        exec(body["code"], g)
    except Exception:
        return {"error": traceback.format_exc()[-1500:]}
    return {"out": g.get("out")}


server.main(["--port", PORT])
