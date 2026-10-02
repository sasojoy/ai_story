"""《天下大勢》原型的網頁介面（Gradio）。

遊戲規則全部在 tianxia/，這個檔案只負責畫面與接線：每次操作都先把現實時間同步進遊戲、
執行動作、存檔，再整個重畫。「門下」（練功與招募）、「戰報」（歷次戰鬥的列表與完整內容）與
「大地圖」（江湖輿圖：四個圖層、地點詳情與安排前往）都是另外的整頁，同一時間只顯示一頁（見 PAGES），
分別由 render_menxia()、戰報頁面與 render_map_page() 重畫。
左欄由上而下是場景列（左邊是地點或事件，右邊是以你為中心的小地圖與「大地圖」按鈕）、選項按鈕、
「剛剛」卡片（最新一則江湖紀錄；打完仗時換成戰鬥卡片，卡片沒寫到的補充放在卡片底下）、
「江湖紀錄」（再來的 5 則，一則一列、可點開看敘事，更早的收在摺疊區裡）。
按戰鬥卡片的「看完整戰報」或右欄的「戰報」按鈕都能打開戰報頁面；點小地圖、小地圖下方或右欄的「大地圖」按鈕
打開大地圖。

sanguo-companions 合併大幅簡化了「門下」頁：不再有多隊切換/換人選單/武學欄配置/招賢分頁，
同伴全服唯一、練功只有自創功法／鍛鍊兩個按鈕（見設計文件四.4、六.2）。
"""
from __future__ import annotations

import shutil
import time
import unicodedata
from pathlib import Path

import gradio as gr

from tianxia.accounts import NAME_TAKEN, PASSWORDS_DIFFER, AccountError, AccountStore, normalize
from tianxia.content import load_content
from tianxia.craft import MATERIALS_PER_CRAFT
from tianxia.engine import Game
from tianxia.journal import CSS as JOURNAL_CSS
from tianxia.save import load_game, path_for, save_game
from tianxia.world_state import WorldStateStore

ROOT = Path(__file__).parent
CONTENT = load_content(ROOT / "content")
SAVE_DIR = ROOT / "saves"
MAX_BUTTONS = 10
# game_state、任務區塊、狀態文字、場景文字、「剛剛」卡片（打完仗時是戰鬥卡片底下的補充）、小地圖、大勢、傳聞、江湖史、
# 選項 id 清單、匿名勾選框、戰鬥卡片、「看完整戰報」按鈕、江湖紀錄、更早的紀錄、「展開更早的紀錄」摺疊區，
# 再加上按鈕（MAX_BUTTONS），最後是全服戰鬥的自訂行動輸入框跟送出按鈕（見設計討論：
# 「魯莽」這類選項該是玩家自己想出來的招，不是從固定清單挑一個）。
LATEST_INDEX = 4
MINIMAP_INDEX = 5
CARD_INDEX = 11
CARD_BUTTON_INDEX = 12
JOURNAL_INDEX = 13
OLDER_INDEX = 14
OLDER_ACCORDION_INDEX = 15
BATTLE_TEXT_INDEX = 16 + MAX_BUTTONS
BATTLE_TEXT_BUTTON_INDEX = 17 + MAX_BUTTONS
N_OUTPUTS = 18 + MAX_BUTTONS
RECENT_ROWS = 5  # 「剛剛」之後直接列出幾則
OLDER_ROWS = 30  # 摺疊區裡最多幾則（存檔本來就只留 30 則）

REPORT_EMPTY_TEXT = "（還沒有戰報。打一場遭遇戰或劇情戰之後，這裡會列出每一場。）"

# 門下頁面（render_menxia）的輸出順序：規則/心得說明、本人角色卡、名冊（本人＋已招募同伴）、
# 選中那個人的角色卡、加入/移出隊伍按鈕、煉製素材（背包）、動作結果，之後是煉製那一塊
# （素材選單、成本說明）與功法庫選單。訊息留在第 6 格不動，新東西一律往後加。
PERSON_HINT = "（點名冊裡的一個人，這裡會顯示他的角色卡。）"
MENXIA_OUTPUTS = 10  # render_menxia 的輸出數量（見上面的順序）；open_menxia 另外前綴兩個可見性更新

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

