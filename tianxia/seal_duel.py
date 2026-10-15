"""奪璽單挑（玉璽碎片設計第五節；PM 2026-10-11 乙）：挑戰者對持有者，照單人頭目戰的規則對稱地打 rounds 回合（duel.py 的純函式）。

- 兩邊都用快照（SealSide，5.3）：份量（拿掉騎兵與部下，計畫「要 PM 定的」第 4 條）、職位、氣血池在開單挑時抓好；池子各扣各的，
  打完不扣回角色、不磨兵器、沒有獎勵（名望與碎片在補送時給）。
- 一回合（5.2）：兩邊都出招時推力＝duel.push_of（往挑戰者算），兩邊各扣自己的池子（duel.harm_of）；有人放手一搏時搏的那一邊照
  duel.gamble_roll 擲，另一邊這一招不算、不扣血；兩邊都搏推力相加。一場每一邊最多搏 gamble_cap 次。
- 在場（5.5）：回合開始時 last_seen 在 presence_window 秒內才算；不在場的那一邊回合一開就預擲一招與一句架勢（代打，5.6），架勢只給
  對手看；在場卻逾時沒送的那一手在結算時才代出（不給架勢）。判成不在場的那一邊這一回合送不出去（LATE）。
- 結算的時機（5.4）：最早在回合開始 pace_seconds 後；在場的都送了就結算，否則等到 round_seconds。
- 勝負（挑戰者的角度）：verdict；再擲（5.8）：take_chance＝cap × take_share[結果]，cap 開單挑時已經乘過局勢與護璽，四個都不超過 1。
- 亂數（5.13）：一回合兩份 seal-round|id|回合|邊（挑戰者那一份先取運氣，各自再取放手一搏的成敗）；代打 seal-proxy|id|回合|邊
  （先取招、再取架勢真假、再取架勢那一句）；再擲 seal-take|id（一次）。全不碰 Game.rng，誰觸發結算結果都一樣。
只改傳進來的 SealDuel 與 SharedWorldState（天下大事、江湖史、全服登記）；不碰任何人的存檔、不叫模型。
"""
from __future__ import annotations

import random
import re
from typing import NamedTuple

from . import battle_instance, seal, tactics
from . import duel as duel_rules
from .battle_instance import CAVALRY_MOVES, DEFAULT_FREE_TEXT_SUCCESS_RATE, BattleParticipant
from .models import MOVES, Content, DuelTuning, SealTuning
from .world_state import SealDuel, SealEvent, SealSide, SharedWorldState

SIDES = ("challenger", "holder")
TEXT = "text"  # pending 裡放手一搏的那一手
WIN_VERDICTS = ("提前大勝", "大勝", "險勝")  # 挑戰者打贏了單挑（PM 丁：再擲沒中名望 +1）

# 待 joy 潤
LATE = "這一回合來不及了，下一回合再出手。"
SENT = "已出招，等對方"
NO_MORE_GAMBLE = "這一場你已經放手一搏兩次了，只剩三招。"
NO_GAMBLE = "亂了心神，這一回合沒法放手一搏"  # 本命戰法：亂神
BOUT_SIDE = {"challenger": "a", "holder": "b"}  # tactics.Bout 的哪一邊
GONE = "這一回合已經結算了，下一回合再出手。"
CALL = "{challenger}（此役戰功居前）向懷璽的{holder}下了戰書，一炷香後陣前單挑，爭『{shard}』。"
CALL_QA = "{challenger}向懷璽的{holder}下了戰書，一炷香後陣前單挑，爭『{shard}』。"  # 挑戰者不是參戰者（小伺服器補上的旁觀散人、管理者不掛決戰開的那一場）
ROUND = "奪璽第 {n} 回合：{lead}——{edge}。"
CLOSE_LINE = "最後氣勢越偏向挑戰者，碎片越可能易主；璽有靈，未必跟著贏家走。"
TAKE = "{challenger}在{where}陣前奪得{holder}懷中的『{shard}』，{holder}力戰失璽。"
NEAR = "{challenger}力挫{holder}，『{shard}』在兩人之間一閃，終究落回{holder}懷中，懷璽不失。"
KEEP = "{holder}擋下了{challenger}，懷璽不失。"
UNSETTLED = "{challenger}與{holder}爭『{shard}』的單挑沒有打完，碎片留在{holder}懷中。"
GAMBLE_WON, GAMBLE_LOST = "{name}放手一搏——成了！", "{name}放手一搏——沒成，反倒露了破綻。"
SETTING = "兩人陣前單挑、爭奪玉璽碎片的"  # 給 battle_instance.assess_gamble
PLACE = "單挑"
SCENE_RULE = "（這一手只爭一回合的氣勢：碎片要到單挑收場再擲才定歸屬，劇情不寫奪下碎片、不寫勝負已分。）"  # FB-176：給模型的場景多這一句
PROMPT = "寫下你陣前的一手（20 字內）"
GAMBLE_NOTE = "放手一搏一場最多兩次；寫得越險，成了推得越多、搏輸了傷的是你自己。"
RESEND = "這一手跟剛才送出的對不上（是不是開了兩個分頁？），請再送一次。"
_SHARD_WORDS = re.compile(r"碎片|印|璽")
_SEIZE_WORDS = re.compile(r"奪|搶|攫|摘|抓起|拿到|拿下|取走|取下|收入懷|入懷|到手")
_SENTENCE = re.compile(r"[。！？!?]")


