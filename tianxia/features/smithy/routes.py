"""鐵匠鋪的 API（功能包 tianxia/features/smithy/；原本寫在 server.py，全部拆包第 41 批照煉製頁的做法搬進來）：殼（server 模組，參數 shell）
照 FEATURES 掛（server 的 features_core.routers 那一行；前面沒有吃得到 /api/smith_line 的帶參數路由，先後不影響）。
這個檔只在殼掛路由時才 import（引擎與假人程式不碰網頁框架）；殼的東西一律照 shell.<名字> 當下讀（測試換掉的也看得到）。
動作表（原本寫在 server.py 的 MAIN_ACTIONS、MENXIA_ACTIONS，全部拆包第 68 批）：殼照 FEATURES 接（main_actions、menxia_actions 掛鉤）。not_while_preparing 原本掛在 Game 的委派上、
包裡的函式沒有：表不再經過委派，所以 name_divine、bind_art 的擋法掛在表上那一條（同一支裝飾器，包裡的函式不動）。"""
from fastapi import APIRouter, Body, Request

from tianxia.core.services import not_while_preparing

from . import divine_actions, forge_actions, gear_actions, trade_actions


def main_actions(shell) -> dict:
    return {
        # 店面的直接開爐（店面獨立介面設計 6.3）：打的是同一個 smithing.forge；出爐卡在 game.smith_result，api_do 一起回
        "smith_forge": lambda g, b: forge_actions.smith_forge(g, str(b.get("kind", "")), str(b.get("main", "")), str(b.get("aux", ""))),
        # 鐵匠鋪的素材買賣（素材與經濟設計第四、五節）：收購一次賣 count 個、升階一次換一個
        "smith_sell": lambda g, b: trade_actions.smith_sell(g, str(b.get("material", "")), max(1, shell._int(b.get("count"), 1))),
        # count：一次熬到底（Config.economy.upgrade_batch）連換幾個，沒給是 1（舊網頁一字不變）
        "smith_upgrade": lambda g, b: trade_actions.smith_upgrade(g, str(b.get("attribute", "")), shell._int(b.get("tier"), 0), max(1, shell._int(b.get("count"), 1))),
        # 打造頁爐火上的「看火候」（鐵匠鋪與合成流程 3.2）：叫同一支 silver.furnace；店開著時選單上沒有 act:furnace，所以另開這一個
        "smith_furnace": lambda g, b: forge_actions.smith_furnace(g),
    }


def menxia_actions(shell) -> dict:
    return {
        # 神器原品定名（打造隱藏配方設計 5.2）：自己打的名字，或 keep 是「沿用譜名」；keep 只認真正的布林 true（同 use_legend）
        "name_divine": not_while_preparing(lambda g, b: divine_actions.name_divine(g, str(b.get("weapon") or ""), str(b.get("name") or ""), b.get("keep") is True)),
        "bind_art": not_while_preparing(lambda g, b: divine_actions.bind_art(g, str(b.get("weapon") or ""), str(b.get("art") or ""))),
        # 裝備庫那一列的「修」「淬煉」（鐵匠鋪與合成流程 3.4）：item 是裝備庫那一件的 id（兵:N、甲:N；舊網頁送 weapon 也收），修好淬完還在裝備庫、不換上；
        # 擋法同店裡的直接開爐（鐵匠鋪開著、那一串是眼前的選單）。身上那件照舊送選項 id（smith:repair 等），不走這裡
        "repair_item": lambda g, b: gear_actions.repair_item(g, str(b.get("item") or b.get("weapon") or "")),
        "temper_item": lambda g, b: gear_actions.temper_item(g, str(b.get("item") or b.get("weapon") or "")),
    }


def router(shell) -> APIRouter:
    r = APIRouter()

    @r.post("/api/smith_line")
    def api_smith_line(request: Request, body: dict = Body(default={})):
        """店面打造那一頁：爐裡放了什麼就問這一爐會怎樣（不算行動、不存檔；店面獨立介面設計 6.3）。參數是客戶端寫的，一律轉成字串。"""
        game = shell._game(request)
        kind, main, aux = (str(body.get(key) or "") for key in ("kind", "main", "aux"))
        return shell.look(game, lambda g: g.smith_line(kind, main or None, aux or None))

    return r
