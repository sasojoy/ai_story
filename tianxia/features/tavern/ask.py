"""問酒家照問題找事實（企劃者 2026-10-27「打聽的功能太弱了，應該大大小小的東西都可以問」）。

以前酒家只知道這一區的局勢、最近六則傳聞、這裡採得到什麼，加上座上客與問話的人自己；題目不在那幾條裡，模型照規定說不清楚，
多數題答不出來。這裡從問句認出問的是什麼（名號、地名、素材、武學、門派、店面、玩法、季勢），從全服抓那一樣的事實，照打聽度
過濾精確度（玩家只說到大區；確切地點留給「查人」）；什麼都沒認出來時給一包常識（附近城鎮與店面、野外的危險與出產、季勢）。
每一條一句、照 `topics` 排在清單最前面；`kinds` 回問到的是哪幾類，答不出來時酒家照它指一條路（`pointer`）。
只讀、只組字、不擲骰（打聽度照 tavern 的公式，一半機會那一格照 tavern.rng_for）。玩家那一份由呼叫端（Game._tavern_ask_facts）
從問句裡的名號載入，這裡不碰資料庫。秘密（配方、口訣、鑄譜、誰是假人）照舊不在清單裡（tavern.SECRET_WORDS 在 A 段就擋了）。"""
from __future__ import annotations

from tianxia import calendar, rules
from tianxia.characters import name_key
from tianxia.models import Content
from tianxia.state import GameState

from . import rules as tavern

# 店面：問到這些字就說最近哪幾處有。鐵匠鋪在帶「城鎮」標籤的地點（equipment.in_town），其餘照地點標籤
SHOPS = (
    ("smith", "鐵匠鋪", ("鐵匠", "打鐵", "兵器", "打造", "鍛造", "淬煉", "修刀", "修劍", "防具", "盔甲", "護甲", "買刀", "買劍", "武器")),
    ("clinic", "醫館", ("醫館", "療傷", "治傷", "養傷", "大夫", "郎中", "受傷", "內傷", "氣血", "看病")),
    ("market", "馬市", ("馬市", "買馬", "坐騎", "馬匹", "良駒", "餵馬", "得到馬", "騎馬", "匹馬")),
    ("tavern", "酒肆", ("酒肆", "酒館", "酒樓", "打聽")),
)
SHOP_LINE = "{shop}：最近的是{places}。"
SHOP_NONE = "這一帶沒有{shop}。"
PLACE_LINE = "{name}在{region}，從這裡走{far}。{kind}{shops}"
PLACE_HERE = "{name}就是這裡，在{region}。{kind}{shops}"
PLACE_SHOPS = "有{shops}。"
PLACE_KIND = {"town": "是城鎮，城裡不便動手。", "wild": "是野外，", "camp": "是營寨，"}
DANGER = {0: "太平", 1: "還算太平", 2: "有些風險", 3: "兇險", 4: "非常兇險"}
PLACE_DANGER = "{word}。"
PLACE_MATS = "一帶採得到{mats}。"
PLACE_SECT = "{sect}就在那裡。"
FAR = {0: "就到", 1: "一站路", 2: "兩站路", 3: "三站路"}
FAR_MORE = "四站以上的路"
FIGURE_SIDE = "{name}是{side}的人。"
FIGURE_STORY = "{name}的出身：{text}"
FIGURE_NOW = "{name}眼下：{text}"
PLAYER_REGION = "江湖人{name}，聽說在{region}一帶；要問確切在哪，得用「查人在哪」。"
PLAYER_FAINT = "江湖人{name}，酒家只聽過名頭，不知道在哪。"
SKILL_LINE = "{name}是一門{quality}的{kind}，走{attr}的路子。{learn}"
SKILL_LEARN = "在{place}學得到。"
SKILL_FIGURE = "是{who}的看家本事。"
SECT_LINE = "{name}在{place}，是{align}道的門派。{desc}"
MAT_SHOP = "{name}在這間酒肆就買得到，一份 {price} 兩。"
SEASON_LINE = "眼下是{when}。"
SEASON_LEFT = "這一季還剩大約 {days} 天。"
HELLO_TOWNS = "附近的城鎮：{towns}。"
HELLO_WILDS = "附近的野外：{wilds}。"
ERA = "天下的大勢：甲子年太平道三十六方同日起事，頭裹黃巾；朝廷派中郎將分頭討伐，各地豪強也拉起鄉勇自保。"

