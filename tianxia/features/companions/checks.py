"""人物情誼包的內容驗證（第二輪第 100 批從核心 content.py 搬來，本體照搬）：content.validate 在原位經 features.check_at 叫（格在 core/features.py 的 CONTENT_SLOTS），先後不變；關著的包照驗。"""
from __future__ import annotations

import re

from tianxia.models import Content
from tianxia.zh import to_traditional


def check_companions(c: Content, need) -> None:
    """歷史武將同行（Config.companions）：標了 recruitable 的人物不能是任何大勢人物（人物表寫了 character 的那十六位帶不走），
    要能深度對話（招募鈕照 Game._figures_here），side 寫的要是劇本的陣營。"""
    big = {fig.character for fig in c.figures.values() if fig.character}
    faction_ids = {f.id for f in c.scenario.factions}
    for cid, ch in c.characters.items():
        if not ch.recruitable:
            continue
        where = f"人物 {cid}"
        need(cid not in big, f"{where}：大勢人物不能標 recruitable（人物表寫了他）")
        need(ch.deep_interaction, f"{where}：標了 recruitable 要能深度對話（deep_interaction）")
        need(ch.side is None or ch.side in faction_ids, f"{where}：side {ch.side} 不是劇本的陣營")


STANCE_MAX = 3  # 一位人物最多幾個心意（整合設計 5.4「2～3 個」）


def check_stances(c: Content, need, where: str, fig) -> None:
    """人物心意（減法季批 6，整合設計 5.4）：要有對話人物（歸類在對話裡）、最多 STANCE_MAX 個、id 不重複、id 不是 stances.NONE；
    字只用繁體；改做的事裡痕跡的鍵是「地點 id:痕跡名」、地點存在、倍數至少 1。"""
    if not fig.stances:
        return
    need(fig.character is not None, f"{where}：有心意的人物要有對話人物（心意在跟他說話時歸類）")
    need(len(fig.stances) <= STANCE_MAX, f"{where}：心意最多 {STANCE_MAX} 個（現在 {len(fig.stances)} 個）")
    ids = [x.id for x in fig.stances]
    need(len(set(ids)) == len(ids), f"{where}：心意的 id 重複了（{ids}）")
    for x in fig.stances:
        at = f"{where} 的心意 {x.id}"
        need(x.id != "none", f"{at}：id 不能是 none（模型歸不進任何一種時填的）")
        for text in (x.name, x.hint, x.rumor, x.chronicle):
            need(to_traditional(text) == text, f"{at}：字只能用繁體中文（{text}）")
        for key, times in x.action.marks.items():
            loc, sep, name = key.partition(":")
            need(bool(sep and name) and loc in c.locations, f"{at}：痕跡要寫成「地點 id:痕跡名」、地點存在（{key}）")
            need(times >= 1, f"{at}：痕跡 {key} 的倍數至少 1")
        if x.action.event_daily is not None:  # 生效時開的人物事件（批 6 修正輪）：從探索的池子抽、可重複（每人每天一則由 stances 管）
            ev = c.events.get(x.action.event_daily)
            need(ev is not None, f"{at}：event_daily 的事件 {x.action.event_daily} 不存在")
            if ev is not None:
                need("explore" in ev.actions and not ev.once and not ev.qiyu and not ev.fortune and ev.free_text is None,
                     f"{at}：event_daily 的事件 {ev.id} 要是探索抽得到、可重複、沒有隨口應對的事件")


ERRAND_SLOTS = ("{place}", "{hero}")  # 託付的字認得的插槽（errands.give、task_text 填）


def check_errands(c: Content, need, where: str, fig) -> None:
    """託付的池子（減法季批 6，整合設計 5.5、5.9）：要有對話人物（信是他寫的）、id 不重複、地點存在；勸降要寫 persuade（勸不成打的隊伍存在、
    痕跡是「地點 id:痕跡名」、推的線是 front 或戰線 id），其他兩種不寫；寫了 stance 要是他自己的心意；字只用繁體、只用認得的插槽。"""
    if not fig.errands:
        return
    need(fig.character is not None, f"{where}：有託付的人物要有對話人物（託付以他的信送到）")
    ids = [d.id for d in fig.errands]
    need(len(set(ids)) == len(ids), f"{where}：託付的 id 重複了（{ids}）")
    stance_ids = {x.id for x in fig.stances}
    lines = {t.id for t in c.scenario.trends} | {"front"}
    for d in fig.errands:
        at = f"{where} 的託付 {d.id}"
        need(d.target in c.locations, f"{at}：地點 {d.target} 不存在")
        need(d.stance is None or d.stance in stance_ids, f"{at}：心意 {d.stance} 不是他的心意（{sorted(stance_ids)}）")
        need((d.kind == "persuade") == (d.persuade is not None), f"{at}：勸降才寫 persuade、勸降一定要寫")
        for text in (d.task, d.text, d.to):
            need(to_traditional(text) == text, f"{at}：字只能用繁體中文（{text}）")
            need(not [s for s in re.findall(r"\{[^}]*\}", text) if s not in ERRAND_SLOTS], f"{at}：只認得 {ERRAND_SLOTS}（{text}）")
        if d.persuade is not None:
            need(d.persuade.foe in c.squads, f"{at}：勸不成打的隊伍 {d.persuade.foe} 不存在")
            for key in d.persuade.marks:
                loc, sep, name = key.partition(":")
                need(bool(sep and name) and loc in c.locations, f"{at}：痕跡要寫成「地點 id:痕跡名」、地點存在（{key}）")
            need(set(d.persuade.trend) <= lines, f"{at}：推的線只能是 front 或戰線 id（{sorted(d.persuade.trend)}）")
