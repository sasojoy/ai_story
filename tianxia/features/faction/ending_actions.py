"""季末與三方卡（三陣營四勝利，減法季整合設計第三章；全部拆包第 35 批；原本是 Game 上的 _season_grant、_four_wins、ending_card、_tier_outlook、
tier_hint、_gentry_now、sides_card，本體一字沒改，self 換成 ctx）。Game 留一行委派的：_season_grant（換季開場）、_four_wins（核心與決戰包都在問）、
ending_card（season_result、server）、tier_hint、sides_card（weekcard、server）；_tier_outlook、_gentry_now 只有包裡叫（沒有委派）。
"""
from __future__ import annotations

from tianxia import allied, wins
from tianxia.characters import CharacterStore, name_key
from tianxia.rules import stances
from tianxia.state import GameState, TierResult
from tianxia.world import _season_vehicle, evaluate_ending


def season_grant(ctx, old: GameState) -> None:
    """三陣營四勝利（減法季設計 3.3）：上一季收季時論了功的人（那一季的 WorldState.final_tiers），新的一季開局照那一階發起手資源
    （wins.start_grant）、掛上稱號（PlayerState.season_title，social.affiliation 接在後面），另寫一則江湖紀錄。
    上一季沒論功（四勝利關著、散人、不到門檻）什麼都不做，一個字都不變。不看新的一季開不開四勝利：獎勵是上一季掙的。"""
    past = ctx.world.past_season(old.player.season_number)
    result = past.final_tiers.get(old.player.name) if past is not None else None
    if result is None or not result.tier:
        return
    silver, xinde = wins.start_grant(wins.rules_of(ctx.content), result.tier)
    p = ctx.state.player
    p.stats["silver"] = p.stats.get("silver", 0) + silver
    p.stats["xinde"] = p.stats.get("xinde", 0) + xinde
    p.season_title = result.title
    line = wins.GRANT_LINE.format(tier=wins.TIER_NAMES[result.tier], title=result.title)
    ctx._write(wins.GRANT_TITLE, [line] + [f"{name} +{n}" for name, n in (("銀兩", silver), ("心得", xinde)) if n])


def four_wins(ctx) -> bool:
    """這一季三陣營四勝利開著嗎（wins.on：減法季的總開關 Config.jianfa＋開季的章）。"""
    return wins.on(ctx.content, ctx.state.world)


def ending_card(ctx) -> dict | None:
    """結局卡（欄位表 main.ending；設計 3.4）：收季之後、四勝利開著的季才有。winner 是贏的那一軍（和局 None），condition 是你算在
    哪一條（兩軍是陣營名，豪強是「地方豪強（官軍）」；散人、豪強沒有階是 None），my_tier 第幾階（0 是沒有），title 稱號，
    reward 下一季分到的，ledger_used 照哪一本排（豪強和局是 wins.BOTH）。收季那一刻存好（WorldState.final_tiers），這裡只讀。"""
    s, c = ctx.state, ctx.content
    w = s.world
    if not w.ended or not ctx._four_wins():
        return None
    result = w.final_tiers.get(s.player.name)
    tier = result.tier if result is not None else 0
    return {
        "winner": wins.winner_of(w, c), "condition": wins.condition_of(c, s.player.faction, result), "my_tier": tier,
        "title": result.title if result is not None else "", "reward": wins.reward_text(wins.rules_of(c), tier),
        "ledger_used": result.ledger_used if result is not None else None,
    }


def tier_outlook(ctx) -> tuple[TierResult, int | None]:
    """此刻就收季（結局照此刻會成立的那一種，world.evaluate_ending）自己拿第幾階、離上一階還差多少（wins.outlook）。名次要讀
    這一季每個人的帳（CharacterStore.books，只挑那幾欄）；自己照記憶體裡的這一份（這一下剛記的貢獻可能還沒存）。"""
    s, c = ctx.state, ctx.content
    me = s.player
    others = [q for q in CharacterStore(ctx.world.db).books(me.season_number) if name_key(q.name) != name_key(me.name)]
    winner = evaluate_ending(_season_vehicle(c, s.world), c).winner
    return wins.outlook(c, [*others, me], me.name, winner)


def tier_hint(ctx) -> str | None:
    """三方卡的 tier_hint（weekcard.sides_card，批 3c）：此刻就收季拿第幾階・離上一階還差多少（「第三階・還差 40」「第一階」
    「未入階・還差 20」，wins.tier_hint）。四勝利開著、季還沒收、投靠了劇本裡的陣營才有；其餘是 None。"""
    s, c = ctx.state, ctx.content
    if not ctx._four_wins() or s.world.ended or c.scenario.find_faction(s.player.faction) is None:
        return None
    return wins.tier_hint(*tier_outlook(ctx))


def gentry_now(ctx, faction) -> str:
    """三方卡豪強那一欄的「現在」：看的人是豪強寫此刻幫誰與兩本帳（設計 3.4），其他人寫此刻依附兩軍各幾人（投靠名冊）。"""
    s, c = ctx.state, ctx.content

    def name(side: str) -> str:
        return c.scenario.faction_name(side, side)

    if s.player.faction == faction.id:
        books = "、".join(wins.NOW_GENTRY_BOOK.format(side=name(side), n=n) for side, n in (wins.ledger_view(s.player, c) or {}).items())
        return wins.NOW_GENTRY_MINE.format(side=name(s.player.ally) if s.player.ally else "", books=books)
    rolls = allied.gentry_totals(ctx.world.roll_counts())
    return "、".join(wins.NOW_GENTRY_ROLL.format(side=name(side), n=rolls.get(side, 0)) for side in faction.allies)


def sides_card(ctx) -> dict | None:
    """三方卡的批 3c 資料（設計 3.4）：劇本的每一方（陣營 id →）{name, goal 要做到, reward 贏了給, join_at 投靠在哪
    [{location, name, minutes}], now 現在}，稱號與比例照 Config.jianfa.tiers。畫面的三方卡是批 1 的 weekcard.sides_card
    （欄位表 main.sides_card），它拿這一份補豪強那一格的「現在」、每一方的「贏了給」與投靠點的分鐘；最後一週「離贏還差多少」
    在 week_unlock.win_gap（wins.gap_line）。四勝利關著、休季沒有。"""
    s, c = ctx.state, ctx.content
    w = s.world
    if not ctx._four_wins() or w.ended:
        return None
    standing = stances(s, c)
    out = {}
    for f in c.scenario.factions:
        now = gentry_now(ctx, f) if f.allies else wins.NOW_ARMY.format(value=standing.get(f.id, 0))
        out[f.id] = {
            "name": f.name, "goal": wins.goal_text(c, f), "reward": wins.reward_card(c, f),
            "join_at": [{"location": loc, "name": c.locations[loc].name, "minutes": ctx.place_minutes(loc)} for loc in f.join_at],
            "now": now,
        }
    return out
