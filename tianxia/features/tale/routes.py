"""戰記的 API 與 server.py 原本的戰記那一段（功能包 tianxia/features/tale/；全部拆包第 52 批照商城的做法搬進來）：殼（server 模組，參數 shell）照 FEATURES 掛
路由（server 的 features_core.routers 那一行；兩條路徑與別的路由不重疊，先後不影響），殼留 8 個一行薄包裝（act、look、main_view 原位叫，測試與 same_behavior 從 server. 叫）。
這個檔只在殼掛路由時才 import（引擎與假人程式不碰網頁框架）。殼的東西一律照 shell.<名字> 當下讀、當下寫（測試換掉的也看得到），state 的宣告留在殼（TALES、TALES_STOP、
TALES_THREAD、TALE_RUNNING……tests/conftest.py 收尾認這幾個名字）；這一包的函式互叫也經 shell.<名字>，同搬之前的模組層查找。
tests/server/test_server.py 的 _users_in_server("QUEUE") 掃這個檔看 narrate_once、tale_round 這兩個函式名：裡面寫 shell.QUEUE，不要先存成別的變數。"""
from __future__ import annotations

import threading
import traceback
from collections.abc import Callable
from pathlib import Path

from fastapi import APIRouter, Query, Request
from fastapi.responses import HTMLResponse

from tianxia.core import battle_base
from tianxia.core.features import Outlock, OutlockJob

from . import tale, tale_html


def outlock(shell) -> Outlock:
    """決戰放手一搏的劇情（narrate_battle）：動作之後看一眼、放鎖才開。定時背景的 tale_round 不在這裡，照舊走 threads 掛鉤（全部拆包第 69 批）。"""
    return Outlock(jobs=(
        OutlockJob("tale", lambda game: shell._tales_waiting(game), lambda game, got: shell.narrate_battle(game)),
    ))


def _tales_waiting(shell, game) -> bool:
    """這一場有等著補劇情的放手一搏、模型叫得到、還沒有一條在寫（narrate_battle）。行動鎖內叫：回合可能在任何人的動作、
    假人程式、逾時的追趕裡結算，所以每一個動作與輪詢之後都看一眼。"""
    if not shell.TALE_THREADS or game.client is None or shell.TALE_RUNNING:
        return False
    return any(battle.tales for battle in game._tale_battles())  # 決戰與攻城戰（領地爭奪第二批）


# 決戰放手一搏的劇情（Joy 2026-10-13「應該要做到能承受」）：評分只回成功率，劇情等回合結算後一整回合批給模型寫一次。
# 全服同時只有一條在寫（TALE_RUNNING）；佇列開著時排在真人的評分後面（當成假人排，名號是 TALE_OWNER，不是任何一個角色）。
def narrate_battle(shell, game) -> bool:
    """這一場有等著補劇情的放手一搏、而且還沒有一條在寫：開一個背景執行緒寫最早那一回合的一批。開了回 True。
    A 鎖內開單（Game.battle_tale_request）→ B 鎖外一整批請模型寫（Game.write_battle_tales，本體在決戰包的 instance.write_tales，預算 battle_tale_budget_seconds）
    → C 鎖內重驗同一場才補（Game.apply_battle_tales；寫不出來的照固定句、不重寫）。呼叫端不能握著行動鎖。"""
    with shell.TALE_LOCK:
        if shell.TALE_RUNNING:
            return False
        shell.TALE_RUNNING = True

    def tale_job() -> None:
        try:
            while shell.narrate_once(game) is not None:  # 一批寫完還有（下一回合也結算了）就接著寫
                pass
        except Exception:  # noqa: BLE001 — 背景執行緒：印出來就好，那幾搏照固定句
            traceback.print_exc()
        finally:
            with shell.TALE_LOCK:
                shell.TALE_RUNNING = False

    threading.Thread(target=tale_job, name="battle-tales", daemon=True).start()
    return True


