"""名將本命兵器（docs/superpowers/specs/2026-10-09-兵器-design.md 4.10；打造第三批，計畫 plans/2026-10-12-打造-3-名將本命兵器.md）。

- 七位名將各一把（content/gear.json 的 signature_arms，暫名待 joy 潤）。情誼到 Config.weapons.signature_affinity 他送你；內容寫了 figure
  的那幾位（現在只有孫堅），這一季打贏他本人 signature_wins 次他讓你奪走（PlayerState.figure_wins，Game._challenge 記）。
- 每位名將每季全服一人：WorldState.signature_arms（鎖內改、動作最後 _save_season 存回去，同名將贈禮 treasures.gifts_due）。
- 拿到的那一把是三階上品、神器原品（original=True：加成照 Config.weapons.original_base，打造隱藏配方設計 4.3）、signature 記人物 id；
  沒有 secret，神器定名、名器、鑄譜都不碰它。名字照內容讀（refresh_names）；拆不得、交不得（equipment.kept、bounties.fit_problem）。
- 拿到時江湖史一行、天下大事傳聞一句（具名）；上神器譜（book_rows，forge_secrets.divine_book 併進去，跨季讀 seasons 表）。
- 不擲骰：兩條路都是門檻，不碰 Game.rng（FB-129）。

只 import models、state、weapons、treasures、figures、rules；只有 engine import 這裡。
"""
from __future__ import annotations

from . import weapons
from .models import Content, SignatureArmDef
from .state import Equipment, GameState, PlayerState

# 待 joy 潤：{general} 是名將的名字、{arm} 是兵器的名字、{who} 是拿到的人的名號。內容的 gift_line／seize_line 有寫就照內容
GIFT_LINE = "{general}解下【{arm}】遞給你：『這把跟了我多年，往後交給你了。』"  # 兵器設計 4.10 的暫用句
SEIZE_LINE = "{general}屢敗在你手下，長嘆一聲，把【{arm}】擲在你腳下：『拿去吧。』"
GAIN_LINE = "本命兵器【{name}】"  # 戰報「得失」那一格（同 treasures.GAIN_LINE）
CHRONICLE_GIFT = "{general}把本命兵器【{arm}】送給了{who}。"
CHRONICLE_SEIZED = "{who}屢敗{general}，奪走了他的本命兵器【{arm}】。"
RUMOR_GIFT = "聽說{general}把隨身多年的【{arm}】給了{who}。"
RUMOR_SEIZED = "聽說{general}的【{arm}】被{who}奪走了。"
ANNAL_GIFT = "{general}把本命兵器【{arm}】交給了你。"  # 行狀（人物）
ANNAL_SEIZED = "你屢敗{general}，奪走了他的本命兵器【{arm}】。"


def owned(p: PlayerState) -> list[Equipment]:
    """身上、裝備庫、寄放的本命兵器。"""
    return [item for item in (p.weapon, *p.rack, *p.held_gear) if item is not None and item.signature is not None]


def new_arm(state: GameState, arm: SignatureArmDef) -> Equipment:
    """新的一把本命兵器（四欄共用的流水號 +1，id「兵:N」）：三階上品、神器原品（加成照 original_base），signature 記人物 id。"""
    item = weapons.new_weapon(state, name=arm.name, kind=arm.kind, attribute=arm.attribute, tier=3, quality="上品", original=True)
    item.signature = arm.character
    return item


def refresh_names(p: PlayerState, content: Content) -> None:
    """讀檔時照內容重寫本命兵器的名字（name 只當備份；同 treasures.refresh_names）：joy 改了名字，手上的跟著改；內容拿掉了那一把
    留著舊名字（加成照神器原品，不看內容）。Game._drop_stale_references 每次建 Game 都叫。"""
    table = {arm.character: arm for arm in content.gear.signature_arms}
    for item in owned(p):
        arm = table.get(item.signature)
        if arm is not None:
            item.name = arm.name
