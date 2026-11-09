"""same_behavior 一軌一檔：placard（這一檔登記 placard）。"""
from __future__ import annotations

import hashlib
import json
import random
from pathlib import Path

from sb.base import Scenario
from sb.harness import ADMIN, CLOCK, STEP, emit, register_track
from sb.tracks.explore import _explore_rules
from sb.tracks.herald import HeraldScenario

# ═══════════════════════════ placard：懸賞榜一軌（全部拆包第 45 批，dev/bounties-1） ═══════════════════════════
# 懸賞榜成包（計畫 docs/superpowers/plans/2026-11-07-懸賞榜包-第1批.md）。herald 走到五種事件交差、compass 走到本週卡兩格、crossblade 走到截殺，
# 可是沒有一軌親手按過 bounty:*、卡上的通緝、系統通緝、退押金、作廢、求援與書信委託、人物倒下掛的懸賞。角色的名字都是原創的（PM 11/04）。懸賞單直接寫進季上的榜（pl_ 開頭），其餘只打公開的 API。

PL_PREFIX = "pl_"


class PlacardScenario(HeraldScenario):
    """懸賞榜一軌（全部拆包第 45 批；--track placard，自己一個資料庫）。
    榜：城裡 act:bounties 進榜（店面那一頁）、揭下、揭不了（要在別處接、揭滿了、重賞與官府通緝的名聲門檻、新手揭通緝）、放棄；
    求兵：挑一張、第三層（灰掉的 bounty:more、回到懸賞榜）、交出庫裡的、交出手上那一把、只有神器原品與本命兵器對得上（bounty:none）；
    搶單（FB-162：不在選單上的 bounty:*）、榜被交光（bounty:empty，FB-156）、酒肆牆上的榜（tavern:board）。
    通緝：玩家卡（散人、同陣營、敵對、新手、沒錢、已經掛著一張、截殺關著）、押金、系統通緝（陣營、官府）、截殺打贏交差、退押金；
    作廢：名額滿了、過了期限、換了陣營、季收了。委託與求援：書信附的委託（欠他的那一件、他兌現的那一件）、焦慮的人物發求援（世界一步）、
    人物倒下掛的懸賞。投靠、改幫、叛投手上的單作廢與確認畫面、事件選項後面的括號（join_note）。
    **前半停在五件寫到一半的事**：世界時間推到下一次掛單（21 天季每天、其他週初）的前一個鐘頭；裴知遠揭了討伐、打探、護送還沒交差；
    梅子衿手上有求援與兩件書信委託；蘇硯冰押著一張通緝還沒到期；陸觀潮坐在榜前、bounty_pick 指著一張求兵還沒交。
    後半：新程式接著交那一件、跨過掛單那一刻、交差（打贏、探索、抵達）、護衛辦成求援、退押金；假人（BotRunner 官軍、黃巾各一，走 bot_policy 的
    act:bounties 與 bounty:；整季機器人 bot.take_bounties）；收季時還坐在榜前的人、開下一季。
    測試內容沒有陣營：開場在記憶體裡補三個陣營（同 tianxia/features/bounties/tests/test_bounties.py 的 beta_setup；前半、後半各補一次），規則關著的季走 start、step 兩格。
    掛單（head 上讀輸出量的）：season21、week7 都是每天一批（issue_day：bounty_day 動、bounty_week 是 0），week 那一格的 issue 回空；issue 的本體只有測試內容經 tick 走到。
    這一軌走不到的（讀輸出量過）：測試內容的求兵（兵器關著，交不出）、大勢人物、人物倒下、改幫、事件拜入門派、酒肆、系統通緝（名聲關著）；season21 的新手揭通緝（新手連榜都看不到）、
    season21 開局那封信（快轉到開榜那一段時過了期，week7 走到）；任何設定下 NOT_HELD、NO_TAKE（選單上不會有那一顆，不在選單上的走 FB-162，只有 tianxia/features/gear/tests/test_shop2.py 直接叫 _bounty）；
    榜開著動身（atlas.travel_block 擋掉，departure 那一行 close_board 只清掌櫃那一句，每一軌動身都走到）；官府通緝的惡名 BEATEN_OFFICIAL（crossblade 那一軌）；
    一類一顆關著的三句討伐說法（STRIKE_PRECISE 那幾句：直接叫 how 的那一軌）。"""

    TAKER, RANGER, FOE, GIVER = "裴知遠", "阮青禾", "鍾九思", "陸觀潮"
    POSTER, QUARRY, AIDE, SITTER = "蘇硯冰", "童霜寒", "梅子衿", "韋望舒"
    DRIFTER, BENDER, PILGRIM, TURNCOAT = "葛春陽", "譚雪竹", "賴秋實", "喻北辰"
    FAMOUS, ROGUE, LAPSER, GREEN = "沈聽瀾", "裘遠黛", "邢晚晴", "聶小舟"
    LONE = RANGER  # HeraldScenario.wild_spot 借他問城外打得到誰
    PLAYERS = {TAKER: "guan", RANGER: None, FOE: "huang", GIVER: "guan", POSTER: "guan", QUARRY: "huang", AIDE: "guan", SITTER: "guan",
               DRIFTER: None, BENDER: "haoqiang", PILGRIM: None, TURNCOAT: "guan", FAMOUS: "guan", ROGUE: None, LAPSER: "guan", GREEN: None}
    NEWBIE = "初見榜文"
    BOT_SEATS = ["榜甲", "榜乙", "榜丙"]
    PHASES_FIRST = ["setup", "unlock", "seat", "browse", "gates", "arms", "scramble", "tavern_wall", "auto", "lapse",
                    "errands", "fallen", "stranded", "cards", "half"]
    PHASES_SECOND = ["resume", "hand_over", "edge", "deliver", "aided", "refund", "bots", "season"]

    def __init__(self, root: Path, profile: str, db: Path):
        super().__init__(root, profile, db)
        if profile == "test":
            from tianxia.models import FactionDef

            self.c.scenario.factions = [FactionDef(id="guan", name="官軍", join_at=["town"]), FactionDef(id="huang", name="黃巾", join_at=["lake"]),
                                        FactionDef(id="haoqiang", name="地方豪強", join_at=["cave"])]
            self.c.squads["thug"].faction = "huang"

    # ── 小工具 ──

    def spots(self) -> list[str]:
        """城外打得到人的地方（照 id 排；打探的地點用）。"""
        return sorted(i for i, x in self.c.locations.items() if x.enemies and self.c.config.explore_mix_of(x.tags).kind != "town")

    def bill(self, bid: str, kind: str, faction: str | None, **kw):
        """榜上一張沒人揭的單。"""
        from tianxia.state import Bounty

        far = self.world.get_season().time + 30 * 86400.0
        return Bounty(id=f"{PL_PREFIX}{bid}", kind=kind, faction=faction, week=1, expires=far, **{"silver": 20, "deeds": 1, "quota": 2, **kw})

    def held(self, bid: str, kind: str, who: str, faction: str | None, **kw):
        return self.bill(bid, kind, faction, takers=[who], **kw)

    def books(self, tag: str) -> None:
        """榜的帳：季曆與掛單跑到哪、榜上每一張（全部欄位）、求援、軍令（雜湊：同一下掛的先後）、傳聞的尾巴。"""
        w = self.world.get_season()
        emit(f"榜 {tag}", {
            "at": [round(w.time, 3), w.hooked_week, w.hooked_day, w.bounty_week, w.bounty_day, w.bounty_seq],
            "bills": [b.model_dump(mode="json") for b in w.bounties], "rallies": [b.model_dump(mode="json") for b in w.rallies],
            "orders": [len(w.orders), hashlib.sha256(json.dumps([o.model_dump(mode="json") for o in w.orders], ensure_ascii=False).encode("utf-8")).hexdigest()[:16]],
            "rumors": [r.text for r in w.rumors][-6:]})

    def me(self, who: str, tag: str) -> None:
        state = self.chars.load(who)
        if state is None:
            emit(f"{who} {tag}（沒有這個人）", None)
            return
        p = state.player
        emit(f"{who} {tag}", {
            "loc": p.location, "faction": p.faction, "ally": p.ally, "silver": p.stats.get("silver", 0), "xinde": p.stats.get("xinde", 0), "done": p.bounties_done,
            "board": [p.picking_bounty, p.bounty_pick, p.shop_line, p.shop_clue, p.shop_hold],
            "weapon": None if p.weapon is None else p.weapon.id, "rack": [x.id for x in p.rack],
            "affinities": dict(sorted(p.affinities.items())), "owed": dict(sorted(p.parley_owed.items())), "debts": sorted(p.parley_debts),
            "records": {k: v.model_dump(mode="json") for k, v in sorted(p.parley_records.items())},
            "letters": [[x.id, x.kind, x.sender, x.lapsed, x.read, None if x.task is None else [x.task.id, list(x.task.done_by)]] for x in p.letters],
            "journal": [[e.title, e.tag, list(e.lines)[:8]] for e in state.journal[:3]]})

    def peer(self, who: str, other: str):
        return self.call(who, "GET", f"/api/peer?name={other}")[1]

    def hunt(self, who: str, other: str, amount) -> None:
        self.call(who, "POST", "/api/peer/act", {"name": other, "action": "wanted", "amount": amount})

    def with_game(self, who: str, fn):
        """照伺服器的做法在鎖裡做一件 API 碰不到的事（人物倒下、心事變了）：從資料庫重讀、同步、做、存季、存角色。"""
        from tianxia.engine import Game

        self.begin()
        with self.world.action_lock():
            g = Game(self.c, self.chars.load(who), rng=random.Random(STEP[0]), world=self.world)
            g.client = None
            g.sync(CLOCK[0])
            out = fn(g)
            g._save_season()
            self.chars.save(g.state)
        return out

    def guan_figure(self) -> tuple[str, str, str] | None:
        """官軍這一邊、對話人物、此刻站在某個地點的大勢人物：(人物 id, 對話人物 id, 地點)。沒有是 None。"""
        from tianxia import figures

        with self.world.action_lock():
            state = self.chars.load(self.AIDE)
        for fid, fig in sorted(self.c.figures.items()):
            ch = self.c.characters.get(fig.character or "")
            if fig.faction != "guan" or ch is None or not ch.deep_interaction:
                continue
            at = next((loc for loc in sorted(self.c.locations) if fid in figures.present_at(state, self.c, loc)), None)
            if at is not None:
                return fid, fig.character, at
        return None

    # ── 前半 ──

    def setup(self) -> None:
        Scenario.setup(self)  # 不接 ExploreScenario.setup；借它的只有小工具（draws、fights、tweak、explore）
        self.books("開季")

    def unlock(self) -> None:
        """減法季第 2 段才開榜（week_unlock）：管理者快轉到那一段的開頭。規則關著的季不鎖。"""
        import math

        from tianxia import calendar, week_unlock

        s = self.world.get_season()
        if not week_unlock.on(self.c, s):
            emit("榜：這一季不鎖", None)
            return
        weeks = week_unlock.weeks_of(self.c, s)
        week = next(n for n in range(1, weeks + 2) if week_unlock.phase(n, weeks) >= 1)
        self.do(ADMIN, "fast_forward", {"hours": math.ceil((calendar.week_start(week, self.c, s) - s.time) / 3600) + 1})
        self.books("開榜那一段")

    def seat(self) -> None:
        for who in self.PLAYERS:
            self.place(who, self.hub(), self.side(who))
            self.edit(who, lambda p: p.stats.update({"silver": 300}))
        for who in self.PLAYERS:
            self.main(who)

    def browse(self) -> None:
        """裴知遠（官軍）進榜：揭討伐、打探、護送（揭滿 3 張），要在別處接的與揭滿之後的灰掉，放棄再揭；黃巾的單他看不到。"""
        who = self.TAKER
        loc = self.strike_spot(who)
        if loc not in self.c.locations:
            loc = (self.spots() + [self.hub()])[0]
        scout = (self.spots() or [self.hub()])[-1]
        move = self.step_to(who)
        dest = move.split(":")[1] if move else self.hub()
        squad = next(iter(self.c.locations[loc].enemies), None)
        self.post(self.bill("strike", "strike", "guan", location=loc, squad=squad), self.bill("scout", "scout", "guan", location=scout),
                  self.bill("escort", "escort", "guan", location=self.hub(), end=dest), self.bill("far", "escort", "guan", location=dest, end=self.hub()),
                  self.bill("other", "strike", "huang", location=loc), self.bill("extra", "scout", "guan", location=scout))
        self.main(who)
        with self.tweak(self.c.config.bounties, max_taken=3):
            self.choose(who, "act:bounties")
            self.choose(who, f"bounty:take:{PL_PREFIX}far")  # 灰的：要在別處接
            for bid in ("strike", "scout", "escort"):
                self.choose(who, f"bounty:take:{PL_PREFIX}{bid}")
            self.choose(who, f"bounty:take:{PL_PREFIX}extra")  # 灰的：揭滿了
            self.choose(who, f"bounty:take:{PL_PREFIX}other")  # 不在選單上：不是給他的
            self.choose(who, f"bounty:drop:{PL_PREFIX}scout")
            self.choose(who, f"bounty:drop:{PL_PREFIX}scout")  # 不在選單上：已經放回去了
            self.choose(who, f"bounty:take:{PL_PREFIX}scout")
            self.choose(who, "bounty:back")
        self.me(who, "揭完")
        self.books("揭完")
        self.main(who)  # 江湖頁：懸賞卡、本週卡的懸賞那一格

    def gates(self) -> None:
        """門檻：重賞要名動一方、官府通緝要俠一路的稱號、新手揭不了通緝（阮青禾看灰掉的；聶小舟剛入江湖）；出名之後揭得到。"""
        loc = (self.spots() + [self.hub()])[0]
        self.post(self.bill("prize", "strike", "guan", location=loc, prize="treasure"),
                  self.bill("official", "wanted", None, auto_by="官府", target=self.FOE, renown_title="江湖巨寇", quota=1),
                  self.bill("plain", "wanted", "huang", poster="（對照）掛單人", target=self.TURNCOAT, quota=1))
        self.choose(self.RANGER, "act:bounties")
        self.choose(self.RANGER, f"bounty:take:{PL_PREFIX}prize")
        self.choose(self.RANGER, f"bounty:take:{PL_PREFIX}official")
        self.choose(self.RANGER, "bounty:back")
        self.edit(self.RANGER, lambda p: p.stats.update({"fame": 10 ** 6, "good": 10 ** 6}))
        self.choose(self.RANGER, "act:bounties")
        self.choose(self.RANGER, f"bounty:take:{PL_PREFIX}prize")
        self.choose(self.RANGER, f"bounty:take:{PL_PREFIX}official")
        self.choose(self.RANGER, f"bounty:drop:{PL_PREFIX}official")
        self.choose(self.RANGER, "bounty:back")
        self.me(self.RANGER, "出名之後")
        now = self.world.get_season().time
        self.edit(self.GREEN, lambda p: setattr(p, "joined_at", now))
        self.choose(self.GREEN, "act:bounties")
        self.choose(self.GREEN, f"bounty:take:{PL_PREFIX}plain")
        self.choose(self.GREEN, "bounty:back")
        self.edit(self.GREEN, lambda p: setattr(p, "joined_at", -1.0e9))

    def arms(self) -> None:
        """陸觀潮交求兵：第二層、挑一張、第三層（灰掉的 bounty:more、回到懸賞榜）、交庫裡最不值錢的、交手上那一把（交了空手）；
        只有神器原品、本命兵器對得上的那兩張（bounty:none）；不在選單上的交出（交過了、不是這一件）；最後坐在榜前、指著一張還沒交（前半停在這裡）。"""
        from tianxia.state import Equipment

        who, cfg = self.GIVER, self.c.config.bounties
        sword = {"slot": "weapon", "kind": "劍", "attribute": "剛", "tier": 1, "quality": "下品"}
        rack = [Equipment(id=f"兵:{500 + i}", name=f"榜前劍{i}", **sword) for i in range(cfg.give_list + 2)]
        rack += [Equipment(id="兵:601", slot="weapon", name="榜前原品", kind="槍", attribute="柔", tier=1, quality="下品", original=True),
                 Equipment(id="兵:602", slot="weapon", name="榜前本命", kind="刀", attribute="快", tier=1, quality="下品", original=True, signature="sunjian")]
        rack += [Equipment(id="兵:604", slot="weapon", name="榜前別樣", kind="槍", attribute="剛", tier=1, quality="下品")]
        rack[1].tempers = 1  # 第三層那一顆的確認句多一句「淬過不加錢」
        held = Equipment(id="兵:603", slot="weapon", name="榜前手上", kind="槍", attribute="快", tier=1, quality="下品")

        def fn(p) -> None:
            p.rack, p.weapon = rack, held

        self.edit(who, fn)
        arms = {"silver": 0, "deeds": 2, "quota": 3}
        self.post(self.bill("arms_a", "arms", "guan", attribute="剛", weapon_kind="劍", **arms), self.bill("arms_b", "arms", "guan", attribute="柔", weapon_kind="槍", **arms),
                  self.bill("arms_c", "arms", "guan", attribute="快", weapon_kind="刀", **arms), self.bill("arms_d", "arms", "guan", attribute="快", weapon_kind="槍", **arms),
                  self.bill("arms_e", "arms", "guan", attribute="剛", weapon_kind="劍", **arms), self.bill("arms_h", "arms", "huang", attribute="剛", weapon_kind="劍", **arms))
        self.main(who)  # 懸賞卡的「你身上合用的」
        self.choose(who, "act:bounties")
        self.choose(who, f"bounty:pick:{PL_PREFIX}arms_a")
        self.choose(who, "bounty:more")  # 灰的
        self.choose(who, "bounty:unpick")
        self.choose(who, f"bounty:pick:{PL_PREFIX}arms_a")
        self.choose(who, f"bounty:give:{PL_PREFIX}arms_a:兵:500")
        self.choose(who, f"bounty:give:{PL_PREFIX}arms_a:兵:501")  # 不在選單上：交過了
        self.choose(who, f"bounty:give:{PL_PREFIX}arms_b:兵:601")  # 不在選單上：原品交不得
        self.choose(who, f"bounty:give:{PL_PREFIX}arms_c:兵:602")  # 不在選單上：本命交不得
        self.choose(who, f"bounty:give:{PL_PREFIX}arms_e:兵:999")  # 不在選單上：沒有這一件
        self.choose(who, f"bounty:give:{PL_PREFIX}arms_e:兵:604")  # 不在選單上：種類不對
        self.choose(who, f"bounty:give:{PL_PREFIX}arms_h:兵:501")  # 不在選單上：不是給他的
        self.choose(who, f"bounty:pick:{PL_PREFIX}arms_d")
        self.choose(who, f"bounty:give:{PL_PREFIX}arms_d:兵:603")  # 手上那一把：交了空手
        self.choose(who, "bounty:none")  # 灰的
        self.me(who, "交完兩張")
        self.books("交完兩張")
        self.choose(who, f"bounty:pick:{PL_PREFIX}arms_e")

    def scramble(self) -> None:
        """搶單（FB-162）：阮青禾開著榜，那一張下榜了；不在選單上的 take、drop、pick、give、亂打的動詞；看得到的全被交光（bounty:empty，FB-156）。"""
        who = self.RANGER
        self.post(self.bill("gone", "scout", "guan", location=self.hub()))
        self.choose(who, "act:bounties")
        self.choose(who, "bounty:unpick")  # 不在選單上
        self.choose(who, f"bounty:drop:{PL_PREFIX}gone")  # 不在選單上：還在榜上、不是他揭的
        self.world.mutate_season(lambda s: s.bounties.__setitem__(slice(None), [b for b in s.bounties if b.id != f"{PL_PREFIX}gone"]))
        for verb in ("take", "drop", "pick"):
            self.choose(who, f"bounty:{verb}:{PL_PREFIX}gone")
        self.choose(who, f"bounty:give:{PL_PREFIX}gone:兵:1")
        self.choose(who, "bounty:nonsense")
        kept: list = []

        def clear(s) -> None:
            kept[:] = s.bounties
            s.bounties[:] = []

        self.world.mutate_season(clear)
        self.main(who)
        self.choose(who, "bounty:empty")  # 灰的
        self.world.mutate_season(lambda s: s.bounties.__setitem__(slice(None), list(kept)))
        self.choose(who, "bounty:back")
        self.choose(who, "bounty:back")  # 不在選單上：已經離開了

    def tavern_wall(self) -> None:
        """酒肆牆上的榜：tavern:board 收起酒肆、打開懸賞榜，返回。"""
        who = self.FOE
        if "act:tavern" not in self.ids(self.main(who)):
            emit("酒肆：此地沒有", None)
            return
        out = self.choose(who, "act:tavern")
        emit("牆上的榜那一顆", self.ids(out).get("tavern:board"))
        if "tavern:board" in self.ids(out):
            self.choose(who, "tavern:board")
            self.me(who, "看牆上的榜")
            self.choose(who, "bounty:back")
        else:
            self.choose(who, "tavern:back")

    def cards(self) -> None:
        """玩家卡的通緝：散人、同陣營沒有鈕；敵對的有；對方新手、自己沒錢、截殺關著；押不對的數、押得對、已經掛著一張。"""
        who, prey = self.POSTER, self.QUARRY
        self.main(prey)
        self.main(who)
        self.peer(self.RANGER, prey)
        self.peer(self.TAKER, who)
        self.peer(who, prey)
        now = self.world.get_season().time
        self.edit(prey, lambda p: setattr(p, "joined_at", now))
        self.peer(who, prey)
        self.edit(prey, lambda p: setattr(p, "joined_at", -1.0e9))
        self.edit(who, lambda p: p.stats.update({"silver": 0}))
        self.peer(who, prey)
        self.hunt(who, prey, 10)
        self.edit(who, lambda p: p.stats.update({"silver": 300}))
        with self.tweak(self.c.config.raid, enabled=False):
            self.peer(who, prey)
            self.hunt(who, prey, 10)
        self.main(prey)  # 測試內容「此地還有」的窗口短：對方照舊同步，卡才在
        self.hunt(who, prey, 1)
        self.hunt(who, prey, "不是數字")
        self.hunt(who, prey, self.c.config.bounties.post_min + 5)
        self.main(prey)
        self.peer(who, prey)
        self.hunt(who, prey, self.c.config.bounties.post_min + 5)
        self.me(who, "押了通緝")
        self.books("押了通緝")

    def auto(self) -> None:
        """系統通緝（本人這一輪）：威震州郡的官軍（對面那一軍掛）、江湖巨寇的散人（官府掛）；同一週不再掛；截殺關著不掛。"""
        with self.tweak(self.c.config.raid, enabled=False):
            self.edit(self.ROGUE, lambda p: p.stats.update({"evil": 10 ** 6}))
            self.main(self.ROGUE)
        self.edit(self.FAMOUS, lambda p: p.stats.update({"fame": 10 ** 6}))
        for who in (self.FAMOUS, self.ROGUE):
            self.main(who)
            self.main(who)
            self.me(who, "系統通緝之後")
        self.books("系統通緝之後")

    def lapse(self) -> None:
        """作廢：名額被交滿、過了期限、掛單的是別的陣營（邢晚晴手上三張，同步時各補一句、拿掉名字）。"""
        who = self.LAPSER
        here = (self.spots() + [self.hub()])[0]
        self.post(self.held("full", "scout", who, "guan", location=here, quota=1, done_by=["（對照）別人"]),
                  self.held("due", "scout", who, "guan", location=here), self.held("side", "scout", who, "huang", location=here))

        def overdue(s) -> None:
            next(b for b in s.bounties if b.id == f"{PL_PREFIX}due").expires = s.time - 1.0

        self.world.mutate_season(overdue)
        self.main(who)
        self.me(who, "作廢之後")
        self.books("作廢之後")

    def errands(self) -> None:
        """委託與求援：焦慮的官軍人物擲中求援（世界一步，世界照 rally_chance 全中）；梅子衿手上兩封信的委託（欠他的那一件、他兌現的那一件），
        信卡與懸賞卡的賞（「他兌現：…」）；前半不辦。"""
        from tianxia import figure_life, figures
        from tianxia.state import Bounty, Letter, ParleyDebt

        who = self.AIDE
        pick = self.guan_figure()
        emit("官軍的大勢人物", pick)
        if pick is not None and figure_life.on(self.c):
            import math

            fid, cid, at = pick
            self.with_game(ADMIN, lambda g: setattr(figures._ensure(g.state, self.c, fid), "prestige", 1))
            s = self.world.get_season()
            with self.tweak(self.c.config.figure_life, rally_chance=1.0):
                self.do(ADMIN, "fast_forward", {"hours": math.ceil(figure_life.period(self.c, s) / 3600) + 1})
            self.place(who, at)
        spots = self.spots() + [self.hub()]
        cid = pick[1] if pick is not None else next(iter(sorted(self.c.characters)), None)
        emit("寫信的人物", cid)
        if cid is not None:
            far = self.world.get_season().time + 30 * 86400.0
            owed = Bounty(id="c901", kind="scout", faction="guan", week=1, expires=far, silver=30, deeds=0, quota=1, location=spots[0], figure=cid, motive="委託")
            terms = Bounty(id="c902", kind="scout", faction="guan", week=1, expires=far, silver=40, deeds=0, quota=1, location=spots[0], figure=cid, motive="委託", parley_ask="spar")

            def fn(p) -> None:
                now = self.world.get_season().time
                p.parley_debts[cid] = ParleyDebt(kind="owe", condition=f"scout:{spots[0]}", due=far, task="c901")
                p.letters += [Letter(id=9001, kind="求援", sender=cid, at=now, text="（對照）書信一", task=owed),
                              Letter(id=9002, kind="條件", sender=cid, at=now, text="（對照）書信二", task=terms)]

            self.edit(who, fn)
        self.main(who)
        self.me(who, "收到委託")
        self.books("求援之後")

    def fallen(self) -> None:
        """人物倒下：盟友掛復仇、仇敵掛追剿（同一邊共用一張，看 posted）。挑盟友與仇敵最多的那一位。"""
        from tianxia import figure_life, figures, relations

        for side in ("huang", "guan"):
            rows = []
            for fid, fig in sorted(self.c.figures.items()):
                cid = fig.character
                if cid in self.c.characters and fig.faction == side:
                    rows.append((-len(relations.allies(self.c, cid)) - len(relations.foes(self.c, cid)), fid))
            fid = min(rows)[1] if rows and min(rows)[0] < 0 and figure_life.on(self.c) else None
            emit(f"倒下的人物（{side}）", fid)
            if fid is None:
                continue
            lines = self.with_game(ADMIN, lambda g, fid=fid: figures.defeat(g.state, self.c, fid, 10 ** 6))
            emit("倒下那幾句", lines)
            self.books("人物倒下之後")

    def stranded_join(self) -> None:
        """投靠：葛春陽（散人）揭著兩邊的單，在官軍的投靠點按投靠：確認畫面寫幾張作廢、確定之後那一張拿掉。"""
        who = self.DRIFTER
        here = (self.spots() + [self.hub()])[0]
        self.post(self.held("drift_h", "scout", who, "huang", location=here), self.held("drift_g", "scout", who, "guan", location=here))
        spot = next(f.join_at[0] for f in self.c.scenario.factions if f.id == "guan")
        self.place(who, spot)
        self.choose(who, "faction:guan")
        self.choose(who, "faction:confirm")
        self.settle_choices(who)
        self.me(who, "投靠之後")

    def stranded_lean(self) -> None:
        """改幫：譚雪竹（豪強、依附官軍）揭著官軍的單，改幫黃巾：那一句寫「改幫」。四勝利關著的季沒有這一顆。"""
        who = self.BENDER
        here = (self.spots() + [self.hub()])[0]
        self.post(self.held("bend", "scout", who, "guan", location=here))
        self.edit(who, lambda p: setattr(p, "ally", "guan"))
        ids = [i for i in self.ids(self.main(who)) if i.startswith("faction:lean:")]
        emit("改幫那幾顆", ids)
        if "faction:lean:huang" in ids:
            self.choose(who, "faction:lean:huang")
        self.me(who, "改幫之後")

    def stranded_note(self) -> None:
        """事件選項拜入陣營名下的門派：賴秋實（散人）揭著對頭的單，選項後面多一個括號（join_note），選下去那一張作廢。沒有這種事件的內容寫「沒有」。"""
        who = self.PILGRIM
        here = (self.spots() + [self.hub()])[0]
        found = None
        for eid, e in sorted(self.c.events.items()):
            for n, ch in enumerate(e.choices):
                owner = self.c.scenario.sect_owner(ch.effect.join_sect) if ch.effect.join_sect else None
                if owner is not None and owner.id in ("guan", "huang"):
                    found = (eid, n, owner.id)
                    break
            if found:
                break
        emit("拜入陣營門派的事件", found)
        if found is None:
            return
        eid, n, side = found
        self.post(self.held("note", "scout", who, "huang" if side == "guan" else "guan", location=here))

        def fn(_g) -> None:
            _g.state.pending_event = eid

        self.with_game(who, fn)
        self.main(who)
        self.choose(who, f"choice:{n}")
        self.settle_choices(who)
        self.me(who, "拜入之後")

    def stranded_defect(self) -> None:
        """叛投：喻北辰（官軍）揭著官軍的單，在黃巾的投靠點按叛投：確認畫面、確定之後那一張拿掉。"""
        who = self.TURNCOAT
        here = (self.spots() + [self.hub()])[0]
        self.post(self.held("turn", "scout", who, "guan", location=here))
        self.place(who, next(f.join_at[0] for f in self.c.scenario.factions if f.id == "huang"))
        ids = [i for i in self.ids(self.main(who)) if i.startswith("defect:")]
        emit("叛投那幾顆", ids)
        if "defect:huang" in ids:
            self.choose(who, "defect:huang")
            self.choose(who, "defect:confirm")
        self.me(who, "叛投之後")

    def stranded(self) -> None:
        self.stranded_join()
        self.stranded_lean()
        self.stranded_note()
        self.stranded_defect()
        self.books("換邊之後")

    def half(self) -> None:
        """前半停在這裡：世界時間推到下一次掛單（21 天季明天 00:00、其他下週一）的前一個鐘頭以內；韋望舒揭一張、坐在榜前到收季。"""
        import math

        from tianxia import calendar

        here = (self.spots() + [self.hub()])[0]
        self.post(self.bill("sit", "scout", "guan", location=here))
        self.choose(self.SITTER, "act:bounties")
        self.choose(self.SITTER, f"bounty:take:{PL_PREFIX}sit")
        s = self.world.get_season()
        at = calendar.point(s.time, self.c, s)
        edge = calendar.day_start(at.cal_day + 1, self.c, s) if calendar.season21_on(s, self.c) else calendar.week_start(at.week + 1, self.c, s)
        hours = math.floor((edge - s.time) / 3600) - 1
        emit("離下一次掛單還有幾個世界時", hours)
        if hours > 0:
            self.do(ADMIN, "fast_forward", {"hours": hours})
        for who in (self.TAKER, self.AIDE, self.POSTER, self.GIVER):
            self.me(who, "前半停在這裡")
        self.books("前半停在這裡")

    # ── 後半 ──

    def resume(self) -> None:
        self.login_all()
        self.main(self.GIVER)
        self.main(self.AIDE)
        self.books("接手")

    def hand_over(self) -> None:
        """舊程式開著的第三層，新程式接著交：bounty_pick 指著的那一張。"""
        who = self.GIVER
        self.choose(who, f"bounty:give:{PL_PREFIX}arms_e:兵:501")
        self.choose(who, "bounty:back")
        self.me(who, "接著交完")

    def edge(self) -> None:
        """跨過掛單那一刻：同一下掛軍令與懸賞。"""
        self.do(ADMIN, "fast_forward", {"hours": 3})
        self.books("跨過掛單那一刻")

    def deliver(self) -> None:
        """舊程式揭的，新程式交差：打贏（討伐）、探索（打探）、抵達（護送）。"""
        who = self.TAKER
        w = self.world.get_season()
        bills = {b.id: b for b in w.bounties}
        strike, scout, escort = (bills.get(f"{PL_PREFIX}{k}") for k in ("strike", "scout", "escort"))
        emit("手上那三張還在嗎", [x is not None for x in (strike, scout, escort)])
        if strike is not None and self.place(who, strike.location):
            self.fight_here(who)
            self.me(who, "打贏之後")
        if scout is not None and self.place(who, scout.location):
            explore_one = _explore_rules()
            with self.draws(explore_one.MATERIAL):
                self.explore(who)
            self.me(who, "探索之後")
        if escort is not None and self.place(who, self.hub()):
            move = next((i for i, o in self.ids(self.main(who)).items() if i.startswith("move:") and o.get("enabled") and i.split(":")[1] == escort.end), None)
            emit(f"{who} 去交護送", move)
            if move is not None:
                self.choose(who, move)
                self.wait_arrive(who)
            self.me(who, "抵達之後")
        self.books("交差之後")

    def aided(self) -> None:
        """舊程式掛的求援與書信委託，新程式辦成：探索（兩件委託：欠他的那一件守約；他兌現的那一件記 parley_owed）、護衛犒軍（求援：道謝信）。"""
        who = self.AIDE
        spots = self.spots() + [self.hub()]
        if self.place(who, spots[0]):
            explore_one = _explore_rules()
            with self.draws(explore_one.MATERIAL):
                self.explore(who)
            self.me(who, "委託辦成")
        self.opening_letter()
        pick = self.guan_figure()
        emit("官軍的大勢人物（後半）", pick)
        if pick is None:
            return
        fid, _cid, at = pick
        self.place(who, at)
        view = self.main(who)
        for verb in ("guard", "rally"):
            oid = f"aid:{verb}:{fid}"
            emit(f"{who} 的 {oid}", self.ids(view).get(oid))
            if self.ids(view).get(oid, {}).get("enabled"):
                self.choose(who, oid)
                self.me(who, f"{verb} 之後")
                break
        self.books("求援之後（後半）")

    def opening_letter(self) -> None:
        """開局那封信附的委託（護送）：邢晚晴從終點隔壁走一步到終點交差（照著走；信上寫的地方沒有隔壁的內容寫「沒有」）。"""
        who = self.LAPSER
        state = self.chars.load(who)
        task = next((x.task for x in state.player.letters if x.task is not None and not x.task.done_by and not x.lapsed), None)
        emit(f"{who} 信上的委託", None if task is None else [task.id, task.kind, task.location, task.end])
        if task is None or task.end is None or task.end not in self.c.locations:
            return
        nearby = next((str(x) for x in self.c.locations[task.end].connections), None)
        if nearby is None or not self.place(who, nearby):
            return
        move = next((i for i, o in self.ids(self.main(who)).items() if i.startswith("move:") and o.get("enabled") and i.split(":")[1] == task.end), None)
        emit(f"{who} 去交信", move)
        if move is not None:
            self.choose(who, move)
            self.wait_arrive(who)
        self.me(who, "交信之後")

    def refund(self) -> None:
        """通緝：阮青禾揭了蘇硯冰掛的那一張、截殺打贏交差；蘇硯冰再押一張，過了期限退押金。"""
        who, prey, poster = self.RANGER, self.QUARRY, self.POSTER
        w = self.world.get_season()
        bill = next((b for b in w.bounties if b.kind == "wanted" and b.poster == poster), None)
        emit("押著的那一張", None if bill is None else bill.id)
        spot = self.wild_spot()
        if bill is not None and spot is not None:
            self.place(who, self.hub())
            self.choose(who, "act:bounties")
            self.choose(who, f"bounty:take:{bill.id}")
            self.choose(who, "bounty:back")
            self.place(prey, spot)
            self.place(who, spot)
            self.main(prey)
            self.peer(who, prey)
            with self.raid_wins():
                self.call(who, "POST", "/api/peer/act", {"name": prey, "action": "raid"})
            self.me(who, "截殺之後")
        self.place(poster, self.hub())
        self.place(prey, self.hub())
        self.main(prey)
        self.main(poster)
        self.hunt(poster, prey, self.c.config.bounties.post_min)
        w = self.world.get_season()
        second = next((b for b in w.bounties if b.kind == "wanted" and b.poster == poster and not b.done_by and b.id != (bill.id if bill else "")), None)
        emit("第二張通緝", None if second is None else second.id)
        if second is not None:
            def overdue(s) -> None:
                next(b for b in s.bounties if b.id == second.id).expires = s.time - 1.0

            self.world.mutate_season(overdue)
            self.main(poster)
            self.me(poster, "退押金之後")
        self.books("退押金之後")

    def bots(self) -> None:
        """假人：BotRunner 官軍、黃巾各一（站在起點，榜上有自己這一邊揭得下的與交得出的求兵）若干輪；整季機器人（bot.take_bounties）。"""
        from collections import Counter

        from tianxia import bot, server_bots
        from tianxia.bot_runner import BotRunner
        from tianxia.engine import Game
        from tianxia.state import BotProfile, Equipment

        spot = (self.spots() + [self.hub()])[0]
        arms = {"silver": 0, "deeds": 2, "quota": 3}
        for i, (name, side) in enumerate(zip(self.BOT_SEATS, ("guan", "huang", "guan"))):
            self.begin()
            g = Game.new(self.c, name, rng=random.Random(i), world=self.world, graduated=True)
            p = g.state.player
            p.bot = BotProfile(personality="普通", seed=81 + i, faction=side, season_number=self.world.get_season_number())
            g.client = None
            g.sync(CLOCK[0])
            for _ in range(6):
                first = next((o.id for o in g.options(odds=False) if o.id.startswith(("choice:", "growth:")) and o.enabled), None)
                if first is None:
                    break
                g.choose(first)
            p.faction, p.location, p.journey = side, self.hub(), None
            p.tutorial_step = len(self.c.tutorial.steps)
            p.joined_at = -1.0e9
            p.stamina = float(self.c.config.stamina_max)
            p.rack = [Equipment(id=f"兵:{700 + i}", slot="weapon", name=f"榜前舊劍{i}", kind="劍", attribute="剛", tier=1, quality="下品")]
            self.chars.save(g.state)
            self.post(self.bill(f"bot_scout_{i}", "scout", side, location=spot), self.bill(f"bot_arms_{i}", "arms", side, attribute="剛", weapon_kind="劍", **arms))
        runner = BotRunner(self.c, self.world, self.chars, rng=random.Random(47), clock=lambda: CLOCK[0])
        tick, online = self.c.config.bot_tick_seconds, server_bots.is_online
        seeds = {81, 82}
        self.c.config.bot_tick_seconds = 10 ** 6
        server_bots.is_online = lambda profile, now: profile.seed in seeds or (profile.seed != 83 and online(profile, now))
        totals = Counter()
        try:
            for _ in range(16):
                STEP[0] += 4
                self.begin()
                report = runner.tick()
                totals.update(acted=report.acted, added=report.added, skipped=report.skipped, failed=report.failed, online=report.online)
        finally:
            self.c.config.bot_tick_seconds, server_bots.is_online = tick, online
        emit("假人 一輪一輪", dict(sorted(totals.items())))
        self.with_game(self.BOT_SEATS[2], lambda g: emit("整季機器人揭懸賞", bot.take_bounties(g)))
        for name in self.BOT_SEATS:
            s = self.chars.load(name)
            emit(f"假人 {name}", {"loc": s.player.location, "done": s.player.bounties_done, "rack": [x.id for x in s.player.rack], "board": [s.player.picking_bounty, s.player.bounty_pick],
                                  "journal": [[e.title, list(e.lines)[:4]] for e in s.journal[:4]],
                                  "state": hashlib.sha256(s.model_dump_json().encode("utf-8")).hexdigest()})
        self.books("假人之後")

    def season(self) -> None:
        """收季：韋望舒還坐在榜前、手上揭著一張（這一季收了）；按返回、開下一季。"""
        who = self.SITTER
        self.main(who)
        self.do(ADMIN, "end_season")
        self.books("收季之後")
        self.main(who)
        self.me(who, "收季之後")
        self.choose(who, "bounty:back")
        self.do(ADMIN, "next_season")
        self.books("換季之後")
        self.main(who)
        self.me(who, "換季之後")


# 改一個字（selftest）：進榜那一句（原本 Game._act；第 45 批搬進懸賞榜包的 actions.py，兩處都列）
register_track("placard", PlacardScenario, (("tianxia/engine.py", "tianxia/features/bounties/actions.py"), ("看上面貼了些什麼。", "看上面貼了些什麼！")), "week7",
               covers=("admin", "battle", "bounties", "bout", "checkin", "companions", "craft", "cultivation", "explore", "faction",
                       "feast", "figure_acts", "gear", "guide", "heroines", "jieyi", "legacy", "looks", "mall", "map",
                       "military", "outlets", "peers", "seal", "sense", "smithy", "socialize", "sortie", "stamina_plays", "story",
                       "tavern", "territory_acts", "travel", "zhuan", "zongmen"))
