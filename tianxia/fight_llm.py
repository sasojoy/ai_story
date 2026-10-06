"""大場面請模型判讀戰局（武學與成長設計 8.3）。

模型只給兩樣：「優勢」（把勝算往上或往下推的百分點，夾在 ±swing）與佔上風、落下風兩版過程；
擲骰、損耗、獎勵都由規則引擎。叫不動、太慢、回得不合格式，一律回 None，呼叫端照平常的回合演出。
這個模組不碰遊戲狀態、不讀時鐘：備料（引擎、鎖內，Game.fight_request）→ 問模型（伺服器、鎖外，judge）→
套用（引擎、鎖內重驗，Game.choose(fight=...)）。鎖外這一段的總時間用 budget（秒）管，跟開爐取名同一套分法
（naming.propose）；預算由呼叫端（server.prepare_fight）算好傳進來。
"""
from __future__ import annotations

import re

from pydantic import BaseModel

from . import zh
from .martial_arts import MartialArt
from .naming import per_post_seconds
from .ollama_client import OllamaClient, capped

TEXT_MAX = 200  # 每一版過程最多幾個字


class FightRequest(BaseModel):
    """鎖內備好、送去問模型的單子；套用時引擎重算一張、要一模一樣才採用（Game._checked_fight）。
    不記賽季時間：模型要想一分鐘，這段時間誰同步一次賽季時鐘就會走，記了判讀就永遠套不上；改記戰報流水號
    （打過一場就變、等模型的時候不會變）與眼前的事件（計畫三 G1）。"""

    option_id: str
    squad_id: str
    location: str
    battle_seq: int  # 開單時的戰報流水號（GameState.battle_seq）
    event: str | None  # 開單時眼前的事件（GameState.pending_event）；遊歷、挑戰本人是 None
    ours: list[str]  # 我方每人一行：名字、武學與內功（名字、品質、屬性、正邪、說明）；部下也上陣
    theirs: str  # 對手一行：名字、屬性、難度（挑戰本人照他此刻的聲威）、有來歷的再接一句描述


class Judgment(BaseModel):
    advantage: int = 0
    winning: str = ""
    losing: str = ""


class PreparedFight(BaseModel):
    """鎖外走完的大場面：備料時的單子，加上模型的判讀。判讀是 None＝模型叫不動、太慢（照平常打，優勢 0）；單子照樣帶著，
    套用時這個選項已經不在了（等判讀的時候別的分頁把人帶走），引擎才說得出是哪一仗沒打成（Game._fight_gone）。"""

    request: FightRequest
    judgment: Judgment | None = None


def member_line(name: str, arts: list[MartialArt | None]) -> str:
    """陣容裡一個人的一行，例如「沈浪：武學【旋風腿】中品・屬快・正派——身法輕靈，專打破綻」；一門都沒有是「赤手空拳」。"""
    described = "、".join(
        f"{a.kind}【{a.name}】{a.quality}・屬{a.attribute}" + (f"・{a.lean}派" if a.lean != "無" else "")
        + (f"——{a.note}" if a.note else "")
        for a in arts if a is not None
    )
    return f"{name}：{described or '赤手空拳'}"


SYSTEM = (
    "你是武俠小說裡的說書人，也是看招的行家。給你雙方的陣容，你判斷哪一方佔優勢、寫兩版過程。"
    "判斷只看招式路數、屬性相剋、說明裡的打法對不對路；名字取得多威風一概不算。"
    "全程使用繁體中文。"
)


def _messages(request: FightRequest, swing: int) -> list[dict[str, str]]:
    ours = "\n".join(request.ours)
    return [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": (
            f"我方：\n{ours}\n對手：{request.theirs}\n\n"
            f"advantage：整數，-{swing} 到 {swing}。正數是我方佔優勢，0 是勢均力敵。\n"
            f"winning：我方最後佔上風的過程，三句以內、{TEXT_MAX} 字以內，不要寫任何數字。\n"
            f"losing：我方最後落下風的過程，三句以內、{TEXT_MAX} 字以內，不要寫任何數字。"
        )},
    ]


SENTENCE_END = re.compile(r"[。！？][」』”）]*")  # 一句話的結尾，連同緊跟著的收尾引號、括號
# 這一段話會被伺服器的 Markdown 轉成 HTML（接在「**過程**」下一行）：這些 ASCII 字元會變成連結、圖片、程式碼區塊、引言、
# 強調、表格，中文敘事一個都用不到（中文標點、全形括號與引號不在內）。模型的字是不可信的輸入（Final review Minor 1）
MARKDOWN_SYNTAX = re.compile(r"[`*_#>\[\]|~<\\]")
RULE_RUN = re.compile(r"^[-+=]+")  # 整段只有 --- 或 === 會變成上一行「**過程**」的標題底線；開頭的 -、+ 一併拿掉


def _account(text) -> str:
    """一版過程：轉成繁體（模型常夾簡體字）、拿掉換行與空白收成一段（卡片上「過程」底下就是一段話）、拿掉 Markdown 語法字元
    （一律是純文字一段，不會冒出連結、圖片、程式碼區塊）、最多 TEXT_MAX 個字。
    太長就退回 TEXT_MAX 以內最後一句話的結尾（「。！？」，後面緊跟的收尾引號一起留），不從句子中間斷；沒有句號才硬切。"""
    text = RULE_RUN.sub("", MARKDOWN_SYNTAX.sub("", zh.to_traditional("".join(str(text or "").split()))))
    if len(text) <= TEXT_MAX:
        return text
    cut = text[:TEXT_MAX]
    ends = [m.end() for m in SENTENCE_END.finditer(cut)]
    return cut[:ends[-1]] if ends else cut


def judge(
    client: OllamaClient | None, request: FightRequest, swing: int, budget: float | None = None,
) -> Judgment | None:
    """B 段（鎖外、很慢）：拿單子問模型，回傳夾好的判讀；叫不動（連不上、逾時、格式不對、預算不夠）回 None。
    client 是 None（伺服器假人）不叫。

    budget（秒）：這一次最多花多久（沒給就照 client 自己的 timeout）。chat_structured 一次最多送兩趟（第一趟＋重問），
    所以拿 client 的複本、timeout 設成 min(client.timeout, budget ÷ 兩趟)，分不到 MIN_POST_SECONDS 就不叫了；原本那個
    client 不動（同一個角色別的請求可能正在用它）。跟 naming.propose 同一套分法。

    必填的只有兩版過程：chat_structured 把必填欄位的空值當成「回答被截斷」，advantage 0（勢均力敵）是合法的判讀，
    放進必填會被當成截斷、重問之後丟掉（計畫三 G2）；沒寫就是 0。優勢不是數字也當 0、超出範圍夾在 ±swing
    （Review Focus 4：模型不能直接決定勝負）。"""
    if client is None:
        return None
    caller = client
    if budget is not None:
        per_post = per_post_seconds(client, budget)
        if per_post is None:
            return None
        caller = capped(client, per_post)
    try:
        reply = caller.chat_structured(
            _messages(request, swing), Judgment, temperature=0.4, required_fields=["winning", "losing"],
        )
    except Exception:  # noqa: BLE001  連不上、逾時、格式不對——一律當作這次沒有判讀
        return None
    if reply is None:
        return None
    try:
        advantage = int(reply.advantage)
    except (TypeError, ValueError, OverflowError):
        advantage = 0
    return Judgment(
        advantage=max(-swing, min(swing, advantage)), winning=_account(reply.winning), losing=_account(reply.losing),
    )
