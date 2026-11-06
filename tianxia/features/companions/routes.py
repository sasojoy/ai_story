"""人物情誼的 API（功能包 tianxia/features/companions/；原本寫在 server.py，開發規範手冊 3.2）：殼（server 模組，參數 shell）照 FEATURES 掛。
這個檔只在殼掛路由時才 import（引擎與假人程式不碰網頁框架）；殼的東西一律照 shell.<名字> 當下讀（測試換掉的也看得到）。
書信小卡、名冊的動作表（原本寫在 server.py 的 MAIN_ACTIONS、MENXIA_ACTIONS，全部拆包第 68 批）：殼照 FEATURES 接（main_actions、menxia_actions 掛鉤）；名冊的核對（join、leave、release 在鎖裡先查名冊）與勸降的鎖外三段式留在殼。
not_while_preparing 原本掛在 Game 的委派上、包裡的函式沒有：表不再經過委派，所以名冊那三條的擋法掛在表上（同一支裝飾器，包裡的函式不動）。"""
from fastapi import APIRouter, Request

from tianxia.core.features import Outlock, OutlockJob
from tianxia.core.services import not_while_preparing

from . import actions, letters, talk_log


def main_actions(shell) -> dict:
    return {
        "letter_read": lambda g, b: actions.read_letter(g, shell._int(b.get("id"), -1)),  # 書信小卡的「收起」（大勢人物擴充第二批）
        "letter_decline": lambda g, b: actions.decline_letter(g, shell._int(b.get("id"), -1)),  # 書信小卡的「婉拒」：委託作罷
    }


def menxia_actions(shell) -> dict:
    return {
        "join": not_while_preparing(lambda g, b: actions.add_to_team(g, str(b.get("person") or ""))),
        "leave": not_while_preparing(lambda g, b: actions.remove_from_team(g, str(b.get("person") or ""))),
        "release": not_while_preparing(lambda g, b: actions.release_companion(g, str(b.get("person") or ""))),  # 放他回江湖（歷史武將同行）：引擎驗是不是你名下的
    }


def router(shell) -> APIRouter:
    r = APIRouter()

    @r.get("/api/figure")
    def api_figure(request: Request, id: str = ""):
        """人物頁（減法季批 6，主機側計畫 1.3 的 figure.stances、figure.errands）：這位人物（對話人物 id）的心意條、你今天記的那一筆、
        他託你的事（actions.figure_view）。關著、他什麼都沒有是 None。只讀。"""
        game = shell._game(request)
        return {"figure": shell.look(game, lambda g: actions.figure_view(g, str(id)[:40]))}

    @r.get("/api/talk_log")
    def api_talk_log(request: Request, id: str = "", season: str = "now", before: int = 0):
        """往來紀錄（介面重整 2026-11-05）：你跟這位人物這一季（season=now）或上一季（prev）說過的話，新的在前、一次 talk_log.PAGE 句；
        before 是上一頁最舊那一句的 id。情誼的增減照同一位人物前一句記下的情誼算。只讀，不拿行動鎖（讀的是旁邊的小檔與角色的名號）。"""
        game = shell._game(request)
        cid = str(id)[:40]
        ch = game.content.characters.get(cid)
        if ch is None:
            return {"lines": [], "more": False}
        p = game.state.player
        number = p.season_number - (1 if season == "prev" else 0)
        store = shell.talk_store()
        rows, more = store.page(shell.name_key(p.name), cid, number, before or None, talk_log.PAGE + 1)
        lines = []
        for i, row in enumerate(rows[:talk_log.PAGE]):
            said = rows[i + 1] if i + 1 < len(rows) and rows[i + 1]["role"] == "user" else None  # 同一輪玩家那一句記的是動作前的情誼
            gain = row["affinity"] - said["affinity"] if said is not None and row["role"] == "assistant" else 0
            lines.append({"id": row["id"], "stamp": row["stamp"], "place": row["place"], "role": row["role"], "text": row["text"], "gain": gain})
        return {"id": cid, "name": ch.name, "face": shell.figure_face(cid), "affinity": p.affinities.get(cid, 0),
                "meets": store.meets(shell.name_key(p.name), cid), "lines": lines, "more": more or len(rows) > talk_log.PAGE}

    return r


# ── 鎖外工作（原本寫在 server.py，全部拆包第 69 批）：殼的東西一律照 shell.<名字> 當下讀（測試換掉的也看得到）；模型呼叫絕不進鎖 ──


def outlock(shell) -> Outlock:
    return Outlock(jobs=(
        OutlockJob("letter", lambda game: _letter_waiting(shell, game), lambda game, got: write_letter(shell, game)),
    ))


LETTER_RUNNING: set[str] = set()  # 正在背景重寫書信的角色（一人一條；名號）


def _letter_waiting(shell, game) -> bool:
    """有一封信等著模型照他的口氣重寫、模型叫得到、這個人還沒有一條在寫（write_letter）。行動鎖內叫。"""
    if not shell.TALE_THREADS or game.client is None or game.state.player.name in LETTER_RUNNING:
        return False
    return game.letter_request() is not None


def write_letter(shell, game) -> bool:
    """書信（大勢人物擴充第二批，letters.py）：開一個背景執行緒重寫。A 鎖內拿單子（Game.letter_request）→ B 鎖外請模型寫
    （letters.write，預算 Config.figure_life.letter_write_budget_seconds；排隊時當假人排、排在真人後面）→ C 鎖內重驗同一封才換
    （Game.apply_letter；寫不出來照固定句）。開了回 True。呼叫端不能握著行動鎖。"""
    name = game.state.player.name
    with shell.TALE_LOCK:
        if name in LETTER_RUNNING:
            return False
        LETTER_RUNNING.add(name)

    def job() -> None:
        try:
            shell.letter_once(game)
        except Exception:  # noqa: BLE001 — 背景執行緒：印出來就好，信照固定句
            shell.traceback.print_exc()
        finally:
            with shell.TALE_LOCK:
                LETTER_RUNNING.discard(name)

    shell.threading.Thread(target=job, name="letter", daemon=True).start()
    return True


def letter_once(shell, game) -> bool:
    """重寫一封（write_letter 的那一圈；測試直接叫）：換了回 True。呼叫端不能握著行動鎖。"""
    with shell._locked(game):
        note = game.letter_request()
    if note is None:
        return False
    budget = game.content.config.figure_life.letter_write_budget_seconds
    started = shell._monotonic()

    def ask() -> str:
        return letters.write(shell.within_budget(game.client, budget - (shell._monotonic() - started)), note)

    if shell.QUEUE is None:
        text = ask()
    else:
        try:
            text = shell.QUEUE.run(game.state.player.name, ask, fallback="", bot=True, wait=budget)
        except (shell.Busy, shell.QueueTimeout):
            text = ""
    with shell._locked(game):
        done = game.apply_letter(note, text)
        shell.open_characters().save(game.state)
    return done
