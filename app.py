"""《天下大勢》原型的網頁介面（Gradio）。

遊戲規則全部在 tianxia/，這個檔案只負責畫面與接線：每次操作都先把現實時間同步進遊戲、
執行動作、存檔，再整個重畫。「門下」（隊伍與武學配置）、「戰報」（歷次戰鬥的列表與完整內容）與
「大地圖」（江湖輿圖：四個圖層、地點詳情與安排前往）都是另外的整頁，同一時間只顯示一頁（見 PAGES），
分別由 render_menxia()、戰報頁面與 render_map_page() 重畫。
左欄由上而下是場景列（左邊是地點或事件，右邊是以你為中心的小地圖與「大地圖」按鈕）、選項按鈕、
「剛剛」卡片（最新一則江湖紀錄；打完仗時換成戰鬥卡片，卡片沒寫到的補充放在卡片底下）、
「江湖紀錄」（再來的 5 則，一則一列、可點開看敘事，更早的收在摺疊區裡）。
按戰鬥卡片的「看完整戰報」或右欄的「戰報」按鈕都能打開戰報頁面；點小地圖、小地圖下方或右欄的「大地圖」按鈕
打開大地圖。
"""
from __future__ import annotations

import re
import shutil
import threading
import time
from pathlib import Path

import gradio as gr

from tianxia.content import load_content
from tianxia.engine import Game
from tianxia.journal import CSS as JOURNAL_CSS
from tianxia.save import load_game, save_game

ROOT = Path(__file__).parent
CONTENT = load_content(ROOT / "content")
SAVE_DIR = ROOT / "saves"
MAX_BUTTONS = 10
# game_state、任務區塊、狀態文字、場景文字、「剛剛」卡片（打完仗時是戰鬥卡片底下的補充）、小地圖、大勢、傳聞、江湖史、
# 選項 id 清單、匿名勾選框、戰鬥卡片、「看完整戰報」按鈕、江湖紀錄、更早的紀錄、「展開更早的紀錄」摺疊區，
# 再加上按鈕（MAX_BUTTONS）。
LATEST_INDEX = 4
MINIMAP_INDEX = 5
CARD_INDEX = 11
CARD_BUTTON_INDEX = 12
JOURNAL_INDEX = 13
OLDER_INDEX = 14
OLDER_ACCORDION_INDEX = 15
N_OUTPUTS = 16 + MAX_BUTTONS
RECENT_ROWS = 5  # 「剛剛」之後直接列出幾則
OLDER_ROWS = 30  # 摺疊區裡最多幾則（存檔本來就只留 30 則）

# 戰報頁面的輸出順序（見 open_report_page／open_report_handler）：
# 江湖畫面顯示與否、戰報頁面顯示與否、戰鬥列表、選定那一場的完整內容。
REPORT_EMPTY_TEXT = "（還沒有戰報。打一場歷練或劇情戰之後，這裡會列出每一場。）"

# 門下頁面（render_menxia）的輸出順序：選取的自選欄、選取的武學、心得與規則、隊伍切換、選中那一隊的資訊列、
# 換人的結果（資訊列正下方）、每一欄一組（欄、人物卡、本命、自選1、自選2、換人選單）、武學庫、武學詳情、
# 配置到、卸下、升一成、散功、武學動作的結果、名冊、名冊裡點選那人的人物卡。
MAX_MEMBERS = 3  # 每隊最多三人
MX_COLUMN_SIZE = 4 + Game.FREE_SLOTS
MX_SWAP_OFFSET = MX_COLUMN_SIZE - 1  # 一欄裡「換人」選單的位置
MX_HEAD_INDEX = 2
MX_TEAM_INDEX = 3
MX_TEAM_INFO_INDEX = 4
MX_SWAP_MESSAGE_INDEX = 5  # 換人的結果（例如換不成的原因），緊接在資訊列底下、換人選單上面
MX_COLUMNS_INDEX = 6
MX_LIBRARY_INDEX = MX_COLUMNS_INDEX + MAX_MEMBERS * MX_COLUMN_SIZE
MX_DETAIL_INDEX = MX_LIBRARY_INDEX + 1
MX_EQUIP_INDEX = MX_LIBRARY_INDEX + 2
MX_UNEQUIP_INDEX = MX_LIBRARY_INDEX + 3
MX_UPGRADE_INDEX = MX_LIBRARY_INDEX + 4
MX_DISPEL_INDEX = MX_LIBRARY_INDEX + 5
MX_MESSAGE_INDEX = MX_LIBRARY_INDEX + 6  # 武學動作（配置、卸下、精進、散功）的結果，在武學按鈕旁
MX_ROSTER_INDEX = MX_LIBRARY_INDEX + 7
MX_PERSON_INDEX = MX_LIBRARY_INDEX + 8
MENXIA_OUTPUTS = MX_PERSON_INDEX + 1
EMPTY_SLOT = Game.EMPTY_CHOICE  # 「換人」選單裡「（空）」的值（空字串）
PERSON_HINT = "（點名冊裡的一個人，這裡會顯示他的人物卡。）"