def narrate_once(shell, game) -> int | None:
    """寫一批（narrate_battle 的一圈）：沒有等著補的回 None，寫了回補上幾句。呼叫端不能握著行動鎖。"""
    with shell._locked(game):
        request = game.battle_tale_request()
    if request is None:
        return None
    definition = shell.CONTENT.battles.get(request.battle_id) or game.content.battles.get(request.battle_id)
    act_ = definition.acts[request.act_index]
    budget = game.content.config.battle_tale_budget_seconds
    started = shell._monotonic()

    def ask() -> dict[str, str]:
        client = shell.within_budget(game.client, budget - (shell._monotonic() - started))
        sides = [f.name for f in definition.factions]  # 兩軍的名字：失手那一句不准寫敵方受損（守門用）
        # fallen 是引擎這一回合真的放倒的人：寫到死人的那一句要指名他們其中一位才算數（守門用）
        return game.write_battle_tales(client, act_, request.items, sides=sides, fallen=request.fallen)

    if shell.QUEUE is None:
        stories = ask()
    else:
        try:  # 排在真人的評分後面（當成假人排）；排不到就照固定句
            stories = shell.QUEUE.run(shell.TALE_OWNER, ask, fallback={}, bot=True, wait=min(budget, 120))
        except shell.Busy:
            stories = {}
    with shell._locked(game):  # 補上了，等著補的單子就少了：推送的指紋跟著變，開著的分頁會更新
        return game.apply_battle_tales(request, stories)


# ── 戰記（Joy 2026-10-29，原稱戰役話本）：決戰收場那一刻在背景寫、全服一份，戰報頁「戰記 ›」與戰記頁讀它 ──
# 介面（主機那邊照同一份寫）：{status: "ready"|"pending"|"none", title, season, battle_name, result,
#   acts: [{title, banner?, scenes: [{head, text, said?: {who, side, line}}]}], cast: [{name, side?, line}], made_at}
# 寫法、產生、存放在 tale.py 與下面這一段：收場之後由背景執行緒（tale_round）一篇一篇寫，
# 存進資料庫旁邊的小檔 <db>-tale.sqlite（不動 SCHEMA_VERSION）。模型叫不動就存引擎自己拼的那一版（tale.plain），
# 所以「史官還在落筆」只會是「還沒輪到它寫」，不會永遠卡著。
def tale_view(shell, battle_id: int, request: Request | None = None) -> dict:
    """一場的戰記：寫好了回整篇（ready）；是決戰、收場了、還沒寫好回 pending；其餘（不是決戰、沒這場、還沒接上）回 none。
    寫好了另外帶分享網址（url，/zhanji/<代碼>）與遊戲裡那一層要開的頁（page，同一頁加 ?in=1；戰記分享頁，Joy 2026-11-04）。"""
    store = shell.TALES
    if store is None:
        return {"status": "none"}
    written = store.get(battle_id)
    if written is not None:
        view = written.model_dump()
        code = store.share_code(battle_id)
        view["page"] = f"/zhanji/{code}?in=1"
        if request is not None:
            view["url"] = f"{shell.public_base(request)}/zhanji/{code}"
        return view
    return {"status": "pending"} if _tale_due(shell, battle_id) else {"status": "none"}


# 戰記頁的封面（web/img/tale/，資料夾 TALE_COVER_DIR 留在殼：測試換它）：那一場自己的圖 > 攻城共用一張 > 那一區的地點圖 > 事件插圖 tale（企劃者的圖還沒到時用）
TALE_SIEGE_COVER = "siege"
TALE_DEFAULT_COVER = "default"
TALE_COVER_ALIAS = {"wancheng_jia": "wancheng", "wancheng_yi": "wancheng"}  # 宛城兩場（甲、乙）共用一張
TALE_LEAD_MAX = 80  # 分享預覽的摘要最多幾個字


def tale_cover(shell, definition) -> str:
    """封面圖的網址（/static/...）；圖檔真的在才給那一張，照上面的順序往下找。"""
    keys = [TALE_COVER_ALIAS.get(definition.id, definition.id)] if definition is not None else []
    if definition is not None and definition.id.startswith("siege_"):
        keys.append(TALE_SIEGE_COVER)
    keys.append(TALE_DEFAULT_COVER)
    for key in keys:
        if (shell.TALE_COVER_DIR / f"{key}.webp").is_file():
            return f"/static/img/tale/{key}.webp"
    region = getattr(definition, "region", None) if definition is not None else None
    if region and (shell.WEB / "img" / "places" / f"{region}.webp").is_file():
        return f"/static/img/places/{region}.webp"
    return "/static/img/events/tale.webp"


