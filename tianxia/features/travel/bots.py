"""假人看到移動的選項怎麼按（開發規範手冊 3.8；原本寫在 bot_policy.score 的 move: 那一段，全部拆包第 47 批）。
road:（折返、路上小事）假人不按：score 沒有這一支，落到最後回 None，這裡一樣。

往哪裡走的分數常數與下一站（_home、_front_*、_losing_front、_summons_hop、_bounty_hop、_order_hop、_focus_hop、_clinic_score、clinic_hop）第二輪第 89 批從 bot_policy、bot 搬來，
舊名 re-export 同一批物件。別包也讀的（_side、_train_value、_turn_cached、_cannot_push、_outmatched、injury_share，第 101 批再加 next_hop：決戰、陣營也讀……）在共用層 bot_base，一律寫 `bot_base.X`，測試換 bot_base 的才打得到。
**模組層不准碰 engine 與假人殼**（bot、bot_policy 模組層 import 這個檔）。"""
from __future__ import annotations

from typing import TYPE_CHECKING

from tianxia import atlas, bot_base, clinic, conquest, orders, rules
from tianxia.core import bounty_base
from tianxia.core.option import Option
from tianxia.state import BotProfile

if TYPE_CHECKING:
    from tianxia.engine import Game
    from tianxia.models import Content

HOME_MOVE_SCORE = 0.3  # 往自己陣營的地盤走（投靠點一帶；第一季濃縮版是輸得最多的那條戰線，離得還遠時是往那邊的下一站）
AWAY_MOVE_SCORE = 0.1
TRAIN_MOVE_SCORE = 0.5  # 往「遊歷對自己陣營有利」的地點走，額外加分
ORDER_MOVE_SCORE = 12.0
SUMMONS_MOVE_SCORE = 15.0
BOUNTY_MOVE_SCORE = 6.0
CLINIC_MOVE_SCORE = 20.0  # 內傷重了往醫館走（clinic_hop）：高過軍令、召見、懸賞的那一步，傷好了才有力氣做事
# 內傷到 bot_base.CLINIC_URGENT 以上：往醫館走、在醫館療傷都排在軍令（ORDER_SCORE 30＋遊歷的大勢分）與召見（SUMMONS_SCORE 50）前面
# （PM 2026-10-12：只給 CLINIC_MOVE_SCORE 時被軍令拉走的假人一季平均帶著三四成內傷）
CLINIC_URGENT_SCORE = 100.0
CLINIC_AT = 0.15  # 內傷到氣血上限的這麼多（約兩三場落敗）就繞去醫館（企劃者 2026-10-12 療傷只在醫館）；整季機器人與假人共用
# 領地爭奪：今天還有出陣次數時往這一邊最該推的那一塊走（推得動、打得贏的目標裡，這一邊的條最高的那幾塊；全是 0 時是最近的那一塊）。
# 一塊要推到 100 才易手，各推各的推不滿（2026-10-22 量 7 天季：一邊一季推的量散在五、六塊上，每一塊都停在一二十）；
# 真人看得到卡上誰推到幾成，會往同一塊湊。跟往懸賞走一樣急，比往軍令走低（軍令的攻城本來就照最高的那一塊）。
FOCUS_MOVE_SCORE = 6.0