# 整頁：江湖畫面、門下、戰報、大地圖；同一時間只顯示一頁（見 show_page），順序同 build_demo() 的 pages。
PAGES = ("main", "menxia", "report", "map")

# 大地圖頁面（render_map_page）的輸出順序：時間與體力、圖層、大地圖、地點下拉選單、地點詳情、「安排前往」按鈕。
MAP_HEAD_INDEX = 0
MAP_LAYER_INDEX = 1
MAP_SVG_INDEX = 2
MAP_PLACE_INDEX = 3
MAP_DETAIL_INDEX = 4
MAP_TRAVEL_INDEX = 5
MAP_OUTPUTS = 6
DEFAULT_LAYER = "situation"
# 點大地圖上的地點：地點包在 data-loc 裡（見 mapview.render_map），把它的 id 當成 click 事件的資料送回 Python。
MAP_CLICK_JS = (
    "element.addEventListener('click', (event) => {"
    " const spot = event.target.closest('[data-loc]');"
    " if (spot) { trigger('click', {loc: spot.getAttribute('data-loc')}); }"
    " });"
)

Slot = tuple[str, int]  # 選中的自選欄：(人物 key, 第幾欄，從 0 起算)

ACT_LOCK = threading.Lock()
UNCHANGED = object()  # 動作回傳它表示什麼都沒做：act 不存檔、不重畫（頁面上的訊息也留著）


def save_path(name: str) -> Path:
    return SAVE_DIR / (re.sub(r'[\\/:*?"<>|]', "_", name) + ".json")


def render(game: Game) -> list:
    """回傳順序必須和 build_demo() 裡的 outputs 一致。"""
    options = game.options()[:MAX_BUTTONS]
    buttons = []
    for i in range(MAX_BUTTONS):
        if i < len(options):
            buttons.append(gr.update(value=options[i].label, visible=True, interactive=options[i].enabled))
        else:
            buttons.append(gr.update(visible=False))
    p = game.state.player
    # 「剛剛」那一格：這次行動打了仗就放戰鬥卡片（結果與獲得損失都在上面），卡片沒寫到的
    # （例如同時完成的新手引導與獎勵）放在卡片底下；沒打仗時放最新一則紀錄的卡片。
    card = game.battle_card() if game.shows_battle_card() else None
    latest = game.battle_extra_html() if card is not None else game.latest_entry_html()
    older = game.journal_html(1 + RECENT_ROWS, OLDER_ROWS)
    return [
        game,
        game.quest_text(),
        game.status_text(),
        game.scene_text(),
        gr.update(value=latest, visible=bool(latest)),
        game.minimap_svg(),
        game.trends_text(),
        game.rumors_text(),
        game.chronicle_text(),
        [o.id for o in options],
        p.anonymous,
        gr.update(value=card or "", visible=card is not None),
        gr.update(visible=card is not None),
        game.journal_html(1, RECENT_ROWS, heading="江湖紀錄", empty="（還沒有更早的紀錄。）"),
        older,
        gr.update(visible=bool(older)),
        *buttons,
    ]


# ── 門下頁面 ──────────────────────────────────────────


def team_index(game: Game, value) -> int:
    """隊伍切換的值；不認得時（例如舊畫面送來的值）回到本隊。"""
    return value if isinstance(value, int) and 0 <= value < len(game.state.player.teams) else 0


def menxia_selection(
    game: Game, slot: Slot | None, target: str | None, team: int = 0
) -> tuple[Slot | None, str | None]:
    """丟掉已經不成立的選取（例如換了新賽季、切換了隊伍）：自選欄要屬於顯示中那一隊的人，武學要在武學庫裡。"""
    if slot is not None:
        key, index = slot
        slot = (key, index) if key in game.team_keys(team) and 0 <= index < Game.FREE_SLOTS else None
    if target not in {t for _, t in game.upgrade_options()}:
        target = None
    return slot, target


