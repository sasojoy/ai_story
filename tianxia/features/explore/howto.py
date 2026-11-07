"""探索包：玩法說明自己那幾句（全部拆包第 59 批；原 tianxia/howto.py，字一個不動）：行動列底下探索那一行（explore_line、outing_line）、
說明頁探索那一條（順序在核心 HOWTO_ORDER）。"""
from __future__ import annotations

from collections.abc import Sequence

from tianxia import rules
from tianxia.models import Content
from tianxia.state import WorldState

from . import explore_rules as explore_one  # 行動列底下那一行用同一份兩個字的叫法

# 探索三選一的三支（models.EXPLORE_BRANCHES）在說明裡怎麼叫
BRANCH_WORDS: dict[str, str] = {"insight": "悟意境", "wild": "遇野怪", "event": "碰上事件"}


def explore_line(
    weights: Sequence[tuple[str, float]], legend: str | None = None, blocked: bool = False, until: str | None = None,
    later: bool = False,
) -> str:
    """探索這一下多半會怎樣。weights 是探索真的擲骰用的那一份（支, 比重）：照地點類型（Config.explore_mix）、
    做不了的已經拿掉、悟意境那一支乘過悟性（Game._explore_weights）。比重嚴格最大的那一支寫「多半」，其他寫「也可能」
    （照比重由大到小）；並列最大就一起寫「可能」；只剩一支寫「會」（FB-101）。不寫百分比。legend 是破境丹的名字（探索每次另擲一次撿不撿得到；
    機率是 0 時呼叫端給 None）。blocked：悟意境那一支只因為這個遊戲日在這裡選錯過做法才拿掉（explore_actions.insight_blocked）；
    句尾補一句什麼時候才悟得出——until 是換日的那一刻（rules.day_turn，已經照季的時間寫法寫好），None 是這一季之內
    不會再換日；later：還會換日、只是季末延後了寫不出那一刻（FB-102），不承諾時刻（待 joy 潤）。"""
    ranked = sorted((pair for pair in weights if pair[1] > 0), key=lambda pair: -pair[1])  # 穩定排序：並列照原本的順序
    words = [BRANCH_WORDS[branch] for branch, _ in ranked]
    if not words:
        head = "這裡多半一無所獲"
    elif len(words) == 1:  # 只剩一支走得了（FB-101）：不說「多半」，好像還有別的可能
        head = f"這裡會{words[0]}"
    elif ranked[0][1] > ranked[1][1]:
        head = f"這裡多半{words[0]}，也可能{'、'.join(words[1:])}"
    else:
        head = f"這裡可能{'、'.join(words)}"
    tail = "" if not blocked else f"；這裡要到 {until} 之後才悟得出" if until else "；這裡要過一陣子才悟得出" if later \
        else "；這一季之內這裡悟不出了"
    return head + (f"；偶得{legend}" if legend else "") + tail


# 減法季探索一顆（整合設計 4.1，批 2）：行動列底下探索那一行。照擲骰用的那一份比重（探索包 explore_actions.outing_weights）排，不寫百分比；都待 joy 潤
OUTING_WORDS = explore_one.BEAT_WORDS
OUTING_HEAD = "出門一趟只碰上一件事"  # 2d（企劃者 2026-10-26「只抽一件事情」）：以前寫「出門一趟走三拍」
OUTING_FOE = {"town": "；城裡遇敵是街上的地痞，給得少", "spar": "；自家營寨遇敵是跟同袍比劃，不掉東西"}
OUTING_BOUNTY = "出門一趟，接了這裡的討伐，每一趟都撞上懸賞那一路，交了差才回到平常"  # 接了這裡的討伐懸賞：整行換成這一句（一定是遭遇，不寫機率）


