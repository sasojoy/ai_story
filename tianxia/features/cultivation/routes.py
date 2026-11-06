"""修練的動作表（功能包 tianxia/features/cultivation/；原本寫在 server.py 的 MAIN_ACTIONS、MENXIA_ACTIONS，全部拆包第 68 批）：殼照 FEATURES 接（main_actions、menxia_actions 掛鉤）。
這個檔只在殼建動作表時才 import（__init__ 的掛鉤裡面才 from . import routes）；殼的東西一律照 shell.<名字> 當下讀（測試換掉的也看得到）。
破境卡那一句（/api/do/ascend_line）是鎖外三段式，留在殼。_int_of、_id_list、KINDS 留在殼（裝備包、殼也用）。"""
from tianxia.core.features import Outlock

from . import actions, ascend


def main_actions(shell) -> dict:
    return {
        "allocate": lambda g, b: actions.allocate_stat(g, str(b.get("stat", ""))),  # 狀態列的配點鈕：升級得到的屬性點加到一項
    }


def menxia_actions(shell) -> dict:
    return {
        "practice": lambda g, b: actions.practice(g, str(b.get("kind") or shell.KINDS[0])),
        "switch": lambda g, b: actions.switch_art(g, str(b.get("art") or "")),
        # 武學重構：把意境裝進武學的意境槽、或拆下來（修練頁與煉製頁都走這裡；不花心得體力）
        "slot": lambda g, b: actions.slot_insight(
            g, str(b.get("art") or ""), str(b.get("insight") or ""), shell._int_of(b.get("index")) if b.get("index") is not None else None,
        ),
        "unslot": lambda g, b: actions.unslot_insight(g, str(b.get("art") or ""), str(b.get("insight") or "")),
        "ascend_dismiss": lambda g, b: actions.ascend_dismiss(g),  # 看過破境卡了
        # 用融的意境修練一次，衝下一品；use_legend 是勾了「服下破境丹」。只認真正的布林 true：字串、數字都不算勾
        "cultivate": lambda g, b: actions.cultivate(g, str(b.get("art") or ""), use_legend=b.get("use_legend") is True),
        "melt": lambda g, b: actions.melt_art(g, str(b.get("art") or "")),  # 功法庫裡的一門熔成心得
        "melt_insight": lambda g, b: actions.melt_insight(g, str(b.get("insight") or "")),
        # 批量熔煉：勾好的武學（arts）與意境（insights）一次熔完；不是串列的當沒勾
        "melt_many": lambda g, b: actions.melt_many(g, shell._id_list(b.get("arts")), shell._id_list(b.get("insights"))),
        "name": lambda g, b: actions.name_mastered(g, str(b.get("name") or "")),  # 第一個練成絕學的人替它取正式名字
        # 傳功門下（Config.chuangong）：名冊上點的那個人（person）練一項（what：neigong／wugong／str／agi／con）；引擎照 lessons 驗
        "chuangong": lambda g, b: actions.chuangong(g, str(b.get("person") or ""), str(b.get("what") or "")),
    }


# ── 鎖外工作（原本寫在 server.py，全部拆包第 69 批）：殼的東西一律照 shell.<名字> 當下讀（測試換掉的也看得到）；模型呼叫絕不進鎖 ──


def outlock(shell) -> Outlock:
    return Outlock(ops={
        "ascend_line": lambda g, b: ascend_line(shell, g),  # 破境卡那一句：模型在行動鎖外寫（見 ascend_line）
    })


def ascend_line(shell, game) -> list[str]:
    """破境卡那一句（tianxia/ascend.py），三段同 create_intent：A Game.ascend_request（只讀）→ B 鎖外 ascend.read
    （預算同隨口應對）→ C Game.ascend_line 存回卡上（卡換了就不存）。叫不動照套句。"""
    started, request = shell._open_request(game, game.ascend_request)
    if request is None:
        return []
    total = game.content.config.free_text_budget_seconds

    def writing():
        return ascend.read(shell.within_budget(game.client, total - (shell._monotonic() - started)), request)

    value = shell.model_call(game, writing, fallback=ascend.fallback(request), left=total - (shell._monotonic() - started), busy=shell.BUSY_FREE_TEXT)
    return shell.act(game, lambda g: g.ascend_line(request, value))
