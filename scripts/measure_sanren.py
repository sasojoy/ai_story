"""散人對陣營：一季下來誰長得比較多（PM 2026-10-08 派工「加強散人玩法」：遊俠名號＋懸賞榜，目標是兩邊差不多）。只量、不改數字。

整季機器人（bot.play_season，真實 content/），每個種子跑兩次、各自一個資料庫：
- 散人：一路不投靠（選單上的投靠、會讓人入陣營的拜師都拿掉），照遊俠名號與懸賞榜長；
- 陣營：一看到投靠就投、照軍令與晉升長（投靠哪一個照選單上第一個出現的）。
兩邊都是「有目標的玩家」：一半的時候照手上的懸賞與軍令走、到了就做（_steer），另一半照整季機器人隨機玩；
城裡的懸賞榜兩邊都會去揭（bot.take_bounties）。模型一律不連（同 measure_forge）。

印每個種子、每一邊的季末：等級、本人威力、全隊威力（本人＋同伴＋部下）、銀兩、名望、同伴數、部下數、心得，
散人另印俠名與名號的階、懸賞完成幾張；陣營另印陣營、階與貢獻。每一邊另印傷與體力（企劃者 2026-10-12 療傷只在醫館）：
一季平均的內傷（佔氣血上限的幾成，每一步取樣）、療傷幾次、花多少銀兩、往醫館繞了幾段路（bot.clinic_hop）、吃了幾顆回體丹、選單上的行動一共花掉多少體力、體力連一次探索都不夠的時間佔一季的幾成（見底%，照賽季時間加權）。底下兩行（懸賞榜設計 11.1）：每一種懸賞交差幾張（包住
bounties._complete 數），以及求兵拿到多少（銀兩、經驗、心得；交出去的兵器幾把〔其中幾把是自己打的〕；包住 bounties.give 數；
求藝企劃者 2026-10-21 拿掉）。最後兩行是兩邊的中位數。
一個種子一個資料庫、只有一個機器人，碰不到別人，截殺一場都不會有：截殺的量看 scripts/sim_server_bots.py（設計 11.2）。

用法：.venv/Scripts/python.exe scripts/measure_sanren.py --seeds 1 2 3 4 5 [--profile weekend|none] [--faction guan|huang|haoqiang] [--no-give] [--bare]
（--profile 預設 weekend：第一季規則開著的週末設定；none 是不套設定覆寫檔，量預設設定〔14 天、第一季規則關著〕的季——
懸賞榜、名號、截殺每季都有之後，那種季也有懸賞可揭〔懸賞榜設計 11.1〕。不用空字串：PowerShell 5.1 會把它吞掉。
--faction 指定陣營那一邊投靠誰：還沒投靠時一路往那個陣營的投靠點走、只投它（不給就照舊投選單上第一個出現的，量不到豪強）；
--no-give 只拿掉求兵（有懸賞榜第一批、沒有第二批：豪強的基準，跟 --faction haoqiang 比）；
--bare 是對照組：拿掉懸賞榜〔含求兵〕與名號的經驗加成，看這一版之前散人跟陣營差多少）
"""
from __future__ import annotations

import argparse
import atexit
import io
import os
import shutil
import statistics
import sys
import tempfile
from collections import Counter
from pathlib import Path
from unittest import mock

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
TMP = Path(tempfile.mkdtemp(prefix="measure_sanren_"))
os.environ["TIANXIA_DB"] = str(TMP / "unused.db")  # 別開到 worktree 的 saves/tianxia.db

from tianxia import bot, bot_policy, bounties, database, encounter, naming, orders, ranger, ranks, team  # noqa: E402
from tianxia.content import load_content, profile_line  # noqa: E402
from tianxia.engine import Game  # noqa: E402
from tianxia.state import PLAYER  # noqa: E402
from tianxia.ollama_client import OllamaClient  # noqa: E402
from tianxia.sqlite_world import open_world  # noqa: E402

STEER = 0.5  # 有目標的玩家：一半的時候照手上的懸賞、軍令走
COLUMNS = ("等級", "本人威力", "全隊威力", "銀兩", "名望", "同伴", "部下", "心得", "內傷%", "療傷", "療傷銀", "繞路", "吃丹", "花體力", "見底%")
KINDS = ("strike", "scout", "escort", "wanted", "arms")
GOT = ("銀兩", "經驗", "心得")