# 玩法：問句裡有這些字就附這一句（數字照 Config 讀，不寫死）。玩家文字的說法，跟攻略一致
GUIDE: tuple[tuple[tuple[str, ...], str], ...] = (
    (("升級", "經驗", "等級", "練功", "變強"), "要長本事，城外打贏對手給的經驗最多；城裡操練穩拿心得；升一級給屬性點，自己配。"),
    (("體力", "累", "精力"), "體力會自己慢慢回；探索、出陣、交友都花體力，閉關、移動不花。"),
    (("氣血", "受傷", "療傷", "醫館", "內傷"), "氣血少了去醫館花銀兩療傷，內傷也是醫館治；歇著也會慢慢回。"),
    (("合成", "煉丹", "意境", "頓悟", "悟"), "意境在各地靜心感悟或打仗時悟出來；兩門意境可以在煉丹爐合成新的。"),
    (("武學", "招式", "功夫", "學武", "拜師"), "基礎武學在各地武館、營地、門派學，名望與銀兩夠了才肯教；武學練到頂可以練成絕學。"),
    (("投靠", "陣營", "官軍", "黃巾", "豪強", "散人"), "剛入江湖是散人；在陣營的營地按「投靠」入伙，也可以拜入陣營名下的門派。"),
    (("出陣", "戰線", "攻城", "打仗", "領地"), "投靠了陣營就能出陣，打贏推動那一塊地的進度、記貢獻；兩軍搶地，佔得多戰線就偏過去。"),
    (("銀兩", "賺錢", "缺錢", "沒錢", "銀子"), "銀兩靠打贏對手、揭懸賞交差、賣素材來；花在療傷、打造、買馬、學武與酒肆。"),
    (("懸賞", "通緝", "榜"), "城鎮裡有懸賞榜，揭了照上面寫的去辦，回來交差拿賞。"),
    (("截殺", "殺人", "偷襲", "仇家"), "野外遇上別一方的人可以截殺；城鎮裡不便動手，新手期也不能碰。"),
    (("殺手", "買兇", "刺客", "保鏢"), "酒肆暗處買得到殺手，報一個查到過的名號；殺手只在城外出手，怕被找上可以雇保鏢、藏行跡。"),
    (("名望", "出名", "名氣", "稱號"), "名望靠打贏有名的對手、立功、做行狀上記得下的事；越有名越好打聽，也越容易被人盯上。"),
    (("決戰", "集結", "大戰"), "季中官軍與黃巾會約一場決戰，到時在大區集結，散人與豪強可以臨時投效一邊。"),
    (("移動", "趕路", "路程", "怎麼去", "走多久"), "移動有步行與疾行，疾行快但花體力；地圖上點地點就能安排前往。"),
    (("大勢人物", "人物", "交友", "求見", "情誼"), "大勢人物在各地，交友聊得投機情誼會漲；名望不夠的會被打發。"),
    (("同伴", "收徒", "門下", "結伴"), "情誼夠深的人物肯跟你走，收在門下一起闖。"),
)
POINTERS = {
    "player": "要問人在哪，可以用「查人在哪」；問人跟誰交好，用「打聽情誼」。",
    "figure": "要問人物在哪、跟誰交好，可以用「查人在哪」「打聽情誼」。",
    "material": "要問素材哪裡採得到，用「打聽素材」最準。",
    "place": "要問那一帶的事，可以先走過去看看，或在那裡的酒肆聽消息。",
}
POINTER_DEFAULT = "新鮮事可以點「聽消息」，問人用「查人在哪」，問素材用「打聽素材」。"


