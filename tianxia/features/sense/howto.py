"""有所感包：玩法說明「意境」那一節（全部拆包第 59 批；原 tianxia/howto.py，字一個不動；順序在核心 HOWTO_ORDER）。"""
from __future__ import annotations

from tianxia import precise, rules
from tianxia.core.howto_base import tenth as _tenth
from tianxia.models import Content
from tianxia.state import WorldState

# 意境提示設計第二節（不寫數字）。輿圖第三版拿掉了意境濾鏡（第 4 批），第 5 批改寫成區圖名字底下的意境字與卡上的「最濃」（PM 2026-10-22；待 joy 潤）
STRONG_HOWTO = "每個地點有一種意境最濃（區圖上名字底下排第一的意境字、卡上「此地能悟」標著「最濃」的那一個），選對那一種的做法比較容易悟成。"
# 地利（武學隨地理環境計畫 Task 5；不寫倍數，待 joy 潤）
TERRAIN_HOWTO = ("- 各地的氣象不同：身上的武學、內功跟此地最濃的意境同一路，打起來順手；被它剋的，施展不開。"
                 "輿圖上點地點，「地利」那一段寫著此地利哪一路。")


def insight_section(content: Content, season: WorldState) -> list[str]:
    """「意境」那一節（HOWTO_ORDER 的 insight）。"""
    cfg = content.config
    outing = rules.jianfa(content, season, "explore_one")
    sense_when = "靜心感悟" if outing else "探索落在悟意境"
    return [
        "#### 意境",
        # 有所感（sensing.choose、sensing.menu）：選對了還要擲一次（rate，沒中給 sense_miss_xinde）；中了可以畫、也可以順其自然（審查 M2）
        # 選錯了要到換日才悟得出（sensing.missed_today；遊戲日跟著季長縮）：說明頁不看此刻，不寫「今天」，寫「一陣子」，時刻看卡上那一行
        f"- {sense_when}時「有所感」，先選做法："
        + (f"選錯了得 {cfg.sense_miss_xinde} 心得，那裡照樣悟得出；" if precise.on(content, season)
           else "選錯了，那裡要過一陣子才悟得出（選之前卡上就寫著要到什麼時候）；")
        + "選對了還要看機緣（沒抓住也有一點心得），"
        "抓住了可以畫一筆，也可以順其自然。哪裡悟得到什麼看地形。" + (STRONG_HOWTO if cfg.insight_strong.enabled else ""),
        *([TERRAIN_HOWTO] if cfg.terrain_arts.enabled and cfg.insight_strong.enabled else []),
        "- 善名、惡名夠高也會悟到意境。合併、揣摩都不會把意境用掉（自己熔掉才沒了）。",
        "- 意境就是技能：裝進武學的意境槽才生效，一個意境同時只能裝在一門上。武學的品級定槽數"
        f"（{'、'.join(f'{q} {n} 格' for q, n in cfg.arts.slots.items())}），也定威力的上限；槽只收那門武學相容的屬性（基礎武學什麼都收）。"
        f"悟到已經會的，化成 {cfg.duplicate_insight_xinde} 心得。",
        # 同效果好幾份（Joy 2026-10-22 選「第二份算半」；「玩家需要知道這個知識」）。照身上兩門一起算（traits.loadout）。待 joy 潤
        f"- 身上兩門武學的意境一起算：同一個效果第二份起算{'一半' if cfg.arts.stack_share == 0.5 else _tenth(cfg.arts.stack_share)}，"
        f"最多到上限的{'一倍半' if cfg.arts.stack_ceiling == 1.5 else f' {cfg.arts.stack_ceiling:g} 倍'}；"
        "同一個真意第二份多一半發動的機會"
        + (f"（本來就每次發動的{'、'.join(always)}改成多撐一回合）" if (always := [h.name for h in content.traits.high if (h.tactic.rate or 0) >= 1]) else "")
        + "，第三份起不再加。修練頁格子上寫著每一份算了幾成。",
        "- 同一個意境放兩次揣摩，強度從 ● 到 ●●●，就是那一招的層數；兩個不同的意境合出複合的意境，是更高階的一招。"
        "兩門武學合出第三門：品級取高的，兩門都練滿、槽都裝滿再升一品（最高上品），槽收的屬性是兩門合起來。",
        "",
    ]
