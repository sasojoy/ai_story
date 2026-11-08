"""裝備包的內容驗證（第二輪第 100 批從核心 content.py 搬來，本體照搬）：content.validate 在原位經 features.check_at 叫（格在 core/features.py 的 CONTENT_SLOTS），先後不變；關著的包照驗。"""
from __future__ import annotations

from tianxia.martial_arts import ATTRIBUTES
from tianxia.models import Content, GOOD_HORSE, TREASURE_EFFECTS, WEAPON_KINDS
from tianxia.naming import GEAR_CLASH, name_problem
from tianxia.weapons import ATTR_WORDS as WEAPON_ATTR_WORDS, WEAPON_WORDS, shop_name as weapon_shop_name
from tianxia.zh import to_traditional


def check_gear(c: Content, need, known) -> None:
    """寶物表、名駒、名將贈禮（content/gear.json，裝備四欄 6.3、5.7）與 Config.treasures：效果的數字剛好八種；良駒的品質權重只寫
    三個品質、不是負的、加起來大於 0。有表時：掉落池至少一件；名字不重複、過得了命名過濾、id 不叫 good_horse、寶物與名駒的 id 不重複；
    贈禮的人物存在、一位只寫一次、送的是名駒或 pool 為 false 的寶物，送禮那一句是繁體、只用 {general}、{gift}；
    pool 為 false 的寶物與名駒都要有人送（不然永遠拿不到）。沒有 gear.json（測試內容）就只查設定。"""
    cfg, book = c.config.treasures, c.gear
    need(set(cfg.effects) == set(TREASURE_EFFECTS), f"Config.treasures.effects 要剛好寫八種效果：{sorted(cfg.effects)}")
    need(
        set(cfg.horse_quality) <= {"下品", "中品", "上品"} and all(v >= 0 for v in cfg.horse_quality.values())
        and sum(cfg.horse_quality.values()) > 0,
        f"Config.treasures.horse_quality 只能寫下品、中品、上品，權重不能是負的、加起來要大於 0：{cfg.horse_quality}",
    )
    if not (book.treasures or book.steeds or book.gifts):
        return
    need(any(t.pool for t in book.treasures.values()), "content/gear.json：掉落池（pool 為 true 的寶物）至少要一件")
    clash = sorted(set(book.treasures) & set(book.steeds))
    need(not clash, f"content/gear.json：寶物與名駒的 id 重複：{clash}")
    names: set[str] = set()
    for item in [*book.treasures.values(), *book.steeds.values()]:
        where = f"裝備表 {item.id}"
        need(item.id != GOOD_HORSE, f"{where}：id 不能叫 {GOOD_HORSE}（事件給良駒用的字）")
        need(item.name not in names, f"{where}：名字 {item.name} 重複")
        names.add(item.name)
        problem = name_problem(item.name, c)
        need(problem in (None, GEAR_CLASH), f"{where}：名字 {item.name} 過不了命名過濾（{problem}）")  # 寶物自己的名字現在會撞到自己
    given: set[str] = set()
    for gift in book.gifts:
        where = f"名將贈禮 {gift.character}"
        known(where, [gift.character], c.characters, "人物")
        need(gift.character not in given, f"{where}：同一位人物寫了兩次")
        given.add(gift.character)
        tdef = book.treasures.get(gift.gear)
        need(gift.gear in book.steeds or (tdef is not None and not tdef.pool), f"{where}：贈禮 {gift.gear} 要是名駒或 pool 為 false 的寶物")
        if gift.line:
            need(to_traditional(gift.line) == gift.line, f"{where}：送禮那一句只能用繁體中文")
            try:
                gift.line.format(general="甲", gift="乙")
            except (KeyError, IndexError, ValueError):
                need(False, f"{where}：送禮那一句只能用 {{general}}、{{gift}}")
    sent = {gift.gear for gift in book.gifts}
    for item_id in [t.id for t in book.treasures.values() if not t.pool] + list(book.steeds):
        need(item_id in sent, f"裝備表 {item_id}：沒有人送（pool 為 false 的寶物與名駒只從名將贈禮來）")


def check_signature_arms(c: Content, need, known) -> None:
    """名將本命兵器（content/gear.json 的 signature_arms，兵器設計 4.10）：人物存在、一位只寫一把；種類、屬性合法；名字跟寶物、名駒、
    隱藏配方的名器、別把本命兵器不重複（name_problem 對寶物表與本命兵器回同一句 GEAR_CLASH，蓋過 FORGE_CLASH，所以這裡另查），
    過得了命名過濾（自己的名字收 GEAR_CLASH），不能帶別種兵器的字、不能跟架上的現成兵器同名（一般組合字表組得出它的話，驗字表那一段
    的 name_problem 會擋下來，不必另查）；figure 是人物表上的大勢人物、而且就是這一位；兩句話是繁體、只用 {general}、{arm}。"""
    book = c.gear
    names = {item.name for item in [*book.treasures.values(), *book.steeds.values(), *c.forge_secrets.values()]}
    shop = {weapon_shop_name(k, a) for k in WEAPON_KINDS for a in WEAPON_ATTR_WORDS}
    seen: set[str] = set()
    for arm in book.signature_arms:
        where = f"本命兵器 {arm.character}"
        known(where, [arm.character], c.characters, "人物")
        need(arm.character not in seen, f"{where}：同一位人物寫了兩次")
        seen.add(arm.character)
        need(arm.kind in WEAPON_KINDS, f"{where}：種類 {arm.kind} 不是兵器種類")
        need(arm.attribute in ATTRIBUTES, f"{where}：屬性 {arm.attribute} 不認得")
        need(arm.name not in names, f"{where}：名字 {arm.name} 重複")
        names.add(arm.name)
        problem = name_problem(arm.name, c)
        need(problem in (None, GEAR_CLASH), f"{where}：名字 {arm.name} 過不了命名過濾（{problem}）")
        others = [word for kind, words in WEAPON_WORDS.items() if kind != arm.kind for word in words]
        need(not any(word in arm.name for word in others), f"{where}：名字 {arm.name} 帶了別種兵器的字")
        need(arm.name not in shop, f"{where}：名字 {arm.name} 跟架上的現成兵器同名")
        if arm.figure is not None:
            known(where, [arm.figure], c.figures, "大勢人物")
            fig = c.figures.get(arm.figure)
            need(fig is None or fig.character == arm.character, f"{where}：大勢人物 {arm.figure} 不是這一位")
        for label, line in (("送兵器那一句", arm.gift_line), ("奪兵器那一句", arm.seize_line)):
            if not line:
                continue
            need(to_traditional(line) == line, f"{where}：{label}只能用繁體中文")
            try:
                line.format(general="甲", arm="乙")
            except (KeyError, IndexError, ValueError):
                need(False, f"{where}：{label}只能用 {{general}}、{{arm}}")
