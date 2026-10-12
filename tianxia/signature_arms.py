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

from . import figures, treasures, weapons
from .models import Content, SignatureArmDef
from .rules import add_chronicle, add_rumor
from .state import Equipment, GameState, PlayerState, SignatureClaim

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
HOW = {"gift": "親手相贈", "seized": "屢敗之後被奪走"}  # 待 joy 潤：神器譜那一行「怎麼到他手上的」
# 待 joy 潤：神器譜一行（同 forge_secrets.divine_book 的寫法：季、名字、種類・屬性、原品在誰手上）
BOOK_LINE = "- 第 {season} 季　【{arm}】　{noun}・屬{attribute}　{general}的本命兵器，{how}，在{owner}手上"


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


def due(state: GameState, content: Content, *, beaten: str | None = None) -> tuple[list[Equipment], list[str]]:
    """該給的本命兵器給出去（兵器設計 4.10）：這一季還沒給過人的每一位名將，情誼到 signature_affinity 是他送的（gift），
    不然內容寫了 figure、你這一季打贏他本人 signature_wins 次是你奪走的（seized）。記下歸屬（WorldState.signature_arms，呼叫端那一下
    動作最後 _save_season 存回去）、交到你手上（裝備庫滿了寄放，treasures.deliver hold=True）、江湖史一行、天下大事傳聞一句（具名）。
    兵器關著不給也不記（開了之後照樣給得出去）。寫了 figure 的那一位這一季退場或重創就不給——beaten 是他（把他打到重創的這一場）例外。
    回（給出去的那幾把, 江湖紀錄的話）。不擲骰。"""
    p, w, cfg = state.player, state.world, content.config.weapons
    if not cfg.enabled:
        return [], []
    items: list[Equipment] = []
    lines: list[str] = []
    for arm in content.gear.signature_arms:
        if arm.character in w.signature_arms:
            continue
        if arm.figure is not None and arm.figure != beaten and figures.is_out(state, arm.figure):
            continue  # 退場、重創：這一季不再出現，本命兵器也跟著沒了（挑戰每季都有設計 3.5、5.4）
        if p.affinities.get(arm.character, 0) >= cfg.signature_affinity:
            via = "gift"
        elif arm.figure is not None and p.figure_wins.get(arm.figure, 0) >= cfg.signature_wins:
            via = "seized"
        else:
            continue
        w.signature_arms[arm.character] = SignatureClaim(owner=p.name, via=via)
        item = new_arm(state, arm)
        words = {"general": content.characters[arm.character].name, "arm": item.name}
        line = (arm.gift_line or GIFT_LINE) if via == "gift" else (arm.seize_line or SEIZE_LINE)
        lines.append(line.format(**words))
        lines += treasures.deliver(state, content, item, hold=True)
        add_chronicle(state, (CHRONICLE_GIFT if via == "gift" else CHRONICLE_SEIZED).format(who=p.name, **words))
        add_rumor(state, (RUMOR_GIFT if via == "gift" else RUMOR_SEIZED).format(who=p.name, **words), None, content=content, named=True)
        items.append(item)
    return items, lines


def annal_line(content: Content, item: Equipment, via: str) -> str:
    """行狀那一句（人物）：誰把哪一把交給你、或你奪走了誰的。"""
    general = content.characters[item.signature].name if item.signature in content.characters else item.signature
    return (ANNAL_GIFT if via == "gift" else ANNAL_SEIZED).format(general=general, arm=item.name)


def book_rows(content: Content, records: list[tuple[int, dict[str, SignatureClaim]]]) -> list[tuple[int, str]]:
    """神器譜裡本命兵器那幾行（打造隱藏配方設計 5.5：本命兵器也上神器譜）：（季數, 那一行），照季、同一季照給出去的先後。
    名字、種類、屬性照現在的內容（joy 改了名，譜上跟著改）；內容拿掉了那一把不寫。"""
    table = {arm.character: arm for arm in content.gear.signature_arms}
    rows: list[tuple[int, str]] = []
    for season, claims in records:
        for cid, claim in claims.items():
            arm = table.get(cid)
            if arm is None:
                continue
            general = content.characters[cid].name if cid in content.characters else cid
            rows.append((season, BOOK_LINE.format(
                season=season, arm=arm.name, noun=weapons.NOUNS.get(arm.kind, arm.kind), attribute=arm.attribute,
                general=general, how=HOW[claim.via], owner=claim.owner,
            )))
    return rows
