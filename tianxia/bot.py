"""亂數機器人：玩完一整季，用於整季測試與平衡模擬。

sanguo-companions 合併大幅重寫：拿掉抽卡、收徒、多隊派遣——招募到新同伴後不用機器人
額外處理，roster.attempt_recruit/recruit 已經自動把人加進隊伍（見 roster.py）。大多數
時候隨機選一個可用的選項（含深度對話的 talk:N，模型叫不動時那輪對話會直接結束，不需要真的連
Ollama）；只有「結識」一定接受；心得攢夠一定步數就拿去練功（沒學過的功法先自創，已經
學過的就鍛鍊，見 spend_xinde）。
"""
from __future__ import annotations

import random
import time
from collections.abc import Callable

from . import craft, materials, team
from .engine import Game, Option
from .models import Content
from .world_state import WorldStateStore

HALF_HOUR = 1800
SPEND_XINDE_EVERY = 5  # 每幾步檢查一次要不要拿心得去練功/療傷/煉製
CRAFT_TRIES = 4  # 煉製時最多試幾組素材組合（第一組是階最高的，其餘隨機）


def wants_heal(game: Game) -> bool:
    now, cap = team.member_neili(game.content, game.state.player.member)
    return now < cap * 0.5


def spend_xinde(game: Game, rng: random.Random) -> None:
    """氣血掉到五成以下先療傷；接著每門（內功/武學）沒學過的就自創（隨機取名），已經學過
    的就鍛鍊一成——不追求最優策略，只求機器人不會把心得放著不用。"""
    if wants_heal(game):
        game.heal()
    member = game.state.player.member
    for kind, slot in (("內功", "neigong_id"), ("武學", "wugong_id")):
        if getattr(member, slot) is None:
            game.create_skill(f"{kind}{rng.randint(0, 10 ** 9)}", kind)
        else:
            game.practice(kind)


def craft_and_keep_the_best(game: Game, rng: random.Random) -> None:
    """素材夠、心得夠就煉一爐，煉出更好的就改練上去。

    刻意挑**階最高的兩樣**素材（而不是隨機挑）：那才會踩到「素材的階位移品質分佈」那條路，
    不然量出來的永遠是最低階的結果。機器人會煉製很重要——不然整季模擬完全碰不到煉製，
    煉製的平衡也就量不到（這是第二刀留下的待辦）。
    """
    held: list[str] = []
    for material, count in materials.bag_contents(game.state, game.content):
        held += [material.id] * count
    if len(held) < craft.MATERIALS_PER_CRAFT:
        return
    # 先試階最高的那一組，被擋下（素材不夠／心得不夠／這門功法已經有了）就換幾組試試。
    # 不換的話一旦撞到「已經煉過」的配方，機器人會從此再也不煉製，整季模擬就測不到煉製了。
    candidates = [held[: craft.MATERIALS_PER_CRAFT]]
    candidates += [[rng.choice(held), rng.choice(held)] for _ in range(CRAFT_TRIES - 1)]
    for pair in candidates:
        for kind in rng.sample(craft.KINDS, len(craft.KINDS)):
            if craft.can_craft(game.state, game.content, pair, kind, game.world) is None:
                game.craft(pair, kind)
                _switch_to_the_strongest(game)
                return


def _switch_to_the_strongest(game: Game) -> None:
    """功法庫裡有比身上這門強的（同一種、第十成威力更高）就改練上去。"""
    state, content, world = game.state, game.content, game.world
    for art_id in list(state.player.arts):
        art = team.resolve_art(art_id, content, world)
        if art is None:
            continue
        slot = "neigong_id" if art.kind == "內功" else "wugong_id"
        current_id = getattr(state.player.member, slot)
        current = team.resolve_art(current_id, content, world) if current_id else None
        if current is None or art.top_power > current.top_power:
            game.switch_art(art_id)


def pick(game: Game, options: list[Option], rng: random.Random) -> str | None:
    """結識（choice 的 effect.recruit）一定接受；其餘隨機挑一個。沒得挑時回傳 None。

    故意排除 act:rest：那是修給真人玩家的保底（體力見底時選單不會整排 disabled），
    機器人不需要、也不該選——act:rest 永遠 enabled，機器人要是跟其他選項一樣隨機挑，
    「沒有其他選項可選」這個訊號就永遠不會成立，下面 play_season() 用這個訊號決定要不要
    呼叫 game.advance() 推進遊戲時間的節奏會被打亂（體力耗盡的頻率大幅降低，時間推進
    跟著變少，一整季要跑完所需的步數暴增到頂到 max_steps 才停，拖垮整個測試套件）。"""
    s = game.state
    if s.pending_event:
        choices = game.content.events[s.pending_event].choices
        for option in options:
            if option.id.startswith("choice:") and choices[int(option.id.partition(":")[2])].effect.recruit:
                return option.id
    options = [o for o in options if o.id != "act:rest"]
    return rng.choice(options).id if options else None


def play_season(
    content: Content, seed: int, max_steps: int = 20000, observe: Callable[[Game], None] | None = None,
    world: WorldStateStore | None = None,
) -> Game:
    """玩完一季：隨機挑選項、遇到結識一定接受、每隔幾步把攢下的心得拿去練功。
    observe 不是 None 時，開始玩之前呼叫一次（開季的樣子），之後每一步之後都呼叫一次
    （模擬器用來記錄名冊與交手的時間點）。"""
    game = Game.new(content, f"機器人{seed}", rng=random.Random(seed), world=world)
    game.world.open_season(now=time.time())  # 模擬時機器人自己就是管理者：籌備中就直接開季，已經開了則什麼都不做；
    # 用現實時間開季，臨時拿真的世界檔跑機器人時，下一次真人 sync 才不會把開季以來幾十年的遊戲時間一口氣追趕上來
    rng = random.Random(seed)
    if observe is not None:
        observe(game)
    for step in range(max_steps):
        if game.state.world.ended:
            break
        options = [o for o in game.options(odds=False) if o.enabled]
        choice = pick(game, options, rng) if options else None
        if choice is not None:
            game.choose(choice)
            if step % SPEND_XINDE_EVERY == 0:
                spend_xinde(game, rng)
                craft_and_keep_the_best(game, rng)
        if choice is None or step % 4 == 0:
            game.advance(HALF_HOUR)
        if observe is not None:
            observe(game)
    return game