UNCHANGED = object()  # 動作回傳它表示什麼都沒做：act 不存檔、不重畫（頁面上的訊息也留著）
KINDS = ("武學", "內功")


def save_path(name: str) -> Path:
    return path_for(SAVE_DIR, name)


def render(game: Game) -> list:
    """回傳順序必須和 build_demo() 裡的 outputs 一致。"""
    options = game.options()[:MAX_BUTTONS]
    free_text_prompt = game.battle_free_text_prompt()
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
        gr.update(value="", label=free_text_prompt or "", visible=free_text_prompt is not None),
        gr.update(visible=free_text_prompt is not None),
    ]


# ── 門下頁面 ──────────────────────────────────────────


def render_menxia(game: Game, person: str | None = None, message: str | None = None) -> list:
    """門下頁面的全部輸出。person 是名冊裡點選的人（None＝本人）；
    message 是剛才那個動作的結果，None 時保留原本的訊息、空字串時清掉。"""
    lines = game.roster_lines()
    valid_keys = {key for _, key in lines}
    if person not in valid_keys:
        person = None
    on_team = person is not None and person in game.state.player.team
    toggle_label = "移出隊伍" if on_team else "加入隊伍"
    out = [
        f"**心得** {game.state.player.stats.get('xinde', 0)}　｜　{game.menxia_rules()}",
        game.member_card("player"),
        gr.update(choices=lines, value=person),
        game.member_card(person) if person else PERSON_HINT,
        gr.update(visible=person is not None, value=toggle_label),
        game.bag_text(),
        gr.update() if message is None else message,
        gr.update(choices=game.material_choices(), value=[]),
        game.craft_line([], KINDS[0]),
        gr.update(choices=game.art_library(), value=None),
    ]
    return out


def act(game: Game | None, action, note: bool = False) -> list:
    """同步時間 → 執行動作 → 存檔 → 重畫。拿跨程式的行動鎖（假人程式也拿同一把），避免計時器、按鈕點擊與假人同時操作。

    note=True 時連門下頁面一起重畫，動作回傳的訊息顯示在門下頁面的訊息區；
    回傳 UNCHANGED 時什麼都不存、不重畫。
    戰報頁面與大地圖頁面是獨立的整頁，不在這裡重畫（見 open_report_page、render_map_page）。
    """
    n = N_OUTPUTS if not note else N_OUTPUTS + MENXIA_OUTPUTS
    if game is None:
        return [gr.skip()] * n
    with game.world.action_lock():
        game.sync(time.time())
        msgs = action(game)
        if msgs is UNCHANGED:
            return [gr.skip()] * n
        save_game(game.state, save_path(game.state.player.name))
        out = render(game)
        if note:
            out += render_menxia(game, None, None if msgs is None else "\n\n".join(msgs))
        return out


def make_option_handler(index: int):
    def handler(game, ids):
        if game is None or index >= len(ids):
            return [gr.skip()] * N_OUTPUTS
        return act(game, lambda g: g.choose(ids[index]))

    return handler


def make_fast_forward_handler(hours: int):
    def handler(game):
        if game is not None and not game.is_admin():
            return act(game, lambda g: g.notice("（只有管理者能快轉時間。）"))
        return act(game, lambda g: g.advance(hours * 3600))

    return handler


def open_season_handler(game):
    return act(game, lambda g: g.admin_open_season(time.time()))


def next_season_handler(game):
    return act(game, lambda g: g.admin_next_season(time.time()))


