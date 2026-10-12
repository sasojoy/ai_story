"""玩家的性別（PM 2026-10-12 派工，企劃者「創建角色時可以選擇性別」）：稱呼換字的唯一地方。

性別存在 PlayerState.gender（「男」／「女」，舊角色沒這欄就是男），不影響任何數值。別人看得到的文字裡寫到玩家的
第三人稱與稱呼一律從這裡拿：pronoun（他／她）、hero（少俠／女俠）、anon（某位少俠／某位女俠）、address（內容裡寫給
玩家看的「少俠」照性別換）。不要在各處各寫一份「她 if ... else 他」。
只 import 標準庫：誰都能 import 它。"""
from __future__ import annotations

import hashlib

MALE = "男"
FEMALE = "女"
GENDERS = (MALE, FEMALE)

# 假人建立時照這個比例給女性（照真人的比例，真人還沒人選過時用這個）：假人看不出來跟真人有差別（伺服器假人設計）
BOT_FEMALE_SHARE = 0.3


def of(who) -> str:
    """一個人的性別：PlayerState、GameState 或直接給字都行；不認得的一律是男（舊存檔、沒選過）。"""
    player = getattr(who, "player", who)
    value = player if isinstance(player, str) else getattr(player, "gender", MALE)
    return FEMALE if value == FEMALE else MALE


def female(who) -> bool:
    return of(who) == FEMALE


def pronoun(who) -> str:
    """第三人稱：他／她。"""
    return "她" if female(who) else "他"


def hero(who) -> str:
    """江湖上的稱呼：少俠／女俠。"""
    return "女俠" if female(who) else "少俠"


def anon(who) -> str:
    """匿名行走的人在地方傳聞裡的名字（rules.display_name）：某位少俠／某位女俠。"""
    return "某位" + hero(who)


# 內容裡當面叫玩家的稱呼：男 → 女。只放當面叫人的字（「少俠」「賢弟」），寫 NPC 的「女俠」「姑娘」不會被動到（只換一個方向）
ADDRESS = (("少俠", "女俠"), ("賢弟", "賢妹"))


def address(text: str, who) -> str:
    """內容裡寫死給玩家的稱呼照性別換（ADDRESS）：女的「少俠」換成「女俠」、「賢弟」換成「賢妹」；男的原樣。"""
    if not text or not female(who):
        return text
    for male, woman in ADDRESS:
        text = text.replace(male, woman)
    return text


def word(gender: str) -> str:
    """模型提示裡寫的那一句（人物對話、放手一搏、大場面判讀、寫傳）。"""
    return "女子" if gender == FEMALE else "男子"


def who_line(who) -> str:
    """提示裡接在玩家名號後面的括號：「男子」／「女子，當面稱她女俠或姑娘」（人物對話、寫傳）。"""
    return "女子，當面稱她女俠或姑娘，寫她用「她」" if female(who) else "男子"


def prompt_line(who) -> str:
    """給模型的一行：「（某某是女子，旁人稱她女俠、姑娘）」。男的照舊不寫——之前的提示沒寫，模型本來就當男的。"""
    if not female(who):
        return ""
    return "（這位江湖人是女子：稱呼她女俠、姑娘，寫她用「她」，不要寫成男子。）"


def for_bot(name: str, female_share: float = BOT_FEMALE_SHARE) -> str:
    """假人的性別：建立時就定好，照名號雜湊擲（同一個名號每次一樣），比例是 female_share。"""
    roll = int.from_bytes(hashlib.sha256(f"性別|{name}".encode()).digest()[:4], "big") / 2**32
    return FEMALE if roll < max(0.0, min(1.0, female_share)) else MALE
