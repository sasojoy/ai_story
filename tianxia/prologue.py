"""序章（新手引導重做設計第三、六、七節）：新角色先在師父的草廬走完前 Tutorial.prologue_steps 步，才進真實世界。

草廬是 Location.prologue_only 的地點：只有站在那裡的人看得到、到得了（atlas.is_unlocked）。序章每一步的特別規則
寫在 TutorialStep 上（content/tutorial.json），這裡把它們讀出來給 engine 用；步驟怎麼推進照舊是 guide.note_action。
沒有序章的內容（tutorial.location 是 None，例如測試內容）這裡每個函式都是「什麼都不做」。"""
from __future__ import annotations

import random
from typing import TYPE_CHECKING

from .martial_arts import MartialArt
from .models import Content, GiveArt, TutorialStep
from .rules import apply_effect
from .state import ONBOARDING_VERSION, GameState, PlayerState
from .world_state import WorldStateStore

if TYPE_CHECKING:  # Option 定義在 engine.py，engine 又 import 這個模組：只給型別標註用，執行時不 import（避免循環）
    from .engine import Option

OLD_BASE_STEPS = 6  # 舊引導不分季的六步（t1～t6）；舊存檔第 6 步起是第一季的兩步（t7、t8），換成序章之後往後挪


def has(content: Content) -> bool:
    return content.tutorial.location is not None


def active(state: GameState, content: Content) -> bool:
    """在序章裡：站在草廬，而且序章還沒走完。走在出師的路上也算（抵達潁川那一刻才離開草廬）。"""
    t = content.tutorial
    return t.location is not None and state.player.location == t.location and state.player.tutorial_step < t.prologue_steps


def step(state: GameState, content: Content) -> TutorialStep | None:
    return content.tutorial.steps[state.player.tutorial_step] if active(state, content) else None


def start_stamina(content: Content) -> int:
    """序章開局的體力：探索一次、合成一次、修練一次剛好用完，第 7 步才有「體力見底、打坐」（設計 3.2）。
    合成的體力是武學與成長計畫五加的（Config.fuse_stamina，5）：設計 3.2 寫的 20 是那之前的算法，現在是 25。"""
    cfg = content.config
    return cfg.action_cost["explore"] + cfg.fuse_stamina + cfg.cultivate_stamina


def begin(state: GameState, content: Content) -> None:
    """把角色放進序章的第一步：草廬、序章的體力、開場事件（遇險）。新角色（Game.new(prologue=True)）與序章走到一半就換季的
    角色用；可以重複呼叫。"""
    t, p = content.tutorial, state.player
    if t.location is None:
        return
    p.location = t.location
    p.journey = None
    p.visited.add(t.location)
    p.tutorial_step = 0
    p.stamina = float(start_stamina(content))
    state.pending_event = t.start_event


def _prologue_events(content: Content) -> set[str]:
    """序章會端出來的事件：開場那一則一路接下去的（next_event），加上每一步的 explore_event。"""
    t = content.tutorial
    found: set[str] = set()
    todo = [t.start_event] + [s.explore_event for s in t.steps[: t.prologue_steps]]
    while todo:
        event_id = todo.pop()
        if event_id is None or event_id in found or event_id not in content.events:
            continue
        found.add(event_id)
        todo += [ch.effect.next_event for ch in content.events[event_id].choices]
    return found


def finish(state: GameState, content: Content, world: WorldStateStore, *, purse: bool) -> list[str]:
    """不是一步一步走完、而是直接離開序章（略過、不走序章的角色、讀檔時發現序章卡住）：站到起點、序章的事件收掉、
    步數跳過序章。purse：給出師那一步的獎勵（盤纏、體力補滿；設計 7.3：略過的人也拿）。回傳獎勵的訊息。"""
    t, p = content.tutorial, state.player
    if t.location is None:
        return []
    if p.location == t.location:
        p.location = content.scenario.start_location
        p.journey = None
        p.resting_since = None
    p.visited.add(p.location)
    if state.pending_event in _prologue_events(content):
        state.pending_event = None
    msgs: list[str] = []
    if p.tutorial_step < t.prologue_steps:
        p.tutorial_step = t.prologue_steps
        if purse:
            msgs = apply_effect(t.steps[t.prologue_steps - 1].reward, state, content, world)
    if purse:
        p.stamina = max(p.stamina, float(content.config.stamina_max))
    return msgs