class Tally:
    """一季的懸賞帳（懸賞榜設計 11.1）：每一種交差幾張（包住 bounties._complete），求兵拿到多少（包住 bounties.give，交成了才記）。"""

    def __init__(self) -> None:
        self.done: Counter = Counter()
        self.got: Counter = Counter()
        self.weapons = 0
        self.forged = 0  # 交出去的兵器裡自己打的（Weapon.recipe 不是 None）

    def complete(self, real):
        def counted(state, content, world, b, *args, **kwargs):
            self.done[b.kind] += 1
            return real(state, content, world, b, *args, **kwargs)
        return counted

    def give(self, real):
        def counted(state, content, world, bounty_id, item_id):
            p = state.player
            b = next((x for x in state.world.bounties if x.id == bounty_id), None)
            w = bounties._weapon(state, item_id)
            silver, xinde = p.stats.get("silver", 0), p.stats.get("xinde", 0)
            msgs = real(state, content, world, bounty_id, item_id)
            if b is None or not msgs[0].startswith(bounties.GIVEN_PREFIX):
                return msgs
            got = self.got
            got["銀兩"] += p.stats.get("silver", 0) - silver
            got["心得"] += p.stats.get("xinde", 0) - xinde
            got["經驗"] += sum(int(m.partition("+")[2]) for m in msgs if m.startswith("經驗 +"))
            self.weapons += 1
            self.forged += int(w is not None and w.recipe is not None)
            return msgs
        return counted

    def lines(self) -> list[str]:
        got = "・".join(f"{k} {self.got[k]}" for k in GOT if self.got[k]) or "什麼都沒拿到"
        return [
            "　交差：" + "・".join(f"{bounties.KIND_NAMES[k]} {self.done[k]}" for k in KINDS),
            f"　求兵：交 {self.weapons} 把（自己打的 {self.forged} 把），{got}",
        ]


def _cleanup() -> None:
    database.close_all()
    shutil.rmtree(TMP, ignore_errors=True)


atexit.register(_cleanup)


def _joins_faction(game, option_id: str) -> bool:
    """這個選項會讓人進陣營：投靠，或拜入陣營名下的門派。"""
    if option_id.startswith("faction:"):
        return True
    s, c = game.state, game.content
    if option_id.startswith("choice:") and option_id.partition(":")[2].isdigit() and s.pending_event:
        choice = c.events[s.pending_event].choices[int(option_id.partition(":")[2])]
        sect = choice.effect.join_sect
        return sect is not None and any(sect in f.sects for f in c.scenario.factions)
    return False


def _steer(game, options, rng) -> str | None:
    """有目標的玩家（兩邊一樣）：一半的時候照手上的事走——懸賞（散人、陣營都能接）與這週的軍令（陣營）要去的地方、
    到了就做那件事（討伐、攻城、截糧：遊歷；打探：探索；守城：守勢行動），手上沒事要趕就在這裡遊歷；另一半照整季機器人隨機玩。"""
    if game.state.pending_event or rng.random() >= STEER:
        return None
    s, c = game.state, game.content
    ids = {o.id for o in options}
    here = s.player.location
    work = {b.kind for b in bounties.mine(s, c) if b.location == here}
    if "act:train" in ids and ("strike" in work or orders.win_counts(s, c, s.player.faction, here)):
        return "act:train"
    if "scout" in work and (choice := bot.explore_choice(ids)) is not None:  # 打探：三選一開著時找素材（出陣探索與地盤）
        return choice
    if "act:duty" in ids and orders.duty_counts(s, c, s.player.faction, here):
        return "act:duty"
    places = bounties.targets(s, c) + orders.targets(s, c, s.player.faction)
    hop = bot_policy.next_hop(game, places) if places else None
    move = next((i for i in ids if i.startswith("move:") and i.partition(":")[2].partition(":")[0] == hop), None)
    if move is not None:
        return move
    return "act:train" if "act:train" in ids else None  # 手上沒事要趕：這裡有得打就打（兩邊一樣；陣營的人碰上自己人是操練）


