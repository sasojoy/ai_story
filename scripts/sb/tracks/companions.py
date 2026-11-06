"""same_behavior 一軌一檔：companions（這一檔登記 companions）。"""
from __future__ import annotations

import contextlib
import hashlib
import os
import random
from pathlib import Path

from sb.base import Scenario
from sb.harness import ADMIN, CLOCK, MODEL, STEP, emit, register_track

# ═══════════════════════════ companions：人物情誼一軌（全部拆包第 19 批，dev/companions-1） ═══════════════════════════
# 同伴招募與名下、心意、託付與勸降、來信與委託、/api/figure 的本體從 engine.py 搬進新包 tianxia/features/companions/（stances、errands、letters
# 留成別名；心意的世界那一半進共用規則層 tianxia/stance_world.py；計畫 docs/superpowers/plans/2026-11-04-人物情誼包-第1批.md）。這一段整塊是這一批的：
# 接在檔尾、最後一行登記（register_track），PM 合的時候不跟別人的行穿插。新開的軌用原創名字（第 22 批 PM 認定第 3 條）。

COMPANIONS_TALK = "他沉吟了一會，點了點頭。"  # 假模型寫的對話那一輪
COMPANIONS_LETTER = "少俠台鑒：此事有勞，望勿推辭。"  # 假模型照他的口氣重寫的信
_COMPANIONS_CLIENTS: dict[type, type] = {}


def _companions_client(base: type) -> type:
    """人物對話、勸降、重寫書信的假模型（base 是 _setup_child 那一層換好的 client 類別）：MODEL["talk"] 給了（{stance}）時對話回一輪（心意開著
    那一種 schema 多填 stance）；MODEL["persuade"] 給了（0～100）時勸降回那個分數；MODEL["letter"] 給了時信回那一句。其餘照 base（丟連線錯誤）。"""
    if base not in _COMPANIONS_CLIENTS:
        class CompanionsClient(base):
            def chat_structured(self, messages, schema, *a, **k):
                fields = getattr(schema, "model_fields", {})
                if schema.__name__ == "PersuadeJudgment" and MODEL.get("persuade") is not None:
                    return schema(success_rate=MODEL["persuade"])
                if schema.__name__ == "LetterText" and MODEL.get("letter") is not None:
                    return schema(letter=MODEL["letter"])
                if "option_tags" in fields and MODEL.get("talk") is not None:
                    extra = {"stance": MODEL["talk"]["stance"]} if "stance" in fields else {}
                    return schema(narrative=COMPANIONS_TALK, options=["勸他速攻", "勸他持重", "告辭"],
                                  option_tags=["真誠請教", "坦誠相待", "尋常寒暄"], **extra)
                return super().chat_structured(messages, schema, *a, **k)

        _COMPANIONS_CLIENTS[base] = CompanionsClient
    return _COMPANIONS_CLIENTS[base]