def score(game: Game, option: Option, profile: BotProfile) -> float | None:
    """選項的分數；None＝假人不會按（road:）。move: 是往哪裡走：往自己陣營的地盤、軍令、召見、懸賞、醫館、領地爭奪要去的地方加分。"""
    kind, _, arg = option.id.partition(":")
    if kind != "move":
        return None
    base = HOME_MOVE_SCORE if arg == _front_hop(game, profile) or arg in _home(game, profile) else AWAY_MOVE_SCORE
    order_hop = ORDER_MOVE_SCORE if arg.partition(":")[0] == _order_hop(game) else 0.0  # 往軍令要去的地方（計畫 T6）
    summons_hop = SUMMONS_MOVE_SCORE if arg.partition(":")[0] == _summons_hop(game) else 0.0  # 往召見的地點（計畫 T5）
    bounty_hop = BOUNTY_MOVE_SCORE if arg.partition(":")[0] == _bounty_hop(game) else 0.0  # 往懸賞要去的地方
    clinic_near = _clinic_score(game) if arg.partition(":")[0] == clinic_hop(game) else 0.0  # 內傷重了往醫館（這一格不能再叫 clinic_hop：會蓋掉同一個檔的函式）
    focus_hop = FOCUS_MOVE_SCORE if arg.partition(":")[0] == _focus_hop(game) else 0.0  # 領地爭奪：往這一邊最該推的那一塊
    return base + order_hop + summons_hop + bounty_hop + clinic_near + focus_hop \
        + (TRAIN_MOVE_SCORE if bot_base._train_value(game, profile, arg) > 0 else 0.0)


def _clinic_score(game: Game) -> float:
    return CLINIC_URGENT_SCORE if bot_base.injury_share(game) >= bot_base.CLINIC_URGENT else CLINIC_MOVE_SCORE


def clinic_hop(game: Game) -> str | None:
    """內傷到 CLINIC_AT、付得起（can_pay_clinic）、人不在醫館也不在路上：往最近的醫館走的下一站（clinic.nearest）；不必去、走不到是 None。"""
    s, c = game.state, game.content
    if not clinic.on(c) or s.player.journey is not None or clinic.here(s, c):
        return None
    if not bot_base.can_pay_clinic(game) or bot_base.injury_share(game) < CLINIC_AT:
        return None
    route = clinic.nearest(s, c)
    return None if route is None else route.path[0]


def _home(game: Game, profile: BotProfile) -> set[str]:
    """陣營的地盤（假人往這一帶走）。第一季濃縮版（開關開著）：己方輸得最多的那條戰線上的所有地點（第一季設計
    第七節：假人照陣營目標往前線去）；陣營對戰線沒有目標（豪強）或開關關著時：投靠點與相鄰的地點。
    豪強分屬兩軍的季，豪強照依附那一軍的目標往前線去（設計第十三節）；回家仍是自己的投靠點。"""
    faction_id = game.state.player.faction or profile.faction
    if faction_id is None:
        return set()
    front = _losing_front(game, bot_base._side(game) or faction_id)
    if front is not None:
        return set(_front_locations(game.content, front))
    join_at = game.content.scenario.faction(faction_id).join_at
    return set(join_at) | {n for loc_id in join_at for n in game.content.locations[loc_id].connections}


def _front_locations(content: Content, front: str) -> list[str]:
    """這條戰線上的所有地點（照內容檔的順序）。"""
    return [loc_id for loc_id in content.locations if rules.front_of(content, loc_id) == front]


def _front_hop(game: Game, profile: BotProfile) -> str | None:
    """第一季濃縮版：假人還沒到己方輸得最多的那條戰線上，往那條戰線路程最近的地點走的下一站（鄰居裡沒有戰線上的地點時，
    光看「目的地在不在地盤」沒有方向，會亂走）；已經在戰線上、走不到、沒有這種戰線（開關關著、豪強、散人）時是 None。"""
    faction_id = bot_base._side(game) or profile.faction  # 豪強分屬兩軍：依附那一軍輸得最多的戰線
    front = _losing_front(game, faction_id) if faction_id is not None else None
    return None if front is None else bot_base.next_hop(game, _front_locations(game.content, front))


def _losing_front(game: Game, faction_id: str) -> str | None:
    """己方輸得最多的戰線：目標是壓低（官軍）就挑戰況最高的、推高（黃巾）就挑最低的，同分取劇本排前面的。
    開關關著、或這個陣營對戰線沒有目標時是 None。"""
    content = game.content
    if not rules.season_one(content, game.state.world):
        return None
    goals = game.content.scenario.faction(faction_id).goals
    fronts = [front for front in rules.front_ids(content) if goals.get(front)]
    if not fronts:
        return None
    return max(fronts, key=lambda front: -goals[front] * rules.trend_value(game.state, content, front))