def admin_choices() -> tuple[list[tuple[str, str]], list[tuple[str, str]], list[tuple[str, str]]]:
    """管理者觸發區的三個下拉選單：（戰鬥, 大事, 大勢線），每項是（顯示文字, id）。照內容固定；
    已經發生過的大事按下去會被引擎拒絕，不必在這裡過濾。"""
    scenario = CONTENT.scenario
    battles = [(b.name, b.id) for b in CONTENT.battles.values()]
    events = [(f"{x.text[:30]}（{x.id}）", x.id) for x in [*scenario.thresholds, *scenario.world_events]]
    trends = [(t.name, t.id) for t in scenario.trends]
    return battles, events, trends


def admin_battle_handler(game, battle_id):
    return act(game, lambda g: g.admin_start_battle(battle_id or "", time.time()))


def admin_fire_handler(game, fire_id):
    return act(game, lambda g: g.admin_fire(fire_id or ""))


def admin_trend_handler(game, trend_id, amount):
    return act(game, lambda g: g.admin_push_trend(trend_id or "", int(amount or 0)))


def seclude_handler(game, hours):
    return act(game, lambda g: g.seclude(int(hours)))


def battle_text_handler(game, text):
    return act(game, lambda g: g.submit_battle_custom_action(text))


def open_menxia(game, person=None):
    """「門下」：藏起江湖畫面、打開門下頁面並重畫。"""
    if game is None:
        return [gr.skip()] * (2 + MENXIA_OUTPUTS)
    with game.world.action_lock():
        return [gr.update(visible=False), gr.update(visible=True)] + render_menxia(game, person, "")


def close_menxia():
    """「返回江湖」。"""
    return [gr.update(visible=True), gr.update(visible=False)]


def roster_pick_handler(game, person):
    """在名冊點一個人：重畫門下頁面（不算行動、不存檔）。"""
    if game is None:
        return [gr.skip()] * MENXIA_OUTPUTS
    with game.world.action_lock():
        return render_menxia(game, person, "")


def toggle_team_handler(game, person):
    if game is None or person is None:
        return [gr.skip()] * MENXIA_OUTPUTS
    if person in game.state.player.team:
        return _menxia_act(game, lambda g: g.remove_from_team(person), person)
    return _menxia_act(game, lambda g: g.add_to_team(person), person)


def _menxia_act(game: Game, action, person: str | None) -> list:
    """門下頁面專屬的動作（加入/移出隊伍、練功、療傷）：同步、動作、存檔、只重畫門下頁面。"""
    with game.world.action_lock():
        game.sync(time.time())
        msgs = action(game)
        save_game(game.state, save_path(game.state.player.name))
        return render_menxia(game, person, "\n\n".join(msgs) if msgs else "")


def create_skill_handler(game, person, kind, name):
    if game is None:
        return [gr.skip()] * MENXIA_OUTPUTS
    return _menxia_act(game, lambda g: g.create_skill(name or "", kind), person)


def practice_handler(game, person, kind):
    if game is None:
        return [gr.skip()] * MENXIA_OUTPUTS
    return _menxia_act(game, lambda g: g.practice(kind), person)


def heal_handler(game, person):
    if game is None:
        return [gr.skip()] * MENXIA_OUTPUTS
    return _menxia_act(game, lambda g: g.heal(), person)


def craft_busy():
    """開爐之前先鎖住按鈕、說一句話：全服第一次發現某個配方時要等本機模型取名，
    實測 27~83 秒（配方已經有人煉過就是查表，瞬間完成）。"""
    return [
        gr.update(interactive=False, value="爐火正旺…"),
        "爐火正旺——若這個配方是江湖上第一次煉成，取名要花上一分鐘，請稍候。",
    ]


def craft_done():
    return gr.update(interactive=True, value="開爐煉製")


def craft_handler(game, person, material_ids, kind):
    if game is None:
        return [gr.skip()] * MENXIA_OUTPUTS
    return _menxia_act(game, lambda g: g.craft(list(material_ids or []), kind), person)


