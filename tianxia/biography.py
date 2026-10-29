"""玩家傳第二批：季末把行狀（tianxia/annals.py）寫成一篇《某某傳》（企劃者 2026-10-12）。

三段式（同開爐取名）：A 鎖內 Game.biography_request 開單（只讀：行狀、身家、那一季的大事）→ B 鎖外 write 請模型寫（不碰狀態）→
C 鎖內 Game.write_biography 重驗再存進 biographies 表。模型寫的文字一律轉繁體、去 markdown，過不了 clean 的檢查（太短、沒寫到名號、
有阿拉伯數字、日文假名）就用 rule_text 照行狀拼一篇（照樣能讀、能分享）。之後可以請史官重寫一次（Config.biography.rewrites）。

文體是史書列傳的半文言：開頭「某某者，……」，分出身與投靠、大戰、與英雄交往、結局四段，最後「評曰」。數字只能是行狀裡的；
名字照行狀寫（其他玩家的名號照遊戲裡的寫）。只讀資料、不 import 引擎。
"""
from __future__ import annotations

import copy
import re
from dataclasses import dataclass, field

from . import gender, zh
from .annals import DUEL, ERRAND, GROUPS, MARK, STANCE, TIER, XINGSHI

MODEL, RULE = "model", "rule"
TITLE = "{name}傳"
_KANA = re.compile(r"[぀-ヿ]")
_MARKUP = re.compile(r"[#*_`>|~]+")


@dataclass(frozen=True)
class BiographyRequest:
    """一篇傳的單子：A 段開、B 段照它寫、C 段比對它還是不是同一份（季別、名號、行狀則數）。"""

    season: int
    name: str
    scenario: str  # 劇本的名字（「黃巾之亂」）
    era_note: str  # 劇本的時代背景（Scenario.era_note）
    profile: dict = field(default_factory=dict)  # annals.profile
    annals: tuple[dict, ...] = ()  # AnnalEntry.model_dump()，照時間先後
    era: tuple[str, ...] = ()  # 那一季的大事（時刻表的公告，沒有就江湖史），最多 ERA_MAX 件
    rewrite: bool = False  # 已經寫過、這是重寫
    sex: str = "男"  # 性別（gender）：傳裡稱他還是她（PM 2026-10-12）
    # 列傳為終點（減法季批 7b-2）：人物評曰的單子（zhuan_end.VerdictJob），C 段每一條接一段「評曰：」；關著的季是空的
    verdicts: tuple = ()


ERA_MAX = 6


def title(name: str) -> str:
    return TITLE.format(name=name)


# ── 事實清單（給模型，也給規則版挑）──────────────────────


def _group(annals: tuple[dict, ...]) -> dict[str, list[dict]]:
    groups: dict[str, list[dict]] = {"deed": [], "showdown": [], "figure": [], "fight": []}
    for e in annals:
        kind = e.get("kind", "deed")
        groups.setdefault(GROUPS.get(kind, kind), []).append(e)  # 起用碎片（annals.SEAL）跟一般的事一起寫
    return groups


def _fact(e: dict) -> str:
    """一則行狀寫成一行事實：「〔時刻・地點〕事實　你說：「…」　對方：…」"""
    where = "・".join(x for x in (e.get("when", ""), e.get("place", "")) if x)
    line = f"〔{where}〕{e.get('text', '')}" if where else e.get("text", "")
    if e.get("quote"):
        line += f"　你說：「{e['quote']}」"
    if e.get("reply"):
        line += f"　回應：{e['reply']}"
    return line