def render_menxia(
    game: Game, slot: Slot | None, target: str | None, message: str | None = None,
    team: int = 0, person: str | None = None, swap: bool = False,
) -> list:
    """門下頁面的全部輸出，順序見 MX_*_INDEX。team 是顯示中的隊伍（0＝本隊），person 是名冊裡點選的人。
    message 是剛才那個動作的結果：換人（swap）的寫在資訊列正下方、換人選單上面，其他寫在武學按鈕旁；
    寫了一處就清掉另一處，頁面上只留最新的一則。message 為 None 時兩處都保留原本的訊息，空字串時兩處都清掉。"""
    team = team_index(game, team)
    slot, target = menxia_selection(game, slot, target, team)
    lines = game.roster_lines()
    if person not in {key for _, key in lines}:
        person = None
    keys = game.team_keys(team)
    if message is None:
        swap_note = skill_note = gr.update()
    else:
        swap_note, skill_note = (message, "") if swap else ("", message)
    out: list = [
        slot, target, f"**心得** {game.state.player.stats.get('xinde', 0)}　｜　{game.menxia_rules()}",
        gr.update(choices=game.team_choices(), value=team), game.team_info(team), swap_note,
    ]
    for col in range(MAX_MEMBERS):
        if team >= game.team_count():  # 還沒開放的隊伍：整排不顯示
            out += [gr.update(visible=False)] + [gr.update()] * (MX_COLUMN_SIZE - 1)
            continue
        if col >= len(keys):  # 空位：只有「換人」選單
            out += [gr.update(visible=True), "（空位）"] + [gr.update(visible=False)] * (1 + Game.FREE_SLOTS)
            out.append(_swap_menu(game, team, col))
            continue
        key = keys[col]
        out += [
            gr.update(visible=True),
            game.member_card(key),
            gr.update(visible=True, value=game.slot_label(key, None), variant="secondary"),
        ]
        out += [
            gr.update(visible=True, value=game.slot_label(key, i), variant="primary" if slot == (key, i) else "secondary")
            for i in range(Game.FREE_SLOTS)
        ]
        out.append(_swap_menu(game, team, col))
    out += [gr.update(choices=game.skill_library(), value=target), game.skill_detail(target)]
    out += _menxia_buttons(game, slot, target, team)
    out.append(skill_note)
    out += [gr.update(choices=lines, value=person), game.member_card(person, innate=True) if person else PERSON_HINT]
    assert len(out) == MENXIA_OUTPUTS
    return out


def _column_key(game: Game, team: int, col: int) -> str | None:
    """第 team 隊第 col 欄的人；空位時為 None。處理函式要在同一把 ACT_LOCK 裡查和用（換人可能同時讓這一隊變少）。"""
    keys = game.team_keys(team)
    return keys[col] if col < len(keys) else None


def _swap_menu(game: Game, team: int, col: int) -> dict:
    """一欄上方的「換人」選單；本隊第一欄是你本人，固定不換：選單鎖住，只寫明原因（各欄才對得齊）。"""
    current = _column_key(game, team, col)
    if team == 0 and col == 0:
        return gr.update(visible=True, interactive=False, choices=[("你本人（固定是本隊的隊長）", current)], value=current)
    return gr.update(visible=True, interactive=True, choices=game.swap_choices(team, col), value=current)


def _menxia_buttons(game: Game, slot: Slot | None, target: str | None, team: int = 0) -> list:
    """「配置到」、「卸下」、「升一成」、「散功」四個按鈕：看選取決定顯示與否，文字寫明是哪一欄、多少心得。"""
    where = ""
    held = None
    if slot is not None:
        names = {key: name for name, key in game.team_members(team)}
        where = f"〔{names[slot[0]]}・自選{slot[1] + 1}〕"
        held = game.slot_skill(*slot)
    can_equip = (
        slot is not None and target is not None and target.startswith("skill:")
        and not game.is_innate(target) and (held is None or target != f"skill:{held}")
    )
    cost = game.upgrade_cost(target) if target else None
    refund = game.dispel_refund(target) if target else None
    return [
        gr.update(visible=can_equip, value=f"配置到{where}"),
        gr.update(visible=held is not None, value=f"卸下{where}"),
        gr.update(
            visible=target is not None, interactive=cost is not None,
            value="已達第十成" if cost is None else f"升一成（心得 {cost}）",
        ),
        gr.update(
            visible=target is not None and not game.is_innate(target), interactive=refund is not None,
            value="散功（第一成無功可散）" if refund is None else f"散功（返還心得 {refund}）",
        ),
    ]


def act(game: Game | None, action, menxia: tuple | None = None, swap: bool = False) -> list:
    """同步時間 → 執行動作 → 存檔 → 重畫。上鎖避免計時器與按鈕點擊同時操作同一存檔。

    menxia＝(選取的自選欄, 選取的武學, 顯示中的隊伍, 名冊裡點選的人) 時連門下頁面一起重畫；
    動作回傳的訊息（None 表示沒有）顯示在頁面上：換人（swap）的在資訊列底下，其他在武學按鈕旁（見 render_menxia）；
    回傳 UNCHANGED 時什麼都不存、不重畫。
    戰報頁面與大地圖頁面是獨立的整頁，不在這裡重畫（見 open_report_page、render_map_page）。
    """
    n = N_OUTPUTS if menxia is None else N_OUTPUTS + MENXIA_OUTPUTS
    if game is None:
        return [gr.skip()] * n
    with ACT_LOCK:
        game.sync(time.time())
        msgs = action(game)
        if msgs is UNCHANGED:
            return [gr.skip()] * n
        save_game(game.state, save_path(game.state.player.name))
        out = render(game)
        if menxia is not None:
            slot, target, *view = menxia
            out += render_menxia(game, slot, target, None if msgs is None else "\n\n".join(msgs), *view, swap=swap)
        return out