def claims_shard(story: str) -> bool:
    """這一版劇情寫了把碎片拿到手：同一句裡有「碎片／印／璽」，也有「奪／搶／抓起／收入懷中／到手」這類字，前後順序不拘
    （FB-176 認「奪下玉璽碎片」；FB-188：真模型也寫「將…玉璽碎片奪入懷中」，碎片在前、動詞在後）。「沒奪到」「未能奪下」這類
    否定的照樣算——寧可多擋，代價只是改播固定句；分在兩句裡的不算。碎片要到單挑收場再擲才定歸屬，這一版不用、改播固定句
    （GAMBLE_WON／GAMBLE_LOST）。場景裡的 SCENE_RULE 擋不住玩家自己寫「奪印」的情形，所以引擎再擋一次。"""
    return any(_SHARD_WORDS.search(part) and _SEIZE_WORDS.search(part) for part in _SENTENCE.split(story or ""))


class TextRequest(NamedTuple):
    """放手一搏的 A 段開的單子（Game.seal_text_request → server.seal_text → Game.seal_gamble）。"""

    duel: str
    round: int
    side: str
    text: str
    name: str
    faction_name: str
    title: str
    scene: str
    target: str
    sex: str = "男"  # 模型寫劇情時的性別（Joy 的 gender：assess_gamble(sex=)）


def other(who: str) -> str:
    return "holder" if who == "challenger" else "challenger"


def side_of(duel: SealDuel, name: str) -> str | None:
    k = seal.key(name)
    return next((w for w in SIDES if seal.key(getattr(duel, w).name) == k), None)


def unmounted(p: BattleParticipant) -> dict[str, float]:
    """參戰者的份量拿掉騎兵與部下（強攻、奇襲除回去）：單挑照頭目戰（_battle_scores(mounted=False)）。"""
    ride = (1 + p.cavalry) * (1 + p.troop_bonus)
    return {m: round(v / ride, 1) if m in CAVALRY_MOVES and ride > 0 else v for m, v in p.scores.items()}


def side_from_participant(p: BattleParticipant, faction: str | None) -> SealSide:
    """參戰者的快照（5.3 前兩列）：威力、份量、職位、氣血上限；池子從滿血開始（決戰裡那一份池子不帶進來）。"""
    kit = p.kit.model_copy(update={"ctx": p.kit.ctx.model_copy(update={"mount_tier": 0, "followers": 0})}) if p.kit else None
    return SealSide(name=p.name, faction=faction, power=p.power, scores=unmounted(p), role=p.role, hp=p.neili_cap, hp_cap=p.neili_cap,
                    kit=kit)