def _power(game) -> tuple[float, float]:
    s, c, w = game.state, game.content, game.world
    members, _, boosts = team._fighters(s, c, w)
    arts = team.team_arts(s, c, w)
    powers = [encounter.member_power(m, arts, None, 1.0, b) for m, b in zip(members, boosts, strict=True)]
    return powers[0], sum(powers)


def _join(game, options, faction: str | None) -> tuple[str | None, list]:
    """陣營那一邊還沒投靠：（這一步要按的, 剩下可以挑的選項）。faction 是 None 時投選單上第一個出現的；指定了就只投它，
    還沒走到它的投靠點就一路往那裡走（別的陣營不投、別陣營名下的門派不拜）。"""
    ids = [o.id for o in options]
    if "faction:confirm" in ids:
        return "faction:confirm", options
    if faction is None:
        return next((i for i in ids if i.startswith("faction:") and i != "faction:cancel"), None), options
    if f"faction:{faction}" in ids:
        return f"faction:{faction}", options
    options = [o for o in options if not _joins_faction(game, o.id)]
    hop = bot_policy.next_hop(game, list(game.content.scenario.faction(faction).join_at))
    move = next((o.id for o in options if o.id.startswith("move:") and o.id.partition(":")[2].partition(":")[0] == hop), None)
    return move, options


def _strip(content, bare: bool, no_give: bool) -> None:
    """對照組：no_give 只拿掉求兵（懸賞榜第一批還在：豪強在第二批之前的基準）；bare 拿掉整個懸賞榜（含求兵）
    與名號的經驗加成（這一版之前的散人）。"""
    if bare or no_give:
        content.config.bounties.give_kinds = []
    if bare:
        content.config.bounties.kinds = []
        content.config.ranger.exp_per_tier = 0.0