def outline(req: BiographyRequest) -> str:
    """給模型的事實清單：身家一段、那一季的大事一段、行狀照四段分好。"""
    p = req.profile
    who = [f"名號：{req.name}"]
    for label, key in (("陣營", "faction"), ("門派", "sect"), ("江湖名號", "ranger")):
        if p.get(key):
            who.append(f"{label}：{p[key]}")
    if p.get("team"):
        who.append(f"同行的人物：{'、'.join(p['team'])}")
    who.append(f"季終等級：{p.get('level', 1)}；名望：{p.get('fame', 0)}；善名：{p.get('good', 0)}；惡名：{p.get('evil', 0)}")
    if p.get("showdowns"):
        who.append(f"參加全服大戰 {p['showdowns']} 場，其中首功 {p.get('top_merits', 0)} 次")
    if "tier" in p:  # 列傳為終點（減法季批 7b）：季末論功（annals.standing）；關著的季身家沒有這個鍵
        who.append(standing_line(p))
    groups = _group(req.annals)
    parts = [f"【時代】{req.scenario}。{req.era_note}".strip(), "【這一季的大事】\n" + ("\n".join(req.era) or "（無）"), "【身家】\n" + "\n".join(who)]
    for label, key in (("出身與行事", "deed"), ("大戰", "showdown"), ("與英雄交往", "figure"), ("單打獨鬥", "fight")):
        rows = groups.get(key, [])
        parts.append(f"【{label}】\n" + ("\n".join(_fact(e) for e in rows) or "（無）"))
    if groups.get(TIER):  # 季末論功的那一則（annals.TIER）自己一段，排在最後（SYSTEM 多 TIER_RULE：寫在結局那一段的最後）
        parts.append("【季末論功】\n" + "\n".join(_fact(e) for e in groups[TIER]))
    return "\n\n".join(parts)


def standing_line(p: dict) -> str:
    """身家裡季末論功那一行（給模型；數字照寫，提示詞要它換成中文）：有階寫照哪一本、第幾階、稱號、貢獻、名次，沒有階寫貢獻與未入階。"""
    if not p.get("tier"):
        return f"季末論功：貢獻 {p.get('contrib', 0)}，未入階"
    return (f"季末論功：{p.get('tier_side', '')}第{_cn(p['tier'])}階「{p.get('tier_title', '')}」，貢獻 {p.get('contrib', 0)}，"
            f"在 {p.get('final_of', 0)} 人中排第 {p.get('final_rank', 0)}")


def _tiered(req: BiographyRequest) -> bool:
    """這一篇有季末論功（身家有 tier，或行狀有 TIER）：系統提示多一條 TIER_RULE。關著的季兩樣都沒有。"""
    return "tier" in req.profile or any(e.get("kind") == TIER for e in req.annals)


# 列傳為終點（減法季 7e）讀的三類新行狀：人物心意（批 6）、託付辦成（批 6）、出陣約戰（批 3b）。它們早就靠 annals.GROUPS 歸段
# （STANCE、ERRAND 在「與英雄交往」，DUEL 在「單打獨鬥」），outline 與備援文字照一般的事讀得到；7e 多的是兩件：模型的提示多一條
# 怎麼寫（TIES_RULE），備援文字替它們留位子、補主詞與時刻（TIES_LINE）——不然人物交談多、單挑多的人，備援文字只取前幾則、這幾則被擠掉。
# 身家有 contrib（annals.profile 只在 zhuan_end 開著時放）才這麼讀；關著的季（或存起來的舊身家）一個字不變。
TIES = frozenset({STANCE, ERRAND, DUEL})
TIES_LINE = {  # 待 joy 潤：備援文字裡這三類各一句（when 是「第二週，」、name 是名號；「替某某…辦成了」「在某地約戰…」原句沒有主詞）
    STANCE: "{when}{text}",
    ERRAND: "{when}{name}{text}",
    DUEL: "{when}{name}{text}",
}


def _zhuan(req: BiographyRequest) -> bool:
    """列傳為終點開著（身家有 contrib；沒有這個鍵的是關著的季，或 7b 以前存起來的舊身家）。"""
    return "contrib" in req.profile


def _ties(req: BiographyRequest) -> bool:
    """這一篇要照 7e 讀：列傳為終點開著、而且行狀裡真的有那三類。沒有就不多寫一個字。"""
    return _zhuan(req) and any(e.get("kind") in TIES for e in req.annals)