def side_from(name: str, faction: str | None, power: float, scores: dict[str, float], role: str, hp_cap: float, fresh: bool = False,
              kit: tactics.BoutSide | None = None) -> SealSide:
    """沒參戰的那一邊（持有者、小伺服器補上的旁觀散人）：engine 照他的 Game 算好給（_battle_power、_battle_scores(mounted=False)、
    team.self_side…）。"""
    return SealSide(name=name, faction=faction, power=power, scores=dict(scores), role=role, hp=hp_cap, hp_cap=hp_cap, fresh=fresh,
                    kit=kit)


def open_duel(
    duel_id: str, shard: str, record: int | None, event_id: str | None, where: str, tier: str, cap: float,
    challenger: SealSide, holder: SealSide, now: float, cfg: SealTuning,
) -> SealDuel:
    return SealDuel(
        id=duel_id, shard=shard, record=record, event_id=event_id, where=where, tier=tier, cap=cap, phase="muster",
        starts_real=now + cfg.muster_seconds, challenger=challenger, holder=holder, rounds=cfg.rounds,
        bout=tactics.open_bout(challenger.kit, holder.kit, challenger.name, holder.name, a_faction=challenger.faction,
                               b_faction=holder.faction),
    )


def present(side: SealSide, now: float, cfg: SealTuning) -> bool:
    return side.last_seen is not None and 0 <= now - side.last_seen <= cfg.presence_window


def note_seen(duel: SealDuel, who: str, now: float, cfg: SealTuning) -> bool:
    """他自己的請求推了這場單挑：記 last_seen；存著的比現在早 seen_write_seconds 以上才寫（低頻寫入，5.5）。回傳有沒有改。"""
    s = getattr(duel, who)
    if s.last_seen is not None and now - s.last_seen < cfg.seen_write_seconds:
        return False
    s.last_seen = now
    return True


def proxy_weights(side: SealSide, cfg: SealTuning) -> list[float]:
    """代打的招的權重：（這一招的份量 ÷ 三招最高）^proxy_power（5.6）；份量全是 0 就平均。"""
    values = [max(0.0, side.scores.get(m, 0.0)) for m in MOVES]
    top = max(values)
    return [(v / top) ** cfg.proxy_power for v in values] if top > 0 else [1.0] * len(MOVES)


def proxy(side: SealSide, rng: random.Random, cfg: SealTuning, tuning: DuelTuning) -> tuple[str, str]:
    """代打預擲一招與一句架勢（tell_truth 的機會照實，其餘是另一招的架勢）：先取招、再取真假、再取句子。"""
    move = rng.choices(MOVES, weights=proxy_weights(side, cfg))[0]
    shown = move if rng.random() < tuning.tell_truth else rng.choice([m for m in MOVES if m != move])
    return move, rng.choice(duel_rules.TELLS[shown])


def open_round(duel: SealDuel, now: float, content: Content, salt: str, tianji: int) -> None:
    """一回合開始：判兩邊在不在場；不在場的那一邊預擲一招與一句架勢（5.6）。"""
    cfg, tuning = content.config.seal, content.config.duel
    duel.opened_real = now
    duel.pending, duel.rates, duel.texts, duel.stories, duel.proxy_move, duel.tell = {}, {}, {}, {}, {}, {}
    for who in SIDES:
        s = getattr(duel, who)
        s.present = present(s, now, cfg)
        if not s.present:
            move, tell = proxy(s, seal.dice(salt, tianji, "seal-proxy", duel.id, duel.round + 1, who), cfg, tuning)
            duel.proxy_move[who], duel.tell[who] = move, tell
            s.proxied = True


def submit_problem(duel: SealDuel, who: str, cfg: SealTuning, text: bool = False) -> str | None:
    """這一邊這一回合送不送得出去；None＝可以。"""
    if duel.phase != "active":
        return GONE
    s = getattr(duel, who)
    if not s.present:
        return LATE
    if who in duel.pending:
        return SENT
    if text and s.gambles >= cfg.gamble_cap:
        return NO_MORE_GAMBLE
    if text and tactics.locks(duel.bout, BOUT_SIDE[who]).no_gamble:  # 本命戰法：亂神了不能放手一搏
        return NO_GAMBLE
    return None