def measure(
    seed: int, profile: str | None, side: str, bare: bool = False, faction: str | None = None, no_give: bool = False,
) -> dict:
    content = load_content(ROOT / "content", profile=profile)
    _strip(content, bare, no_give)
    world = open_world(TMP / f"{side}{seed}.db")
    original_pick = bot.pick
    tally = Tally()

    def pick(game, options, rng):
        if side == "散人":
            options = [o for o in options if not _joins_faction(game, o.id)]
        elif game.state.player.faction is None:
            move, options = _join(game, options, faction)
            if move is not None:
                return move
        steered = _steer(game, options, rng)
        return steered if steered is not None else original_pick(game, options, rng)

    def refuse(*args, **kwargs):
        raise RuntimeError("量測不連模型")

    care = Counter()  # 傷與體力：療傷次數與銀兩、往醫館繞路的段數、吃了幾顆丹、內傷取樣
    real_heal, real_pill, real_choose = Game.heal, Game.take_stamina_pill, Game.choose
    clinic_hop = getattr(bot, "clinic_hop", lambda game: None)  # 醫館之前的版本沒有（拿來量改動前的基準）

    def heal(self):
        silver = self.state.player.stats.get("silver", 0)
        msgs = real_heal(self)
        if msgs and msgs[0].startswith("療傷完畢"):
            care["療傷"] += 1
            care["療傷銀"] += silver - self.state.player.stats.get("silver", 0)
        return msgs

    def pill(self, *args, **kwargs):
        pills = self.state.player.stamina_pills
        msgs = real_pill(self, *args, **kwargs)
        care["吃丹"] += pills - self.state.player.stamina_pills
        return msgs

    def choose(self, option_id, *args, **kwargs):
        if option_id.startswith("move:") and option_id.partition(":")[2].partition(":")[0] == clinic_hop(self):
            care["繞路"] += 1
        stamina = self.state.player.stamina
        msgs = real_choose(self, option_id, *args, **kwargs)
        care["花體力"] += max(0, round(stamina - self.state.player.stamina))
        return msgs

    last = {}  # 見底%：上一次取樣的賽季時間與那時體力見不見底（照經過的賽季時間加權：沒事做時一步就是一大段時間）

    def observe(game):
        now, empty = game.state.world.time, game.state.player.stamina < game.content.config.action_cost["explore"]
        if last:
            care["見底秒"] += (now - last["t"]) if last["empty"] else 0
            care["總秒"] += now - last["t"]
        last.update(t=now, empty=empty)
        member = game.state.player.member
        _, cap = team.member_neili(game.content, member, team.con_of(game.state, game.content, game.world, PLAYER))
        care["樣本"] += 1
        care["內傷千分"] += round(1000 * member.injury / cap)

    with mock.patch.object(naming, "propose", lambda *a, **k: (None, "")), \
            mock.patch.object(naming, "pick", lambda *a, **k: (None, "")), \
            mock.patch.object(OllamaClient, "chat_structured", refuse), mock.patch.object(OllamaClient, "chat_text", refuse), \
            mock.patch("requests.post", refuse), mock.patch("requests.get", refuse), \
            mock.patch.object(bot, "pick", pick), \
            mock.patch.object(bounties, "_complete", tally.complete(bounties._complete)), \
            mock.patch.object(bounties, "give", tally.give(bounties.give)), \
            mock.patch.object(Game, "heal", heal), mock.patch.object(Game, "take_stamina_pill", pill), \
            mock.patch.object(Game, "choose", choose):
        game = bot.play_season(content, seed, world=world, observe=observe)
    s, c = game.state, game.content
    p = s.player
    mine, whole = _power(game)
    row = {
        "等級": p.member.level, "本人威力": round(mine), "全隊威力": round(whole), "銀兩": p.stats.get("silver", 0),
        "名望": p.stats.get("fame", 0), "同伴": len(p.team), "部下": len(p.followers), "心得": p.stats.get("xinde", 0),
        "faction": p.faction, "tally": tally,
        "內傷%": round(care["內傷千分"] / max(1, care["樣本"]) / 10, 1),
        **{k: care[k] for k in ("療傷", "療傷銀", "繞路", "吃丹", "花體力")},
        "見底%": round(100 * care["見底秒"] / max(1, care["總秒"]), 1),  # 體力連一次探索都不夠的時間佔一季的幾成
    }
    if p.faction is None:
        row["俠名"] = ranger.points(s)
        row["名號"] = ranger.tier(s, c)
        row["懸賞"] = p.bounties_done
    else:
        row["階"] = ranks.rank_of(s)
        row["貢獻"] = p.contrib
    return row


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--seeds", type=int, nargs="+", default=[1, 2, 3])
    parser.add_argument("--profile", default="weekend",
                        help="設定覆寫檔（content/profiles/<名字>.json）；none＝不套，量預設設定（14 天、第一季規則關著）的季")
    parser.add_argument("--faction", default=None, help="陣營那一邊投靠誰（劇本的陣營 id，例如 guan、huang、haoqiang）；不給就投第一個碰到的")
    parser.add_argument("--no-give", action="store_true", help="對照組：只拿掉求兵（豪強的基準）")
    parser.add_argument("--bare", action="store_true", help="對照組：拿掉懸賞榜（含求兵）與名號的經驗加成")
    args = parser.parse_args()
    profile = None if args.profile == "none" else args.profile
    content = load_content(ROOT / "content", profile=profile)
    if args.faction is not None and args.faction not in {f.id for f in content.scenario.factions}:
        parser.error(f"劇本沒有陣營 {args.faction}：{'、'.join(f.id for f in content.scenario.factions)}")
    print(profile_line(content, profile), flush=True)
    rows: dict[str, list[dict]] = {"散人": [], "陣營": []}
    for seed in args.seeds:
        for side in rows:
            row = measure(seed, profile, side, bare=args.bare, faction=args.faction, no_give=args.no_give)
            rows[side].append(row)
            extra = (f"俠名 {row['俠名']}（第 {row['名號']} 階）懸賞 {row['懸賞']}" if row["faction"] is None
                     else f"{row['faction']} 第 {row['階']} 階 貢獻 {row['貢獻']}")
            print(f"種子 {seed} {side}：" + "　".join(f"{k} {row[k]}" for k in COLUMNS) + f"　{extra}", flush=True)
            for line in row["tally"].lines():
                print(line, flush=True)
    for side, side_rows in rows.items():
        print(f"{side}中位數：" + "　".join(f"{k} {statistics.median(r[k] for r in side_rows):g}" for k in COLUMNS))


if __name__ == "__main__":
    main()
