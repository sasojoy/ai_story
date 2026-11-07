"""鐵匠鋪包：玩法說明「鐵匠鋪與神器」那一節（全部拆包第 59 批；原 tianxia/howto.py，字一個不動；順序在核心 HOWTO_ORDER）。"""
from __future__ import annotations

from tianxia import calendar, equipment, rules
from tianxia.core.howto_base import section as _section
from tianxia.models import Content
from tianxia.state import WorldState


def forge_lines(content: Content, season: WorldState) -> list[str]:
    """玩法說明「鐵匠鋪與神器」（待 joy 潤）：神器配方與線索照這一季開季時蓋的章寫（素材與經濟設計第二、三節；沒蓋章的季照舊的說法），
    殘譜照 Config.forge_secrets.scrap_every_mode。兵器、防具都關著是空的（整段不畫）。
    FB-268（PM 定，設計第九節「開關關著一個字都不變」）：只在新規則用得上時才畫——這一季蓋了每種兵器一條或線索分片的章，
    或線索分片、殘譜三種探索的開關開著；三個開關都關、季也沒蓋章時是空的（玩法說明跟改之前一字不差）。"""
    if not (equipment.on(content, "weapon") or equipment.on(content, "armor")):
        return []
    rule = content.config.forge_secrets
    if not (season.forge_divine_per_kind or season.forge_split_clues or rule.split_clues or rule.scrap_every_mode):
        return []
    lines = ["城鎮的鐵匠鋪賣兵器防具、修、淬煉，也能自己打造：照主料定階、輔料定屬性；打中這一季藏著的配方，打出名器。"]
    if any(r.divine for r in content.forge_secrets.values()):
        if season.forge_divine_per_kind and calendar.season_one_on(season, content):
            lines.append("每一種兵器這一季都有一條神器配方（防具一條）：全服第一把是原品、由你定名，之後照著打的是仿品。")
        elif season.forge_divine_per_kind:
            lines.append("神器配方照天機挑，同一種兵器最多一條：全服第一把是原品、由你定名，之後照著打的是仿品。")
        else:
            lines.append("這一季藏著幾條神器配方：全服第一把是原品、由你定名，之後照著打的是仿品。")
    if season.forge_split_clues:
        lines.append("神器配方的線索拆成三片：哪一種兵器、主料、輔料。在各家鐵匠鋪花了錢，鐵匠會順口說出他知道的片子（同一家說完之前不重複），"
                     "說書、殘譜也聽得到；三片湊齊，鑄譜上那一條就完整。")
    else:
        lines.append("配方的口訣聽說書、聽鐵匠順口、撿殘譜都聽得到，記在鑄譜上。")
    if rule.scrap_every_mode and rules.jianfa(content, season, "explore_one") and (rule.scrap_chance > 0 or content.config.secrets.scrap_chance > 0):
        lines.append("殘譜三種探索都撿得到。")
    return lines


def forge_section(content: Content, season: WorldState) -> list[str]:
    """「鐵匠鋪與神器」那一節（HOWTO_ORDER 的 forge）。"""
    return _section("鐵匠鋪與神器", forge_lines(content, season))