def choice_flags(content: Content, event_id: str, index: int) -> set[str]:
    """選了事件的第 index 個選項之後，（接下去的事件任選）有機會留下哪些旗標。假人走序章（Game._graduate）用它挑
    「走得到這一步完成條件」的選項，不靠寫死的選項編號：內容怎麼改，走法跟著改。"""
    found: set[str] = set()
    seen: set[str] = set()
    todo = [content.events[event_id].choices[index].effect]
    while todo:
        effect = todo.pop()
        found.update(effect.flags_add)
        nxt = effect.next_event
        if nxt is not None and nxt in content.events and nxt not in seen:
            seen.add(nxt)
            todo += [ch.effect for ch in content.events[nxt].choices]
    return found


def migrated_step(player: PlayerState, content: Content) -> int:
    """舊存檔（onboarding 比 ONBOARDING_VERSION 小）的引導步數換成新的：一律當作走過序章（設計 7.2），
    舊的第一季兩步（舊的第 6、7 步）接在序章後面、走到哪裡就接著那裡。沒有序章的內容照舊。"""
    n = content.tutorial.prologue_steps
    if player.onboarding >= ONBOARDING_VERSION or n == 0:
        return player.tutorial_step
    return n + max(0, player.tutorial_step - OLD_BASE_STEPS)


def allowed(options: list[Option], state: GameState, content: Content) -> list[Option]:
    """在草廬閒著的時候選單只留這一步要的（TutorialStep.allow，前綴比對）：新人不會在草廬交友、亂打坐打亂了步驟。"""
    current = step(state, content)
    if current is None:
        return options
    return [o for o in options if any(o.id.startswith(prefix) for prefix in current.allow)]


def can_travel(state: GameState, content: Content) -> bool:
    """輿圖的安排前往：序章裡只有出師那一步（allow 有 move:）走得了。"""
    current = step(state, content)
    return current is None or any(prefix.startswith("move:") for prefix in current.allow)


# ── 序章裡安排好的結果（每一步的特別規則，TutorialStep 的欄位）：都只在序章裡有，不在序章回「不管」的值 ──


class SureRandom(random.Random):
    """random() 永遠是 0：修練擲骰一定中（序章第 6 步，設計 3.2：第一次修練一定升品）。"""

    def random(self) -> float:
        return 0.0


def explore_event(state: GameState, content: Content) -> str | None:
    """這一步在草廬探索，一定端出哪則事件（四景四選一）。"""
    current = step(state, content)
    return current.explore_event if current is not None else None


def enemies(state: GameState, content: Content) -> list[str]:
    """這一步草廬的對手（遊歷才出現：雪恥那一步才有斷眉）；序章裡別的步驟是空的。"""
    current = step(state, content)
    return list(current.enemies) if current is not None else []


def fight_tier(state: GameState, content: Content) -> str | None:
    """這一步的遊歷結果照寫好的（雪恥：險勝）；沒有就是 None（照平常擲）。"""
    current = step(state, content)
    return current.force_tier if current is not None else None


def instant_rest(state: GameState, content: Content) -> str:
    """非空：這一步的打坐一坐就回滿（說這一句）；空字串是照平常的打坐。"""
    current = step(state, content)
    return current.instant_rest if current is not None else ""


def sure_rng(state: GameState, content: Content) -> random.Random | None:
    """這一步的修練一定升品：回一個永遠擲中的亂數；其他時候是 None（用遊戲自己的亂數）。"""
    current = step(state, content)
    return SureRandom() if current is not None and current.sure_cultivate else None


def melt_only(state: GameState, content: Content) -> str | None:
    """序章裡只准熔哪一門；序章裡別的步驟一門都不准熔（回空字串）；不在序章是 None（不限）。"""
    current = step(state, content)
    if current is None:
        return None
    return current.melt_only or ""


def fuse_base(state: GameState, content: Content) -> str | None:
    """序章裡合成只准拿哪一門當底；序章裡別的步驟不准合成（回空字串）；不在序章是 None（不限）。"""
    current = step(state, content)
    if current is None:
        return None
    return current.fuse_base or ""


