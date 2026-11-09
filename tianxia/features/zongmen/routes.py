"""門派的玩家動作（手冊第十五節 G10）：俠客頁門下那一段「師門武譜」的獻式、學式、照殘頁偷學（/api/do/zongmen_offer、zongmen_learn、zongmen_page）。
試練走此地還能做的選項（zongmen:try:…，假人也按得到）。只在殼建動作表時才 import。"""
from tianxia.core.services import not_while_preparing

from . import actions


def main_actions(shell) -> dict:
    return {
        "zongmen_offer": not_while_preparing(lambda g, b: g._log(actions.offer(g, str(b.get("id", ""))))),
        "zongmen_learn": not_while_preparing(lambda g, b: g._log(actions.learn(g, str(b.get("id", ""))))),
        "zongmen_page": not_while_preparing(lambda g, b: g._log(actions.page_learn(g, str(b.get("sect", "")), str(b.get("id", ""))))),
    }