SYSTEM = (
    "你是史官，替一位江湖人物寫列傳。文體仿《三國志》列傳的半文言：文雅、簡潔、讀得懂，不要太艱澀。\n"
    "規矩：\n"
    "1. 開頭第一句寫「{name}者，」，全篇稱{him}為「{name}」。{name}是{word}。\n"
    "2. 分四段：出身與投靠、大戰、與英雄交往、結局；最後另起一段，以「評曰：」開頭，寫兩三句評語。段與段之間空一行。\n"
    "3. 只能寫事實清單裡有的事。不得杜撰事件、人名、地名、官職、數目；清單裡沒有的就略過不寫。\n"
    "4. 數目一律用中文數字寫（例如「三回合」），不得用阿拉伯數字；清單裡沒有的數目不寫。\n"
    "5. {him}說過的話可以照原句引用，寫成「{name}曰：「……」」；人物回的話也可以引。\n"
    "6. 字數視事實多寡，四百到一千五百字。不寫標題、不用任何標記符號、不分點列。只用繁體中文。"
)
# 列傳為終點（減法季批 7b）：有季末論功的那一篇多這一條（_tiered）；關著的季系統提示一個字不變
TIER_RULE = "\n7. 季末論功的名次與第幾階，寫在結局那一段的最後。"
# 減法季 7e：清單裡有人物心意、受託辦事、約戰（TIES）的那一篇多這一條（_ties；待 joy 潤）。條號接在前面的後面（有 TIER_RULE 是 8，沒有是 7）
TIES_RULE = ("\n{n}. 清單裡若有人物心意、受託辦事、出陣約戰這幾類事，各用一兩句帶過，放進與英雄交往或結局那一段。"
             "人物心意是眾人合力勸成的，只能寫{name}也在其中，不可寫成{him}一人改了人物的主意；約戰的勝負只用清單裡的字，對手是誰照清單寫。")


def messages(req: BiographyRequest) -> list[dict[str, str]]:
    ask = f"請替「{req.name}」寫列傳。以下是事實清單：\n\n{outline(req)}"
    if req.rewrite:
        ask += "\n\n（這是重寫：換一種起筆與剪裁。）"
    him = gender.pronoun(req.sex)
    system = SYSTEM.format(name=req.name, him=him, word=gender.word(req.sex)) + (TIER_RULE if _tiered(req) else "")
    if _ties(req):
        system += TIES_RULE.format(n=8 if _tiered(req) else 7, name=req.name, him=him)
    return [{"role": "system", "content": system}, {"role": "user", "content": ask}]


def clean(raw: str | None, req: BiographyRequest) -> str | None:
    """模型寫的整理成可以存的全文：轉繁體、去標記、段落之間一個空行。過不了（太短、太長、沒寫到名號、有阿拉伯數字或假名）回 None。"""
    if not raw:
        return None
    text = zh.to_traditional(str(raw))
    text = _MARKUP.sub("", text)
    paras = [" ".join(line.split()) for line in re.split(r"\n\s*\n|\n", text)]
    paras = [x for x in paras if x and x not in (title(req.name), f"《{title(req.name)}》")]
    text = "\n\n".join(paras)
    if not (200 <= len(text) <= 3000) or req.name not in text or re.search(r"[0-9０-９]", text) or _KANA.search(text):
        return None
    return text


def write(client, req: BiographyRequest, seconds: float) -> str | None:
    """B 段（行動鎖外）：請模型寫，拿不到或過不了 clean 就是 None（C 段照規則拼）。不碰狀態、不拿鎖。"""
    if client is None or seconds <= 0:
        return None
    capped = copy.copy(client)
    capped.timeout = seconds
    if hasattr(capped, "retry"):
        capped.retry = False
    try:
        raw = capped.chat_text(messages(req), temperature=0.7, num_predict=2400)
    except Exception:  # noqa: BLE001 — 模型叫不動一律走規則版
        return None
    return clean(raw, req)


