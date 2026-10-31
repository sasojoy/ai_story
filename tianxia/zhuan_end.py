"""列傳為終點（減法季整合設計第九章；主機側計畫第八節，批 7b）：季末的列傳是一季的終點。

這一份管三件事（純規則；讀寫錢包、存檔的是 Game）：
- 四件只對準列傳的商品用掉的票（mall.EFFECTS 的 zhuan_art、zhuan_seal、zhuan_quote；購買那一列就是票，用了在那一列的 data
  記 used、season，親筆評曰另記 fid）：列傳插畫的圖庫鍵（illustration_for，<陣營>_<win|lose>，圖檔由雲端批 8 放
  web/img/zhuan/）、紀念印上的字（seal_text）、休季那三顆行動（zhuan:pick_art、zhuan:seal、zhuan:quote:<人物>）。
- 深交上限與深交名額（批 7b～7d）已拿掉（企劃者 2026-10-28「不要限制深交名額」）：情誼照舊一路往上長、知己不限人數；
  DEEP_SLOT 這個鍵留在 mall.EFFECTS，只為了已經買過的那幾列讀得出來、退得了款。
- 人物評曰（批 7b-2，見檔尾）。

開關是 Config.jianfa 的子開關 zhuan_end ＋ 開季的章（on → rules.jianfa）；關著什麼都不做、商城不上架這四件（MallWindow.rule）。
不讀時鐘、不碰 Game.rng。tianxia 裡只 import models、state（wins、rules、gender、zh 在函式裡延後 import）。新寫給玩家看的字都待 joy 潤。"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import NamedTuple

from pydantic import BaseModel

from .models import Content
from .state import GameState, WorldState

TITLE = "列傳"  # 江湖紀錄的標題（休季用票）
PREFIX = "zhuan:"
PICK_ART, SEAL = "zhuan:pick_art", "zhuan:seal"
QUOTE = "zhuan:quote:"
ART, SEAL_TICKET, QUOTE_TICKET, DEEP_SLOT = "zhuan_art", "zhuan_seal", "zhuan_quote", "deep_slot"  # mall.EFFECTS 的鍵
ART_DIR = "zhuan"  # 圖檔在 web/img/zhuan/<鍵>.webp（雲端批 8 放；沒有檔案時伺服器不給 src）
SEASON_NAME = "{scenario}・第 {n} 季"

# 待 joy 潤
ART_BUTTON = "用列傳插畫：列傳開頭配一幅水墨"
SEAL_BUTTON = "蓋紀念印：{seal}"
QUOTE_BUTTON = "請{name}寫一句親筆評曰（情誼 {value}）"
ART_DONE = "列傳開頭配上了一幅水墨。"
SEAL_DONE = "列傳末尾蓋上一方朱印：{seal}。"
QUOTE_DONE = "你請{name}替你的列傳寫一句評曰。"
QUOTE_LATER = "你的列傳已經寫成，下一次重修時這一句才會寫進去。"
ART_NO_SIDE = "沒投靠一方的人，列傳配不了插畫。"  # 插畫票不賣的原因（FB-845）
ART_FREE = "你的列傳得了第一階，插畫白送，不必買。"
_DIGITS = "〇一二三四五六七八九十"
_DIGIT = re.compile(r"[0-9０-９]")
_KANA = re.compile(r"[぀-ヿㇰ-ㇿ]")


def on(content: Content, world: WorldState | None) -> bool:
    from .rules import jianfa  # noqa: PLC0415

    return jianfa(content, world, "zhuan_end")


def _cn(n: int) -> str:
    return _DIGITS[n] if 0 <= n <= 10 else str(n)


# ── 列傳插畫與紀念印 ──


def illustration_for(state: GameState, content: Content, season: WorldState) -> str:
    """列傳插畫的圖庫鍵「<陣營>_<win|lose>」（第一批 6 張：三方各贏、各輸；設計第九章）。兩軍看結局贏的是不是自己；豪強看照哪一本論功
    （那一本是贏的那一軍才算贏；沒論功照此刻幫的那一軍）；和局都是 lose。散人、季還沒收是空字串。"""
    from .wins import winner_of  # noqa: PLC0415

    p = state.player
    faction = content.scenario.find_faction(p.faction)
    if faction is None or not season.ended:
        return ""
    winner = winner_of(season, content)
    if faction.allies:
        result = season.final_tiers.get(p.name)
        side = result.ledger_used if result is not None and result.ledger_used in faction.allies else p.ally
        won = winner is not None and side == winner
    else:
        won = winner == faction.id
    return f"{faction.id}_{'win' if won else 'lose'}"


def art_problem(state: GameState, content: Content, season: WorldState) -> str | None:
    """列傳插畫票這一季用不用得上（FB-845）：用不上就不賣，回商城那一列灰掉要寫的原因；用得上是 None。
    沒投靠劇本裡的陣營的人（散人）列傳配不了插畫；休季時已經得第一階的人插畫白送（Game._zhuan_options 也是這兩條），
    季中看不出會是第幾階，照舊賣。"""
    p = state.player
    if content.scenario.find_faction(p.faction) is None:
        return ART_NO_SIDE
    result = season.final_tiers.get(p.name) if season.ended else None
    return ART_FREE if result is not None and result.tier == 1 else None


def art_path(key: str) -> str:
    """圖庫鍵 → web/img 底下的路徑（不含副檔名）；伺服器照 scene_art 的做法看檔案在不在。"""
    return f"{ART_DIR}/{key}"


def seal_text(content: Content, season_number: int, profile: dict) -> str:
    """紀念印上的字：季名「黃巾之亂・第 N 季」，有論功時接名次與第幾階（照身家 annals.standing 的 tier_side、final_rank、tier）。"""
    from .wins import TIER_NAMES  # noqa: PLC0415

    parts = [SEASON_NAME.format(scenario=content.scenario.name, n=season_number)]
    if profile.get("final_rank"):
        parts.append(f"{profile.get('tier_side', '')}第 {profile['final_rank']} 名")
    if profile.get("tier"):
        parts.append(f"{TIER_NAMES[profile['tier']]}「{profile.get('tier_title', '')}」")
    return "・".join(parts)


def season_tickets(purchases, season: int) -> dict:
    """這一季用掉、沒退的票（Wallet.purchases 的那幾筆）：{"art": 用了插畫票, "seal": 用了紀念印, "quotes": [請了哪幾位人物]}。
    quotes 照請的先後（FB-846）：每一次請都用最舊的一張票（Game._zhuan_act 拿 mall.tokens 的第一張），所以票的編號由小到大就是請的先後；
    Wallet.purchases 是新的在前，這裡先倒過來排（不看用掉的時刻：快轉只活在一個 Game 的記憶體裡，時刻可能倒退）。"""
    out = {"art": False, "seal": False, "quotes": []}
    for b in sorted(purchases, key=lambda b: b.id):
        if b.refunded is not None or not b.data.get("used") or b.data.get("season") != season:
            continue
        if b.data.get(ART):
            out["art"] = True
        if b.data.get(SEAL_TICKET):
            out["seal"] = True
        if b.data.get(QUOTE_TICKET) and b.data.get("fid"):
            out["quotes"].append(b.data["fid"])
    return out


def unused(purchases, effect: str, season: int | None = None) -> list:
    """帶著 effect、沒退、還沒用掉的那幾筆（舊的在前；同 mall.tokens，只是拿已經讀好的那一份，不再讀資料庫）。
    season 給了只算那一季買的（FB-845：列傳的票綁買的那一季，之後的季不再冒出用票的鈕）。"""
    return [b for b in reversed(purchases) if b.refunded is None and b.data.get(effect) and not b.data.get("used")
            and (season is None or b.season == season)]


def extras(content: Content, season_number: int, profile: dict, tickets: dict, text: str | None = None) -> dict:
    """列傳多畫的那幾樣（休季的 biography_entry、讀傳的 biography_view、公開頁都照它）：tier 季末論功（{tier, title, rank, of, side}；
    沒有階是 None）、illustration 插畫的圖庫鍵（第一階白送，或這一季用了插畫票；沒有是 None）、seal 紀念印的字（這一季蓋了才有）、
    verdicts 這一季替你寫評曰的人物（[{figure, name, reason}]）。
    verdicts 照寫成的那一篇傳列（FB-847）：text 是傳的全文（寫成了才有），名單就是正文裡真的有「評曰：某某云：「…」」的那幾位，照正文的次序——
    傳寫成之後才請的人不列（等重修寫進去才列）、管理者退了用過的那一張也不因此拿掉（正文還有他）；text 是 None（還沒寫成）列的是「要寫的人」：
    身家裡白送的那幾位，接買了親筆評曰請的（照請的先後）。身家裡白送的理由（affinity、tier）照身家寫，其餘都是 bought。"""
    tier = profile.get("tier") or 0
    art = profile.get("illustration") or None
    reasons = {w["fid"]: w["reason"] for w in profile.get("verdicts", [])}
    if text is None:
        writers_ = with_bought([Writer(fid, reason) for fid, reason in reasons.items()], tickets.get("quotes", []), content)
    else:
        writers_ = written_writers(text, content, reasons)
    return {
        "tier": {"tier": tier, "title": profile.get("tier_title", ""), "rank": profile.get("final_rank", 0),
                 "of": profile.get("final_of", 0), "side": profile.get("tier_side", "")} if tier else None,
        "illustration": art if art and (tier == 1 or tickets.get("art")) else None,
        "seal": seal_text(content, season_number, profile) if tickets.get("seal") else None,
        "verdicts": [{"figure": w.fid, "name": content.characters[w.fid].name, "reason": w.reason}
                     for w in writers_ if w.fid in content.characters],
    }


def quote_figures(state: GameState, content: Content, taken: set[str]) -> list[tuple[str, int]]:
    """親筆評曰挑得到的人物（設計第九章：情誼 letter_affinity〔40〕以上、signature_affinity〔70〕以下；70 以上本來就白送）：
    [(人物 id, 情誼)]，情誼高的在前；taken 是這一季已經替你寫的（白送的與請過的）。"""
    low, high = content.config.figure_life.letter_affinity, content.config.signature_affinity
    picks = [(cid, v) for cid, v in state.player.affinities.items() if cid in content.characters and low <= v < high and cid not in taken]
    return sorted(picks, key=lambda x: (-x[1], x[0]))


# ── 人物評曰（批 7b-2；設計第九章、3.3）──
# 三段式同書信（letters.request／write／apply）：A 鎖內 Game.biography_request 把每一位寫手開成一張 VerdictJob（verdict_request），
# B 鎖外 server.write_zhuan 寫完正文再逐條請模型寫（write_verdict；排在真人後面），C 鎖內 Game.write_biography 每一條接一段「評曰：」
# （apply_verdict；寫不出來照固定句 content/verdicts.json）。模型只寫字：四十字以內、繁體、沒有數字、沒有假名，不給任何數字。

AFFINITY, TIER, BOUGHT = "affinity", "tier", "bought"  # 誰替你寫：情誼 70 以上的、第一二階的主將或家主、買了親筆評曰請的
REASONS = (AFFINITY, TIER, BOUGHT)
VERDICT_HEAD = "評曰：{name}云：「"  # 人物評曰那一段的開頭（written_writers 照它認寫成的傳裡有誰）
VERDICT_PARA = VERDICT_HEAD + "{text}」"  # 接在正文後面的一段（網頁與公開頁照段首「評曰」認，待 joy 潤）
DEFAULT_VERDICTS = {  # 內容沒有 verdicts.json（測試內容）時的固定句
    AFFINITY: ["{name}與吾相交一季，可謂知己。"],
    TIER: ["{name}此季之功，吾親書以表之。"],
    BOUGHT: ["{name}行事磊落，不可不記。"],
}
VERDICT_PREDICT = 200  # 四十字的一句加 JSON 外殼（只加不減）
ABOUT_MAX = 4  # 給模型看的「這一季的事」最多幾則行狀


class Writer(NamedTuple):
    fid: str  # 人物 id（content.characters）
    reason: str  # AFFINITY／TIER／BOUGHT


@dataclass(frozen=True)
class VerdictJob:
    """一條評曰的單子（A 段開、B 段照它寫、C 段照 fid 對回去）。"""

    fid: str
    reason: str
    name: str  # 人物的名字
    persona: str  # 人物的性格與處境（給模型）
    hero: str  # 少俠／女俠
    player: str  # 名號
    about: str  # 這一季跟他有關、份量重的事（給模型；可以有數字，模型被要求不寫）
    fixed: str  # 固定句（{name} 換好了）


def writers(state: GameState, content: Content, season: WorldState) -> list[Writer]:
    """這一季替你寫評曰的人物（不含買了請的，那幾位照票）：第一、二階由自己這一方 FactionDef.verdict_by 裡跟你情誼最高的那一位寫
    （一樣高照寫的順序；官軍皇甫嵩或盧植、黃巾張角或波才、豪強曹操）；情誼到 signature_affinity（70）以上的人物各一位（情誼高的在前），
    最多 Config.jianfa.verdict_affinity_max（3）位——深交不限人數之後（企劃者 2026-10-28），PM 定只取情誼最高的前三位，省模型呼叫、
    固定句也不重複。同一位人物只寫一條。關著的季、散人沒有階也沒有 70 以上的人物是空的。"""
    p, c = state.player, content
    out: dict[str, str] = {}
    result = season.final_tiers.get(p.name)
    faction = c.scenario.find_faction(p.faction)
    if result is not None and result.tier in (1, 2) and faction is not None and faction.verdict_by:
        order = {cid: i for i, cid in enumerate(faction.verdict_by)}
        out[min(faction.verdict_by, key=lambda cid: (-p.affinities.get(cid, 0), order[cid]))] = TIER
    edge, room = c.config.signature_affinity, c.config.jianfa.verdict_affinity_max
    for cid, value in sorted(p.affinities.items(), key=lambda x: (-x[1], x[0])):
        if room <= 0:
            break
        if value >= edge and cid in c.characters and cid not in out:
            out[cid] = AFFINITY
            room -= 1
    return [Writer(cid, reason) for cid, reason in out.items()]


def with_bought(free: list[Writer], bought: list[str], content: Content) -> list[Writer]:
    """白送的寫手後面接買了親筆評曰請的（照請的先後；已經白送的、不在 characters 裡的略過）。"""
    seen = {w.fid for w in free}
    out = list(free)
    for cid in bought:
        if cid in content.characters and cid not in seen:
            out.append(Writer(cid, BOUGHT))
            seen.add(cid)
    return out


def written_writers(text: str, content: Content, reasons: dict[str, str]) -> list[Writer]:
    """寫成的傳裡真的有評曰的人物（FB-847）：照正文的段首「評曰：某某云：「」認（某某是 content.characters 裡的名字；史官自己的「評曰：」
    後面不接這個開頭），同一位只算第一段，照正文的次序。理由：reasons（身家裡白送的 fid → affinity／tier）有的照它，其餘（請來的）是 bought。"""
    names = {ch.name: cid for cid, ch in content.characters.items()}
    out: list[Writer] = []
    seen: set[str] = set()
    for para in (text or "").split("\n\n"):
        if not para.endswith("」"):
            continue
        for name, cid in names.items():
            if cid not in seen and para.startswith(VERDICT_HEAD.format(name=name)):
                seen.add(cid)
                out.append(Writer(cid, reasons.get(cid, BOUGHT)))
                break
    return out


def _pool(content: Content, reason: str) -> list[str]:
    return list(content.verdicts.get(reason) or DEFAULT_VERDICTS[reason])


def fixed_verdicts(content: Content, writers: list[Writer], player: str, season_number: int) -> dict[str, str]:
    """同一篇傳裡每位寫手的固定句（FB-848：模型叫不動時，兩位寫手不能一字不差）：整篇一起挑，人物 id → 一句（{name} 換好了）。
    同一個理由的寫手照順序輪著挑（起點照「季|名號|理由」的雜湊，第 k 位往後數 k 句，不碰任何亂數）；整篇用過的句子不再挑；
    自己那一組的句子不夠了，往別組借沒用過的（content.check_verdicts 擋各組之間重複的句子）；全部用過了才重複。"""
    pools = {reason: _pool(content, reason) for reason in REASONS}
    used: set[str] = set()
    nth: dict[str, int] = {}
    out: dict[str, str] = {}
    for w in writers:
        k = nth.get(w.reason, 0)
        nth[w.reason] = k + 1
        pool = pools[w.reason]
        start = (int(hashlib.sha1(f"{season_number}|{player}|{w.reason}".encode()).hexdigest(), 16) + k) % len(pool)
        own = pool[start:] + pool[:start]
        borrowed = [line for reason in REASONS if reason != w.reason for line in pools[reason]]
        pick = next((line for line in own + borrowed if line not in used), own[0])
        used.add(pick)
        out[w.fid] = pick.replace("{name}", player)
    return out


def fixed_verdict(content: Content, writer: Writer, player: str, season_number: int) -> str:
    """一位寫手的固定句（整篇只有他一位時；Game 開單走 fixed_verdicts，整篇一起挑才不撞句）。"""
    return fixed_verdicts(content, [writer], player, season_number)[writer.fid]


def verdict_request(content: Content, writer: Writer, player: str, sex: str, annals: tuple[dict, ...], profile: dict,
                    season_number: int, fixed: str | None = None) -> VerdictJob:
    """A 段：照傳的單子（名號、行狀、身家）開一張評曰的單子。只讀這幾樣，不讀角色：以前的季照存起來的那一份也開得出來。
    fixed 是這一篇整篇挑好的固定句（fixed_verdicts）；沒給就只照這一位挑。"""
    ch = content.characters[writer.fid]
    persona = "；".join(x for x in (ch.personality, ch.situation) if x)[:200]
    mine = [e for e in annals if e.get("figure") == writer.fid]
    rest = sorted((e for e in annals if e.get("figure") != writer.fid), key=lambda e: -e.get("weight", 1))
    facts = [e.get("text", "") for e in (mine + rest)[:ABOUT_MAX]]
    if profile.get("tier"):
        facts.append(f"季末論功：{profile.get('tier_side', '')}第{_cn(profile['tier'])}階「{profile.get('tier_title', '')}」")
    elif profile.get("faction"):
        facts.append(f"投靠{profile['faction']}")
    from . import gender  # noqa: PLC0415

    return VerdictJob(
        fid=writer.fid, reason=writer.reason, name=ch.name, persona=persona, hero=gender.hero(sex), player=player,
        about="；".join(f for f in facts if f),
        fixed=fixed if fixed is not None else fixed_verdict(content, writer, player, season_number),
    )


class VerdictText(BaseModel):
    verdict: str = ""


def messages(job: VerdictJob, limit: int) -> list[dict[str, str]]:
    why = {
        TIER: f"這一季{job.hero}在你麾下立了大功，論功行賞，由你親筆替{job.hero}的列傳寫一句評語。",
        AFFINITY: f"你跟{job.hero}情誼深厚，季末替{job.hero}的列傳寫一句評語。",  # 玩家看得到的一律叫「情誼」（test_explain 也掃模型的字串）
        BOUGHT: f"{job.hero}跟你略有情誼，請你替{job.hero}的列傳寫一句評語。",
    }[job.reason]
    return [
        {"role": "system", "content": (
            f"你是東漢末年的{job.name}。{job.persona}\n"
            f"{why}用你自己的口氣、半文言、繁體中文，一句話、{limit}字以內；稱對方為「{job.player}」。"
            "不要寫任何數字（數目也不要寫），不要寫署名、標點以外的符號、markdown。"
        )},
        {"role": "user", "content": f"{job.player}這一季的事：{job.about or '（無）'}。\n請給 verdict。"},
    ]


def clean_verdict(raw: str | None, limit: int, *known: str) -> str:
    """模型寫的評曰：轉繁體、去標記與引號、去空白；空的、太長、有數字或假名回空字串（照固定句）。
    有英文字母也回空字串（M-07），known（名號、這一季的事）裡本來就有的不算。"""
    from . import zh  # noqa: PLC0415

    text = zh.to_traditional(str(raw or "")).strip()
    text = re.sub(r"[*#>`_]+", "", text)
    text = re.sub(r"\s+", "", text).strip("「」『』\"'“”")
    if not text or len(text) > limit or _DIGIT.search(text) or _KANA.search(text) or zh.stray_latin(text, *known):
        return ""
    return text


def write_verdict(client, job: VerdictJob, limit: int) -> str:
    """B 段（鎖外）：請模型照他的口氣寫一句；叫不動、寫壞了回空字串（C 段照固定句）。不碰狀態、不拿鎖。"""
    if client is None:
        return ""
    try:
        result = client.chat_structured(messages(job, limit), VerdictText, temperature=0.8, num_predict=VERDICT_PREDICT,
                                        schema_required=["verdict"])
    except Exception:  # noqa: BLE001 — 模型叫不動一律照固定句
        return ""
    return clean_verdict(result.verdict, limit, job.player, job.about)


def apply_verdict(job: VerdictJob, text: str) -> str:
    """C 段：一條評曰寫成接在正文後面的一段（寫不出來是空字串就用固定句）。"""
    return VERDICT_PARA.format(name=job.name, text=text or job.fixed)


def check_verdicts(content: Content) -> list[str]:
    """content/verdicts.json 寫錯的地方（content.validate 叫）：理由只能是三種、每一組至少一句、拿掉 {name} 之後在 verdict_chars 以內、
    沒有阿拉伯數字、各組之間與組裡面的句子不重複（同一篇傳不撞句，fixed_verdicts 往別組借時才借得到不同的）。沒有這個檔是空的。"""
    out: list[str] = []
    limit = content.config.jianfa.verdict_chars
    seen: set[str] = set()
    for reason, lines in content.verdicts.items():
        if reason not in REASONS:
            out.append(f"理由 {reason} 不是 {'、'.join(REASONS)} 其中之一")
        if not lines:
            out.append(f"{reason} 至少要一句")
        for line in lines:
            if len(line.replace("{name}", "")) > limit or _DIGIT.search(line):
                out.append(f"{reason}「{line}」要在 {limit} 字以內、不寫數字")
            if line in seen:
                out.append(f"{reason}「{line}」跟別的句子重複了")
            seen.add(line)
    return out