class CompanionsScenario(Scenario):
    """人物情誼（全部拆包第 19 批；--track companions，自己一個資料庫）。
    顧行舟招募：沒到情誼門檻沒有鈕；到了按下去婉拒、要求決鬥（失敗的兩支）、招到（名下、隊伍）；名下滿了灰掉。白鷺汀是黃巾：只追隨官軍的灰掉、
    慢一步按到有主的人回「已經被某某招攬走了」。溫景明按招募之前全服記號還在（同步先減半、按招募那一下清記號，_recruit_one 的 _settle_partings）。
    測試內容走舊的 act:recruit（recruit_at；_recruit）。名下：修練頁的名冊與人物卡（release_view）、移出、加入、本人與部下那兩句、放回江湖、放不是自己的。
    魏長卿在籌備中按名冊（_not_while_preparing）。陶秋水在談盧植（假模型歸一個心意）：選選項記到一筆（貢獻、/api/figure 的 my_stance_today），同一天再說
    不再記；速戰差一筆到門檻（天下大事、江湖史，下一次同步記行狀 _stance_annals）；**前半停在還在談**。石望舒託付自然來（情誼夠、送信日第一順位）、走到地點；
    程遠山、秦照夜各開一件勸降，韋南星一件送信一件探營：**前半切在託付還開著、信還沒回、委託做到一半**。柳聽泉收求援（附委託，沒看過、沒婉拒）。
    後半：陶秋水選下一顆、告辭；石望舒交差（交信、探營、勸降照開到哪一種）；勸降走一遍拒絕（不在地點、沒寫字、太長、沒有這一件）、模型叫不動（什麼都不發生）、
    成了（痕跡、推線、獎勵、行狀、心意 +1）、敗了（打一場）；韋南星探營（花體力、卡留見聞）、婉拒那一封、過了期限作罷（情誼扣）；柳聽泉鎖外重寫信
    （server.letter_once）、收起、婉拒委託、道賀（figure_life.spread 記的 cheers）、邀宴、委託過期、09:00 看守替他送信（server._notice_keys → morning_mail）、
    敬過酒的宴不邀、宴客關著不邀；欠人物的事過了期限，那幾句併進「書信」（debts）。人物頁 /api/figure（有心意有託付、沒有、不認得、太長的 id）。假人（BotRunner；心意直接記一筆 voice_stance、測試內容按舊招募）；時鐘往前推（跨 00:00、
    跨週：daily 換手與持重拉進度、週初歸零）；換季。沒有陣營、沒有託付、沒有盧植的設定寫「沒有」略過，同一串 API 照打。"""

    RECRUITER, RIVAL, DRIFTER, PREP = "顧行舟", "白鷺汀", "溫景明", "魏長卿"
    TALKER, MAILER, RUNNER, ENVOY, LOSER, LAPSER = "陶秋水", "柳聽泉", "石望舒", "程遠山", "秦照夜", "韋南星"
    PLAYERS = {RECRUITER: "guan", RIVAL: "huang", DRIFTER: None, TALKER: "guan", MAILER: "guan", RUNNER: "guan", ENVOY: "guan", LOSER: "guan",
               LAPSER: "guan"}
    BOT_SEATS = ["情甲", "情乙", "情丙"]
    LUZHI = "luzhi"
    PHASES_FIRST = ["setup", "seat", "recruit", "named", "talk", "errands_open", "letters_open", "half"]
    PHASES_SECOND = ["resume", "talk_on", "errands_on", "persuade", "lapse", "letters_on", "debts", "figure_page", "bots", "clock", "season"]

    def __init__(self, root: Path, profile: str, db: Path):
        super().__init__(root, profile, db)
        from tianxia import ollama_client

        inner = ollama_client.OllamaClient.from_config.__func__  # _setup_child 換好的那一層（不連網路、大場面判讀）

        def from_config(cls, cfg):
            client = inner(cls, cfg)
            client.__class__ = _companions_client(type(client))
            return client

        ollama_client.OllamaClient.from_config = classmethod(from_config)

    # ── 小工具 ──

    def begin(self) -> None:
        """同酒肆那一軌：每個請求換一份空的勝算記憶（前半＋後半是兩個行程，選單上的勝算字才對得上）。"""
        super().begin()
        from tianxia import team

        self.server.ODDS_MEMO = team.OddsMemo()

    def everyone(self) -> list[str]:
        return list(self.PLAYERS)

    def edit_state(self, name: str, fn) -> None:
        with self.world.action_lock():
            state = self.chars.load(name)
            state.world = self.world.get_season()
            fn(state)
            self.chars.save(state)

    @contextlib.contextmanager
    def tuned(self, owner=None, **values):
        """這一下把設定改成這幾個值（同一個行程裡共用 CONTENT，出來要還原）。"""
        owner = self.c.config if owner is None else owner
        before = {k: getattr(owner, k) for k in values}
        for k, v in values.items():
            setattr(owner, k, v)
        emit("這一下的設定", {k: v for k, v in values.items()})
        try:
            yield
        finally:
            for k, v in before.items():
                setattr(owner, k, v)

    def on_errands(self) -> bool:
        from tianxia import errands

        return errands.on(self.c, self.world.get_season())

    def me(self, who: str, tag: str) -> None:
        """存檔裡這一包碰得到的那幾格：心意帳、託付、信、流水號、送信日、等著寫的道賀、隊伍、情誼（這幾位）、體力、貢獻、銀兩、心得，行狀與最新三則紀錄。"""
        state = self.chars.load(who)
        if state is None:
            emit(f"{who} {tag}（沒有這個人）", None)
            return
        p = state.player
        emit(f"{who} {tag}", {
            "stance_notes": {k: v.model_dump(mode="json") for k, v in sorted(p.stance_notes.items())},
            "errands": [e.model_dump(mode="json") for e in p.errands], "letters": [x.model_dump(mode="json") for x in p.letters],
            "letter_seq": p.letter_seq, "letter_day": p.letter_day, "cheers": list(p.cheers), "team": list(p.team),
            "affinities": dict(sorted(p.affinities.items())), "parted_done": list(p.parted_done), "stamina": p.stamina, "contrib": p.contrib,
            "silver": p.stats.get("silver", 0), "xinde": p.stats.get("xinde", 0), "annals": [[a.kind, a.text, a.figure] for a in p.annals],
            "pending_companion": p.pending_companion, "journal": [[e.title, e.tag, list(e.lines)] for e in state.journal[:3]]})

    def season_view(self, tag: str) -> None:
        """季上這一包碰得到的：心意的計數、此刻照著做的、週；名下（全服）；痕跡；最近的天下大事與江湖史。"""
        s = self.world.get_season()
        emit(f"季上 {tag}", {
            "counts": {k: dict(sorted(v.items())) for k, v in sorted(s.stance_counts.items())},
            "active": {k: v.model_dump(mode="json") for k, v in sorted(s.stance_active.items())}, "week": s.stance_week,
            "owners": {k: [v.owner, list(v.parted_from)] for k, v in sorted(self.world.companions().items()) if v.owner or v.parted_from},
            "marks": dict(sorted(s.marks.items())), "rumors": [r.text for r in s.rumors[-4:]], "chronicle": [r.text for r in s.chronicle[-3:]]})

    def buttons(self, who: str, prefix: str) -> list:
        view = self.main(who)
        return [o for i, o in self.ids(view).items() if i.startswith(prefix)]

    def beside(self, who: str, cid: str) -> None:
        """站到這位人物此刻在的地方（人物活起來的季他會走動）。"""
        from tianxia import figure_life

        loc = figure_life.where(GameStateHolder(self.world.get_season()), self.c, cid)
        emit(f"{cid} 此刻在", loc)
        self.place(who, loc)

    def errand_of(self, who: str, *status) -> object | None:
        state = self.chars.load(who)
        rows = [e for e in state.player.errands if not status or e.status in status]
        return rows[-1] if rows else None

    def give(self, who: str, fid: str, eid: str) -> None:
        """直接開一件（同 errands.offer 挑中之後那一下；Game.persuade 的測試也這樣開）。"""
        from tianxia import errands

        self.edit_state(who, lambda s: errands.give(s, self.c, fid, eid))
        self.me(who, f"開一件 {eid}")

    def press_errand(self, who: str, tag: str) -> None:
        """照身上那一件的種類按「此地」那一顆（交信、探營直接辦；勸降先叫出輸入框、再寫一句）。"""
        e = self.errand_of(who, "open")
        if e is None:
            emit(f"{who} {tag}：身上沒有還開著的託付", None)
            return
        self.place(who, e.target)
        verb = {"letter": "deliver", "scout": "scout", "persuade": "persuade"}[e.kind]
        emit(f"{who} {tag} 選單上那一顆", self.buttons(who, "errand:"))
        self.choose(who, f"errand:{verb}:{e.id}")
        if e.kind == "persuade":
            MODEL["persuade"] = 70
            self.do(who, "persuade_text", {"id": e.id, "text": "放下刀槍，回家種田吧"})
            MODEL["persuade"] = None
        self.me(who, f"{tag} 之後")

    # ── 前半 ──

    def setup(self) -> None:
        from tianxia.accounts import AccountStore
        from tianxia.engine import Game

        store = AccountStore(self.world.db)
        self.passwords[ADMIN] = "pw-admin-123456"
        with self.world.db.transaction():
            store.register(self.login_of(ADMIN), self.passwords[ADMIN])
            game = Game.new(self.c, ADMIN, world=self.world)
            self.chars.save(game.state)
            store.bind_character(self.login_of(ADMIN), ADMIN)
        self.clients[ADMIN] = self.TestClient(self.server.app)
        self.call(ADMIN, "POST", "/api/login", {"login": self.login_of(ADMIN), "password": self.passwords[ADMIN]})
        for who in [self.PREP, *self.PLAYERS]:
            self.clients[who] = self.TestClient(self.server.app)
            self.passwords[who] = "pw-" + self.login_of(who)
            self.call(who, "POST", "/api/register", {"login": self.login_of(who), "password": self.passwords[who],
                                                    "again": self.passwords[who]})
            self.call(who, "POST", "/api/character", {"name": who, "gender": "男"})
            if who == self.PREP:  # 籌備中（管理者還沒開季）：名冊那三顆只回一句（_not_while_preparing；測試內容自動開季，照常做）
                for op in ("join", "leave", "release"):
                    self.call(who, "POST", f"/api/menxia/{op}", {"person": "player"})
                self.do(ADMIN, "open_season")
        for who in self.PLAYERS:
            self.do(who, "skip_tutorial")
            self.settle_choices(who)

    def seat(self) -> None:
        factions = {f.id: f for f in self.c.scenario.factions}
        for who, side in self.PLAYERS.items():
            if side not in factions or not factions[side].join_at:
                continue
            if not self.place(who, factions[side].join_at[0]):
                continue
            self.choose(who, f"faction:{side}")
            self.choose(who, "faction:confirm")
            self.settle_choices(who)
        for who in self.PLAYERS:
            self.place(who, None)  # 體力補滿、過了新手期
            self.me(who, "站好")

    def recruit(self) -> None:
        """招募：見上。十五位那一套（正式內容）站涿郡、測試內容站 town（舊的 act:recruit）。"""
        who, rival, drifter = self.RECRUITER, self.RIVAL, self.DRIFTER
        if "liubei" not in self.c.characters:
            self.place(who, "town")
            self.main(who)
            emit("舊招募那一顆", self.buttons(who, "act:recruit"))
            with self.tuned(recruit_base_chance=-9.0, recruit_affinity_bonus=0.0, duel_chance_on_fail=0.0):
                self.choose(who, "act:recruit")
            with self.tuned(recruit_base_chance=-9.0, recruit_affinity_bonus=0.0, duel_chance_on_fail=1.0):
                self.choose(who, "act:recruit")
            with self.tuned(recruit_base_chance=9.0):
                for _ in range(4):
                    self.place(who, None)
                    self.choose(who, "act:recruit")
                    self.me(who, "舊招募按一次")
            self.place(rival, "cave")
            emit("此地沒有人招得了", self.choose(rival, "act:recruit"))
            self.season_view("舊招募之後")
            return
        self.beside(who, "guanyu")
        emit("還沒到情誼門檻", self.buttons(who, "act:recruit"))
        self.edit(who, lambda p: p.affinities.update({"liubei": 40, "guanyu": 40, "zhangfei": 40}))
        emit("到了情誼門檻", self.buttons(who, "act:recruit"))
        with self.tuned(recruit_base_chance=-9.0, recruit_affinity_bonus=0.0, duel_chance_on_fail=0.0):
            self.choose(who, "act:recruit:guanyu")
        self.me(who, "招募被婉拒")
        with self.tuned(recruit_base_chance=-9.0, recruit_affinity_bonus=0.0, duel_chance_on_fail=1.0):
            self.choose(who, "act:recruit:guanyu")
        self.me(who, "招募被要求決鬥")
        self.world.try_recruit("caocao", who, cap=3)
        self.world.try_recruit("yuanshao", who, cap=3)
        with self.tuned(recruit_base_chance=9.0):
            for _ in range(4):
                if self.world.get_companion("liubei").owner is not None:
                    break
                self.beside(who, "liubei")
                self.choose(who, "act:recruit:liubei")
        self.me(who, "招到一位")
        self.beside(who, "guanyu")
        emit("名下滿了", self.buttons(who, "act:recruit"))
        self.choose(who, "act:recruit:guanyu")
        self.beside(rival, "guanyu")
        self.edit(rival, lambda p: p.affinities.update({"liubei": 40, "guanyu": 40, "zhangfei": 40}))
        emit("黃巾看到的", self.buttons(rival, "act:recruit"))
        self.choose(rival, "act:recruit:guanyu")
        self.choose(rival, "act:recruit:liubei")  # 慢一步：有主了（Refused）
        self.beside(drifter, "xunyu")
        self.edit(drifter, lambda p: p.affinities.update({"xunyu": 90}))
        self.world.update_companion("xunyu", lambda pr: pr.parted_from.append(drifter))
        self.season_view("回江湖的記號")
        with self.tuned(recruit_base_chance=9.0):
            self.choose(drifter, "act:recruit:xunyu")  # 同步先減半、按下去那一下清記號
        self.me(drifter, "回江湖的人再招")
        self.season_view("招募之後")

    def named(self) -> None:
        """名下：修練頁的名冊與人物卡（放他回江湖那一句）、移出、加入、本人與部下那兩句、放回江湖、名冊裡沒有的人、放不是自己的。"""
        who = self.RECRUITER
        roster_rows = (self.call(who, "GET", "/api/menxia")[1] or {}).get("roster") or []
        keys = [r["key"] for r in roster_rows]
        emit("名冊", roster_rows)
        mate = next((k for k in keys if k != "player" and not k.startswith("follower:")), None)
        if mate is not None:
            emit("人物卡的放回江湖", (self.call(who, "GET", f"/api/menxia?person={mate}")[1] or {}).get("release"))
            self.call(who, "POST", "/api/menxia/leave", {"person": mate})
            self.call(who, "POST", "/api/menxia/join", {"person": mate})
        emit("本人那一列的放回江湖", (self.call(who, "GET", "/api/menxia?person=player")[1] or {}).get("release"))
        self.call(who, "POST", "/api/menxia/join", {"person": "player"})
        self.call(who, "POST", "/api/menxia/leave", {"person": "player"})
        self.call(who, "POST", "/api/menxia/release", {"person": "player"})
        self.call(who, "POST", "/api/menxia/join", {"person": "沒這個人"})
        if "follower_guan_spear" in self.c.followers:
            self.edit(who, lambda p: setattr(p, "followers", ["follower_guan_spear"]))
        self.call(who, "POST", "/api/menxia/join", {"person": "follower:0"})
        self.call(who, "POST", "/api/menxia/leave", {"person": "follower:0"})
        self.edit(who, lambda p: setattr(p, "followers", []))
        if mate is not None:
            self.call(who, "POST", "/api/menxia/release", {"person": mate})
            self.me(who, "放回江湖之後")
            self.main(who)
            self.call(self.RIVAL, "POST", "/api/menxia/release", {"person": mate})  # 不在他的名冊上
        self.season_view("名下之後")

    def talk(self) -> None:
        """人物心意：陶秋水在跟盧植談（直接擺成上一輪給了選項；tests/kit/stances_kit.talking 同一個擺法）。速戰差一筆到門檻，選第一顆、模型歸速戰：記一筆
        （貢獻、過門檻：天下大事、江湖史；/api/figure 的 my_stance_today），下一次同步記行狀；再自己說一句：今天記過了不再記。前半停在還在談。"""
        who = self.TALKER
        if self.LUZHI not in self.c.characters:
            emit("這份內容沒有盧植", None)
            return
        self.place(who, "luzhi_camp")
        def talking(p) -> None:
            p.pending_companion = self.LUZHI
            p.last_offered_dialogue[self.LUZHI] = [["勸他趁黃巾未穩速攻廣宗", "告辭"], ["真誠請教", "尋常寒暄"]]
            p.affinities.setdefault(self.LUZHI, 20)

        self.edit(who, talking)
        view = self.main(who)
        emit("談話中的人物頁（main.figure）", view.get("figure") if isinstance(view, dict) else None)

        def nearly(s) -> None:  # 速戰差一筆到門檻（下面這一下就過門檻：天下大事、江湖史；下一次同步記行狀）
            from tianxia import stances

            if stances.on(self.c, s):
                s.stance_week, s.stance_counts = stances.week_of(self.c, s), {self.LUZHI: {"suzhan": 29}}

        self.world.mutate_season(nearly)
        MODEL["talk"] = {"stance": "suzhan"}
        self.choose(who, "talk:0")
        self.me(who, "記到一筆")
        self.season_view("過門檻")
        self.call(who, "GET", f"/api/figure?id={self.LUZHI}")
        self.main(who)  # 下一次同步：這一週勸過的心意到了門檻，記一則行狀（_stance_annals）
        self.me(who, "行狀")
        MODEL["talk"] = {"stance": "chizhong"}
        self.call(who, "POST", "/api/say", {"text": "不如持重些"})  # 今天記過了：不再記、不再給貢獻
        self.me(who, "同一天再說一句")
        MODEL["talk"] = None

    def errands_open(self) -> None:
        """託付：石望舒情誼夠、人物自然來信（送信日第一順位）；程遠山、秦照夜各開一件勸降，韋南星一件送信、一件探營。都不辦（切在這裡）。"""
        if not self.on_errands():
            emit("這一季沒有託付", None)
            self.edit(self.RUNNER, lambda p: p.affinities.update({self.LUZHI: 50}) if self.LUZHI in self.c.characters else None)
            self.main(self.RUNNER)
            self.me(self.RUNNER, "關著的季")
            return
        self.edit(self.RUNNER, lambda p: p.affinities.update({self.LUZHI: 50}))
        view = self.main(self.RUNNER)
        emit("託付的信（main.letter、main.errands）", [view.get("letter"), view.get("errands")])
        self.me(self.RUNNER, "託付來了")
        for who in (self.ENVOY, self.LOSER):
            self.edit(who, lambda p: p.affinities.update({self.LUZHI: 50}))
            self.give(who, self.LUZHI, "luzhi_persuade")
        self.edit(self.LAPSER, lambda p: p.affinities.update({self.LUZHI: 50, "huangfusong": 50}))
        self.give(self.LAPSER, self.LUZHI, "luzhi_scout")
        self.give(self.LAPSER, "huangfusong", "huangfu_letter")
        emit("不在地點：選單上沒有那一顆", self.buttons(self.ENVOY, "errand:"))
        self.call(self.ENVOY, "GET", f"/api/figure?id={self.LUZHI}")

    def letters_open(self) -> None:
        """書信：柳聽泉情誼夠的人物焦慮（聲威不到開季的一半），寫求援、附一件委託；信還沒看、委託還沒婉拒（切在這裡）。"""
        from tianxia import figures, letters

        who = self.MAILER
        if not letters.on(self.c) or "qinjie" not in self.c.characters:
            emit("這一季沒有書信", self.main(who).get("letter"))
            return
        self.world.mutate_season(lambda s: setattr(figures._ensure(GameStateHolder(s), self.c, "qinjie"), "prestige", 1))
        self.edit(who, lambda p: p.affinities.update({"qinjie": 40}))
        view = self.main(who)
        emit("求援的信（main.letter）", view.get("letter"))
        self.me(who, "求援來了")

    def half(self) -> None:
        for who in self.everyone():
            self.me(who, "前半停在這裡")
        self.season_view("前半停在這裡")

    # ── 後半 ──

    def resume(self) -> None:
        self.login_all()

    def talk_on(self) -> None:
        """還在談：選下一顆（今天記過了）、告辭。"""
        who = self.TALKER
        if self.LUZHI not in self.c.characters:
            emit("這份內容沒有盧植", None)
            return
        MODEL["talk"] = {"stance": "xumin"}
        view = self.choose(who, "talk:1")
        self.me(who, "接著談")
        MODEL["talk"] = None
        opts = self.ids(view)
        emit("談話的選單", sorted(opts))
        self.choose(who, "talk:leave")
        self.me(who, "告辭")

    def errands_on(self) -> None:
        """石望舒照身上那一件的種類交差（半舊半新：舊程式開的、新程式辦完）。"""
        self.press_errand(self.RUNNER, "交差")
        self.choose(self.RUNNER, "errand:deliver:e999")
        if self.on_errands():  # 交信：走到就交（道謝信不佔一天一封、情誼照寫的數字給、貢獻、心意 +1、行狀）
            self.give(self.RUNNER, self.LUZHI, "luzhi_letter")
            self.press_errand(self.RUNNER, "交信")
        self.season_view("交差之後")

    def persuade(self) -> None:
        """勸降：拒絕的路、模型叫不動（什麼都不發生）、成了、敗了（打一場）。"""
        if not self.on_errands():
            emit("這一季沒有託付", None)
            self.do(self.ENVOY, "persuade_text", {"id": "e1", "text": "放下刀槍"})
            return
        who = self.ENVOY
        e = self.errand_of(who, "open")
        self.do(who, "persuade_text", {"id": e.id, "text": "放下刀槍"})  # 還不在地點
        self.place(who, e.target)
        emit("勸降那一顆", self.buttons(who, "errand:"))
        self.choose(who, f"errand:persuade:{e.id}")  # 只叫出輸入框：不寫紀錄
        self.me(who, "叫出輸入框")
        self.do(who, "persuade_text", {"id": e.id, "text": ""})
        self.do(who, "persuade_text", {"id": e.id, "text": "放" * 30})
        self.do(who, "persuade_text", {"id": "e999", "text": "放下刀槍"})
        MODEL["persuade"] = None
        self.do(who, "persuade_text", {"id": e.id, "text": "放下刀槍"})  # 模型叫不動
        self.me(who, "模型叫不動")
        jf = self.c.config.jianfa
        with self.tuned(jf, persuade_floor=100, persuade_cap=100):
            MODEL["persuade"] = 70
            self.do(who, "persuade_text", {"id": e.id, "text": "放下刀槍，回家種田吧"})
        self.me(who, "勸成了")
        self.season_view("勸成了")
        loser = self.LOSER
        e = self.errand_of(loser, "open")
        self.place(loser, e.target)
        with self.tuned(jf, persuade_floor=0, persuade_cap=0):
            self.do(loser, "persuade_text", {"id": e.id, "text": "放下刀槍，回家種田吧"})
        MODEL["persuade"] = None
        self.me(loser, "勸不成、打一場")
        self.choose(loser, f"errand:persuade:{e.id}")  # 那一件沒了

    def lapse(self) -> None:
        """韋南星：探營（花體力、卡留在見聞）；另一封婉拒；再開一件過了期限作罷（情誼扣）。"""
        who = self.LAPSER
        if not self.on_errands():
            emit("這一季沒有託付", None)
            self.do(who, "letter_decline", {"id": -1})
            return
        scout = next(e for e in self.chars.load(who).player.errands if e.errand == "luzhi_scout")
        self.place(who, scout.target)
        emit("探營那一顆", self.buttons(who, "errand:"))
        self.choose(who, f"errand:scout:{scout.id}")
        self.me(who, "探營之後")
        emit("見聞裡那張卡", [r.text for r in self.world.get_season().rumors if r.layer == "personal" and r.character == who])
        letter = next(e for e in self.chars.load(who).player.errands if e.errand == "huangfu_letter")
        self.do(who, "letter_decline", {"id": letter.letter})
        self.me(who, "婉拒之後")
        self.do(who, "letter_decline", {"id": letter.letter})  # 第二次：沒有這封信可婉拒
        self.do(who, "letter_decline", {"id": -1})
        self.give(who, "bocai", "bocai_letter")

        def expire(s) -> None:
            s.player.errands[-1].expires = s.world.time - 1

        self.edit_state(who, expire)
        self.main(who)  # 同步：過了期限作罷，情誼扣
        self.me(who, "過了期限")

    def letters_on(self) -> None:
        """柳聽泉：鎖外重寫信（server.letter_once，假模型）、收起、婉拒委託、委託過期；道賀（figure_life.spread 記 cheers）、邀宴；09:00 的看守替他送信；
        敬過酒的宴不邀、宴客關著不邀（審查 M04：之前沒有人敬過酒，這兩個判斷沒有人走到）。"""
        from tianxia import figure_life, letters
        from tianxia.state import Feast, Toast

        who = self.MAILER
        if not letters.on(self.c) or "qinjie" not in self.c.characters:
            emit("這一季沒有書信", self.do(who, "letter_read", {"id": -1}))
            return
        self.main(who)
        game = self.server.game_for(who)
        MODEL["letter"] = COMPANIONS_LETTER
        self.begin()
        emit("鎖外重寫", self.server.letter_once(game))
        MODEL["letter"] = None
        self.begin()
        emit("再寫一次（寫過了）", self.server.letter_once(game))
        self.me(who, "重寫之後")
        self.server.GAMES.clear()
        view = self.main(who)
        card = view.get("letter") if isinstance(view, dict) else None
        emit("小卡", card)
        if card is not None:
            self.do(who, "letter_decline", {"id": card["id"]})
            self.do(who, "letter_read", {"id": card["id"]})
        self.do(who, "letter_read", {"id": -1})  # 沒有這封信
        self.me(who, "收起信")

        def cheers(s) -> None:  # 他欣賞你做的事（figure_life.spread 讓情誼往上動、情誼到 letter_affinity：記著等寫道賀）
            s.player.location = self.c.figures["zhangmancheng"].location
            s.player.affinities["qinjie"] = 45
            emit("風聞", figure_life.spread(s, self.c, "beat", "zhangmancheng", at=s.player.location, side="huang",
                                           text="在宛城打退了張曼成"))
            s.player.letter_day = -1

        self.edit_state(who, cheers)
        self.me(who, "記下道賀")
        self.main(who)
        self.me(who, "道賀的信")

        def feast(s) -> None:
            s.feast_seq += 1
            s.feasts.append(Feast(id=s.feast_seq, host="xushao", place="yingchuan", start=s.time, end=s.time + 2 * 3600))

        self.world.mutate_season(feast)
        self.edit(who, lambda p: (p.affinities.update({"xushao": 40}), setattr(p, "letter_day", -1)))
        self.main(who)
        self.me(who, "邀宴的信")
        self.edit(who, lambda p: setattr(p, "letter_day", -1))
        self.begin()
        game = self.server.game_for(who)
        with self.server._locked(game):
            notes, busy = self.server._notice_keys(game, self.login_of(who), CLOCK[0])
        emit("09:00 的看守", [[n.key for n in notes], busy])
        self.me(who, "看守之後")

        def expire(s) -> None:
            for letter in s.player.letters:
                if letter.task is not None and not letter.lapsed:
                    letter.task.expires = s.world.time - 1

        self.edit_state(who, expire)
        self.main(who)
        self.me(who, "委託過期")

        def toasted_feast(s) -> None:  # 再擺一場、你已經敬過酒：不邀；拿掉那一杯，宴客關著也不邀，開著才邀（_feast_letter 那兩個判斷，第 19 批改寫成 figure_life.feast_invites）
            s.feast_seq += 1
            s.feasts.append(Feast(id=s.feast_seq, host="xushao", place="yingchuan", start=s.time, end=s.time + 2 * 3600,
                                  toasts=[Toast(name=who, text="敬主人一杯", score=40, at=s.time)]))

        def no_toasts(s) -> None:
            for f in s.feasts:
                f.toasts.clear()

        self.world.mutate_season(toasted_feast)
        self.edit(who, lambda p: setattr(p, "letter_day", -1))
        self.main(who)
        self.me(who, "敬過酒的宴不邀")
        self.world.mutate_season(no_toasts)
        self.edit(who, lambda p: setattr(p, "letter_day", -1))
        with self.tuned(self.c.config.figure_life, feasts=False):
            self.main(who)
            self.me(who, "宴客關著不邀")
        self.edit(who, lambda p: setattr(p, "letter_day", -1))
        self.main(who)
        self.me(who, "拿掉那一杯才邀")

    def debts(self) -> None:
        """欠人物的事過了期限（ParleyDebt；parley.lapse，第 20 批搬）：同步時那幾句併進「書信」那一則（Game.sync 的 mail → deliver_mail，第 19 批改成帶出入參數的委派；審查 M14）。"""
        from tianxia.state import ParleyDebt

        who = self.MAILER
        cid = "qinjie" if "qinjie" in self.c.characters else next(iter(self.c.characters))

        def owed(s) -> None:
            s.player.parley_debts[cid] = ParleyDebt(kind="owe", condition="silver", due=s.world.time - 1)

        self.edit_state(who, owed)
        self.main(who)
        self.me(who, "欠他的事過了期限")

    def figure_page(self) -> None:
        """人物頁：有心意有託付的、沒有的、不認得的、太長的、沒帶 id。"""
        for who in (self.RUNNER, self.DRIFTER):
            for cid in (self.LUZHI, "bocai", "huangfusong", "zhangjiao", "nosuch", "x" * 80):
                self.call(who, "GET", f"/api/figure?id={cid}")
            self.call(who, "GET", "/api/figure")

    def clock(self) -> None:
        """時鐘往前推：跨 00:00（daily：換手、持重每天拉下對面的進度）、跨週（週初歸零）。先把心意擺成速戰在做事、持重票數追過，跨 00:00 換手，
        盧植那條線上自家佔著的地方擺一條對面的進度，持重拉得下來；痕跡的倍數、人物開的事件（碰過一次 met 今天不再抽到）、推線的倍數都讀世界那一半。"""
        from tianxia import conquest, figures, stances

        season = self.world.get_season()
        if not stances.on(self.c, season):
            emit("這一季沒有心意", stances.push_scale(GameStateHolder(season), self.c, self.LUZHI))
            STEP[0] += 1500
            self.main(self.TALKER)
            self.season_view("跨天")
            return
        from tianxia.state import StanceOn

        def preset(s) -> None:
            s.stance_week = stances.week_of(self.c, s)
            s.stance_counts = {self.LUZHI: {"chizhong": 50, "suzhan": 31}}
            s.stance_active = {self.LUZHI: StanceOn(stance="suzhan", at=s.time, week=s.stance_week)}

        self.world.mutate_season(preset)
        self.season_view("跨天之前")
        holder = GameStateHolder(self.world.get_season())
        emit("世界那一半讀到的", {"active": stances.active(holder, self.c, self.LUZHI).id, "push": stances.push_scale(holder, self.c, self.LUZHI),
                               "mark": stances.mark_scale(holder, self.c, "xiaquyang:band_turned"),
                               "closed": sorted(stances.closed_events(GameStateFor(self.chars.load(self.TALKER), holder.world), self.c))})

        def met(s) -> None:
            stances.met(s, self.c, "stance_luzhi_assault")
            emit("碰過那一則", sorted(stances.closed_events(s, self.c)))

        self.edit_state(self.TALKER, met)
        guarded = None
        if conquest.on(self.c, holder.world):
            fig = figures.state_of(holder, self.c, self.LUZHI)
            side = self.c.figures[self.LUZHI].faction
            guarded = next((loc for loc in conquest.blocks(self.c) if conquest.line_of(holder.world, self.c, loc) == fig.front
                            and conquest.holder(holder.world, self.c, loc) == side), None)
        if guarded is not None:
            self.preset_bar(guarded, "huang", 40.0, self.RIVAL)
        STEP[0] += 1500
        self.main(self.TALKER)
        self.season_view("跨了一天")
        if guarded is not None:
            emit("持重拉下對面的進度", [guarded, conquest.bars(self.world.get_season(), guarded)])
        STEP[0] += 60 * 24 * 8
        self.main(self.TALKER)
        self.season_view("跨了一週")
        self.me(self.TALKER, "跨了一週")

    def bots(self) -> None:
        """假人：BotRunner 十輪（正式內容的假人每天照名號雜湊直接記一筆心意 voice_stance：機會調成 1；測試內容沒有陣營，伺服器假人不出手）。
        整季機器人（bot.pick）站在託付的地點也不按 errand:（永遠按得下去的前綴），測試內容站 town 照挑舊的招募（act:recruit）。"""
        from collections import Counter

        from tianxia import bot, errands, server_bots
        from tianxia.bot_runner import BotRunner
        from tianxia.engine import Game
        from tianxia.state import BotProfile

        sides = [f.id for f in self.c.scenario.factions]
        start = "luzhi_camp" if "luzhi_camp" in self.c.locations else "town"
        for i, name in enumerate(self.BOT_SEATS):
            self.begin()
            g = Game.new(self.c, name, rng=random.Random(i), world=self.world, graduated=True)
            p = g.state.player
            p.bot = BotProfile(personality="普通", seed=71 + i, faction=sides[i % 2] if sides else None,
                               season_number=self.world.get_season_number())
            g.client = None
            g.sync(CLOCK[0])
            for _ in range(6):
                first = next((o.id for o in g.options(odds=False) if o.id.startswith("choice:") and o.enabled), None)
                if first is None:
                    break
                g.choose(first)
            p.faction, p.location, p.journey = p.bot.faction, start, None
            p.visited.add(start)
            p.tutorial_step = len(self.c.tutorial.steps)
            p.joined_at = -1.0e9
            self.chars.save(g.state)
        emit("假人開工時的賽季", self.world.season_phase())
        runner = BotRunner(self.c, self.world, self.chars, rng=random.Random(17), clock=lambda: CLOCK[0])
        tick, online = self.c.config.bot_tick_seconds, server_bots.is_online
        seeds = {71 + i for i in range(len(self.BOT_SEATS))}
        self.c.config.bot_tick_seconds = 10 ** 6
        server_bots.is_online = lambda profile, now: profile.seed in seeds or online(profile, now)
        totals = Counter()
        try:
            with self.tuned(self.c.config.jianfa, bot_stance_chance=1.0):
                for _ in range(int(os.environ.get("SB_COMPANIONS_TICKS", "10"))):
                    STEP[0] += 4
                    self.begin()
                    report = runner.tick()
                    totals.update(acted=report.acted, added=report.added, skipped=report.skipped, failed=report.failed, online=report.online)
        finally:
            self.c.config.bot_tick_seconds, server_bots.is_online = tick, online
        emit("情誼假人 一輪一輪", dict(sorted(totals.items())))
        self.season_view("假人之後")
        for name in self.BOT_SEATS:
            s = self.chars.load(name)
            p = s.player
            emit(f"情誼假人 {name}", {"notes": {k: v.model_dump(mode="json") for k, v in sorted(p.stance_notes.items())}, "contrib": p.contrib,
                                     "errands": len(p.errands), "letters": len(p.letters), "team": list(p.team),
                                     "state": hashlib.sha256(s.model_dump_json().encode("utf-8")).hexdigest()})
        self.begin()
        solo = Game.new(self.c, "情丁", rng=random.Random(5), world=self.world, graduated=True)
        solo.client = None
        solo.sync(CLOCK[0])
        for _ in range(6):
            first = next((o.id for o in solo.options(odds=False) if o.id.startswith("choice:") and o.enabled), None)
            if first is None:
                break
            solo.choose(first)
        p = solo.state.player
        p.tutorial_step = len(self.c.tutorial.steps)
        if self.on_errands():
            errands.give(solo.state, self.c, self.LUZHI, "luzhi_letter")
            p.location = p.errands[-1].target
        else:
            p.location = "lake" if "lake" in self.c.locations else start  # 測試內容的 town 前半都被招走了
        p.journey = None
        opts = solo.options(odds=False)
        emit("整季機器人眼前的選單", [o.id for o in opts])
        emit("整季機器人挑的", sorted({str(bot.pick(solo, opts, random.Random(k))) for k in range(40)}))
        rng = random.Random(9)
        for _ in range(12):
            picked = bot.pick(solo, solo.options(odds=False), rng)
            if picked is None or picked == "act:on_road":
                break
            solo.choose(picked)
            emit("整季機器人按了", [picked, [e.title for e in solo.state.journal[:1]], list(p.team)])

    def season(self) -> None:
        """收季、開下一季：託付、信、心意帳換季清掉；名下照全服的放掉。看守（morning_mail）：柳聽泉還停在上一季、情誼夠、等著寫道賀。看守那條路進鎖就換了季
        （server._locked → _reload → _reconcile_season：身上的信與道賀都清了），季數那道檢查走不到；所以再拿資料庫裡原樣的那一列直接問一次：拿掉檢查就真的會送
        （審查 M07；morning_mail 開著的 season21、week7，其餘的設定送信日是 None、本來就不送）。"""
        self.do(ADMIN, "end_season")
        self.main(self.RECRUITER)
        self.do(ADMIN, "next_season")
        if "qinjie" in self.c.characters:
            self.edit(self.MAILER, lambda p: (p.affinities.update({"qinjie": 45}), setattr(p, "cheers", ["qinjie|在潁川打退了黃巾"]),
                                              setattr(p, "letter_day", -1)))
        self.begin()
        game = self.server.game_for(self.MAILER)
        with self.server._locked(game):
            emit("看守那條路（進鎖已換季）", [game.morning_mail(CLOCK[0]), len(game.state.player.letters), list(game.state.player.cheers)])
            game.state = self.chars.load(self.MAILER)
            emit("還停在上一季的人", [game.morning_mail(CLOCK[0]), len(game.state.player.letters), list(game.state.player.cheers)])
        for who in self.everyone():
            self.main(who)
            self.me(who, "換季之後")
        self.season_view("換季之後")


class GameStateHolder:
    """世界那一半的函式只讀 state.world：季上直接問時（不是誰的存檔）的最小一份。"""

    def __init__(self, world):
        self.world = world


class GameStateFor:
    """同上，closed_events 另外讀 state.player（這個人今天碰過那一則沒）。"""

    def __init__(self, state, world):
        self.player, self.world = state.player, world


# 改一個字（selftest）：託付辦成了那一句（errands.DONE；搬之前在 tianxia/errands.py、之後在包裡）
register_track("companions", CompanionsScenario, (("tianxia/features/companions/errands.py", "tianxia/errands.py"),
                                                  ('DONE = "{who}託你的事辦成了。"', 'DONE = "{who}託你的事辦成了！"')), "week7")