def _short(name: str) -> str:
    """地名的短寫（「潁川郡（陽翟）」也認「潁川郡」「陽翟」）。"""
    out = {name}
    if "（" in name:
        head, _, rest = name.partition("（")
        out |= {head, rest.rstrip("）")}
    return out


def _mentions(question: str, names: set[str]) -> bool:
    return any(len(n) >= 2 and n in question for n in names)


def far_text(content: Content, start: str, goal: str) -> str:
    n = tavern.hops(content, start, goal)
    return FAR.get(n, FAR_MORE)


def _kind_of(content: Content, loc_id: str) -> str:
    loc = content.locations[loc_id]
    kind = content.config.explore_mix_of(loc.tags).kind
    return kind if kind in PLACE_KIND else "wild"


def _shops_at(content: Content, loc_id: str) -> list[str]:
    loc = content.locations[loc_id]
    out = []
    if "城鎮" in loc.tags:  # 鐵匠鋪在帶「城鎮」標籤的地點（equipment.in_town）
        out.append("鐵匠鋪")
    for tag in ("醫館", "酒肆", "馬市"):
        if tag in loc.tags:
            out.append(tag)
    return out


def _has_shop(content: Content, loc_id: str, key: str) -> bool:
    loc = content.locations[loc_id]
    if key == "smith":
        return "城鎮" in loc.tags
    return {"clinic": "醫館", "market": "馬市", "tavern": "酒肆"}[key] in loc.tags


def _places(content: Content) -> list[str]:
    return [lid for lid, loc in content.locations.items() if not loc.prologue_only]


def place_lines(state: GameState, content: Content, loc_id: str) -> list[str]:
    """一個地點：在哪個大區、從這裡走幾站、城鎮或野外、危險、有什麼店、採得到什麼、門派。"""
    loc = content.locations[loc_id]
    here = state.player.location
    region = tavern.region_name(content, loc_id)
    kind = _kind_of(content, loc_id)
    text = PLACE_KIND[kind]
    if kind != "town":
        text += PLACE_DANGER.format(word=DANGER.get(max(0, min(4, loc.danger)), "兇險"))
    shops = _shops_at(content, loc_id)
    shop_text = PLACE_SHOPS.format(shops="、".join(shops)) if shops else ""
    if loc_id == here:
        lines = [PLACE_HERE.format(name=loc.name, region=region, kind=text, shops=shop_text)]
    else:
        lines = [PLACE_LINE.format(name=loc.name, region=region, far=far_text(content, here, loc_id), kind=text, shops=shop_text)]
    mats = [content.materials[m].name for m in loc.materials if m in content.materials]
    if mats:
        lines.append(f"{loc.name}" + PLACE_MATS.format(mats="、".join(mats)))
    for sect in content.sects.values():
        if sect.location == loc_id:
            lines.append(PLACE_SECT.format(sect=sect.name))
    return lines


def shop_lines(state: GameState, content: Content, key: str, label: str) -> list[str]:
    here = state.player.location
    spots = sorted((lid for lid in _places(content) if _has_shop(content, lid, key)),
                   key=lambda lid: (tavern.hops(content, here, lid), lid))[:3]
    if not spots:
        return [SHOP_NONE.format(shop=label)]
    named = [("這裡" if lid == here else content.locations[lid].name) + ("" if lid == here else f"（{far_text(content, here, lid)}）")
             for lid in spots]
    return [SHOP_LINE.format(shop=label, places="、".join(named))]


