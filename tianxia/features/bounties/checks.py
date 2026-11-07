"""懸賞包的內容驗證（第二輪第 100 批從核心 content.py 搬來，本體照搬）：content.validate 在原位經 features.check_at 叫（格在 core/features.py 的 CONTENT_SLOTS），先後不變；關著的包照驗。"""
from __future__ import annotations

from tianxia.martial_arts import ATTRIBUTES
from tianxia.models import Content


def check_bounties(c: Content, need) -> None:
    """懸賞榜的設定（Config.bounties，懸賞榜設計 4.1 末段）：種類只能是認得的（不認得的 bounties.issue 會默默跳過）；求兵挑屬性的
    範圍至少一個、而且是認得的屬性；求兵的價錢剛好寫三個品質與四個階（1～4 階，四階 ×6；少一個，交那種兵器時會 KeyError）。
    give_kinds 只能是 arms（求藝企劃者 2026-10-21 拿掉，寫 art 直接報錯，不默默跳過）。
    give_kinds、give_attributes 不能重複：kinds 寫兩次 strike 是「掛兩張」，give_kinds 寫兩次 arms 卻只會掛一張（issue 照種類各掛一張），
    照 kinds 的習慣寫會被默默吃掉；give_attributes 重複會讓三方抽到同一個屬性。
    賞的字典（silver、exp、deeds、xinde）：設定覆寫檔寫了就是整張換掉，少寫 give_kinds 裡某一種的那一項，掛得出來、交得了，領到的卻默默是 0
    （bounties.py 都是 .get(種類, 0)）。所以預設有寫的項目，掛出去的每一種都要留著（預設 silver 沒有 arms：求兵的銀兩走 arms_silver × arms_tier）。"""
    cfg = c.config.bounties
    need(set(cfg.kinds) <= {"strike", "scout", "escort"}, f"Config.bounties.kinds 只能有 strike、scout、escort：{cfg.kinds}")
    need(
        set(cfg.give_kinds) <= {"arms"} and len(set(cfg.give_kinds)) == len(cfg.give_kinds),
        f"Config.bounties.give_kinds 只能有 arms（求藝 2026-10-21 拿掉），最多寫一次：{cfg.give_kinds}",
    )
    need(
        bool(cfg.give_attributes) and set(cfg.give_attributes) <= set(ATTRIBUTES)
        and len(set(cfg.give_attributes)) == len(cfg.give_attributes),
        f"Config.bounties.give_attributes 至少一個、不重複，而且只能是 {'、'.join(ATTRIBUTES)}：{cfg.give_attributes}",
    )
    need(set(cfg.arms_silver) == {"下品", "中品", "上品"}, f"Config.bounties.arms_silver 要剛好寫下品、中品、上品：{sorted(cfg.arms_silver)}")
    need(set(cfg.arms_tier) == {"1", "2", "3", "4"}, f"Config.bounties.arms_tier 要剛好寫 1、2、3、4：{sorted(cfg.arms_tier)}")
    defaults = type(cfg)()  # 預設長什麼樣，就是「該寫哪幾項」的依據
    for field in ("silver", "exp", "deeds", "xinde"):
        given = getattr(cfg, field)
        missing = [kind for kind in cfg.give_kinds if kind in getattr(defaults, field) and kind not in given]
        need(
            not missing,
            f"Config.bounties.{field} 少了 {'、'.join(missing)} 的賞（整張字典換掉時，give_kinds 裡每一種都要寫，少了會默默給 0）：{sorted(given)}",
        )