def _summons_hop(game: Game) -> str | None:
    """往召見的地點，路程最近的那一站；沒有召見、已經在、走不到時是 None（計畫 T5）。"""
    summons = game.state.player.summons
    return bot_base.next_hop(game, [summons.location]) if summons is not None else None


def _bounty_hop(game: Game) -> str | None:
    """往手上的懸賞要去的地方，路程最近的那一站；沒有、已經在、走不到時是 None。"""
    places = bounty_base.targets(game.state, game.content)
    return bot_base.next_hop(game, places) if places else None


def _order_hop(game: Game) -> str | None:
    """往這週軍令要去的地方，路程最近的那一站；已經在、沒有軍令、走不到時是 None（計畫 T6）。
    領地爭奪：只為了截糧才去、去了出陣推不動的地方不去（翻地 QA 順帶：開季的截糧軍令把假人拉到碰不到的中立地，一直在那裡出陣、連輸中立駐軍）；
    攻城、守城的地方照 orders.targets（自家被戰書凍結的那一塊推不動，但要去加入攻城站守方，FB-605）；攻城、截糧的地方贏面太低的不去
    （_outmatched，2026-10-22 7 天季）。"""
    return bot_base._turn_cached(("order_hop",), lambda: _order_hop_now(game))


def _order_hop_now(game: Game) -> str | None:
    s, c, side = game.state, game.content, bot_base._side(game)
    places = orders.targets(s, c, side)
    if places and conquest.on(c, s.world):
        others = set(orders.targets(s, c, side, skip=frozenset({"intercept"})))
        places = [loc for loc in places if loc in others or not bot_base._cannot_push(game, loc)]
        # 攻城的地方要出陣攻打贏才記得到：贏面太低的不去（守城、護糧、打擊人物不靠出陣攻打，照走）
        keep = set(orders.targets(s, c, side, skip=frozenset({"intercept", "siege"})))
        places = [loc for loc in places if loc in keep or not bot_base._outmatched(game, loc)]
    return bot_base.next_hop(game, places) if places else None


def _focus_hop(game: Game) -> str | None:
    """往這一邊最該推的那一塊路程最近的那一站（領地爭奪）：推得動（conquest.push_problem 是 None）、打得贏（不是 _outmatched）的目標裡，
    這一邊的條最高的那幾塊（並列都算）。今天的出陣次數用完、已經在那裡、開關關著、散人都是 None。"""
    s, c, side = game.state, game.content, bot_base._side(game)
    if side is None or not conquest.on(c, s.world) or game.sorties_left() <= 0:
        return None

    def compute() -> str | None:
        # 勝算貴（每一路模擬四十場）：照「條高的先、近的先」一塊一塊問，問到第一塊打得贏的就是它——同「打得贏的裡面條最高、一樣高挑最近」
        # （近照 next_hop 的排法：路程、站數、路），不必每一塊都算勝算
        here = s.player.location
        routes = atlas.shortest_routes(s, c)
        ready = [
            loc for loc in conquest.blocks(c)
            if (loc == here or (loc in routes and routes[loc].path)) and conquest.push_problem(s.world, c, side, loc, "attack") is None
        ]

        def order(loc: str) -> tuple:
            route = routes.get(loc)
            near = (0.0, 0, []) if loc == here or route is None else (round(route.minutes, 6), len(route.path), route.path)
            return (-conquest.bar(s.world, loc, side), *near)

        for loc in sorted(ready, key=order):
            if not bot_base._outmatched(game, loc):
                return bot_base.next_hop(game, [loc])  # 已經在那裡是 None
        return None

    return bot_base._turn_cached(("focus_hop",), compute)
