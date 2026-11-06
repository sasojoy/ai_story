"""修練包：玩法說明「心得」「修練與煉製」兩節（全部拆包第 59 批；原 tianxia/howto.py，字一個不動；順序在核心 HOWTO_ORDER）。"""
from __future__ import annotations

from tianxia.core.howto_base import section as _section
from tianxia.models import Content


def pages_lines() -> list[str]:
    """玩法說明「修練與煉製」：底部兩個分頁各做什麼（修練頁 pagePractice、煉製頁 pageCraft 的實際內容）。價錢寫在「心得」那一節。"""
    return [
        "**修練**：最上面是你的人物，點身上的光點看那一門功夫或那一件裝備。練成（花心得升一成）、每一門底下的意境槽（點空格裝意境、"
        "點 × 拆下，隨時換；槽收得下的屬性才裝得進去）、改練、熔掉用不上的武學與意境（拿回心得；功法庫上頭的「批量熔煉」一次勾一堆）、"
        "閉關、療傷（只在有醫館的城鎮）；上品、練滿十成的武學才有「修練」那一顆：等打贏硬仗的契機，或服破境丹強行衝關；"
        "底下是裝備（兵器、防具、坐騎、寶物）、同伴與部下（心得夠了可以傳功給他們）。",
        "**煉製**：太極火爐只放意境：兩個不同的意境合出新的意境、同一種的兩份揣摩得更深；放進爐裡的都不會用掉。"
        "武學不拿來合，意境到「修練」去裝進武學的槽。爐子底下的「自創武學」另開一頁，花心得自創一門上品武學"
        "（執器、擺式、立意、成形、立名五步；按下立意就收心得、擱下不退，成了形不滿意可以用萬寶閣的重悟帖重骰形、或重讀那一句意）。每一門功夫都有自己的一手招，功法卡上招名前面蓋一枚印：學來的蓋「看家」、"
        "人物的本命蓋「本命」、自創的蓋你名號的第一個字、練成絕學的絕招蓋金色的「絕」。"  # 待 joy 潤
        "最底下是背包。",
    ]


def xinde_section(content: Content) -> list[str]:
    """「心得」那一節（HOWTO_ORDER 的 xinde）。"""
    cfg = content.config
    return [
        "#### 心得",
        f"- 學武的本錢：練成（第 N 成升下一成花 N×{cfg.practice_xinde_per_level}）、"
        f"兩個意境合併（{cfg.merge_xinde} 心得、{cfg.merge_stamina} 體力）、自創武學都花它。",
        f"- 打贏、操練、閉關（每小時至少 {cfg.seclusion_xinde_per_hour}，悟性越高越多）、邊走邊想（{cfg.road_think_xinde}）都有心得；"
        "用不上的功法熔掉也能拿回一些。狀態列的 💡 會在你付得起、又真的有事可做時提醒你去哪一頁。",
        "",
    ]


def pages_section() -> list[str]:
    """「修練與煉製」那一節（pages）。"""
    return _section("修練與煉製", pages_lines())
