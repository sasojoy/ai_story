"""The real server from one unpacked copy, for the web comparison: clock and random frozen, model on a dead port, one staging route.

usage: python -u serve.py <copy root> <port> <db file> [profile]

Exit 3 when something this wrapper patches is gone (the code it patches moves around between waves; a patch that silently
stops applying would turn into noise on every run). gate.py turns that into its exit 2.
"""
import importlib
import os
import random
import sys
import threading
import time
import traceback
import types

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
SEAL_MODULES = ("tianxia.features.seal.seal", "tianxia.seal")


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
if missing:
    print("webqa: patch targets gone:", ", ".join(missing), flush=True)
    sys.exit(3)

assert server.CONTENT.config.ollama_url == "http://127.0.0.1:9", server.CONTENT.config.ollama_url
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
WRITERS = ("xingshi", "event-flavor", "battle-tales", "arena-crowd", "letter", "yuedan")


def _writers_done(seconds: float = 8.0) -> None:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline and any(t.name in WRITERS and t.is_alive() for t in threading.enumerate()):
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
