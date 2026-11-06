"""same_behavior 一軌一檔：abacus（這一檔登記 abacus）。"""
from __future__ import annotations

import contextlib
import random

from sb.base import Scenario
from sb.harness import ADMIN, CLOCK, STEP, emit, register_track
from sb.tracks.zhuan import ZhuanScenario

# ── 商城收尾一軌（全部拆包第 58 批；--track abacus）：六條 /api/mall、三個管理者工具每一條都打到，切在舊程式賣了、新程式才用的那一刻 ──


class AbacusScenario(Scenario):
    """商城收尾一軌（全部拆包第 58 批；--track abacus，自己一個資料庫）。班底的名字都是原創（PM 11/04）。這一批動到 routes.py，所以六條路由
    （GET /api/mall、/api/mall/records，POST /api/mall/buy、/api/mall/claim、/api/mall/rename、/api/admin/mall）與 /api/do 的三個工具（mall_reissue、
    mall_revoke、mall_refund）每一條都打到；別軌只碰 mall_reissue 與 /api/mall/buy（當發錢買票用）。

    前半（舊程式）：shelf 第一次進來、沒登入 401、不是管理者 403、管理者照名號、照帳號、查無此人；grant 補發（同編號、沒原因、壞金額、不是管理者、
    沒送編號由伺服器產〔secrets 固定〕）；buying 買成、同編號重送（already）、幾件、限購夾件數、限購滿、沒這件、元寶不夠、各種效果、還沒上架的列傳那幾件、
    暫停中被擋（管理者照做）；card 月卡回饋與今天的份；early_name 舊程式就改了名；half 停在寫到一半：硯田生買下一件、回應沒收到，易安客手上一張舊程式賣的帖，
    月卡明天的份還沒領，遲歸人還沒輪到過自己（封測發放沒發）。
    後半（新程式）：resume 重新登入、舊程式買好的編號重送（already）、新程式發封測元寶（week7）、舊程式改的名照新名號讀；claim 隔天領；refund 硯田生每一筆逐一退
    （回體丹用掉的不追、月卡少天數與回饋扣回、票與形象收回）與退不了的幾種；revoke 扣回與扣不了的幾種、管理者與本人看帳、把新手扣到 0 再買（一件的元寶不夠）；
    rename 舊程式賣的帖由新程式用：沒帖、空的、太長、看不見的字元、同名、有人用、保留的名號（經 server.name_taken）、撞內容的 id、管理者、奪璽單挑還沒打完、改成、
    沒帖了；direct 不經路由直接叫包：rename_left、entry、view、records 與不給 taken 的 rename_self（actions 自己查角色表與 reserved_names：三國名人、管理者、內容人物、
    有人用、同名、改成）；bots 假人那一輪照拿封測發放（week7 帳上 5000、沒有購買紀錄）、手上有帖也不讓用；season 休季的貨架、帳上不寫季曆、紀念印上架買得到、
    開下一季限購重算、重悟帖與破境丹帶著走、藏經匣第一次回來時歸零。
    開關關著的設定（test）同一串 API 照打：路由與工具一律 404，直接叫包回「商城沒有開。」。

    這一軌走不到的：列傳插畫白送（ART_FREE：要休季得第一階；散人不賣 ART_NO_SIDE 有走到）；zhuan_art 買成（要第 3 週起，列傳一軌買過）；rename 成了之後
    GAMES 換鍵看不出來（begin() 每一步清空 GAMES，那兩行有跑、下一步用不到）；決戰還沒打完擋改名（只走奪璽單挑那一半，兩者同一句判斷）。"""

    PLAYERS = {"硯田生": "guan", "易安客": "huang", "守拙叟": "guan"}
    NEWBIE = "寒窗客"
    LATE = "遲歸人"
    BOT_SEATS = ["盤甲", "盤乙"]
    PHASES_FIRST = ["setup", "shelf", "grant", "buying", "card", "early_name", "half"]
    PHASES_SECOND = ["resume", "claim", "refund", "revoke", "rename", "direct", "bots", "season"]
    BUYER, NAMER, EARLY = "硯田生", "易安客", "守拙叟"

    # ── 小工具 ──

    def buy(self, who: str, item: str, ref: str, **extra):
        return self.call(who, "POST", "/api/mall/buy", {"item": item, "ref": ref, **extra})[1]

    def renamed(self, who: str, name: str):
        return self.call(who, "POST", "/api/mall/rename", {"name": name})[1]

    def claim_today(self, who: str):
        return self.call(who, "POST", "/api/mall/claim")[1]

    def ledger(self, name: str, who: str = ADMIN):
        return self.call(who, "POST", "/api/admin/mall", {"name": name})[1]

    def reissue(self, name: str, amount, ref: str, note: str = "算盤", who: str = ADMIN):
        return self.do(who, "mall_reissue", {"name": name, "amount": amount, "note": note, "ref": ref})

    def stranger(self, method: str, url: str, body: dict | None = None) -> None:
        """沒登入的人。"""
        self.begin()
        client = self.TestClient(self.server.app)
        r = client.post(url, json=body if body is not None else {}) if method == "POST" else client.get(url)
        emit(f"沒登入 {method} {url} {r.status_code}", r.text[:200])

    def purchases(self, name: str) -> list:
        from tianxia.characters import name_key
        from tianxia.wallet import Wallet

        return Wallet(self.world.db).purchases(name_key(name))

    def wallet_of(self, name: str) -> int:
        from tianxia.characters import name_key
        from tianxia.wallet import Wallet

        return Wallet(self.world.db).balance(name_key(name))

    def named(self, who: str, new: str) -> str:
        """改成了就是新名號，沒改成（商城關著）還是舊的。"""
        return new if self.chars.load(new) is not None else who

    @contextlib.contextmanager
    def server_ref(self, text: str):
        """網頁沒送合格的編號時伺服器自己產（secrets.token_urlsafe，會進帳）：這一下固定成 text，跑兩次才比得了。"""
        import secrets

        real = secrets.token_urlsafe
        secrets.token_urlsafe = lambda nbytes=None: text
        try:
            yield
        finally:
            secrets.token_urlsafe = real

    def at_hand(self, name: str, tag: str, fn) -> None:
        """不經路由、直接叫包（rename_left 沒有路由；rename_self 不給 taken 那一條只有測試、腳本走）：照伺服器那樣拿鎖、同步、做、存。"""
        from tianxia.engine import Game
        from tianxia.features.mall import actions

        self.begin()
        with self.world.action_lock():
            g = Game(self.c, self.chars.load(name), world=self.world)
            g.client = None
            g.sync(CLOCK[0])
            out = fn(g, actions)
            g._save_season()
            self.chars.save(g.state)
        emit(f"{name} 直接叫包 {tag}", out)

    # ── 前半（舊程式） ──

    def shelf(self) -> None:
        """第一次進來：貨架、帳、沒登入的人、不是管理者查帳、管理者照名號、照帳號、查無此人。"""
        self.call(self.BUYER, "GET", "/api/mall")
        self.call(self.BUYER, "GET", "/api/mall/records")
        self.stranger("GET", "/api/mall")
        self.stranger("POST", "/api/mall/buy", {"item": "pills_5", "ref": "abacus-nobody"})
        self.ledger(self.BUYER, who=self.BUYER)
        self.ledger(self.BUYER)
        self.ledger(self.login_of(self.BUYER))
        self.ledger("查無此人")

    def grant(self) -> None:
        """補發：成了、同一個編號再送、沒寫原因、金額不對、照帳號、查無此人、不是管理者、沒送編號（伺服器產）。"""
        self.reissue(self.BUYER, 9000, "abacus-g-buyer")
        self.reissue(self.BUYER, 9000, "abacus-g-buyer")
        self.reissue(self.BUYER, 100, "abacus-g-nonote", note="")
        self.reissue(self.BUYER, -5, "abacus-g-bad")
        self.reissue(self.login_of(self.NAMER), 1000, "abacus-g-namer")
        self.reissue("查無此人", 100, "abacus-g-nobody")
        self.reissue(self.NAMER, 100, "abacus-g-self", who=self.NAMER)
        self.reissue(self.EARLY, 1500, "abacus-g-early")
        self.reissue(ADMIN, 1000, "abacus-g-admin")
        with self.server_ref("abacus-server-ref-1"):
            self.do(ADMIN, "mall_reissue", {"name": self.EARLY, "amount": 1, "note": "算盤"})

    def buying(self) -> None:
        """買：成了；同一個編號再送（already）；一次好幾件；限購夾件數；沒有這件；元寶不夠；各種效果；還沒上架；編號不合格（伺服器產）；暫停中被擋。"""
        self.buy(self.BUYER, "pills_5", "abacus-b-1")
        self.buy(self.BUYER, "pills_5", "abacus-b-1")
        self.buy(self.BUYER, "pills_5", "abacus-b-2", qty=2)
        self.buy(self.BUYER, "pills_5", "abacus-b-3", qty=9)
        self.buy(self.BUYER, "pills_5", "abacus-b-4")
        self.buy(self.BUYER, "沒有這件", "abacus-b-5")
        self.buy(self.BUYER, "pills_30", "abacus-b-6", qty=99)
        for item in ("holding_15", "reroll_1", "legend_1", "inscribe_ink", "rewrite_zhuan", "look_moying"):
            self.buy(self.BUYER, item, f"abacus-e-{item}")
        for item in ("zhuan_art", "zhuan_seal", "zhuan_quote"):  # 列傳那幾件：還沒到週數、休季才賣
            self.buy(self.BUYER, item, f"abacus-w-{item}")
        with self.server_ref("abacus-server-ref-2"):
            self.buy(self.BUYER, "inscribe_ink", "短")
        self.buy(self.NEWBIE, "pills_5", "abacus-n-1")  # 新手還在序章或開局；有沒有封測發放看設定（沒有的是元寶不夠）
        self.buy(self.NAMER, "rename", "abacus-r-1")  # 這一張留到後半（新程式）才用
        self.buy(self.NAMER, "rename", "abacus-r-2")  # 一季限一張
        for item in ("reroll_1", "legend_1", "holding_15"):  # 不退的這一份：收季時看換季帶著走的（重悟帖、破境丹）與只這一季的（藏經匣）
            self.buy(self.NAMER, item, f"abacus-k-{item}")
        self.do(ADMIN, "pause_clock")
        self.buy(self.BUYER, "inscribe_ink", "abacus-p-1")
        self.claim_today(self.BUYER)
        self.reissue(self.BUYER, 1, "abacus-p-2")  # 帳跟季無關：暫停中管理者照做
        self.do(ADMIN, "resume_clock")

    def card(self) -> None:
        """月卡：買下（當場回饋）、領今天的份、領過了、沒有卡的人。"""
        self.buy(self.BUYER, "card_30", "abacus-c-1")
        self.claim_today(self.BUYER)
        self.claim_today(self.BUYER)
        self.claim_today(self.NAMER)

    def early_name(self) -> None:
        """舊程式就改了名：後半登入、讀帳都照新名號。"""
        self.buy(self.EARLY, "rename", "abacus-r-3")
        self.renamed(self.EARLY, "抱樸叟")

    def half(self) -> None:
        """停在寫到一半：硯田生買下一件、回應沒收到（後半新程式收到同一個編號）；易安客手上一張舊程式賣的帖；硯田生的月卡明天的份還沒領；
        遲歸人帳號角色都建好了、還沒輪到過自己（封測發放由新程式發）。"""
        from tianxia.accounts import AccountStore
        from tianxia.engine import Game

        self.buy(self.BUYER, "inscribe_ink", "abacus-h-1")
        store = AccountStore(self.world.db)
        self.begin()
        self.passwords[self.LATE] = "pw-" + self.login_of(self.LATE)
        with self.world.db.transaction():
            store.register(self.login_of(self.LATE), self.passwords[self.LATE])
            game = Game.new(self.c, self.LATE, world=self.world)
            self.chars.save(game.state)
            store.bind_character(self.login_of(self.LATE), self.LATE)
        self.clients[self.LATE] = self.TestClient(self.server.app)
        emit("遲歸人 還沒輪到過自己", [p.item for p in self.purchases(self.LATE)])

    # ── 後半（新程式） ──

    def resume(self) -> None:
        self.login_all()
        self.buy(self.BUYER, "inscribe_ink", "abacus-h-1")  # 舊程式買好的編號重送：已經買好了（already）
        self.main(self.LATE)  # 新程式發封測元寶
        self.call(self.LATE, "GET", "/api/mall/records")
        self.main(self.EARLY)
        self.call(self.EARLY, "GET", "/api/mall/records")
        self.ledger("抱樸叟")
        self.ledger(self.EARLY)  # 舊名號：查不到

    def claim(self) -> None:
        """隔天：舊程式賣的月卡，新程式領今天的份；再領一次；貨架與入口跟著換。"""
        STEP[0] += 1440
        self.claim_today(self.BUYER)
        self.claim_today(self.BUYER)
        self.call(self.BUYER, "GET", "/api/mall")

    def refund(self) -> None:
        """退：硯田生買過的每一筆逐一退（回體丹用掉幾顆不追、月卡少天數與回饋扣回、票作廢）；退過了、沒有這一筆、沒寫原因、不是管理者。"""
        self.edit(self.BUYER, lambda p: setattr(p, "stamina_pills", 1))
        bought = self.purchases(self.BUYER)
        emit("硯田生 買過的", [[x.item, x.price, x.refunded] for x in bought])
        for i, x in enumerate(bought):
            self.do(ADMIN, "mall_refund", {"name": self.BUYER, "id": x.id, "note": f"算盤 {i}"})
        first = bought[0].id if bought else 1
        self.do(ADMIN, "mall_refund", {"name": self.BUYER, "id": first, "note": "算盤"})
        self.do(ADMIN, "mall_refund", {"name": self.BUYER, "id": 10 ** 6, "note": "算盤"})
        self.do(ADMIN, "mall_refund", {"name": self.BUYER, "id": first, "note": ""})
        self.do(self.NAMER, "mall_refund", {"name": self.BUYER, "id": first, "note": "算盤"})
        self.do(ADMIN, "mall_refund", {"name": "查無此人", "id": first, "note": "算盤"})
        self.call(self.BUYER, "GET", "/api/mall/records")

    def revoke(self) -> None:
        """扣回：成了、扣不了那麼多、沒寫原因、同一個編號、不是管理者；管理者看帳、本人看帳。"""
        self.do(ADMIN, "mall_revoke", {"name": self.BUYER, "amount": 10, "note": "算盤", "ref": "abacus-v-1"})
        self.do(ADMIN, "mall_revoke", {"name": self.BUYER, "amount": 10, "note": "算盤", "ref": "abacus-v-1"})
        self.do(ADMIN, "mall_revoke", {"name": self.BUYER, "amount": 10 ** 7, "note": "算盤", "ref": "abacus-v-2"})
        self.do(ADMIN, "mall_revoke", {"name": self.BUYER, "amount": 10, "note": "", "ref": "abacus-v-3"})
        self.do(self.NAMER, "mall_revoke", {"name": self.BUYER, "amount": 10, "note": "算盤", "ref": "abacus-v-4"})
        self.ledger(self.BUYER)
        self.call(self.BUYER, "GET", "/api/mall/records")
        left = self.wallet_of(self.NEWBIE)
        self.do(ADMIN, "mall_revoke", {"name": self.NEWBIE, "amount": left, "note": "算盤", "ref": "abacus-v-5"})
        self.buy(self.NEWBIE, "pills_30", "abacus-n-2")  # 一件的元寶不夠

    def rename(self) -> None:
        """易名帖：沒有帖、空的、太長、看不見的字元、同名、有人用（真人、保留的名號）、撞到內容的 id、管理者、奪璽單挑還沒打完；舊程式賣的那一張由新程式改成；再改一次沒帖了。"""
        from tianxia.world_state import SealDuel, SealSide

        self.renamed(self.BUYER, "換個名")
        self.renamed(self.NAMER, "")
        self.renamed(self.NAMER, "名" * (self.server.NAME_MAX + 1))
        self.renamed(self.NAMER, "零​寬")
        self.renamed(self.NAMER, self.NAMER)
        self.renamed(self.NAMER, self.BUYER)
        self.renamed(self.NAMER, "曹操")
        self.renamed(self.NAMER, "Rayal")
        self.renamed(self.NAMER, next(iter(self.c.locations)))
        self.buy(ADMIN, "rename", "abacus-r-admin")
        self.renamed(ADMIN, "新掌門")

        def side(name: str) -> SealSide:
            return SealSide(name=name, hp=100.0, hp_cap=100.0)

        self.world.mutate(lambda s: s.seal_duels.append(SealDuel(id="abacus:0", shard="abacus", starts_real=CLOCK[0],
                                                                 challenger=side(self.NAMER), holder=side(self.BUYER))))
        emit("擺一場奪璽單挑", None)
        self.renamed(self.NAMER, "易水生")
        self.world.mutate(lambda s: s.seal_duels.clear())
        emit("單挑清掉", None)
        self.renamed(self.NAMER, "易水生")
        self.main(self.NAMER)
        self.call(self.NAMER, "GET", "/api/mall/records")
        self.renamed(self.NAMER, "再易名")
        self.ledger("易水生")

    def direct(self) -> None:
        """不經路由的：手上幾張帖（rename_left 沒有路由）、狀態列入口、不給 taken 的改名（照角色表與保留的名號查：伺服器一律給 taken，這一條只有測試、腳本走）。"""
        self.reissue(self.LATE, 1000, "abacus-g-late")
        self.buy(self.LATE, "rename", "abacus-r-late")
        self.at_hand(self.LATE, "手上幾張帖", lambda g, a: a.rename_left(g))
        self.at_hand(self.LATE, "入口", lambda g, a: a.entry(g))
        self.at_hand(self.LATE, "三國名人", lambda g, a: a.rename_self(g, "曹操"))
        self.at_hand(self.LATE, "管理者的名號", lambda g, a: a.rename_self(g, "Rayal"))
        figure = next((f.name for f in self.c.figures.values()), "沒有人物")
        self.at_hand(self.LATE, "內容裡的人物", lambda g, a: a.rename_self(g, figure))
        self.at_hand(self.LATE, "有人用", lambda g, a: a.rename_self(g, self.BUYER))
        self.at_hand(self.LATE, "同名", lambda g, a: a.rename_self(g, self.LATE))
        self.at_hand(self.LATE, "改成", lambda g, a: a.rename_self(g, "晚歸客"))
        late = self.named(self.LATE, "晚歸客")
        self.at_hand(late, "手上幾張帖", lambda g, a: a.rename_left(g))
        self.at_hand(late, "貨架與帳", lambda g, a: [a.view(g), a.records(g)])
        self.main(self.LATE)

    def bots(self) -> None:
        """假人：自己那一輪照樣拿封測發放（on_own_turn）、從不買（帳上沒有購買紀錄）；手上就算有帖也不讓用。"""
        from tianxia.characters import name_key
        from tianxia.engine import Game
        from tianxia.state import BotProfile
        from tianxia.wallet import Wallet

        sides = [f.id for f in self.c.scenario.factions]
        for i, name in enumerate(self.BOT_SEATS):
            self.begin()
            g = Game.new(self.c, name, rng=random.Random(i), world=self.world, graduated=True)
            p = g.state.player
            p.bot = BotProfile(personality="普通", seed=91 + i, faction=sides[i % 2] if sides else None, season_number=self.world.get_season_number())
            g.client = None
            p.faction = p.bot.faction
            self.chars.save(g.state)
        ZhuanScenario.bot_rounds(self, "封測發放", 3)
        for name in self.BOT_SEATS:
            emit(f"假人 {name} 的帳", [self.wallet_of(name), [x.item for x in self.purchases(name)]])
        first = self.BOT_SEATS[0]
        Wallet(self.world.db).post(name_key(first), 500, "grant", "abacus:bot", time=CLOCK[0])
        self.at_hand(first, "塞一張帖", lambda g, a: a.buy(g, "rename", "abacus-bot-1"))
        self.at_hand(first, "易名帖不讓用", lambda g, a: a.rename_self(g, "盤丙"))
        ZhuanScenario.bot_rounds(self, "之後", 2)

    def season(self) -> None:
        """收季：休季的貨架（紀念印、親筆評曰上架）、帳上不寫季曆、管理者照做；開下一季：限購一季的又能買、換季帶著走的票還在、月卡照領。"""
        self.do(ADMIN, "end_season")
        self.call(self.BUYER, "GET", "/api/mall")
        self.call(self.BUYER, "GET", "/api/mall/records")
        self.buy(self.BUYER, "zhuan_seal", "abacus-s-1")
        self.buy(self.BUYER, "card_30", "abacus-s-2")
        self.claim_today(self.BUYER)
        self.reissue(self.BUYER, 5, "abacus-s-3")
        self.ledger(self.BUYER)
        self.do(ADMIN, "next_season")
        self.main(self.BUYER)
        self.call(self.BUYER, "GET", "/api/mall")
        self.call(self.BUYER, "GET", "/api/mall/records")
        STEP[0] += 1440
        self.claim_today(self.BUYER)
        self.buy(self.EARLY, "rename", "abacus-s-4")
        self.renamed(self.EARLY, "歸真叟")
        self.main(self.EARLY)
        self.ledger(self.BUYER)
        namer = self.chars.load(self.named(self.NAMER, "易水生")).player
        emit("易水生 帶到下一季的", [namer.create_rerolls, namer.legend_items, namer.holding_bonus, namer.stamina_pills])
        self.main(self.NAMER)
        namer = self.chars.load(self.named(self.NAMER, "易水生")).player
        emit("易水生 第一次回來之後", [namer.create_rerolls, namer.legend_items, namer.holding_bonus, namer.stamina_pills])


# 改一個字（selftest）：同一個編號再送回的那一句（mall.DUPLICATE：前半買好、後半新程式收到重送，FB-491）
register_track("abacus", AbacusScenario, (("tianxia/features/mall/rules.py", "tianxia/mall.py"),
                                          ('DUPLICATE = "這一筆已經買好了：「{name}」。"', 'DUPLICATE = "這一筆已經買好了：「{name}」！"')), "week7")