def tale_page_view(shell, record_id: int, written: tale.Tale) -> dict:
    """戰記頁（tale_html.page）要的那一份：整篇加上封面、抬頭、兩邊（名字與顏色）、在場幾人、分享預覽的摘要。只讀。"""
    battle = shell.open_world().ended_battle(record_id)
    definition = shell.CONTENT.battles.get(battle.battle_id) if battle is not None else None
    view = written.model_dump()
    names = battle_base.side_names(battle, definition) if battle is not None and definition is not None else {}
    view["sides"] = [{"name": name, "cls": tale_html.SIDE_CLASS.get(side, "")} for side, name in names.items()]
    view["present"] = len(battle.participants) if battle is not None else 0
    view["title"] = written.title or f"{written.battle_name}{tale.TITLE_SUFFIX}"
    view["kicker"] = f"天下大勢・第 {written.season} 季・{shell.CONTENT.scenario.name}"
    view["stamp"] = written.result
    view["sub"] = battle.outcome_reason if battle is not None and battle.outcome_reason else ""
    first = next((sc.text for a in written.acts for sc in a.scenes if sc.text.strip()), "")
    line = first.strip().split("\n", 1)[0]
    view["lead"] = line if len(line) <= TALE_LEAD_MAX else line[: TALE_LEAD_MAX - 1] + "…"
    view["cover"] = shell.tale_cover(definition)
    return view


def _tale_due(shell, record_id: int) -> bool:
    """這一場該有戰記：收場的決戰，有結果（季終沒打完的 unfinished 沒有結果，不寫）。"""
    battle = shell.open_world().ended_battle(record_id)
    return battle is not None and not battle.unfinished and bool(battle.outcome_title)


def tale_index(shell, game) -> list[dict]:
    """江湖史的戰記目錄（新的在前）：開關關著、或主機還沒接上都是空的。"""
    if not shell.TALES_IN_CHRONICLE or shell.TALES is None:
        return []
    return [{"battle_id": record_id, "title": written.battle_name, "season": written.season, "result": written.result}
            for record_id, written in shell.TALES.listing(game.world.get_season_number())]


# ── 戰記怎麼寫出來：全服一條背景執行緒（start_tales，main() 經 threads 掛鉤開），每 TALE_ROUND_SECONDS 秒看一次這一季有沒有收場了
# 卻還沒有戰記的決戰，有就寫一篇。不拿行動鎖（只讀收場的那一場與它的回合、寫旁邊的小檔），模型呼叫排在真人後面
# （佇列開著時當假人排）；省電模式下沒有真人來過就不叫，不把模型載回 VRAM（同旁白改寫）。
TALE_ROUND_SECONDS = 30.0  # 看一次的間隔（一季頂多十來場，寫完就閒著）
# 一篇的模型預算。2026-11-04 改成一幕一趟之後實測（第 8 季廣宗，3 幕 17 拍＋8 人的名錄，gemma4:12b）：
# 四趟共 227 秒，180 秒會在名錄那一趟前就用完、名錄整段退回引擎那幾句。單趟還是最多 120 秒
# （within_budget 取 min(client.timeout, 剩下的一半)），所以真人要等的上限沒變。
TALE_BUDGET_SECONDS = 420.0
TALE_OWNER_KEY = "戰記"  # 佇列裡的名號（不是任何角色）


def tale_store_path(shell) -> Path:
    db = shell.default_path()
    return db.with_name(f"{db.stem}-tale.sqlite")


def start_tales(shell, config, client=None) -> threading.Thread | None:
    """建 TALES（小檔不管叫不叫得動模型都建：讀的一邊才有東西可查）、開背景執行緒（daemon）。只有 main() 與測試呼叫。"""
    shell.TALES = tale.TaleStore(tale_store_path(shell))
    if client is None:
        try:
            client = shell.OllamaClient.from_config(config)
        except Exception:  # noqa: BLE001  建不起 client：照模板寫，不擋伺服器
            client = None
    shell.TALES_CLIENT = client
    failures = shell._StepFailures(shell.time.monotonic, "戰記")

    def loop() -> None:
        while not shell.TALES_STOP.wait(TALE_ROUND_SECONDS):
            try:
                shell.tale_round()
            except Exception as e:  # noqa: BLE001  一篇出錯不能讓整條停下來
                failures.failed(e)
            failures.tick()

    shell.TALES_THREAD = threading.Thread(target=loop, daemon=True, name="tales")
    shell.TALES_THREAD.start()
    return shell.TALES_THREAD


