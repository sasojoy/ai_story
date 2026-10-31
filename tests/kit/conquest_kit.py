"""領地爭奪（第 38 項改版）測試共用的建法（計畫的 Global Constraints：不改 tests/conftest.py，共用的放這裡）。"""
from __future__ import annotations

import random
import tempfile
from pathlib import Path
from unittest import mock

from conftest import real_content
from tianxia import conquest, conquest_day, team, territory
from tianxia.encounter import EncounterResult
from tianxia.engine import Game
from tianxia.models import Content
from tianxia.sqlite_world import open_world
from tianxia.state import SiegeSlot


def conquest_rules(content: Content, xingshi: bool = False) -> Content:
    """領地爭奪的測試用的內容（地盤開著就是領地爭奪，沒有開關），回傳同一份內容。〈天下形勢〉（第三批 A，Config.xingshi）預設關掉：第一、二批的測試照舊
    （每天結算不開單、不多一則天下大事），要測它的另外給 xingshi=True。
    減法季的出陣約戰（批 3b，jianfa 的 sortie_duel）關掉：這裡建的局測的是翻地、混戰、出陣攻守那一套（season21、week7 的設定減法季開著，
    出陣換成約戰之後那幾條就不成立了；斷言不動。約戰的測試在 tianxia/features/sortie/tests/test_sortie_duel*.py，建法 tests/kit/duel_kit.py）。"""
    content.config.xingshi.enabled = xingshi
    content.config.jianfa.sortie_duel = False
    return content


def _new(content: Content, name: str, world=None) -> Game:
    """world 沒給：每一局自己一個資料庫檔（同一條測試建兩局時，第二局不會讀到第一局種下、蓋了別的章的季）。"""
    content.config.auto_open_first_season = True
    if world is None:
        world = open_world(Path(tempfile.mkdtemp(prefix="conquest-")) / "tianxia.db")
    game = Game.new(content, name, rng=random.Random(0), world=world)
    game.client = None
    territory.update(game.state.world, content)  # 開季那一下：第一次算，不發天下大事
    return game


def conquest_game(profile: str = "season21", name: str = "沈浪", world=None, xingshi: bool = False) -> Game:
    """正式內容、開季時就打開領地爭奪的一局（同 test_territory._game 的建法）；xingshi 打開〈天下形勢〉。"""
    return _new(conquest_rules(real_content(profile), xingshi), name, world)


def plain_game(profile: str = "week7", name: str = "沈浪", world=None) -> Game:
    """同上，正式內容照原樣（領地爭奪 2026-10-27 起沒有開關，地盤開著就是）。"""
    return _new(real_content(profile), name, world)


def join(game: Game, side: str | None) -> Game:
    """直接把陣營寫進存檔（不走投靠的確認），引導走完、體力補滿：完成步驟的獎勵與序章不混進出陣的帳。"""
    p, c = game.state.player, game.content
    p.faction = side
    p.tutorial_step = len(c.tutorial.steps)
    p.stamina = float(c.config.stamina_max)
    return game


def go(game: Game, loc_id: str) -> Game:
    p = game.state.player
    p.location, p.journey = loc_id, None
    p.visited.add(loc_id)
    return game


def fight(tier: str = "大勝"):
    """單次判定照給的結果（同 test_sortie._fight）。"""
    return mock.patch.object(team, "fight", return_value=EncounterResult(tier=tier, margin=50, our_power=200, difficulty=40))


def win_sortie(game: Game) -> list[str]:
    """在所在地出陣攻、打贏一場（固定結果）。"""
    with fight():
        return game.choose("act:train")


def contribution(game: Game) -> int:
    """本季的貢獻（push.add_contribution 寫進的那一份）。"""
    return game.state.player.contrib


def announce(game: Game, loc_id: str, side: str, minute: int = 21 * 60, merged: tuple[str, ...] = ()) -> SiegeSlot:
    """把一場攻城直接排進今天的時程表（同戰書排的那一場，不看階與門檻、不記 day_log）：side 攻 loc_id，一小時後開打、半小時後開集結。
    merged 給兩軍時併成一場。名字是第二批（每天公告）留下來的；那時寫 by="commander"（主將定奪），輿圖第三版第 5 批收掉之後寫戰書。"""
    w = game.state.world
    attackers = list(merged) or [side]
    slot = SiegeSlot(
        id=f"t-{loc_id}-{len(w.conquest.schedule)}", key=w.conquest.settled_key, loc=loc_id, minute=minute,
        at=w.time + 3600, muster_at=w.time + 1800, attackers=attackers,
        by={a: conquest_day.LETTER for a in attackers}, reasons={a: "" for a in attackers},
    )
    w.conquest.schedule.append(slot)
    return slot


def press(game: Game, loc_id: str, side: str, amount: float = 20, name: str = "敵將") -> None:
    """side 在這一塊推了一截（翻地與爭搶：守城軍令認「自家被推得最高、守得動」的那幾塊，conquest.focus_blocks）。第二批的測試拿 announce
    當「這一塊被公告要攻」的，翻地之後換成這個——announce 排進時程表等於那一塊被戰書凍結，凍結的守不動、不算守城的地方。"""
    conquest.push(game.state.world, game.content, loc_id, side, name, amount, "attack")