def make_option_handler(index: int):
    def handler(game, ids):
        if game is None or index >= len(ids):
            return [gr.skip()] * N_OUTPUTS
        return act(game, lambda g: g.choose(ids[index]))

    return handler


def make_fast_forward_handler(hours: int):
    def handler(game):
        return act(game, lambda g: g.advance(hours * 3600))

    return handler


def seclude_handler(game, hours):
    return act(game, lambda g: g.seclude(int(hours)))


def open_menxia(game, slot, target, team=0, person=None):
    """「門下」：藏起江湖畫面、打開門下頁面並重畫（停在上次看的那一隊）。"""
    if game is None:
        return [gr.skip()] * (2 + MENXIA_OUTPUTS)
    with ACT_LOCK:
        return [gr.update(visible=False), gr.update(visible=True)] + render_menxia(game, slot, target, "", team, person)


def close_menxia():
    """「返回江湖」。"""
    return [gr.update(visible=True), gr.update(visible=False)]


def make_innate_slot_handler(col: int):
    """點某人的本命欄：在武學庫與詳情選中他的本命，並取消自選欄的選取。"""

    def handler(game, slot, target, team=0, person=None):
        if game is None:
            return [gr.skip()] * MENXIA_OUTPUTS
        with ACT_LOCK:
            team = team_index(game, team)
            key = _column_key(game, team, col)
            if key is None:
                return [gr.skip()] * MENXIA_OUTPUTS
            return render_menxia(game, None, game.innate_target(key) or target, "", team, person)

    return handler


def make_free_slot_handler(col: int, index: int):
    """點某人的自選欄：選取這一欄；欄裡有武學時，也一併選中那門武學。"""

    def handler(game, slot, target, team=0, person=None):
        if game is None:
            return [gr.skip()] * MENXIA_OUTPUTS
        with ACT_LOCK:
            team = team_index(game, team)
            key = _column_key(game, team, col)
            if key is None:
                return [gr.skip()] * MENXIA_OUTPUTS
            held = game.slot_skill(key, index)
            return render_menxia(game, (key, index), f"skill:{held}" if held else target, "", team, person)

    return handler


def view_handler(game, slot, target, team=0, person=None):
    """在武學庫選一門武學、切換隊伍、在名冊點一個人：重畫門下頁面（不算行動、不存檔）；
    自選欄的選取只在還是顯示中那一隊的人時保留。"""
    if game is None:
        return [gr.skip()] * MENXIA_OUTPUTS
    with ACT_LOCK:
        return render_menxia(game, slot, target, "", team, person)


def _page_skip() -> list:
    return [gr.skip()] * (N_OUTPUTS + MENXIA_OUTPUTS)


def make_swap_handler(col: int):
    """某一欄上方的「換人」選單（選單失焦時送來，滑鼠、鍵盤選都一樣）：把這一位換成選的人（「（空）」＝空出這一位）。
    照一般動作同步、存檔、重畫；結果寫在資訊列正下方（換不成時寫原因，例如統御超過上限，選單回到原本的人）。
    選的就是這一位現在的人（點開又離開、或重選同一人），或空位選了空時什麼都不做。"""

    def handler(game, slot, target, team, person, choice):
        if game is None or choice is None:
            return _page_skip()
        team = team_index(game, team)
        key = None if choice == EMPTY_SLOT else choice

        def move(g: Game):
            if _column_key(g, team, col) == key:  # 在 act 的鎖裡查：這一位已經是他（或本來就空著）
                return UNCHANGED
            return g.set_member(team, col, key)

        return act(game, move, menxia=(slot, target, team, person), swap=True)

    return handler


def equip_handler(game, slot, target, team=0, person=None):
    """把選中的武學配到選中的自選欄；原本配在別人身上的會移過來（同一門武學同時只能配給一個人）。"""
    if game is None:
        return _page_skip()
    team = team_index(game, team)
    slot, target = menxia_selection(game, slot, target, team)
    if slot is None or target is None or not target.startswith("skill:"):
        return _page_skip()
    key, index = slot
    skill_id = target.removeprefix("skill:")
    return act(game, lambda g: g.set_loadout(key, index, skill_id), menxia=(slot, target, team, person))