def outing_line(weights: dict[str, float], foe: str | None = None) -> str:
    """探索一顆開著時行動列底下探索那一行（Game.action_notes）：weights 是這一處這一趟四類事的比重（做不了的已經是 0）；比重最大的寫「多半」、
    其他照大小寫「也可能」，並列最大一起寫「可能」，只剩一類寫「會」（同 explore_line 的寫法）。foe：城裡的地痞（"town"）、自家營寨的比劃
    （"spar"）各補一句；接了這裡的討伐（"bounty"）整行換成 OUTING_BOUNTY（每一趟都是懸賞那一路的遭遇）；其餘 None。"""
    if foe == "bounty":
        return OUTING_BOUNTY
    ranked = sorted(((k, w) for k, w in weights.items() if w > 0), key=lambda pair: -pair[1])
    words = [OUTING_WORDS[k] for k, _ in ranked]
    if len(words) == 1:
        body = f"，會{words[0]}"
    elif ranked and ranked[0][1] > ranked[1][1]:
        body = f"，多半{words[0]}，也可能{'、'.join(words[1:])}"
    else:
        body = f"，可能{'、'.join(words)}" if words else ""
    return OUTING_HEAD + body + OUTING_FOE.get(foe or "", "")


def outing_lines(content: Content, season: WorldState | None = None) -> list[str]:
    """減法季探索一顆（整合設計 4.1，批 2；2d 企劃者 2026-10-26 改成一趟一件事；待 joy 潤）的玩法說明：一顆、出門一趟碰上一件事、
    地點決定多半給什麼、地痞與比劃、懸賞。數字讀 Config.jianfa。"""
    jf = content.config.jianfa
    tables = "，".join(explore_one.named_hint(t) for t in jf.explore_tables)
    legend = f"偶爾撿到{content.config.legend_item_name}。" if content.config.explore_legend_chance > 0 else ""
    return [
        f"- **探索**（體力 {jf.explore_stamina}）：只有一顆，按一下是出門一趟，一趟只碰上一件事，"
        f"照這個地方抽遇事、遇敵、得料或有悟其中一件——地點決定多半給什麼（{tables}），危險的地方遇敵多些、遇事少些，運氣決定這一趟給什麼。"
        "得料、遇敵當場算完；遇事、有悟要你自己選。回來是一段話，底下一行寫這一趟的得失。"
        "城裡沒有對手時遇上的是街上的地痞，給得少；自家營寨遇敵是跟同袍比劃，不受傷也不掉東西。"
        f"接了這裡的討伐懸賞，在那裡出門每一趟都撞上懸賞那一路，交了差才回到平常。{legend}",
    ]


def _kind_name(tags: Sequence[str]) -> str:
    """一種地點類型（Config.explore_mix 的一筆）怎麼叫：照它的標籤（三個以上寫「等地」）；沒有標籤的是「其他地方」。"""
    if not tags:
        return "其他地方"
    return "、".join(tags[:3]) + ("等地" if len(tags) > 3 else "")


def mix_sentence(content: Content) -> str:
    """玩法說明裡探索的比例：每一種地點類型一句「營寨、祭壇、塢堡多半碰上事件，也可能遇野怪、悟意境」——跟探索擲骰讀同一份
    Config.explore_mix（還沒扣掉「這裡做不了」的支：那是行動列底下那一行的事）。"""
    return "；".join(
        _kind_name(mix.tags) + explore_line(list(mix.weights.items())).removeprefix("這裡") for mix in content.config.explore_mix
    )


def explore_section(content: Content, season: WorldState) -> list[str]:
    """玩法說明探索那一條（HOWTO_ORDER 的 explore）：探索一顆開著寫 outing_lines，關著寫舊探索。"""
    cfg = content.config
    cost = cfg.action_cost
    if rules.jianfa(content, season, "explore_one"):
        return outing_lines(content, season)
    legend = f"每次探索還有機會撿到{cfg.legend_item_name}。" if cfg.explore_legend_chance > 0 else ""
    # 舊探索（照地點比例自動抽；探索一顆開著時換成 outing_lines）
    old_explore = [f"- **探索**（體力 {cost['explore']}）：照地點三選一：悟意境、遇野怪、碰上事件。{mix_sentence(content)}。偶有奇遇。{legend}"]
    return old_explore