def submit(duel: SealDuel, who: str, move: str | None = None, text: str | None = None, rate: int | None = None,
           stories: tuple[str, str] | list[str] | None = None) -> None:
    """記這一邊這一回合的一手（呼叫端先看過 submit_problem）。送出不等於結算（同決戰）。"""
    if text is None:
        duel.pending[who] = move or "固守"
        return
    duel.pending[who], duel.texts[who] = TEXT, text
    duel.rates[who] = max(0, min(100, int(DEFAULT_FREE_TEXT_SUCCESS_RATE if rate is None else rate)))
    if stories:  # 寫了奪下碎片的那一版不用（FB-176）；兩版各自判
        duel.stories[who] = ["" if claims_shard(str(s)) else str(s) for s in stories[:2]]


def sent(duel: SealDuel) -> int:
    """「已出招 X／2」：只算親自送出的（代打那一手到結算才算，5.6）。"""
    return len(duel.pending)


def due(duel: SealDuel, now: float, cfg: SealTuning) -> bool:
    if duel.phase != "active" or duel.opened_real is None:
        return False
    waited = now - duel.opened_real
    if waited < cfg.pace_seconds:
        return False
    here = [w for w in SIDES if getattr(duel, w).present]
    return all(w in duel.pending for w in here) or waited >= cfg.round_seconds


def _weight(side: SealSide, move: str, content: Content) -> float:
    return side.scores.get(move) or battle_instance.strength(content.config.battle, side.power) * content.config.duel.foe_fit


def edge_words(duel: SealDuel, viewer: str | None = None) -> str:
    """氣勢那一句：viewer 是持有者就倒過來、寫「你」；挑戰者寫「你」；其他人（圍觀、天下大事）寫挑戰者的名號。"""
    who = side_of(duel, viewer) if viewer else None
    edge = 100 - duel.edge if who == "holder" else duel.edge
    return duel_rules.edge_words(edge, "你" if who else duel.challenger.name)