# ── 規則版（模型叫不動時；照樣能讀、能分享）───────────────


def _strip(text: str, name: str = "") -> str:
    """一則行狀的事實接進句子裡：數目換成中文、「你」換成名號（行狀是寫給你看的，傳是第三人稱）、去掉句尾的句號。
    你說的那一句、人物回的那一句不經過這裡。"""
    text = _plain(text).rstrip("。")
    return text.replace("你", name) if name else text


def _plain(text: str) -> str:
    """行狀的字是畫面上的寫法（「出手 4 回合」「情誼 +6」「第 3／12」）：阿拉伯數字換成中文、拿掉數字兩邊的空格與正負號。"""
    text = re.sub(r"排第\s*(\d+)／(\d+)", lambda m: f"在{_cn(int(m.group(2)))}人中排第{_cn(int(m.group(1)))}", text)
    sign = {"+": "增", "-": "減", "": ""}
    return re.sub(r"\s*([+-]?)(\d+)\s*", lambda m: sign[m.group(1)] + _cn(int(m.group(2))), text)


def _end(text: str) -> str:
    """句子收尾：已經有句末標點（含引號收尾）就不再補「。」，免得「？。」「」。」。"""
    text = text.rstrip()
    done = text[-1:] in ("。", "！", "？") or (text.endswith("」") and text[-2:-1] in ("。", "！", "？"))
    return text if not text or done else text + "。"


def _when(when: str) -> str:
    """行狀的時刻只留到週或日：「第 3 週・週二 21:40」→「第三週」，「第2天 14:05」→「第二日」。"""
    m = re.match(r"第\s*(\d+)\s*週", when)
    if m:
        return f"第{_cn(int(m.group(1)))}週"
    m = re.match(r"第\s*(\d+)\s*天", when)
    return f"第{_cn(int(m.group(1)))}日" if m else ""


