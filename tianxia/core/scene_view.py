"""場景卡（核心本體；第二輪第 91 批，計畫 docs/superpowers/plans/2026-11-07-第二輪-第91批.md，導覽 docs/guide/核心與存檔.md）。

江湖頁場景卡的文字與上面那張圖。原本是 Game 上的 5 個方法（第一階 ctx 就是 Game，開發規範手冊 3.3）；Game 留 5 個一行委派（名字照舊，server 與測試都讀）。
「眼前是哪一張」原本是一條寫死哪一包排第幾的 if 鏈，現在照 core/features.py 的 SCENE_ORDER 一格一格問：核心留收季、事件、地點三格（OWN_CORE、ART_CORE），其餘十包（bout、battle、feast、sense、story、companions、faction、socialize、military、travel）登記 Feature.scenes()。

- 模組裡互相叫直接叫函式（沒有一個被測試換掉，量過；_core_refs 只看 ast.Name，這樣 test_for 才算得到呼叫端）。留在 Game 上的（_event_text）與 features_core.scene_over 經 ctx、經模組。
- 被測試換掉的模組屬性（place_state.on、place_state.kind_at、precise.on）：place_state.view、marks_rules.describe、atlas.region_of、story_base.stage_art 一律寫「模組.函式」，不 from … import 函式。
  jianfa、season_one、fill_marks 照 page_view 從 ..rules 拿名字（沒有人換）。
- scene_art 的 place 那一格靠「_own_scene_text == location_text」判斷真的站在地點上：讀的是整條 own 鏈，少登記一格，地點的圖會蓋在那一格的畫面上。

engine 在 page_view、status_view 之後才 import 這一份（這裡 import 的模組那時都已經載入）。

改這一份要跑的測試：scripts/test_for.py（CORE_SERVICES：這個檔的底 scene、place、marks、engine，加改到的函式那一群）；
same_behavior 的 vista、stack 兩軌（場景的先後與圖，兩層以上疊著的只有這兩軌比）。
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from .. import atlas, place_state, story_base
from .. import marks as marks_rules
from ..rules import fill_marks, jianfa, season_one
from . import features as features_core

if TYPE_CHECKING:
    from ..engine import Game  # noqa: F401  ctx 就是 Game（第一階）


def place_state_view(ctx: Game) -> dict | None:
    """地點會變樣（main.place_state）：此刻所在地的樣子 {kind, name, line}；太平、在路上、關著是 None。"""
    s = ctx.state
    if s.player.journey is not None:
        return None
    return place_state.view(s.world, ctx.content, s.player.location)


def location_text(ctx: Game) -> str:
    loc = ctx.content.locations[ctx.state.player.location]
    # 地點會變樣（世界活起來第二批）：不是太平的地方，地名那一行底下多一段「〔戰火〕這一帶剛打過仗……」；地名那一行不動
    # （有畫時網頁照 scene_art 的 head 把它拿掉、疊在畫上）。太平、關著一個字都不變
    mood = place_state.view(ctx.state.world, ctx.content, loc.id)
    head = f"【{loc.name}】危險 {'★' * loc.danger}" + (f"\n\n〔{place_state.NAMES[mood['kind']]}〕{mood['line']}" if mood is not None else "")
    if jianfa(ctx.content, ctx.state.world, "marks_visible"):  # 減法季批 4：痕跡過了門檻，描寫多接一段（marks.describe）
        return f"{head}\n\n{marks_rules.describe(loc, ctx.state.world, ctx.content)}"
    return f"{head}\n\n{loc.describe(ctx.state.world.flags)}"  # 宛城的描寫隨版本換


def _art_ended(ctx: Game) -> dict | None:
    return {} if ctx.state.world.ended else None


def _art_event(ctx: Game) -> dict | None:
    s, c = ctx.state, ctx.content
    if not s.pending_event:
        return None
    event = c.events[s.pending_event]
    own = story_base.stage_art(s, c)  # 一條線事件段的專屬圖（StoryStage.image）蓋過事件的類型圖
    if not event.image and own is None:
        return {}
    path = own or f"events/{event.image}"
    return {"kind": "event", "path": path, "title": event.title, "sub": "", "head": f"**{event.title}**"}


def _art_place(ctx: Game) -> dict:
    s, c = ctx.state, ctx.content
    if _own_scene_text(ctx) != location_text(ctx):  # 投靠、叛投、求見、伏筆問話、在路上……都不是地點的描寫
        return {}
    loc = c.locations[s.player.location]
    if loc.image:
        path = loc.image
    else:
        region = atlas.region_of(c, loc.id)
        path = f"places/{region.id}" if region is not None else "places/world"
    art = {"kind": "place", "path": path, "title": loc.name, "sub": f"危險 {'★' * loc.danger}", "head": f"【{loc.name}】危險 {'★' * loc.danger}"}
    mood = place_state.view(s.world, c, loc.id)  # 地點會變樣：疊在畫上的那一行多寫此刻的樣子，畫照樣子換色調（網頁的 mood-<kind>）
    if mood is not None:
        art["sub"] += f"・{mood['name']}"
        art["mood"] = mood["kind"]
    return art


def scene_art(ctx: Game) -> dict | None:
    """江湖頁場景卡上面那張圖（減法季批 8 圖像版；減法季整合設計第八章、第一批圖提示單）。回 {kind, path, title, sub, head}：
    path 是 web/img/ 底下不含副檔名的路徑；head 是場景 Markdown 的第一行（地名那一行、事件標題、人名），有圖時網頁把它疊在圖上、
    不在卡片裡寫第二次。事件開著（pending_event）→ 事件的類型圖 events/<Event.image>；跟人物談話 → 他的像（CharacterDef.image）；
    平常站在地點 → Location.image，沒寫就是所屬大區的 places/<大區 id>（atlas.region_of），沒有大區是 places/world。
    其餘的畫面一律 None、一字不變：全服戰鬥蓋著場景、季收了、單挑、擂台、宴席、有所感、投靠與叛投、求見名單、伏筆問話、在路上，
    還有事件沒寫 image、人物沒有像。圖檔在不在是伺服器的事（server.scene_art）。"""
    return features_core.scene_first("art", ART_CORE, ctx) or None


def scene_text(ctx: Game) -> str:
    """有全服戰鬥時大家都看得到戰場；照常遊玩的人（集結中、只能觀戰、開打了還沒投效的散人，見 _fighting），自己眼前的事
    （事件、對話、地點）接在戰場底下，不然遇到事件時只看得到選項、看不到事件本身。序章裡不畫戰場（_battle_for_me）。
    蓋在畫面上的問功能包（scene_over，接縫掛鉤，第 11 批）：決戰包回（戰場那一段, 要不要整個取代）。"""
    over = features_core.scene_over(ctx)
    if over is None:
        return _own_scene_text(ctx)
    battle_scene, whole = over
    if whole:
        return battle_scene  # 開打後在場上的人：戰場取代整個畫面；其餘照常遊玩，自己眼前的事接在底下（同 options）
    return f"{battle_scene}\n\n---\n\n{_own_scene_text(ctx)}"


def _own_ended(ctx: Game) -> str | None:
    s, c = ctx.state, ctx.content
    if not s.world.ended:
        return None
    if season_one(c, s.world):  # 第一季：結局寫在江湖頁最上面的結算卡（season_result），場景寫所在的地方（FB-046）
        return location_text(ctx)
    return f"## {s.world.ending_title}\n\n{s.world.ending_text}"


def _own_event(ctx: Game) -> str | None:
    s, c = ctx.state, ctx.content
    if not s.pending_event:
        return None
    event = c.events[s.pending_event]
    return f"**{event.title}**\n\n{fill_marks(ctx._event_text(event), s)}"


def _own_scene_text(ctx: Game) -> str:
    """自己眼前的那一張：照 SCENE_ORDER["own"] 一格一格問，第一個不是 None 的算（"" 也算：取名的意境不在了，文字就是空字串，不往下掉）。"""
    return features_core.scene_first("own", OWN_CORE, ctx)


# 場景卡核心自己的格（SCENE_ORDER 那張表上不是包登記的；放在檔尾：上面的函式都定義過了）
OWN_CORE = {"ended": _own_ended, "event": _own_event, "place": location_text}
ART_CORE = {"ended": _art_ended, "event": _art_event, "place": _art_place}