def figure_lines(state: GameState, content: Content, cid: str) -> list[str]:
    """一位人物：在哪（照打聽度，tavern.seek_figure_lines）、哪一方、出身與眼下處境（內容檔寫好的，不是模型編的）、心事。"""
    from tianxia import figures  # noqa: PLC0415  過渡：待搬（大勢人物在哪）

    ch = content.characters[cid]
    lines = [line.removeprefix("酒家說：「").removesuffix("」") for line in tavern.seek_figure_lines(state, content, cid)]
    fid = figures.of_character(content, cid)
    if fid is not None:
        fig = content.figures[fid]
        lines.append(FIGURE_SIDE.format(name=ch.name, side=content.scenario.faction_name(fig.faction, fig.faction)))
        mood = figures.mood_of(state, content, fid)
        if mood in tavern.MOOD_WORDS:
            lines.append(ch.name + tavern.MOOD_WORDS[mood].lstrip("，") + "。")
    if ch.background:
        lines.append(FIGURE_STORY.format(name=ch.name, text=ch.background))
    if ch.situation:
        lines.append(FIGURE_NOW.format(name=ch.name, text=ch.situation))
    return lines


def player_lines(state: GameState, content: Content, other: GameState, wanted: set[str] | None = None) -> list[str]:
    """一個玩家：照打聽度說哪一方、稱號、身邊同伴、近來的事（tavern.ties_player_lines），人在哪只說到大區（確切地點是「查人在哪」的事）。"""
    score = tavern.person_reach(state, content, other, wanted)
    p = other.player
    lines, ok = tavern.ties_player_lines(state, content, other, [], wanted)
    if score >= 2:
        loc = p.location if p.journey is None else tavern._road_end(other)
        lines.append(PLAYER_REGION.format(name=p.name, region=tavern.region_name(content, loc)))
    elif score >= 0:
        lines.append(PLAYER_FAINT.format(name=p.name))
    return lines


def skill_lines(state: GameState, content: Content, sid: str) -> list[str]:
    sk = content.skills[sid]
    learn = ""
    if sk.learn is not None and sk.learn.at in content.locations:
        learn = SKILL_LEARN.format(place=content.locations[sk.learn.at].name)
    else:
        owners = [ch.name for ch in content.characters.values() if sid in (ch.starting_wugong, ch.starting_neigong)]
        if owners:
            learn = SKILL_FIGURE.format(who="、".join(owners[:2]))
    return [SKILL_LINE.format(name=sk.name, quality=sk.quality, kind=sk.kind, attr=sk.attribute, learn=learn)]


def material_facts(state: GameState, content: Content, mid: str) -> list[str]:
    m = content.materials[mid]
    lines, _ = tavern.material_lines(state, content, m)
    lines = [line.removeprefix("酒家說：「").removesuffix("」") for line in lines]
    price = content.config.tavern.material_prices.get(m.tier)
    if price is not None:
        lines.append(MAT_SHOP.format(name=m.name, price=tavern.price(content, state.world, price)))
    return lines


def material_spots(state: GameState, content: Content) -> list[str]:
    """沒點名哪一樣素材時：最近的三處產地各採得到什麼。"""
    here = state.player.location
    spots = sorted((lid for lid in _places(content) if content.locations[lid].materials),
                   key=lambda lid: (tavern.hops(content, here, lid), lid))[:3]
    return [content.locations[lid].name + f"（{far_text(content, here, lid)}）" + PLACE_MATS.format(
        mats="、".join(content.materials[m].name for m in content.locations[lid].materials if m in content.materials)) for lid in spots]


def season_lines(state: GameState, content: Content) -> list[str]:
    w = state.world
    out = [SEASON_LINE.format(when=calendar.stamp_text(w.time, content, w)), ERA]
    note = rules.stance_rule_note(state, content)
    if note:
        out.append(note)
    return out


