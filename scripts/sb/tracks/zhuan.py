"""same_behavior 一軌一檔：zhuan（這一檔登記 zhuan）。"""
from __future__ import annotations

import contextlib
import hashlib
import random

from sb.base import Scenario
from sb.harness import ADMIN, CLOCK, MODEL, STEP, emit, register_track

# ═══════════════════════════ zhuan：列傳一軌（全部拆包第 29 批，dev/zhuan-1） ═══════════════════════════
# 列傳（tianxia/biography.py、zhuan_end.py、zhuan_html.py 與 Game 上寫傳、休季三顆、行狀頁的 20 個方法、server 的列傳那一段與 5 條路由、zhuan: 前綴）
# 搬進新包 tianxia/features/zhuan/（舊名留成別名；計畫 docs/superpowers/plans/2026-11-04-列傳包-第1批.md）。角色的名字都是原創的（PM 11/04）。

ZHUAN_FIGURES = ("luzhi", "zhujun", "caocao")  # 評曰與親筆評曰的人物（正式內容有；測試內容沒有就改拿人物表的前三位）


class ZhuanScenario(Scenario):
    """列傳（--track zhuan，自己一個資料庫）。休季的選單、行狀頁、寫傳 A（鎖內開單）→ B（鎖外叫模型）→ C（鎖內重驗再存）、人物評曰、三張票、
    分享與公開頁、換季之後讀舊的一季，全部經公開的 API；寫傳的背景執行緒改成當場跑完（不然「回應」與「寫完」是賽跑，雜湊不穩）。
    - 岑書瀾（官軍）：模型擋著（DeadClient）→ 規則版；分享、收回、再分享（同一個代碼）、公開頁、收回之後 404。**前半就寫好了**。
    - 封硯秋（黃巾）：買插畫、紀念印、親筆評曰兩張與重修列傳；前半用掉插畫、紀念印、第一張評曰、用規則版寫成（買了的評曰寫成固定句）；
      後半模型回了重寫、第二張評曰在寫成之後才用（QUOTE_LATER）、重寫次數用完被擋。
    - 葛臨川（官軍）：情誼高的三位人物白送評曰；前半只買了紀念印、傳還沒寫；後半模型回了才寫（正文＋三條 VerdictText）。
    - 邵玄度（散人）：插畫票不賣、按不到；規則版寫成。桓子衿（官軍）只有系統記的行狀（投靠、季末論功）：寫得成、立刻分享。紀懷素（新人，一則行狀都沒有）：
      讀不到、寫不了、分享不了。
    - 屈懷瑾（黃巾）：收季之後一直沒回來過，管理者開下一季之後才第一次同步（換季那一刻 _zhuan_past 補季末論功），再讀、寫、分享舊的一季。
    - 擠在一起的：同一篇已經在寫（ZHUAN_JOBS 有）就不再開；不存在的季；沒有登入。
    - 半舊半新：前半停在「休季、票買了用了一半、有人寫成了有人沒寫、有人分享出去了」，後半接著寫、重寫、換季。
    - 假人：BotRunner 兩個在休季與換季之後各跑幾輪（其中一個手上有紀念印的票，看它按不按 zhuan:seal；沒有行狀的假人沒有傳）。
    五種設定：none、weekend（列傳為終點關著：休季一顆灰鈕，傳照寫）、season21、week7、test（行狀關著：每一條都回「不能」）。"""

    RULE, MODEL_W, FREE, LONE, EMPTY, LAPSED = "岑書瀾", "封硯秋", "葛臨川", "邵玄度", "桓子衿", "屈懷瑾"
    PLAYERS = {RULE: "guan", MODEL_W: "huang", FREE: "guan", LONE: None, EMPTY: "guan", LAPSED: "huang"}
    NEWBIE = "紀懷素"
    BOT_SEATS = ["冊甲", "冊乙"]
    PHASES_FIRST = ["setup", "seed", "records", "close", "tickets", "first_writes", "pending", "half"]
    PHASES_SECOND = ["resume", "second_writes", "after_written", "pages", "bots", "roll", "old_season", "bots_again"]

    # ── 小工具 ──

    def edit_state(self, name: str, fn) -> None:
        with self.world.action_lock():
            state = self.chars.load(name)
            state.world = self.world.get_season()
            fn(state)
            self.chars.save(state)

    def figs(self) -> list[str]:
        have = [f for f in ZHUAN_FIGURES if f in self.c.characters]
        return have if len(have) == len(ZHUAN_FIGURES) else sorted(self.c.characters)[:3]

    @contextlib.contextmanager
    def inline(self):
        """server 的背景執行緒（write_zhuan 的 zhuan-<季>）當場跑完：不用另一條執行緒，回應裡的 writing 與寫完的內容就不是賽跑。"""
        real = self.server.threading

        class Inline:
            def __init__(self, target=None, name=None, daemon=None, **kw):
                self.target = target

            def start(self):
                self.target()

        class Shim:
            Thread = Inline

            def __getattr__(self, n):
                return getattr(real, n)

        self.server.threading = Shim()
        try:
            yield
        finally:
            self.server.threading = real

    def zwrite(self, who: str, body: dict, model: bool = False):
        """POST /api/zhuan/write（背景執行緒當場跑完、模型擋著或回了）。"""
        MODEL["zhuan"] = model
        try:
            with self.inline():
                return self.call(who, "POST", "/api/zhuan/write", body)
        finally:
            MODEL["zhuan"] = False

    def number(self, who: str) -> int:
        return self.chars.load(who).player.season_number

    def me(self, who: str, tag: str) -> None:
        from tianxia.characters import name_key
        from tianxia.wallet import Wallet

        state = self.chars.load(who)
        if state is None:
            emit(f"{who} {tag}（沒有這個人）", None)
            return
        p = state.player
        tier = self.world.get_season().final_tiers.get(who)
        emit(f"{who} {tag}", {
            "season": p.season_number, "loc": p.location, "faction": p.faction, "contrib": p.contrib, "seen": p.xingshi_seen,
            "annals": [[a.kind, a.text, a.weight, a.figure] for a in p.annals],
            "tickets": [[r.item, r.season, r.data, r.refunded] for r in Wallet(self.world.db).purchases(name_key(who))],
            "tier": None if tier is None else tier.model_dump(mode="json"),
            "journal": [[e.title, list(e.lines)[:3]] for e in state.journal[:3]], "jobs": sorted(self.server.ZHUAN_JOBS)})

    def zopts(self, who: str, tag: str) -> list[str]:
        """休季選單上 season: 與 zhuan: 開頭的幾顆（灰的也寫）。"""
        opts = self.options(who)
        got = [[i, o.get("label"), o.get("enabled")] for i, o in opts.items() if i.startswith(("zhuan:", "season:"))]
        emit(f"{who} {tag} 休季選單", got)
        return [i for i, _, on in got if i.startswith("zhuan:") and on]

    def options(self, who: str) -> dict:
        return self.ids(self.main(who))

    def write(self, who: str, tag: str, *, rewrite: bool = False, model: bool = False, season: int | None = None) -> None:
        """POST /api/zhuan/write（模型擋著或回了），再讀一次那一季。"""
        n = self.number(who) if season is None else season
        self.zwrite(who, {"season": n, "rewrite": rewrite}, model)
        self.call(who, "GET", f"/api/zhuan?season={n}")
        self.me(who, tag)

    def share(self, who: str, public: bool, tag: str, season: int | None = None) -> str | None:
        n = self.number(who) if season is None else season
        import secrets

        real = secrets.token_urlsafe
        secrets.token_urlsafe = lambda nbytes=None: f"zc{STEP[0] + 1:04d}"  # 分享代碼是 secrets.token_urlsafe(6)：隨機的，換成照步數的固定代碼
        try:
            code, view = self.call(who, "POST", "/api/zhuan/share", {"season": n, "public": public})
        finally:
            secrets.token_urlsafe = real
        url = view.get("url") if isinstance(view, dict) else None
        emit(f"{who} {tag} 分享網址", url)
        return url

    def page(self, tag: str, url: str | None) -> None:
        """公開頁（不用登入）：整頁的 sha256、長度與開頭。"""
        if not url:
            emit(f"頁面 {tag}", "沒有網址")
            return
        path = "/zhuan/" + url.rsplit("/zhuan/", 1)[-1]
        self.begin()
        r = self.TestClient(self.server.app).get(path)
        emit(f"頁面 {tag} {path}", {"status": r.status_code, "len": len(r.text), "sha": hashlib.sha256(r.text.encode("utf-8")).hexdigest(),
                                     "head": r.text[:160], "has": [k for k in ("評曰", "<img", "朱印", "og:image") if k in r.text]})

    # ── 前半 ──

    def seed(self) -> None:
        """每個人站到陣營的投靠點、記兩三則行狀、擺貢獻（收季時排名次）與跟人物的情誼（評曰的寫手）。桓子衿一則行狀都沒有。"""
        from tianxia.features.zhuan import standing as annals

        figs, sides = self.figs(), {f.id: f for f in self.c.scenario.factions}
        affinity = {self.MODEL_W: {figs[0]: 55, figs[1]: 45}, self.FREE: {figs[0]: 75, figs[1]: 72, figs[2]: 80},
                    self.LONE: {figs[0]: 50}, self.LAPSED: {figs[0]: 76}}
        for i, (who, side) in enumerate(self.PLAYERS.items()):
            f = sides.get(side) if side else None
            self.place(who, f.join_at[0] if f is not None and f.join_at else None, side)

            def fn(s, who=who, i=i):
                p = s.player
                if who != self.EMPTY:
                    annals.note(s, self.c, annals.DEED, f"{who}在城外守了一夜。", 3)
                    annals.note(s, self.c, annals.DEED, f"{who}替路過的商旅解了圍。", 2)
                p.contrib = 0 if who == self.EMPTY else 60 - 9 * i
                if who == self.LAPSED:
                    p.contrib = 60  # 到 min_contribution（40）以上才有階，換季補論功才走得到
                p.affinities.update(affinity.get(who, {}))
            self.edit_state(who, fn)
            self.me(who, "擺好行狀")
        # 〈天下形勢〉一篇寫到岑書瀾與屈懷瑾（同步時記一則；屈懷瑾要換季才補，走 xingshi_notes 的換季那一條）
        from tianxia.state import XingshiEssay

        names = f"{self.RULE}與{self.LAPSED}"
        self.world.mutate_season(lambda s: s.xingshi.append(XingshiEssay(key=1, time=1000, n=1, essay=f"潁川一帶，{names}連日奔走。", line="是日：兩軍相持。")))

    def records(self) -> None:
        """各包記一筆行狀（全部拆包第 29 批之二，annals 拆兩半）：打贏（交手）、差事辦成、人物立場、決戰（大戰）、約戰單挑、攻守、玉璽、痕跡、奇事各記一則
        （種類、份量、人物、保留的名號），〈天下形勢〉與季末論功是 seed／close 的同步記的；再各自先看一次狀態（annals_mark 有了才比得出變化）。
        看 /api/annals 的小標、時刻與排序、酒肆打聽得到的（heard）與文字工具。"""
        from tianxia.features.zhuan import standing as annals
        from tianxia.engine import Game

        figs = self.figs()
        for who in (self.RULE, self.FREE, self.MODEL_W):
            def fn(s, who=who):
                c = self.c
                other = self.MODEL_W if who != self.MODEL_W else self.RULE
                annals.note(s, c, annals.FIGHT, f"{who}在城門外打贏了{other}。", 4, keep=[other])
                annals.note(s, c, annals.ERRAND, f"替{figs[0]}跑了一趟腿，辦成了。", 3, figure=figs[0])
                annals.note(s, c, annals.STANCE, "他改做另一件事。", 2, figure=figs[1])
                big = annals.entry(s, c, annals.SHOWDOWN, f"{who}在決戰裡守住了一處關口。", 5, quote="死守", reply="好！", place="潁川", time=s.world.time)
                s.player.annals.append(big)
                annals.trim(s, c)
                annals.note(s, c, annals.DUEL, f"在渡口約戰{other}，險勝。", 3, keep=[other])
                annals.note(s, c, annals.CONQUER, "率先攻入一處城邑", 4, place="城外", time=s.world.time)
                annals.note(s, c, annals.SEAL, "起用了一片碎片。", 4)
                annals.note(s, c, annals.MARK, "這裡頭有你出的一分力。", 2)
                annals.note(s, c, annals.STORY, "一樁奇事收了尾。" * 3, 4)
                annals.note(s, c, annals.DEED, "", 3)  # 空句不記
                emit(f"{who} 行狀的分類", [[e.kind, annals.KINDS.get(e.kind), annals.GROUPS.get(e.kind), annals.heard(e)] for e in s.player.annals])
                Game(c, s, world=self.world)._log([])  # 先看一次：annals_mark 有了，下一次才比得出變化
                emit(f"{who} 先看了", {"mark": s.player.annals_mark, "n": len(s.player.annals)})
            self.edit_state(who, fn)
            self.call(who, "GET", "/api/annals")
            self.me(who, "各包記完")
        emit("文字工具", [annals.clip("甲\n乙  丙" * 30, 20), annals.first_sentence("你好嗎？我很好。" * 12)])

    def close(self) -> None:
        """管理者收季；除了屈懷瑾，每個人同步一次進休季（季末論功、〈天下形勢〉各記一則行狀）並看行狀頁。"""
        self.do(ADMIN, "end_season")
        emit("收季之後的名次", {k: v.model_dump(mode="json") for k, v in sorted(self.world.get_season().final_tiers.items())})
        for who in self.PLAYERS:
            if who == self.LAPSED:
                continue
            self.main(who)
            self.me(who, "收季之後")
            self.call(who, "GET", "/api/annals")

    def tickets(self) -> None:
        """商城買票（管理者補發元寶）、休季選單上的鈕、用掉一部分：封硯秋用插畫、紀念印、第一張親筆評曰；葛臨川蓋紀念印；邵玄度的插畫票不賣、按不到。"""
        buys = {self.MODEL_W: ["zhuan_art", "zhuan_seal", "zhuan_quote", "zhuan_quote", "rewrite_zhuan"], self.FREE: ["zhuan_seal", "zhuan_quote"],
                self.LONE: ["zhuan_art", "zhuan_seal"], self.EMPTY: ["zhuan_seal"], self.RULE: ["zhuan_seal"]}
        for n, (who, items) in enumerate(buys.items()):  # 編號只認英數字、底線、減號（其餘伺服器產隨機的）
            self.do(ADMIN, "mall_reissue", {"name": who, "amount": 1500, "note": "對照", "ref": f"zhuan-grant-{n}"})
            for k, item in enumerate(items):
                self.call(who, "POST", "/api/mall/buy", {"item": item, "ref": f"zhuan-buy-{n}-{k}"})
            self.me(who, "買完")
        for who in (self.MODEL_W, self.FREE, self.LONE, self.EMPTY, self.RULE):
            ids = self.zopts(who, "買完之後")
            if who == self.MODEL_W:
                for pick in ("zhuan:pick_art", "zhuan:seal", next((i for i in ids if i.startswith("zhuan:quote:")), "zhuan:quote:nope")):
                    self.choose(who, pick)
                self.choose(who, "zhuan:seal")  # 用過了
                self.choose(who, "zhuan:quote:nope")  # 不在選單上
            elif who in (self.FREE, self.EMPTY):
                self.choose(who, "zhuan:seal")
            elif who == self.LONE:
                self.choose(who, "zhuan:pick_art")
            self.zopts(who, "用完之後")
            self.me(who, "用完票")

    def first_writes(self) -> None:
        """前半寫成的（模型擋著，規則版）：岑書瀾（分享出去）、封硯秋（買的評曰寫成固定句）、邵玄度；先擋掉不合規矩的（沒寫過不能重寫、不存在的季、新人沒有傳）。"""
        n = self.number(self.RULE)
        self.zwrite(self.RULE, {"season": n, "rewrite": True})  # 還沒寫過，不能重寫
        self.zwrite(self.RULE, {"season": 99})
        self.call(self.RULE, "GET", "/api/zhuan?season=99")
        self.call(self.EMPTY, "GET", f"/api/zhuan?season={n}")
        self.zwrite(self.EMPTY, {"season": n})
        self.share(self.EMPTY, True, "寫成就分享")
        for path in (f"/api/zhuan?season={n}", "/api/annals"):  # 一則行狀都沒有的新人：讀不到、寫不了、分享不了
            self.call(self.NEWBIE, "GET", path)
        self.zwrite(self.NEWBIE, {"season": n})
        self.share(self.NEWBIE, True, "沒有傳")
        self.call(self.RULE, "GET", f"/api/zhuan?season={n}")
        self.write(self.RULE, "規則版寫成")
        self.zwrite(self.RULE, {"season": n})  # 寫過了，不能再「寫」
        url = self.share(self.RULE, True, "公開")
        self.page("岑書瀾 公開", url)
        self.write(self.MODEL_W, "規則版寫成（買了評曰）")
        self.write(self.LONE, "規則版寫成")
        self.main(self.RULE)
        self.main(self.MODEL_W)

    def pending(self) -> None:
        """半舊半新的切點：狀態變了（情誼跨格、等級；同伴不會記：建 Game 時 engine.py 的 _drop_stale_references 把隊伍收成名下的同伴〔roster 開著〕，edit_state 塞進去的那一位 watch 看不到）、annals_mark 還是舊的（edit_state 直接存，沒有走動作）——有 mark 還沒寫成行狀。
        前半停在這裡，後半第一件事（flush）才讓 watch 比出來。"""
        figs = self.figs()
        for who in (self.RULE, self.FREE):
            def fn(s, who=who):
                p = s.player
                p.affinities[figs[1]] = 95
                p.member.level += self.c.config.biography.level_every * 2
                if figs[2] not in p.team:
                    p.team.append(figs[2])
            self.edit_state(who, fn)
            s = self.chars.load(who)
            emit(f"{who} 變了還沒記", {"mark": s.player.annals_mark, "annals": len(s.player.annals), "level": s.player.member.level, "team": list(s.player.team)})

    def half(self) -> None:
        for who in self.PLAYERS:
            self.me(who, "前半停在這裡")

    # ── 後半 ──

    def resume(self) -> None:
        self.login_all()
        self.flush()  # 前半留下的變化先補記，再做別的（不然 main 的同步會先補）
        for who in self.PLAYERS:
            if who != self.LAPSED:
                self.main(who)
                self.zopts(who, "接手")

    def flush(self) -> None:
        """後半第一件事：同步比出前半留下的變化（情誼、等級各記一筆），看行狀頁。"""
        from tianxia.engine import Game

        for who in (self.RULE, self.FREE):
            def fn(s):
                Game(self.c, s, world=self.world)._log([])
            self.edit_state(who, fn)
            self.me(who, "補記之後")
            self.call(who, "GET", "/api/annals")

    def second_writes(self) -> None:
        """模型回了：葛臨川才寫（正文＋三條評曰）；封硯秋重寫（買了重修列傳，一季能重寫兩次）；岑書瀾重寫一次（模型擋著）；同一篇已經在寫就不再開。"""
        n = self.number(self.FREE)
        self.write(self.FREE, "模型回了寫成", model=True)
        self.write(self.MODEL_W, "模型回了重寫一", rewrite=True, model=True)
        self.write(self.RULE, "模型擋著重寫", rewrite=True)
        key = (self.LONE.casefold(), n)
        self.server.ZHUAN_JOBS[key] = 0.0  # 這一篇已經在寫
        try:
            self.zwrite(self.LONE, {"season": n, "rewrite": True})
            self.call(self.LONE, "GET", f"/api/zhuan?season={n}")
        finally:
            self.server.ZHUAN_JOBS.pop(key, None)

    def after_written(self) -> None:
        """封硯秋寫成之後才用第二張親筆評曰（QUOTE_LATER，要下一次重修才寫進去），再重寫兩次（第二次是買的那一張，第三次被擋）。"""
        who = self.MODEL_W
        ids = self.zopts(who, "寫成之後")
        pick = next((i for i in ids if i.startswith("zhuan:quote:")), None)
        if pick is not None:
            self.choose(who, pick)
        self.write(who, "模型回了重寫二", rewrite=True, model=True)
        self.write(who, "重寫次數用完", rewrite=True, model=True)
        self.zopts(who, "重寫之後")

    def pages(self) -> None:
        """分享：封硯秋（有插畫、紀念印）、葛臨川、屈懷瑾還沒寫（分享不了）；岑書瀾收回再分享（同一個代碼）、收回之後公開頁 404；不認得的代碼。"""
        for who in (self.MODEL_W, self.FREE):
            self.page(f"{who} 公開", self.share(who, True, "公開"))
        self.share(self.LAPSED, True, "還沒寫")
        self.share(self.RULE, False, "收回")
        self.page("岑書瀾 收回之後", "https://x/zhuan/" + (self.world.biography(self.number(self.RULE), self.RULE) or {}).get("share_code", "none"))
        self.page("岑書瀾 再公開", self.share(self.RULE, True, "再公開"))
        self.page("不認得的代碼", "https://x/zhuan/nope-nope")
        self.call(self.RULE, "GET", "/api/annals")
        client = self.TestClient(self.server.app)
        self.begin()
        r = client.get(f"/api/zhuan?season={self.number(self.RULE)}")
        emit("沒登入讀傳", [r.status_code, r.text[:120]])

    def bot_seats(self) -> None:
        """休季開著時加入的兩個假人（冊甲手上有紀念印的票）。"""
        from tianxia.features.zhuan import standing as annals
        from tianxia.characters import name_key
        from tianxia.engine import Game
        from tianxia.features.mall import actions as mall_actions
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
            p.contrib = 30 - 10 * i
            annals.note(g.state, self.c, annals.DEED, f"{name}在渡口守了半日。", 3)
            self.chars.save(g.state)
            if i == 0:
                Wallet(self.world.db).post(name_key(name), 500, "grant", "zhuan:bot", time=CLOCK[0])
                self.begin()
                g2 = Game(self.c, self.chars.load(name), world=self.world)
                g2.client = None
                emit(f"{name} 買紀念印", mall_actions.buy(g2, "zhuan_seal", "zhuan-bot-1"))
                self.chars.save(g2.state)

    def bot_rounds(self, tag: str, rounds: int) -> None:
        from collections import Counter

        from tianxia import server_bots
        from tianxia.bot_runner import BotRunner

        runner = BotRunner(self.c, self.world, self.chars, rng=random.Random(23), clock=lambda: CLOCK[0])
        tick, online = self.c.config.bot_tick_seconds, server_bots.is_online
        seeds = {91 + i for i in range(len(self.BOT_SEATS))}
        self.c.config.bot_tick_seconds = 10 ** 6
        server_bots.is_online = lambda profile, now: profile.seed in seeds or online(profile, now)
        totals = Counter()
        try:
            for _ in range(rounds):
                STEP[0] += 4
                self.begin()
                report = runner.tick()
                totals.update(acted=report.acted, added=report.added, skipped=report.skipped, failed=report.failed, online=report.online)
        finally:
            self.c.config.bot_tick_seconds, server_bots.is_online = tick, online
        emit(f"假人 {tag} 一輪一輪", dict(sorted(totals.items())))
        for name in self.BOT_SEATS:
            s = self.chars.load(name)
            p = s.player
            emit(f"假人 {name} {tag}", {"season": p.season_number, "annals": [[a.kind, a.text] for a in p.annals], "journal": [[e.title, list(e.lines)[:2]] for e in s.journal[:2]],
                                         "state": hashlib.sha256(s.model_dump_json().encode("utf-8")).hexdigest()})

    def bots(self) -> None:
        self.bot_seats()
        self.bot_rounds("休季", 4)

    def roll(self) -> None:
        """管理者開下一季：屈懷瑾這時才第一次同步（沒回來過，_zhuan_past 補季末論功再存行狀）；其他人第一次同步也是換季那一刻。"""
        self.old = self.world.get_season_number()
        self.do(ADMIN, "next_season")
        emit("換季之後的賽季", [self.world.get_season_number(), self.world.season_phase()])
        for who in [self.LAPSED, *(w for w in self.PLAYERS if w != self.LAPSED)]:
            self.main(who)
            self.me(who, "換季之後")
            self.call(who, "GET", "/api/annals")
            self.zopts(who, "換季之後")

    def old_season(self) -> None:
        """讀舊的一季（過去的季照存起來的行狀與身家）：屈懷瑾寫（模型回了，白送的評曰開單時照身家）、分享、公開頁；封硯秋、葛臨川的舊傳；新的一季不能寫。"""
        old = self.world.get_season_number() - 1
        for who in (self.MODEL_W, self.FREE, self.RULE, self.LONE, self.EMPTY):
            self.call(who, "GET", f"/api/zhuan?season={old}")
        self.write(self.LAPSED, "舊的一季寫成", model=True, season=old)
        self.page("屈懷瑾 公開", self.share(self.LAPSED, True, "公開", season=old))
        self.write(self.LAPSED, "舊的一季重寫", rewrite=True, season=old)
        self.write(self.EMPTY, "舊的一季沒有行狀", season=old)
        self.zwrite(self.RULE, {"season": old + 1})
        self.zwrite(self.RULE, {"season": old, "rewrite": True})

    def bots_again(self) -> None:
        self.bot_rounds("換季之後", 3)


# 改一個字（selftest）：蓋紀念印那一句（搬之前在 tianxia/zhuan_end.py、之後在 tianxia/features/zhuan/zhuan_end.py）
register_track("zhuan", ZhuanScenario, (("tianxia/features/zhuan/zhuan_end.py",),
                                        ('SEAL_DONE = "列傳末尾蓋上一方朱印：{seal}。"', 'SEAL_DONE = "列傳末尾蓋上一方朱印：{seal}！"')), "season21")