def tale_material(shell, world, battle) -> tale.Material | None:
    """把收場的一場決戰整理成寫戰記的料（只讀）。內容裡沒有這一場（換過內容的舊季）是 None。"""
    definition = shell.CONTENT.battles.get(battle.battle_id)
    if definition is None or battle.record_id is None:
        return None
    return tale.gather(
        definition, battle, world.battle_rounds(battle.record_id),
        season=world.get_season_number(), side_names=battle_base.side_names(battle, definition),
    )


def tale_round(shell, clock: Callable[[], float]) -> int | None:
    """寫一篇（背景執行緒的一輪；測試直接叫）：這一季收場了、還沒有戰記的決戰挑最新的一場寫。回傳寫好的流水號，
    沒做事是 None。模型叫不動、寫壞就存模板版（照引擎自己那幾句），不留著讓玩家一直看「史官還在落筆」。
    呼叫端不能握著行動鎖。預設的 clock（time.time）寫在殼的那一行包裝上。"""
    store = shell.TALES
    if store is None:
        return None
    if shell.power_save.on() and clock() - shell.LAST_HUMAN > shell.ONLINE_SECONDS:
        return None  # 省電模式、沒人在線：等有人來再寫
    world = shell.open_world()
    if world.season_phase() != "running":
        return None
    season = world.get_season_number()
    done = store.done(season)
    todo = [b for b in world.season_ended_battles(season)
            if b.record_id is not None and b.record_id not in done and not b.unfinished and b.outcome_title]
    if not todo:
        return None
    battle = todo[-1]  # 最新的那一場先（玩家剛打完就在等它）
    material = tale_material(shell, world, battle)
    if material is None:
        return None
    budget, started = TALE_BUDGET_SECONDS, shell._monotonic()

    def fresh():  # 一幕一趟：每一趟照「還剩多少」重算預算，用完回 None（剩下的幕照引擎那一句，不是整篇垮掉）
        return shell.within_budget(shell.TALES_CLIENT, budget - (shell._monotonic() - started))

    def ask() -> tuple[dict, dict]:
        return tale.write(fresh(), material, next_client=fresh)

    if shell.QUEUE is None:
        scenes, cast = ask()
    else:
        try:  # 排在真人後面（當成假人排）；排不到這一輪就算了，下一輪再寫
            scenes, cast = shell.QUEUE.run(TALE_OWNER_KEY, ask, fallback=({}, {}), bot=True, wait=min(budget, 120))
        except shell.Busy:
            return None
    store.put(material.record_id, tale.compose(material, scenes, cast, made_at=clock()))
    return material.record_id


def router(shell) -> APIRouter:
    r = APIRouter()

    @r.get("/zhanji/{code}")
    def tale_page(code: str, request: Request, embedded: str | None = Query(default=None, alias="in")):
        """戰記頁（不用登入、唯讀；Joy 2026-11-04）：只認發出去的分享代碼，其餘一律 404。帶 Open Graph，貼到 LINE、FB 有預覽；
        ?in=1 是遊戲裡戰報頁疊的那一層（頂條換成「‹ 返回」、不畫招攬）。"""
        store = shell.TALES
        record_id = store.record_for(code) if store is not None else None
        written = store.get(record_id) if record_id is not None else None
        if written is None:
            return HTMLResponse(tale_html.missing(), status_code=404)
        base = shell.public_base(request)
        view = tale_page_view(shell, record_id, written)
        return HTMLResponse(tale_html.page(view, url=f"{base}/zhanji/{code}", image=f"{base}{view['cover']}", embedded=embedded == "1"))

    @r.get("/api/tale/{battle_id}")
    def api_tale(request: Request, battle_id: int):
        shell._game(request)  # 要登入，跟戰報一樣
        return shell.tale_view(battle_id, request)

    return r