def unequip_handler(game, slot, target, team=0, person=None):
    if game is None:
        return _page_skip()
    team = team_index(game, team)
    slot, target = menxia_selection(game, slot, target, team)
    if slot is None:
        return _page_skip()
    key, index = slot
    return act(game, lambda g: g.set_loadout(key, index, None), menxia=(slot, target, team, person))


def upgrade_handler(game, slot, target, team=0, person=None):
    if game is None:
        return _page_skip()
    team = team_index(game, team)
    slot, target = menxia_selection(game, slot, target, team)
    if target is None:
        return _page_skip()
    return act(game, lambda g: g.upgrade(target), menxia=(slot, target, team, person))


def dispel_handler(game, slot, target, team=0, person=None):
    if game is None:
        return _page_skip()
    team = team_index(game, team)
    slot, target = menxia_selection(game, slot, target, team)
    if target is None:
        return _page_skip()
    return act(game, lambda g: g.dispel(target), menxia=(slot, target, team, person))


def _report_page(record_id: int | None, game: Game) -> list:
    """戰報頁面的四項輸出：藏起江湖畫面、顯示戰報頁面、戰鬥列表、選定那一場的完整內容
    （沒有任何戰報時顯示 REPORT_EMPTY_TEXT）。"""
    detail = game.battle_detail(record_id) if record_id is not None else REPORT_EMPTY_TEXT
    return [
        gr.update(visible=False),
        gr.update(visible=True),
        gr.update(choices=game.battle_list(), value=record_id),
        detail,
    ]


def open_report_page(game):
    """右欄「戰報」按鈕：打開戰報頁面，選好最新一場。"""
    if game is None:
        return [gr.skip()] * 4
    with ACT_LOCK:
        return _report_page(game.latest_battle_id(), game)


def open_report_handler(game):
    """場景卡片上的「看完整戰報」：打開戰報頁面，並選好卡片上的這一場。"""
    if game is None:
        return [gr.skip()] * 4
    with ACT_LOCK:
        return _report_page(game.battle_card_id(), game)


def close_report():
    """戰報頁面的「返回江湖」。"""
    return [gr.update(visible=True), gr.update(visible=False)]


def report_pick_handler(game, record_id):
    """在戰報列表點選一場：右邊顯示這一場的完整內容。"""
    if game is None:
        return gr.skip()
    with ACT_LOCK:
        return game.battle_detail(record_id)


def anonymous_handler(game, value):
    return act(game, lambda g: g.set_anonymous(value))


def show_page(page: str) -> list:
    """四個整頁（PAGES）的顯示與否：只顯示 page 那一頁。"""
    return [gr.update(visible=name == page) for name in PAGES]


def render_map_page(game: Game, layer: str, selected: str | None, notice: str = "") -> list:
    """大地圖頁面的全部輸出，順序見 MAP_*_INDEX。選的地點不在下拉選單裡（例如走動後、換了新賽季）時改選所在地。
    notice 寫在地點詳情的最上面（例如「安排前往」沒走成的原因）。"""
    places = game.map_places()
    if selected not in {loc_id for _, loc_id in places}:
        selected = game.state.player.location
    if layer not in Game.MAP_LAYERS:
        layer = DEFAULT_LAYER
    button = game.travel_button(selected)
    out = [
        game.map_header(),
        gr.update(value=layer),
        game.world_map_svg(layer, selected),
        gr.update(choices=places, value=selected),
        (f"{notice}\n\n" if notice else "") + game.place_detail(selected),
        gr.update(visible=False) if button is None else gr.update(visible=True, value=button[0], interactive=button[1]),
    ]
    assert len(out) == MAP_OUTPUTS
    return out


def open_world_map(game):
    """右欄「大地圖」、點小地圖或小地圖下方的「大地圖」：打開大地圖頁面，預設「局勢」、選中所在地。
    打開大地圖可能完成新手引導的一步，所以先照一般動作同步、存檔、重畫江湖畫面。"""
    if game is None:
        return [gr.skip()] * (N_OUTPUTS + len(PAGES) + MAP_OUTPUTS)
    out = act(game, lambda g: g.view_map())
    with ACT_LOCK:
        return out + show_page("map") + render_map_page(game, DEFAULT_LAYER, None)


def map_page_handler(game, layer, selected):
    """切換圖層，或從下拉選單選地點：重畫大地圖頁面（不算行動，不存檔）。"""
    if game is None:
        return [gr.skip()] * MAP_OUTPUTS
    with ACT_LOCK:
        return render_map_page(game, layer, selected)


def clicked_place(evt: gr.EventData | None) -> str | None:
    """點大地圖送來的地點 id（MAP_CLICK_JS 送 {loc: 地點 id}）；沒有資料或資料的樣子不對時為 None。"""
    try:
        loc_id = evt.loc
    except (AttributeError, TypeError, KeyError, IndexError):
        return None
    return loc_id if isinstance(loc_id, str) else None