def resolve(duel: SealDuel, content: Content, salt: str, tianji: int) -> str:
    """結算這一回合（呼叫端先看過 due）：照 5.2 推氣勢、扣兩邊的池子，回這一回合那一句（兩邊具名，天下大事與戰報用）。"""
    cfg, tuning, battle_t = content.config.seal, content.config.duel, content.config.battle
    n = duel.round + 1
    c, h = duel.challenger, duel.holder
    rolls = {w: seal.dice(salt, tianji, "seal-round", duel.id, n, w) for w in SIDES}
    plays: dict[str, str] = {}
    for w in SIDES:
        if w in duel.pending:
            plays[w] = duel.pending[w]
            getattr(duel, w).acted += 1  # 自己出的這一手（FB-174）
        elif w in duel.proxy_move:
            plays[w] = duel.proxy_move[w]
        else:  # 在場卻逾時沒送：結算時才代出（不給架勢）
            plays[w] = proxy(getattr(duel, w), seal.dice(salt, tianji, "seal-proxy", duel.id, n, w), cfg, tuning)[0]
            getattr(duel, w).proxied = True
    luck = rolls["challenger"].uniform(-tuning.luck, tuning.luck) * tactics.luck_scale(duel.bout)  # 先取運氣：不論有沒有人搏，取數順序固定
    gamblers = [w for w in SIDES if plays[w] == TEXT]
    harm = {w: 0 for w in SIDES}
    push = 0
    step = None
    trng = seal.dice(salt, tianji, "seal-tactic", duel.id, n) if duel.bout is not None else None
    if duel.bout is not None:  # 本命戰法（第二批）：不在場、被代打的那一邊看穿或對手亂神時出剋他的招
        step = tactics.step(duel.bout, plays["challenger"], plays["holder"], duel.edge, content.config.tactics, trng,
                            a_ratio=c.hp / max(1.0, c.hp_cap), b_ratio=h.hp / max(1.0, h.hp_cap),
                            a_auto=not c.present, b_auto=not h.present)
    if not gamblers:
        mc, mh = plays["challenger"], plays["holder"]
        if step is not None:
            mc, mh = step.a_move, step.b_move
        sc, sh = _weight(c, mc or "", content), _weight(h, mh or "", content)
        beat = step.beat if step is not None else duel_rules.counter(mc, mh)
        push = round(tactics.scale_push(duel_rules.push_of(sc, sh, beat, c.role, tuning, battle_t, luck, foe_role=h.role), step))
        harm["challenger"] = duel_rules.harm_of(c.hp_cap, sc, sh, beat, tuning)
        harm["holder"] = duel_rules.harm_of(h.hp_cap, sh, sc, -beat, tuning)
        if step is not None:
            harm["challenger"] = round(harm["challenger"] * (1 - step.a_cut)) * step.a_hit
            harm["holder"] = round(harm["holder"] * (1 - step.b_cut)) * step.b_hit
        lead = f"{c.name}{mc or '定在原地'}，{h.name}" + (f"以{mh}相迎" if mh else "定在原地")
    else:
        parts = []
        for w in gamblers:
            s = getattr(duel, w)
            s.gambles += 1
            rate = duel.rates.get(w, DEFAULT_FREE_TEXT_SUCCESS_RATE)
            won, delta, hp, rate = duel_rules.gamble_roll(rate, s.hp_cap, s.power, s.role, tuning, battle_t, rolls[w])
            saved = None
            if not won and duel.bout is not None:
                saved = tactics.divine_save(getattr(duel.bout, BOUT_SIDE[w]).holders, trng)
                if saved is not None:
                    won = True
                    delta, hp = duel_rules.success_of(rate, s.hp_cap, s.power, tuning, battle_t)
            push += delta if w == "challenger" else -delta
            harm[w] = hp
            story = (duel.stories.get(w) or ["", ""])[0 if won and saved is None else 1 if not won else 0]
            parts.append((story or (GAMBLE_WON if won else GAMBLE_LOST).format(name=s.name)).rstrip("。"))
            if saved is not None:
                parts[-1] = tactics.divine_line(saved).rstrip("！")
        lead = "；".join(parts)
    guarded_lines: list[str] = []
    if step is not None:
        push += round(step.push)
        harm["challenger"] = round(harm["challenger"] - step.a_hp * c.hp_cap)
        harm["holder"] = round(harm["holder"] - step.b_hp * h.hp_cap)
        for w, key, s in (("challenger", "a", c), ("holder", "b", h)):
            guarded, said = tactics.guard_pool(duel.bout, key, s.hp, harm[w], s.hp_cap)
            harm[w] = round(guarded)
            guarded_lines += said
    c.hp = max(0.0, min(c.hp_cap, c.hp - harm["challenger"]))
    h.hp = max(0.0, min(h.hp_cap, h.hp - harm["holder"]))
    before = duel.edge
    duel.edge = max(0.0, min(100.0, duel.edge + push))
    duel.round = n
    fired = (list(step.lines) + guarded_lines) if step is not None else []
    if step is not None:
        fired += tactics.close_round(duel.bout, duel.edge - before, content.config.tactics, trng)
    line = tactics.round_line(ROUND.format(n=n, lead=lead, edge=edge_words(duel)), fired)
    duel.lines.append(line)
    return line


def verdict(duel: SealDuel, tuning: DuelTuning) -> str | None:
    """分出勝負沒有（挑戰者的角度，5.2）：挑戰者池子見底或氣勢 ≤ early_lose 落敗（同一回合兩邊見底也算落敗，偏持有者）；
    持有者池子見底是大勝（不算提前大勝）；氣勢 ≥ early_win 提前大勝；打滿看 big／win／draw。還沒是 None。"""
    if duel.challenger.hp <= 0 or duel.edge <= tuning.early_lose:
        return "落敗"
    if duel.holder.hp <= 0:
        return "大勝"
    if duel.edge >= tuning.early_win:
        return "提前大勝"
    return duel_rules.verdict_at(duel.edge, duel.challenger.hp, duel.round, duel.rounds, tuning)


