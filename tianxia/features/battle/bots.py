"""假人看到決戰的選項怎麼按（開發規範手冊 3.8；原本寫在 bot_policy.score 的 battle 那一段與 bot_policy._battle_score，全部拆包第 7 批拿了
battle: 前綴之後搬來，照宴客）。bot_policy 照舊留著 _battle_score、JOIN_BATTLE_SCORE 這兩個名字（tests/bots/test_bot_policy.py、
tests/season/test_real_content.py 直接叫；指到這裡同一個函式、同一個數）。

集結時的加入、臨時投效由 bot_policy.take_turn 自己挑（battle:join 一看到就按、投效照 bot.enlist_pick），回合裡的三招由 battle_move 挑；
走到打分數的只有這兩支剩下的：加入與晚到一律 JOIN_BATTLE_SCORE，出招照份量，其餘（挑同伴、觀戰、已選擇……）不按。

投效挑哪一軍（enlist_pick，從 bot）、走向決戰與別走出決戰的大區（_toward_battle、_staying_for_the_battle，從 bot_policy）第二輪第 101 批搬來，舊名 re-export 同一批物件；take_turn 叫這幾支的先後留在殼。下一站在共用層 bot_base（`bot_base.next_hop`）。**模組層不准碰 engine 與假人殼**（bot、bot_policy 模組層 import 這個檔）。
"""
from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING

from . import instance as battle_instance  # 這一包的回合規則（第 54 批搬進來：招的份量、氣血狀態）
from tianxia import atlas, bot_base
from tianxia.core.option import Option

if TYPE_CHECKING:
    from tianxia.engine import Game

JOIN_BATTLE_SCORE = 100.0


def battle_score(game, arg: str) -> float | None:
    """集結或晚到時加入（一定站自己陣營那邊，引擎只給這個選項）；交戰中照自己每招的份量（乘這一場的氣血狀態）打分數，
    扣血相對剩下的氣血越重扣分越多（決戰改版一）。沒有招的選項一律 0。
    沒有快照（份量全 0）時只剩扣血的差別，損耗最低的固守分數最高。"""
    kind, _, tag = arg.partition(":")
    if kind in ("join", "join_late"):
        return JOIN_BATTLE_SCORE
    if kind != "act":
        return None
    battle = game.battle_now()  # 自己參戰的那一場（決戰或攻城，領地爭奪第二批）
    definition = game.content.battles[battle.battle_id]
    me = battle.participants.get(game.state.player.name)
    if me is None:
        return 0.0
    tuning = game.content.config.battle
    hp = max(me.neili, 1.0)
    option = battle_instance.option_of(definition, battle.act_index, me.faction, tag)
    if option is None or option.move is None:  # 放手一搏等沒有招的：假人不選（free_text 本來就排除）
        return 0.0
    return me.scores.get(option.move, 0.0) * battle_instance.condition(me) / 100 - tuning.damage[option.move] / hp


def score(game, option: Option) -> float | None:
    """選項的分數；None＝假人不會按。"""
    return battle_score(game, option.id.partition(":")[2])


def enlist_pick(game: Game, option_ids: list[str]) -> str | None:
    """投靠了陣營、卻不是交戰兩軍的機器人（地方豪強）怎麼臨時投效（Joy 2026-10-13「豪強在大決戰還是要加入某一陣營」）：
    投人少的那一軍，一樣多照名號＋這一場的雜湊挑（不碰亂數）。散人不走這裡（散人的假人不投效）；選單上沒有投效鈕是 None。"""
    battle = game.battle_now()  # 有攻城戰時是自己看的那一場（領地爭奪第二批）
    sides = [i for i in option_ids if i.startswith("battle:enlist:")]
    if battle is None or not sides or game.state.player.faction is None:
        return None
    counts = {  # 鈕 id 可能帶「@流水號」（同一個大區兩場以上，領地爭奪第二批）
        i: sum(1 for p in battle.participants.values() if p.faction == i.removeprefix("battle:enlist:").partition("@")[0]) for i in sides
    }

    def tie(option_id: str) -> str:
        return hashlib.sha256(f"{game.state.player.name}|{battle.battle_id}|{option_id}".encode()).hexdigest()

    return min(sides, key=lambda i: (counts[i], tie(i)))


def _toward_battle(game: Game) -> list[str] | None:
    """自己這一方的全服決戰在集結或開打、自己人卻不在現場（見 Game.rally_region）：往那個大區路程最近的地點走一站，步行
    （企劃者 2026-10-12 拿掉趕路之前是體力夠就趕路；假人不疾行）。不是這種情況、走不過去、或現在不能
    安排前往（例如有事件待處理）就回傳 None，照平常挑選項。"""
    region = game.rally_region()
    if region is None:
        return None
    hop = bot_base.next_hop(game, atlas.region_locations(game.content, region))
    if hop is None:
        return None
    if game.state.player.ambush is not None:  # 守著埋伏走不開：先收伏，下一輪再動身
        return game.choose("ambush:lift")
    ways = {option.mode: option for option in game.travel_options(hop) or []}
    if "walk" in ways and ways["walk"].enabled:
        return game.travel(hop, "walk")
    return None


def _staying_for_the_battle(game: Game, battle_id: str, options: list[Option]) -> list[Option]:
    """已經參戰的假人在集結時不走出決戰的大區：集結時選單照常有前往（FB-009），但以前選單只有加入、假人一直待在
    現場，開打時人都在；區內站與站之間照常走。決戰不限地點時不用管。"""
    definition = game.content.battles.get(battle_id)
    region = definition.region if definition is not None else None
    if region is None:
        return options

    def leaves(option_id: str) -> bool:
        if not option_id.startswith("move:"):
            return False
        dest = atlas.region_of(game.content, option_id[len("move:"):].partition(":")[0])
        return dest is None or dest.id != region

    return [o for o in options if not leaves(o.id)]