def craft_preview_handler(game, material_ids, kind):
    """選了素材／換了種類就更新成本說明（不算行動、不存檔）。"""
    if game is None:
        return gr.skip()
    return game.craft_line(list(material_ids or []), kind)


def switch_art_handler(game, person, art_id):
    if game is None or not art_id:
        return [gr.skip()] * MENXIA_OUTPUTS
    return _menxia_act(game, lambda g: g.switch_art(art_id), person)


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
    with game.world.action_lock():
        return _report_page(game.latest_battle_id(), game)


def open_report_handler(game):
    """場景卡片上的「看完整戰報」：打開戰報頁面，並選好卡片上的這一場。"""
    if game is None:
        return [gr.skip()] * 4
    with game.world.action_lock():
        return _report_page(game.battle_card_id(), game)


def close_report():
    """戰報頁面的「返回江湖」。"""
    return [gr.update(visible=True), gr.update(visible=False)]


def report_pick_handler(game, record_id):
    """在戰報列表點選一場：右邊顯示這一場的完整內容。"""
    if game is None:
        return gr.skip()
    with game.world.action_lock():
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
    with game.world.action_lock():
        return out + show_page("map") + render_map_page(game, DEFAULT_LAYER, None)


def map_page_handler(game, layer, selected):
    """切換圖層，或從下拉選單選地點：重畫大地圖頁面（不算行動，不存檔）。"""
    if game is None:
        return [gr.skip()] * MAP_OUTPUTS
    with game.world.action_lock():
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
    with game.world.action_lock():
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
    with game.world.action_lock():
        return out + show_page("map") + render_map_page(game, layer, selected, f"**沒能出發**：{reason}")


def close_world_map():
    """大地圖頁面的「返回江湖」。"""
    return show_page("main")


def skip_tutorial_handler(game):
    return act(game, lambda g: g.skip_tutorial())


def tick_handler(game, person):
    """計時器：同步時間，連同門下頁面一起重畫（保留目前的選取，氣血等數字才會跟著走）。"""
    if game is None:
        return [gr.skip()] * (N_OUTPUTS + MENXIA_OUTPUTS)
    with game.world.action_lock():
        game.sync(time.time())
        save_game(game.state, save_path(game.state.player.name))
        return render(game) + render_menxia(game, person, None)


def open_game(name: str) -> Game:
    """讀取存檔；舊格式讀不進來時，先把原檔備份到 saves/backup/ 再開新角色，不刪除任何東西。"""
    path = save_path(name)
    if not path.exists():
        return Game.new(CONTENT, name)
    try:
        state = load_game(path)
        if state.player.bot is not None:  # 伺服器假人的存檔：不讓真人接手（伺服器假人設計第五節）
            raise gr.Error(NAME_TAKEN)
        return Game(CONTENT, state)
    except gr.Error:  # gr.Error 也是 ValueError 的子類別：不先放行，下面會把假人的存檔當成壞檔備份掉
        raise
    except ValueError:  # pydantic 的 ValidationError 屬於 ValueError
        backup = SAVE_DIR / "backup" / f"{path.stem}-{int(time.time())}.json"
        backup.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, backup)
        game = Game.new(CONTENT, name)
        game.notice(f"（舊存檔的格式已不相容，已備份到 saves/backup/{backup.name}；這是新的開始。）", "舊存檔已備份")
        return game


LOGIN_FAILURES: dict[str, list[float]] = {}  # 擋猜密碼的紀錄，整個伺服器共用、只放記憶體（帳號密碼登入設計第三節）
NAME_MAX = 16  # 角色名號的長度上限
BAD_NAME = f"名號最多 {NAME_MAX} 字，也不能有看不見的字元。"  # 看不見的字元（零寬、控制、雙向排版）會讓兩個名號看起來一樣


def account_store() -> AccountStore:
    return AccountStore(SAVE_DIR / "accounts" / "accounts.json", failures=LOGIN_FAILURES)