def map_click_handler(game, layer, evt: gr.EventData):
    """在大地圖上點一個地點：選中它；點到選不了的地方、或送來的資料不對時不動。"""
    loc_id = clicked_place(evt)
    if game is None or loc_id not in {place for _, place in game.map_places()}:
        return [gr.skip()] * MAP_OUTPUTS
    with ACT_LOCK:
        return render_map_page(game, layer, loc_id)


def travel_handler(game, layer, selected):
    """「安排前往」：一站一站走過去，走完回到江湖畫面，場景顯示抵達的地點（大地圖頁面藏起來，不用重畫）。
    按鈕是舊的而走不成時（例如打開大地圖之後才冒出事件），留在大地圖，地點詳情最上面寫出原因。"""
    if game is None:
        return [gr.skip()] * (N_OUTPUTS + len(PAGES) + MAP_OUTPUTS)
    refused: list[str] = []

    def go(g: Game) -> list[str]:
        start = g.state.player.location
        msgs = g.travel(selected)
        if g.state.player.location == start:  # 走得成一定會走出第一站；沒動就是被擋下來了
            refused.extend(msgs)
        return msgs

    out = act(game, go)
    if not refused:
        return out + show_page("main") + [gr.skip()] * MAP_OUTPUTS
    reason = refused[0].strip("（）")
    with ACT_LOCK:
        return out + show_page("map") + render_map_page(game, layer, selected, f"**沒能出發**：{reason}")


def close_world_map():
    """大地圖頁面的「返回江湖」。"""
    return show_page("main")


def skip_tutorial_handler(game):
    return act(game, lambda g: g.skip_tutorial())


def tick_handler(game, slot, target, team=0, person=None):
    """計時器：同步時間，連同門下頁面一起重畫（保留目前的選取、隊伍與訊息），內力等數字才會跟著走。"""
    return act(game, lambda g: None, menxia=(slot, target, team, person))


def open_game(name: str) -> Game:
    """讀取存檔；舊格式讀不進來時，先把原檔備份到 saves/backup/ 再開新角色，不刪除任何東西。"""
    path = save_path(name)
    if not path.exists():
        return Game.new(CONTENT, name)
    try:
        return Game(CONTENT, load_game(path))
    except ValueError:  # pydantic 的 ValidationError 屬於 ValueError
        backup = SAVE_DIR / "backup" / f"{path.stem}-{int(time.time())}.json"
        backup.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, backup)
        game = Game.new(CONTENT, name)
        game.notice(f"（舊存檔的格式已不相容，已備份到 saves/backup/{backup.name}；這是新的開始。）", "舊存檔已備份")
        return game


def start(name):
    """踏入江湖：藏起開始畫面、顯示江湖畫面，門下、戰報、大地圖頁面維持隱藏。"""
    name = (name or "").strip()
    if not name:
        raise gr.Error("請先輸入你的名號。")
    return act(open_game(name), lambda g: None) + [gr.update(visible=False)] + show_page("main")  # start_col、PAGES