# 不照劇本走的動作：序章裡亂按不會收到東西、也不會把後面的步驟卡死（準備好的心得、體力是照劇本算的）。
# 回傳擋下的原因（要寫給玩家看的一句話）；None＝可以做（含不在序章）。跟 melt_only 一樣，動作的拒絕與修練頁、煉製頁的按鈕走同一個判斷。


def fuse_problem(
    state: GameState, content: Content, art_id: str | None, insight_ids: list[str], other_art: str | None = None,
) -> str | None:
    """序章裡開爐：只准在合成那一步、拿師父說的那一門融一個意境；別的（別的底、兩門武學、合併、別的步驟）都擋。"""
    base = fuse_base(state, content)
    if base is None:
        return None
    if not base:
        return "師父這一步沒叫你合成。"
    if art_id != base or other_art or len(insight_ids) != 1:
        return f"師父要你拿【{content.skills[base].name}】融一個意境。"
    return None


def practice_problem(state: GameState, content: Content, world: WorldStateStore, kind: str) -> str | None:
    """序章裡練成：只在「練到第幾成」那一步（done_when.fused_level）、練身上換上的那一門合成出來的武學；
    心得是照劇本備的，花在基本功上就練不到第三成。"""
    current = step(state, content)
    if current is None:
        return None
    if not current.done_when.fused_level:
        return "師父這一步沒叫你練功。"
    member = state.player.member
    worn = member.neigong_id if kind == "內功" else member.wugong_id
    if worn is None or worn not in {art.id for art in fused_arts(state, content, world)}:
        return "師父要你練新得的那一門，先把它換上。"
    return None


def cultivate_problem(state: GameState, content: Content) -> str | None:
    """序章裡修練：只在安排好一定升品的那一步（sure_cultivate）；體力是照劇本備的。"""
    current = step(state, content)
    if current is None or current.sure_cultivate:
        return None
    return "師父這一步沒叫你修練。"


def seclude_problem(state: GameState, content: Content) -> str | None:
    """序章裡不閉關：閉關是師父沒教的一條路，而且一次就能把心得賺過劇本備好的帳（20 → 170）。待 joy 潤。"""
    return "師父沒叫你閉關。" if active(state, content) else None


def melt_insight_problem(state: GameState, content: Content) -> str | None:
    """序章裡不熔意境：序章的意境是合成要用的，熔了後面就走不下去。待 joy 潤。"""
    return "師父沒叫你熔意境。" if active(state, content) else None


def fused_arts(state: GameState, content: Content, world: WorldStateStore) -> list[MartialArt]:
    """身上與功法庫裡合成出來的武學（自己那一份，品質照自己修到的），照擁有的順序。"""
    from . import library, team  # team、library 都 import 很多東西，放在函式裡避免循環

    arts = (team.player_art(state, content, world, art_id) for art_id in library.owned_arts(state))
    return [art for art in arts if art is not None and art.origin == "fused"]


def fill(text: str, state: GameState, content: Content, world: WorldStateStore) -> str:
    """序章的話裡的 {武學}：換成合成出來的那一門（序章只合一門）；還沒有就寫「新武學」。"""
    if "{武學}" not in text:
        return text
    arts = fused_arts(state, content, world)
    return text.replace("{武學}", arts[0].name if arts else "新武學")


def give_art(state: GameState, content: Content, world: WorldStateStore, give: GiveArt) -> list[str]:
    """完成某一步時給一門內容武學（雪恥之後掉出來的雜學），照寫的成數；已經有了就不給。"""
    from . import library, team

    if give.id in library.owned_arts(state):
        return []
    art = team.resolve_art(give.id, content, world)
    msgs = library.store_art(state, art)
    member = state.player.member
    if member.wugong_id == give.id:
        member.wugong_level = give.level
    elif member.neigong_id == give.id:
        member.neigong_level = give.level
    else:
        state.player.art_levels[give.id] = give.level
    return msgs


def view(state: GameState, content: Content) -> dict | None:
    """網頁的序章畫面（設計 6.1）：reveal 是到這一步為止亮起來的元件（排序過），glow 是這一步要發光的鈕，
    skip 是第一步才有的「略過序章」。不在序章是 None（網頁照平常畫）。"""
    current = step(state, content)
    if current is None:
        return None
    t = content.tutorial
    shown = {key for s in t.steps[: state.player.tutorial_step + 1] for key in s.reveal}
    return {"reveal": sorted(shown), "glow": list(current.glow), "skip": state.player.tutorial_step == 0}