def side_tier(result: str | None, edge: float | None, who: str, tuning: DuelTuning) -> str:
    """戰報那一格的結果字（battlelog.TIER_WORDS 認得的四種），照這一方寫（5.9：持有者那份照挑戰者的翻過來）。
    挑戰者：提前大勝寫大勝，其餘照寫。持有者：挑戰者勝（提前大勝、大勝、險勝）是落敗、僵持是僵持；挑戰者落敗時照收場的氣勢分，
    持有者那一邊的氣勢（100 − edge）到 big 寫大勝、否則險勝（舊資料沒有 edge 寫險勝）。沒打成（result 是 None）寫僵持。"""
    if result is None:
        return "僵持"
    if who == "challenger":
        return "大勝" if result == "提前大勝" else result
    if result in WIN_VERDICTS:
        return "落敗"
    if result == "僵持":
        return "僵持"
    return "大勝" if edge is not None and 100 - edge >= tuning.big else "險勝"


def take_chance(duel: SealDuel, result: str, cfg: SealTuning) -> float:
    """這一場易手的機率（5.8）：cap（已乘局勢與護璽）× 單挑係數，最多 Config.seal.cap。"""
    return min(cfg.cap, duel.cap * cfg.take_share.get(result, 0.0))


def _still_valid(shared: SharedWorldState, duel: SealDuel) -> bool:
    """持有者還是原來那人、挑戰者此刻手上沒有碎片（開打前、寫入前都重驗，5.9、5.12）。"""
    shard = shared.seal.shards.get(duel.shard)
    return (shard is not None and shard.state == "held" and seal.key(shard.holder) == seal.key(duel.holder.name)
            and seal.key(duel.challenger.name) not in seal.holders(shared.seal))


def finish(shared: SharedWorldState, duel: SealDuel, content: Content, result: str | None, now: float) -> SealEvent:
    """收場（5.9）：重驗之後再擲 seal-take|id（管理者定了結果就照它），易手或懷璽不失；寫登記一筆、天下大事、江湖史；這一場從清單
    拿掉，排隊的下一場從現在起下戰書。result 是 None（季終、管理者取消）或重驗不過：記成沒打成，只寫天下大事。"""
    cfg = content.config.seal
    reg = seal.filled(shared.seal, content)
    season = shared.season_number
    c, h = duel.challenger, duel.holder
    shard_name = content.seal[duel.shard].name if duel.shard in content.seal else duel.shard
    words = {"challenger": c.name, "holder": h.name, "shard": shard_name, "where": duel.where or "江湖"}
    common = dict(shard=duel.shard, record=duel.record, where=duel.where, lines=list(duel.lines), fresh=h.fresh, edge=round(duel.edge, 1),
                  proxied=[w for w in SIDES if getattr(duel, w).proxied],
                  absent=[w for w in SIDES if getattr(duel, w).proxied and not getattr(duel, w).acted],  # 整場都代打（FB-174）
                  at=shared.season.time)  # 收場那一刻：兩份戰報照它蓋時刻（FB-175）
    shared.seal_duels = [d for d in shared.seal_duels if d.id != duel.id]
    if shared.seal_duels:
        shared.seal_duels[0].starts_real = now + cfg.muster_seconds
    if result is None or not _still_valid(shared, duel):
        text = UNSETTLED.format(**words)
        seal.rumor(shared.season, text)
        return seal.log(reg, season, "unsettled", holder=h.name, other=c.name, text=text, **common)
    roll = seal.dice(reg.salt, shared.tianji, "seal-take", duel.id).random()
    taken = duel.fixed if duel.fixed is not None else roll < take_chance(duel, result, cfg)
    shard = reg.shards[duel.shard]
    if taken:
        shard.holder, shard.since_season, shard.former, shard.absent = c.name, season, h.name, 0
        text = TAKE.format(**words)
        event = seal.log(reg, season, "take", holder=c.name, other=h.name, result=result, text=text, **common)
    else:
        text = (NEAR if result in WIN_VERDICTS else KEEP).format(**words)
        event = seal.log(reg, season, "keep", holder=h.name, other=c.name, result=result, text=text, **common)
    seal.rumor(shared.season, text)
    seal.chronicle(shared.season, text)
    return event