def name_taken(name: str) -> bool:
    """名號有人用：已經有存檔（真人或假人一樣）、綁在某個帳號上，或是管理者的名號。
    假人與真人回同一句話，就沒辦法用名號試出誰是假人（帳號密碼登入設計第三節）。"""
    admins = {a.casefold() for a in CONTENT.config.admins}
    return save_path(name).exists() or account_store().owner_of(name) is not None or name.casefold() in admins


def _entered(game: Game, account_key: str) -> list:
    """進遊戲：藏起開始畫面與建立角色、顯示江湖畫面；管理者才看得到設定頁的管理者區塊。"""
    return (
        act(game, lambda g: None) + [gr.update(visible=False), gr.update(visible=False)]  # start_col、create_col
        + show_page("main") + [gr.update(visible=game.is_admin()), account_key]  # PAGES、admin_group、account_state
    )


def _needs_character(account_key: str) -> list:
    """登入了但帳號還沒有角色：顯示「取名號，建立角色」。"""
    return (
        [gr.skip()] * N_OUTPUTS + [gr.update(visible=False), gr.update(visible=True)]
        + [gr.skip()] * len(PAGES) + [gr.skip(), account_key]
    )


def login(login_name, password):
    try:
        account = account_store().authenticate(login_name, password)
    except AccountError as exc:
        raise gr.Error(str(exc))
    key = normalize(login_name)
    if account.character is None:
        return _needs_character(key)
    return _entered(open_game(account.character), key)


def register(login_name, password, again):
    if (password or "") != (again or ""):
        raise gr.Error(PASSWORDS_DIFFER)
    try:
        with WorldStateStore().action_lock():
            account_store().register(login_name, password)
    except AccountError as exc:
        raise gr.Error(str(exc))
    return _needs_character(normalize(login_name))


def create_character(account_key, name):
    """建立角色：檢查名號沒人用 → 建存檔 → 綁到帳號，三步在同一把行動鎖裡做完（不跟假人程式取名撞在一起）。"""
    if not account_key:
        raise gr.Error("請先登入。")
    name = unicodedata.normalize("NFKC", name or "").strip()  # 全形英數字當成一般英數字：不能用「Ｒａｙａｌ」冒充「Rayal」
    if not name:
        raise gr.Error("請先輸入你的名號。")
    if len(name) > NAME_MAX or any(unicodedata.category(ch) in ("Cc", "Cf") for ch in name):
        raise gr.Error(BAD_NAME)
    store = account_store()
    with WorldStateStore().action_lock():
        account = store.get(account_key)
        if account is None:
            raise gr.Error("請先登入。")
        if account.character is not None:  # 連按兩次：已經建好了，直接進遊戲
            game = open_game(account.character)
        else:
            if name_taken(name):
                raise gr.Error(NAME_TAKEN)
            game = Game.new(CONTENT, name)
            save_game(game.state, save_path(name))
            store.bind_character(account_key, name)
    return _entered(game, account_key)


def change_password_handler(account_key, old, new, again):
    """設定頁的修改密碼：結果寫在表單旁邊，不寫進江湖紀錄；成功或失敗都把三個密碼欄清空。"""
    if not account_key:
        return ["請先登入。", "", "", ""]
    if (new or "") != (again or ""):
        return [PASSWORDS_DIFFER, "", "", ""]
    try:
        with WorldStateStore().action_lock():
            account_store().change_password(account_key, old, new)
    except AccountError as exc:
        return [str(exc), "", "", ""]
    return ["密碼已更新。", "", "", ""]


def reset_password_handler(game, target, temp):
    """管理者幫人重設密碼（先照帳號找，再照名號找）；臨時密碼由管理者私下告訴對方。"""
    if game is None or not game.is_admin():
        return ["（只有管理者能重設密碼。）", ""]
    store = account_store()
    try:
        with WorldStateStore().action_lock():
            key = store.find(target)
            if key is None:
                return ["找不到這個帳號或名號。", ""]
            store.set_password(key, temp)
    except AccountError as exc:
        return [str(exc), ""]
    return [f"已重設 {store.get(key).login} 的密碼。", ""]