def _pick(rows: list[dict], limit: int, prefer: frozenset[str] = frozenset()) -> list[dict]:
    """備援文字每一段最多取 limit 則，照時間先後排。prefer 空的（關著的季）就是前 limit 則，跟以前一樣；有 prefer（7e，列傳為終點）：
    那幾類先留 limit 的一半位子（份量重的先、同份量取近的），剩下的位子照時間先後給別的（包括沒進一半位子的那幾類）。"""
    if not prefer:
        return rows[:limit]
    wanted = sorted((i for i, e in enumerate(rows) if e.get("kind") in prefer), key=lambda i: (-rows[i].get("weight", 1), -i))
    chosen = set(wanted[: limit // 2])
    chosen |= set([i for i in range(len(rows)) if i not in chosen][: limit - len(chosen)])
    return [rows[i] for i in sorted(chosen)]


def _tie_line(e: dict, name: str) -> str:
    """心意、託付、約戰（TIES）的一句備援（7e）：時刻只留到週或日、接在前面，沒有主詞的補上名號（TIES_LINE）。"""
    when = _when(e.get("when", ""))
    return _end(TIES_LINE[e["kind"]].format(when=f"{when}，" if when else "", name=name, text=_strip(e["text"], name)))


def rule_text(req: BiographyRequest) -> str:
    """照行狀拼一篇：四段加評曰。每一句都是行狀裡的原話，只多一些接筆的字。"""
    name, p = req.name, req.profile
    groups = _group(req.annals)
    head = f"{name}者，不知何許人也。生逢{req.scenario}，天下紛擾，負藝行走江湖。"
    joined = [e for e in groups["deed"] if e.get("weight", 1) >= 3][:6]
    deeds = "".join(f"{_when(e.get('when', '')) + '，' if _when(e.get('when', '')) else ''}{_strip(e['text'], name)}。" for e in joined)
    if not deeds and p.get("faction"):
        deeds = f"後投{p['faction']}。"
    # 減法季：痕跡（MARK，份量 2，上面挑不到）與〈天下形勢〉寫到名號（XINGSHI）接在行事後面，最多三則；關著的季沒有這兩種
    heard = [e for e in groups["deed"] if e.get("kind") in (MARK, XINGSHI) and e not in joined][:3]
    deeds += "".join(f"{_strip(e['text'], name)}。" for e in heard)
    paras = [head + deeds]
    battles = groups["showdown"]
    if battles:
        lines = []
        for e in battles[:6]:
            line = _end(_strip(e["text"], name))
            if e.get("quote"):
                line += f"{name}曰：「{e['quote']}」"
                if e.get("reply"):
                    line += "於是" + _end(_strip(e["reply"]))
            lines.append(_end(line))
        paras.append("其臨陣也，" + "".join(lines))
    else:
        paras.append(f"{name}未嘗與於天下大戰。")
    zhuan = _zhuan(req)  # 列傳為終點開著（7e）：心意、託付、約戰各留位子、補主詞與時刻；關著照原本取前幾則
    figures = groups["figure"]
    if figures:
        lines = []
        for e in _pick(figures, 8, frozenset({STANCE, ERRAND}) if zhuan else frozenset()):
            if zhuan and e.get("kind") in TIES:
                lines.append(_tie_line(e, name))
                continue
            line = _end(_strip(e["text"], name))
            if e.get("quote"):
                line += f"{name}問曰：「{e['quote']}」"
            if e.get("reply"):
                line += f"對曰：「{e['reply']}」"
            lines.append(_end(line))
        paras.append("其與當世英雄交也，" + "".join(lines))
    fights = _pick(groups["fight"], 4, frozenset({DUEL}) if zhuan else frozenset())
    end = "".join(_tie_line(e, name) if zhuan and e.get("kind") in TIES else f"{_strip(e['text'], name)}。" for e in fights)
    tail = f"季終，年資武藝至第{_cn(p.get('level', 1))}級"
    if p.get("ranger"):
        tail += f"，江湖稱「{p['ranger']}」"
    elif p.get("faction"):
        tail += f"，仍在{p['faction']}麾下"
    tier = "".join(f"{_strip(e['text'], name)}。" for e in groups.get(TIER, [])[:1])  # 季末論功寫在結局那一段的最後（減法季批 7b）
    paras.append(end + tail + "。" + tier)
    paras.append("評曰：" + _verdict(name, p, bool(battles), bool(figures)))
    return "\n\n".join(paras)


def _verdict(name: str, p: dict, fought: bool, met: bool) -> str:
    good, evil = p.get("good", 0), p.get("evil", 0)
    lean = "行事近俠，鄉里稱之" if good > evil else "行事近梟，人多畏之" if evil > good else "毀譽參半，自成一家"
    parts = [f"{name}{lean}。"]
    if p.get("top_merits"):
        parts.append("陣前屢立首功，非徒勇也。")
    elif fought:
        parts.append("身與大戰，亦一時之選。")
    if met:
        parts.append("與英雄周旋，進退有度。")
    parts.append("亂世之中，能自全其名者，蓋亦難矣。")
    return "".join(parts)


_DIGITS = "〇一二三四五六七八九"


def _cn(n: int) -> str:
    """整數寫成中文（一萬以內照位數讀，「一百零五」；再大就一個數字一個字）。"""
    n = int(n)
    if n < 10:
        return _DIGITS[n]
    if n < 20:
        return "十" + (_DIGITS[n - 10] if n > 10 else "")
    if n >= 10000:
        return "".join(_DIGITS[int(d)] for d in str(n))
    out, zero = "", False
    for unit, size in (("千", 1000), ("百", 100), ("十", 10), ("", 1)):
        digit, n = divmod(n, size)
        if digit:
            out += ("零" if zero and out else "") + _DIGITS[digit] + unit
            zero = False
        else:
            zero = True
    return out


def lead(text: str, limit: int = 100) -> str:
    """全文的第一段（分享預覽的摘要），超過 limit 字截斷補「…」。"""
    first = text.split("\n\n", 1)[0].strip()
    return first if len(first) <= limit else first[: limit - 1] + "…"