def advance(shared: SharedWorldState, content: Content, now: float) -> list[str]:
    """把排第一的那一場推一步（_seal_tick、送出一手之後都叫），一次最多結算一回合：下戰書時間到了就開打（先重驗）；回合該結算就結算、
    分出勝負就收場，否則開下一回合。暫停中不推；季已經結束（自然收季、管理者收季）就記成沒打完（5.11）。回傳這一步寫的那幾句。"""
    if not shared.seal_duels or shared.paused_at is not None:
        return []
    duel = shared.seal_duels[0]
    reg = seal.filled(shared.seal, content)  # 密鹽只讀（伺服器啟動時產生；測試與腳本是空字串）
    if shared.season.ended:
        return [finish(shared, duel, content, None, now).text]
    if duel.phase == "muster":
        if now < duel.starts_real:
            return []
        if not _still_valid(shared, duel):
            return [finish(shared, duel, content, None, now).text]
        duel.phase = "active"
        open_round(duel, now, content, reg.salt, shared.tianji)
        return []
    if not due(duel, now, content.config.seal):
        return []
    line = resolve(duel, content, reg.salt, shared.tianji)
    seal.rumor(shared.season, line)
    result = verdict(duel, content.config.duel)
    if result is not None:
        return [line, finish(shared, duel, content, result, now).text]
    open_round(duel, now, content, reg.salt, shared.tianji)
    return [line]


def needs_write(duel: SealDuel, who: str | None, now: float, cfg: SealTuning, *, own: bool, ended: bool) -> bool:
    """_seal_tick 要不要開一次 world.mutate（每 10 秒的輪詢不能每次都寫）：季結束了、要記自己的 last_seen、下戰書到點、回合該結算。"""
    if ended:
        return True
    if own and who is not None:
        seen = getattr(duel, who).last_seen
        if seen is None or now - seen >= cfg.seen_write_seconds:
            return True
    return now >= duel.starts_real if duel.phase == "muster" else due(duel, now, cfg)


def card(duel: SealDuel, viewer: str | None, now: float, content: Content) -> dict:
    """江湖頁「奪璽」卡（5.10，status_data["seal_duel"]）：全服看得到。代打那一邊的架勢只在他的對手的卡上；不寫機率、不寫誰在線。"""
    cfg = content.config.seal
    who = side_of(duel, viewer) if viewer else None
    me = getattr(duel, who) if who else None
    active = duel.phase == "active"
    left = (duel.opened_real or now) + cfg.round_seconds - now if active else duel.starts_real - now
    return {
        "id": duel.id, "shard": content.seal[duel.shard].name if duel.shard in content.seal else duel.shard,
        "challenger": duel.challenger.name, "holder": duel.holder.name, "phase": duel.phase,
        "round": duel.round + (1 if active else 0), "rounds": duel.rounds, "edge": edge_words(duel, viewer),
        "lines": duel.lines[-3:], "sent": sent(duel), "left": max(0, int(left)), "note": CLOSE_LINE,
        "mine": who is not None,
        "tell": duel.tell.get(other(who), "") if who else "",
        "late": bool(who and active and not me.present),
        "turn": bool(who and active and me.present and who not in duel.pending),
        "gambles_left": max(0, cfg.gamble_cap - me.gambles) if me else 0,
    }


def foe_line(me: SealSide, foe: SealSide, content: Content) -> str:
    """給模型評成功率的那一行：對手是誰、身手跟你比（只寫比較，字同 battle_instance.target_line）。"""
    tuning = content.config.battle
    ratio = battle_instance.strength(tuning, foe.power) / max(1.0, battle_instance.strength(tuning, me.power))
    how = ("遠比玩家強" if ratio >= 1.5 else "比玩家強" if ratio >= 1.1 else "跟玩家不相上下" if ratio > 0.9
           else "比玩家弱" if ratio > 0.6 else "遠比玩家弱")
    hurt = "，已經帶傷" if foe.hp < foe.hp_cap * 0.5 else ""
    return f"{foe.name}（身手{how}{hurt}）"


def scene(duel: SealDuel, who: str, content: Content) -> tuple[str, str]:
    """assess_gamble 讀的 title 與 text（duel.Scene 的兩欄）。"""
    shard = content.seal[duel.shard].name if duel.shard in content.seal else duel.shard
    tell = duel.tell.get(other(who), "")
    text = f"第 {duel.round + 1}／{duel.rounds} 回合，{edge_words(duel, getattr(duel, who).name)}。{tell}{SCENE_RULE}"
    return f"奪璽單挑・『{shard}』", text