def build_demo() -> gr.Blocks:
    with gr.Blocks(title="天下大勢") as demo:
        game_state = gr.State(None)
        ids_state = gr.State([])
        gr.Markdown("# 天下大勢 · 原型")
        account_state = gr.State(None)
        with gr.Column(visible=True) as start_col:
            with gr.Tab("登入"):
                login_box = gr.Textbox(label="帳號")
                login_pw_box = gr.Textbox(label="密碼", type="password")
                login_btn = gr.Button("登入", variant="primary")
            with gr.Tab("註冊"):
                reg_box = gr.Textbox(label="帳號", placeholder="英文字母、數字、底線，3～20 字")
                reg_pw_box = gr.Textbox(label="密碼", type="password", placeholder="至少 6 字")
                reg_pw2_box = gr.Textbox(label="再輸入一次密碼", type="password")
                reg_btn = gr.Button("註冊", variant="primary")
        with gr.Column(visible=False) as create_col:
            gr.Markdown("這個帳號還沒有角色。取一個名號，踏入江湖。")
            name_box = gr.Textbox(label="你的名號", placeholder="例如：沈青衫")
            start_btn = gr.Button("建立角色", variant="primary")
        with gr.Row(visible=False) as game_row:
            with gr.Column(scale=3):
                with gr.Row(equal_height=False):
                    scene_md = gr.Markdown(scale=3)
                    with gr.Column(scale=2, min_width=180):
                        minimap_html = gr.HTML()  # 預設的 js_on_load：點一下就觸發 click
                        mini_map_btn = gr.Button("大地圖", size="sm")
                option_btns = [gr.Button(visible=False) for _ in range(MAX_BUTTONS)]
                # 全服即時戰鬥的自訂行動（20 字內）：魯莽/放手一搏這類選項是玩家自己想出
                # 來的招，不是固定清單裡選一個（見設計討論）；平常（不在這種回合）都隱藏。
                with gr.Row():
                    battle_text_tb = gr.Textbox(
                        visible=False, show_label=True, scale=4, placeholder="輸入你想做的事（20字內）", max_lines=1,
                    )
                    battle_text_btn = gr.Button("送出", visible=False, scale=1, variant="primary")
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
                        gr.Markdown("閉關可以得到心得，期間氣血回復加倍。")
                        hours_sl = gr.Slider(1, 12, value=8, step=1, label="閉關時數（小時）")
                        seclude_btn = gr.Button("開始閉關")
                    with gr.Tab("設定"):
                        anon_cb = gr.Checkbox(label="匿名行走（江湖傳聞中不顯示名號）")
                        skip_tutorial_btn = gr.Button("略過新手引導")
                        with gr.Group():
                            gr.Markdown("**修改密碼**")
                            old_pw_box = gr.Textbox(label="舊密碼", type="password")
                            new_pw_box = gr.Textbox(label="新密碼", type="password")
                            new_pw2_box = gr.Textbox(label="再輸入一次新密碼", type="password")
                            change_pw_btn = gr.Button("修改密碼")
                            change_pw_md = gr.Markdown()
                        with gr.Group(visible=False) as admin_group:
                            gr.Markdown("**管理者**")
                            with gr.Row():
                                open_season_btn = gr.Button("開季")
                                next_season_btn = gr.Button("開啟下一季")
                            gr.Markdown("時間快轉（全服一起快轉，只在測試時用）")
                            with gr.Row():
                                ff_btns = {h: gr.Button(f"+{h} 小時") for h in (1, 8, 24)}
                            battle_choices, event_choices, trend_choices = admin_choices()
                            gr.Markdown("觸發（人少、大勢推不到門檻時用；效果跟自然發生一樣）")
                            with gr.Row():
                                admin_battle_dd = gr.Dropdown(battle_choices, label="戰鬥", interactive=True)
                                admin_battle_btn = gr.Button("立刻開戰")
                            with gr.Row():
                                admin_fire_dd = gr.Dropdown(event_choices, label="大事", interactive=True)
                                admin_fire_btn = gr.Button("觸發")
                            with gr.Row():
                                admin_trend_dd = gr.Dropdown(trend_choices, label="大勢線", interactive=True)
                                admin_trend_nb = gr.Number(value=10, precision=0, label="推動量（負數＝壓低）")
                                admin_trend_btn = gr.Button("推動")
                            gr.Markdown("重設密碼（朋友忘記密碼時用；臨時密碼私下告訴他）")
                            with gr.Row():
                                reset_target_box = gr.Textbox(label="帳號或名號")
                                reset_pw_box = gr.Textbox(label="臨時密碼")
                                reset_btn = gr.Button("重設密碼")
                            reset_md = gr.Markdown()
        with gr.Column(visible=False) as menxia_col:
            with gr.Row(equal_height=True):
                gr.Markdown("## 門下", scale=1)
                back_btn = gr.Button("返回江湖", scale=0, min_width=120)
            mx_head_md = gr.Markdown()
            with gr.Row():
                with gr.Column(scale=1):
                    gr.Markdown("**本人**")
                    player_card_md = gr.Markdown()
                    gr.Markdown("**名冊**（本人與已招募的同伴；點名字看角色卡）")
                    roster_radio = gr.Radio(label="", choices=[], interactive=True)
                with gr.Column(scale=1):
                    gr.Markdown("**角色卡**")
                    person_card_md = gr.Markdown(PERSON_HINT)
                    team_toggle_btn = gr.Button("加入隊伍", visible=False)
            gr.Markdown("---")
            bag_md = gr.Markdown()
            craft_head_md = gr.Markdown()
            with gr.Row():
                craft_mats_dd = gr.Dropdown(
                    label=f"投入 {MATERIALS_PER_CRAFT} 樣素材（可以選同一種兩次）", choices=[],
                    multiselect=True, max_choices=MATERIALS_PER_CRAFT, interactive=True,
                )
                craft_kind_radio = gr.Radio(label="煉內功／武學", choices=list(KINDS), value=KINDS[0], interactive=True)
            craft_btn = gr.Button("開爐煉製", variant="primary")
            gr.Markdown("---\n**功法庫**：煉出來還沒配上身的功法。改練會把目前那一門收回庫裡，熟練度各自保留。")
            with gr.Row():
                arts_radio = gr.Radio(label="", choices=[], interactive=True)
                switch_btn = gr.Button("改練", scale=0, min_width=120)
            gr.Markdown("---\n**練功**：自創功法（取名決定屬性/威力/成長性，全服不能重名）或鍛鍊已學會的。")
            with gr.Row():
                kind_radio = gr.Radio(label="內功／武學", choices=list(KINDS), value="武學", interactive=True)
                skill_name_tb = gr.Textbox(label="自創功法的名字", placeholder="幫你的武學取個名字")
            with gr.Row():
                create_btn = gr.Button("自創功法", variant="primary")
                practice_btn = gr.Button("鍛鍊")
                heal_btn = gr.Button("療傷")
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
            battle_text_tb, battle_text_btn,
        ]
        assert len(outputs) == N_OUTPUTS
        pages = [game_row, menxia_col, report_col, map_col]
        assert len(pages) == len(PAGES)
        map_outputs = [map_head_md, layer_radio, world_map_html, place_dd, place_md, travel_btn]
        assert len(map_outputs) == MAP_OUTPUTS
        menxia_outputs = [
            mx_head_md, player_card_md, roster_radio, person_card_md, team_toggle_btn, bag_md, mx_message_md,
            craft_mats_dd, craft_head_md, arts_radio,
        ]

        entry_outputs = outputs + [start_col, create_col] + pages + [admin_group, account_state]
        login_btn.click(login, inputs=[login_box, login_pw_box], outputs=entry_outputs)
        login_pw_box.submit(login, inputs=[login_box, login_pw_box], outputs=entry_outputs)
        reg_btn.click(register, inputs=[reg_box, reg_pw_box, reg_pw2_box], outputs=entry_outputs)
        start_btn.click(create_character, inputs=[account_state, name_box], outputs=entry_outputs)
        name_box.submit(create_character, inputs=[account_state, name_box], outputs=entry_outputs)
        change_pw_btn.click(
            change_password_handler, inputs=[account_state, old_pw_box, new_pw_box, new_pw2_box],
            outputs=[change_pw_md, old_pw_box, new_pw_box, new_pw2_box],
        )
        reset_btn.click(reset_password_handler, inputs=[game_state, reset_target_box, reset_pw_box], outputs=[reset_md, reset_pw_box])
        for i, btn in enumerate(option_btns):
            btn.click(make_option_handler(i), inputs=[game_state, ids_state], outputs=outputs)
        seclude_btn.click(seclude_handler, inputs=[game_state, hours_sl], outputs=outputs)
        battle_text_btn.click(battle_text_handler, inputs=[game_state, battle_text_tb], outputs=outputs)
        battle_text_tb.submit(battle_text_handler, inputs=[game_state, battle_text_tb], outputs=outputs)
        anon_cb.input(anonymous_handler, inputs=[game_state, anon_cb], outputs=outputs)
        skip_tutorial_btn.click(skip_tutorial_handler, inputs=[game_state], outputs=outputs)
        for hours, btn in ff_btns.items():
            btn.click(make_fast_forward_handler(hours), inputs=[game_state], outputs=outputs)
        open_season_btn.click(open_season_handler, inputs=[game_state], outputs=outputs)
        next_season_btn.click(next_season_handler, inputs=[game_state], outputs=outputs)
        admin_battle_btn.click(admin_battle_handler, inputs=[game_state, admin_battle_dd], outputs=outputs)
        admin_fire_btn.click(admin_fire_handler, inputs=[game_state, admin_fire_dd], outputs=outputs)
        admin_trend_btn.click(
            admin_trend_handler, inputs=[game_state, admin_trend_dd, admin_trend_nb], outputs=outputs
        )

        menxia_btn.click(open_menxia, inputs=[game_state], outputs=[game_row, menxia_col] + menxia_outputs)
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
        roster_radio.input(roster_pick_handler, inputs=[game_state, roster_radio], outputs=menxia_outputs)
        team_toggle_btn.click(toggle_team_handler, inputs=[game_state, roster_radio], outputs=menxia_outputs)
        create_btn.click(
            create_skill_handler, inputs=[game_state, roster_radio, kind_radio, skill_name_tb], outputs=menxia_outputs
        )
        practice_btn.click(practice_handler, inputs=[game_state, roster_radio, kind_radio], outputs=menxia_outputs)
        heal_btn.click(heal_handler, inputs=[game_state, roster_radio], outputs=menxia_outputs)
        craft_btn.click(craft_busy, outputs=[craft_btn, mx_message_md]).then(
            craft_handler, inputs=[game_state, roster_radio, craft_mats_dd, craft_kind_radio],
            outputs=menxia_outputs,
        ).then(craft_done, outputs=[craft_btn])
        craft_mats_dd.input(
            craft_preview_handler, inputs=[game_state, craft_mats_dd, craft_kind_radio], outputs=[craft_head_md],
        )
        craft_kind_radio.input(
            craft_preview_handler, inputs=[game_state, craft_mats_dd, craft_kind_radio], outputs=[craft_head_md],
        )
        switch_btn.click(switch_art_handler, inputs=[game_state, roster_radio, arts_radio], outputs=menxia_outputs)
        gr.Timer(10).tick(tick_handler, inputs=[game_state, roster_radio], outputs=outputs + menxia_outputs)
    return demo


if __name__ == "__main__":
    build_demo().launch(server_name="0.0.0.0", server_port=7861, share=True)