def hello_lines(state: GameState, content: Content) -> list[str]:
    """什麼都沒認出來時的常識包：附近的城鎮與店面、附近的野外與危險、出產。"""
    here = state.player.location
    near = sorted((lid for lid in _places(content) if lid != here), key=lambda lid: (tavern.hops(content, here, lid), lid))
    towns = [lid for lid in near if "城鎮" in content.locations[lid].tags][:3]
    wilds = [lid for lid in near if _kind_of(content, lid) == "wild"][:3]
    out = []
    if towns:
        out.append(HELLO_TOWNS.format(towns="、".join(f"{content.locations[t].name}（{far_text(content, here, t)}，有{'、'.join(_shops_at(content, t))}）"
                                                   for t in towns)))
    if wilds:
        bits = []
        for lid in wilds:
            loc = content.locations[lid]
            mats = "、".join(content.materials[m].name for m in loc.materials[:2] if m in content.materials)
            bits.append(f"{loc.name}（{far_text(content, here, lid)}，{DANGER.get(max(0, min(4, loc.danger)), '兇險')}" + (f"，產{mats}" if mats else "") + "）")
        out.append(HELLO_WILDS.format(wilds="、".join(bits)))
    return out


def topics(state: GameState, content: Content, question: str, players: dict[str, GameState],
           wanted: set[str] | None = None) -> tuple[list[str], list[str]]:
    """從問句找事實：回（事實, 問到的是哪幾類）。players 是問句裡點到名號的玩家（名號 → 存檔，呼叫端載入）。"""
    q = question
    facts: list[str] = []
    kinds: list[str] = []
    for cid, ch in content.characters.items():
        if _mentions(q, {ch.name}):
            facts += figure_lines(state, content, cid)
            kinds.append("figure")
    for name, other in players.items():
        if name_key(name) == name_key(state.player.name):
            continue
        facts += player_lines(state, content, other, wanted)
        kinds.append("player")
    for lid in _places(content):
        if _mentions(q, _short(content.locations[lid].name)):
            facts += place_lines(state, content, lid)
            kinds.append("place")
    for mid, m in content.materials.items():
        if _mentions(q, {m.name}):
            facts += material_facts(state, content, mid)
            kinds.append("material")
    for sid, sk in content.skills.items():
        if _mentions(q, {sk.name}):
            facts += skill_lines(state, content, sid)
            kinds.append("skill")
    for sect in content.sects.values():
        if _mentions(q, {sect.name}) and sect.location in content.locations:
            facts.append(SECT_LINE.format(name=sect.name, place=content.locations[sect.location].name, align=sect.alignment, desc=sect.desc))
            kinds.append("sect")
    for key, label, words in SHOPS:
        if any(word in q for word in words):
            facts += shop_lines(state, content, key, label)
            kinds.append("shop")
    for words, line in GUIDE:
        if any(word in q for word in words):
            facts.append("玩法：" + line)
            kinds.append("guide")
    if any(word in q for word in ("素材", "材料", "採集", "原料")) and "material" not in kinds:
        facts += material_spots(state, content)
        kinds.append("material")
    if any(word in q for word in ("天下", "大勢", "局勢", "戰況", "這一季", "季", "朝廷", "黃巾", "官軍", "甚麼時候", "什麼時候", "時局")):
        facts += season_lines(state, content)
        kinds.append("season")
    if not kinds:
        facts += hello_lines(state, content) + season_lines(state, content)
    seen: set[str] = set()
    return [f for f in facts if not (f in seen or seen.add(f))], kinds


def pointer(kinds: list[str]) -> str:
    """答不出來時酒家指的那一條路：照問到的第一類。"""
    for kind in kinds:
        if kind in POINTERS:
            return POINTERS[kind]
    return POINTER_DEFAULT


def name_hits(question: str, names: set[str]) -> list[str]:
    """問句裡點到的玩家名號（兩個字以上、長的先認；被長名號蓋住的短名號不算）。"""
    hits: list[str] = []
    for name in sorted(names, key=len, reverse=True):
        if len(name) >= 2 and name in question and not any(name in h for h in hits):
            hits.append(name)
    return hits[:3]