def build_demo() -> gr.Blocks:
    with gr.Blocks(title="天下大勢") as demo:
        game_state = gr.State(None)
        ids_state = gr.State([])
        mx_slot = gr.State(None)  # 門下頁面選中的自選欄（Slot）
        mx_target = gr.State(None)  # 門下頁面選中的武學：skill:<id> 或 innate:<key>
        gr.Markdown("# 天下大勢 · 原型")
        with gr.Column(visible=True) as start_col:
            name_box = gr.Textbox(label="你的名號", placeholder="例如：沈青衫（輸入舊名號會讀取存檔）")
            start_btn = gr.Button("踏入江湖", variant="primary")
        with gr.Row(visible=False) as game_row:
            with gr.Column(scale=3):
                with gr.Row(equal_height=False):
                    scene_md = gr.Markdown(scale=3)
                    with gr.Column(scale=2, min_width=180):
                        minimap_html = gr.HTML()  # 預設的 js_on_load：點一下就觸發 click
                        mini_map_btn = gr.Button("大地圖", size="sm")
                option_btns = [gr.Button(visible=False) for _ in range(MAX_BUTTONS)]
                # 「剛剛」：最新一則江湖紀錄的卡片；這次行動打了仗時改放戰鬥卡片，latest_html 則放卡片沒寫到的補充。
                battle_card_md = gr.Markdown(visible=False, container=True)
                latest_html = gr.HTML(css_template=JOURNAL_CSS)
                card_btn = gr.Button("看完整戰報", visible=False)
                journal_html = gr.HTML(css_template=JOURNAL_CSS)
                with gr.Accordion("展開更早的紀錄", open=False, visible=False) as older_acc:
                    older_html = gr.HTML(css_template=JOURNAL_CSS)
            with gr.Column(scale=2):
                with gr.Accordion("主線與目標", open=True):
                    quest_md = gr.Markdown()
                status_md = gr.Markdown()
                with gr.Row():
                    menxia_btn = gr.Button("門下")
                    report_btn = gr.Button("戰報")
                    map_btn = gr.Button("大地圖")
                with gr.Tabs():
                    with gr.Tab("江湖大勢"):
                        trends_md = gr.Markdown()
                    with gr.Tab("江湖傳聞"):
                        rumors_md = gr.Markdown()
                    with gr.Tab("江湖史"):
                        chronicle_md = gr.Markdown()
                    with gr.Tab("閉關"):
                        gr.Markdown("閉關可以得到心得，期間內力回復加倍。")
                        hours_sl = gr.Slider(1, 12, value=8, step=1, label="閉關時數（小時）")
                        seclude_btn = gr.Button("開始閉關")
                    with gr.Tab("設定"):
                        anon_cb = gr.Checkbox(label="匿名行走（江湖傳聞中不顯示名號）")
                        skip_tutorial_btn = gr.Button("略過新手引導")
                        gr.Markdown("**測試用：時間快轉**")
                        with gr.Row():
                            ff_btns = {h: gr.Button(f"+{h} 小時") for h in (1, 8, 24)}
        with gr.Column(visible=False) as menxia_col:
            with gr.Row(equal_height=True):
                gr.Markdown("## 門下", scale=1)
                mx_head_md = gr.Markdown(scale=6)
                back_btn = gr.Button("返回江湖", scale=0, min_width=120)
            team_radio = gr.Radio(label="隊伍", choices=[], interactive=True)  # 值是第幾隊；還沒打開門下時為 None（＝本隊）
            team_info_md = gr.Markdown()
            swap_message_md = gr.Markdown()  # 換人的結果：放在換人選單旁，不必往下捲到武學按鈕那裡才看得到
            members = []
            with gr.Row():
                for _ in range(MAX_MEMBERS):
                    with gr.Column(visible=False, min_width=240) as member_col:
                        swap_dd = gr.Dropdown(label="換人", choices=[], interactive=True)
                        card_md = gr.Markdown()
                        slot_btns = [gr.Button("（空）") for _ in range(1 + Game.FREE_SLOTS)]  # 本命、自選…
                    members.append((member_col, card_md, slot_btns, swap_dd))
            with gr.Row():
                with gr.Column(scale=1):
                    roster_radio = gr.Radio(label="名冊（點名字看人物卡）", choices=[], interactive=True)
                with gr.Column(scale=1):
                    person_md = gr.Markdown()
            with gr.Row():
                with gr.Column(scale=1):
                    library_radio = gr.Radio(label="武學庫", choices=[], interactive=True)
                with gr.Column(scale=1):
                    gr.Markdown("**武學詳情**")
                    detail_md = gr.Markdown()
                    with gr.Row():
                        equip_btn = gr.Button("配置到", variant="primary", visible=False)
                        unequip_btn = gr.Button("卸下", visible=False)
                        upgrade_btn = gr.Button("升一成", visible=False)
                        dispel_btn = gr.Button("散功", variant="stop", visible=False)
                    mx_message_md = gr.Markdown()
        with gr.Column(visible=False) as report_col:
            with gr.Row(equal_height=True):
                gr.Markdown("## 戰報", scale=1)
                gr.Markdown(scale=6)
                report_back_btn = gr.Button("返回江湖", scale=0, min_width=120)
            with gr.Row():
                with gr.Column(scale=1):
                    report_list_radio = gr.Radio(label="歷次戰鬥（最新在前）", choices=[], interactive=True)
                with gr.Column(scale=2):
                    report_detail_md = gr.Markdown()
        with gr.Column(visible=False) as map_col:
            with gr.Row(equal_height=True):
                gr.Markdown("## 江湖輿圖", scale=1)
                map_head_md = gr.Markdown(scale=6)
                map_back_btn = gr.Button("返回江湖", scale=0, min_width=120)
            layer_radio = gr.Radio(
                label="圖層", choices=[(name, key) for key, name in Game.MAP_LAYERS.items()], value=DEFAULT_LAYER,
                interactive=True,
            )
            with gr.Row():
                with gr.Column(scale=3):
                    world_map_html = gr.HTML(js_on_load=MAP_CLICK_JS)
                with gr.Column(scale=2, min_width=260):
                    place_dd = gr.Dropdown(label="地點（也可以直接點地圖）", choices=[], interactive=True)
                    place_md = gr.Markdown()
                    travel_btn = gr.Button("安排前往", variant="primary", visible=False)

        outputs = [
            game_state, quest_md, status_md, scene_md, latest_html, minimap_html, trends_md, rumors_md, chronicle_md,
            ids_state, anon_cb, battle_card_md, card_btn, journal_html, older_html, older_acc,
            *option_btns,
        ]
        assert len(outputs) == N_OUTPUTS
        pages = [game_row, menxia_col, report_col, map_col]
        assert len(pages) == len(PAGES)
        map_outputs = [map_head_md, layer_radio, world_map_html, place_dd, place_md, travel_btn]
        assert len(map_outputs) == MAP_OUTPUTS
        menxia_outputs = [mx_slot, mx_target, mx_head_md, team_radio, team_info_md, swap_message_md]
        for member_col, card_md, slot_btns, swap_dd in members:
            menxia_outputs += [member_col, card_md, *slot_btns, swap_dd]
        menxia_outputs += [library_radio, detail_md, equip_btn, unequip_btn, upgrade_btn, dispel_btn, mx_message_md]
        menxia_outputs += [roster_radio, person_md]
        assert len(menxia_outputs) == MENXIA_OUTPUTS
        selection = [game_state, mx_slot, mx_target, team_radio, roster_radio]

        start_btn.click(start, inputs=[name_box], outputs=outputs + [start_col] + pages)
        name_box.submit(start, inputs=[name_box], outputs=outputs + [start_col] + pages)
        for i, btn in enumerate(option_btns):
            btn.click(make_option_handler(i), inputs=[game_state, ids_state], outputs=outputs)
        seclude_btn.click(seclude_handler, inputs=[game_state, hours_sl], outputs=outputs)
        anon_cb.input(anonymous_handler, inputs=[game_state, anon_cb], outputs=outputs)
        skip_tutorial_btn.click(skip_tutorial_handler, inputs=[game_state], outputs=outputs)
        for hours, btn in ff_btns.items():
            btn.click(make_fast_forward_handler(hours), inputs=[game_state], outputs=outputs)

        menxia_btn.click(open_menxia, inputs=selection, outputs=[game_row, menxia_col] + menxia_outputs)
        back_btn.click(close_menxia, outputs=[game_row, menxia_col])
        report_outputs = [game_row, report_col, report_list_radio, report_detail_md]
        report_btn.click(open_report_page, inputs=[game_state], outputs=report_outputs)
        card_btn.click(open_report_handler, inputs=[game_state], outputs=report_outputs)
        report_back_btn.click(close_report, outputs=[game_row, report_col])
        report_list_radio.input(
            report_pick_handler, inputs=[game_state, report_list_radio], outputs=[report_detail_md]
        )
        for opener in (map_btn, mini_map_btn, minimap_html):
            opener.click(open_world_map, inputs=[game_state], outputs=outputs + pages + map_outputs)
        map_back_btn.click(close_world_map, outputs=pages)
        layer_radio.input(map_page_handler, inputs=[game_state, layer_radio, place_dd], outputs=map_outputs)
        place_dd.input(map_page_handler, inputs=[game_state, layer_radio, place_dd], outputs=map_outputs)
        world_map_html.click(map_click_handler, inputs=[game_state, layer_radio], outputs=map_outputs)
        travel_btn.click(
            travel_handler, inputs=[game_state, layer_radio, place_dd], outputs=outputs + pages + map_outputs
        )
        for col, (_, _, (innate_btn, *free_btns), swap_dd) in enumerate(members):
            innate_btn.click(make_innate_slot_handler(col), inputs=selection, outputs=menxia_outputs)
            for index, btn in enumerate(free_btns):
                btn.click(make_free_slot_handler(col, index), inputs=selection, outputs=menxia_outputs)
            # 接 blur：滑鼠、鍵盤選好都會失焦、各送一次（select 鍵盤選不送，input 滑鼠選會送兩次）。
            swap_dd.blur(make_swap_handler(col), inputs=selection + [swap_dd], outputs=outputs + menxia_outputs)
        library_radio.input(
            view_handler, inputs=[game_state, mx_slot, library_radio, team_radio, roster_radio], outputs=menxia_outputs
        )
        team_radio.input(view_handler, inputs=selection, outputs=menxia_outputs)
        roster_radio.input(view_handler, inputs=selection, outputs=menxia_outputs)
        for btn, handler in (
            (equip_btn, equip_handler), (unequip_btn, unequip_handler),
            (upgrade_btn, upgrade_handler), (dispel_btn, dispel_handler),
        ):
            btn.click(handler, inputs=selection, outputs=outputs + menxia_outputs)
        gr.Timer(10).tick(tick_handler, inputs=selection, outputs=outputs + menxia_outputs)
    return demo


if __name__ == "__main__":
    build_demo().launch(server_name="127.0.0.1", server_port=7861)
