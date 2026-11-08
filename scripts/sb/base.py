"""same_behavior 的 Scenario、DuelScenario 與它們的假人：其他軌都從這裡繼承（第二輪第 70 批）。"""
from __future__ import annotations

import contextlib
import hashlib
import json
import os
import random
import time
from pathlib import Path

from sb import harness
from sb.harness import (
    ADMIN, BUF, CLOCK, CLOCK0, MODEL, STEP, STEP_SECONDS, _fake_monotonic, _setup_child, db_text, emit, register_bots, register_track,
)

BOT_PROFILES = ("week7",)
DUEL_BOT_PROFILES = ("season21", "week7")  # 約戰的假人（推現實時鐘的整季機器人、BotRunner 兩軍各 4 個）：約戰開著的兩種
DUEL_PROFILES = ("season21", "week7")  # 減法季開著、出陣換成約戰的季：先照原樣（約戰）走一段，攻守混戰那幾段把約戰關掉走


# ═══════════════════════════ 子行程：TestClient 情境 ═══════════════════════════


@contextlib.contextmanager
def _three_way_off(cfg):
    """探索三選一（develop 還有，主幹第 13 批拿掉）：情境在記憶體裡關掉探索一顆（jianfa.explore_one、jianfa.enabled）的那幾下，develop 根的 act:explore
    會開三選一，主幹是舊探索。這幾下兩邊都走舊探索才比得起來：develop 關 explore_modes，主幹關它以前連帶關掉的那三樣（同 BoutScenario.explore_modes_off）。"""
    rows = [(cfg.explore_modes, "enabled", False)] if hasattr(cfg, "explore_modes") else []
    if hasattr(cfg, "event_trend_share"):
        rows += [(cfg, "precise_actions", False), (cfg, "event_trend_share", 1.0), (cfg, "sense_treasure_points", 0)]
    saved = [(owner, key, getattr(owner, key)) for owner, key, _ in rows]
    for owner, key, value in rows:
        setattr(owner, key, value)
    try:
        yield
    finally:
        for owner, key, value in saved:
            setattr(owner, key, value)


class Scenario:
    """一種設定的整段情境。每一段（PHASES 的一個名字）是一個方法；段落結束寫資料庫的雜湊，最後寫整份資料庫。"""

    def __init__(self, root: Path, profile: str, db: Path):
        self.root, self.profile, self.db = root, profile, db
        import server

        server._monotonic = _fake_monotonic  # 斷路器與模型預算的時鐘（server 每次叫都讀模組層的 _monotonic）
        # 審查 S-10（develop 6d926c17 起）：同一個來源 IP 一小時最多註冊 5 個帳號；TestClient 全是同一個來源，不放開的話第 6 個人起註冊不了
        server.REGISTER_LIMIT = 10 ** 6
        if profile == "test":
            from tianxia.content import load_content

            server.CONTENT = load_content(root / "tests" / "fixtures" / "content")
        self.server = server
        self.c = server.CONTENT
        from fastapi.testclient import TestClient

        from tianxia.characters import CharacterStore
        from tianxia.sqlite_world import open_world

        self.TestClient = TestClient
        self.world = open_world()
        self.chars = CharacterStore(self.world.db)
        self.clients: dict[str, object] = {}
        self.passwords: dict[str, str] = {}
        self.duel_default = self.c.config.jianfa.sortie_duel if hasattr(self.c.config, "jianfa") else None
        self.big_default = self.c.config.big_fight_difficulty

    # ── 打 API ──

    def begin(self) -> None:
        STEP[0] += 1
        CLOCK[0] = CLOCK0 + STEP[0] * STEP_SECONDS
        random.seed(STEP[0])
        self.server.GAMES.clear()  # 每個請求重建 Game（rng 只看資料庫與這一步）

    auto_prep = True  # 開季準備卡出現時自己按掉（clear_prep）；自己走那張卡的軌（growth、legacy）關掉

    def request(self, who: str, method: str, url: str, body: dict | None = None):
        self.begin()
        client = self.clients[who]
        r = client.post(url, json=body if body is not None else {}) if method == "POST" else client.get(url)
        try:
            data = r.json()
        except Exception:  # noqa: BLE001
            data = r.text[:300]
        emit(f"{who} {method} {url} {json.dumps(body, ensure_ascii=False) if body else ''} {r.status_code}", data)
        return r.status_code, data

    def call(self, who: str, method: str, url: str, body: dict | None = None):
        harness.IN_CALL[0] += 1  # 第 107 批：切點（前半寫完、快照）要不在請求中間，run 斷言是 0
        try:
            return self._call(who, method, url, body)
        finally:
            harness.IN_CALL[0] -= 1

    def _call(self, who: str, method: str, url: str, body: dict | None = None):
        status, data = self.request(who, method, url, body)
        if not self.auto_prep or self.prep_of(data) is None or {"season:preparing", "season:resting"} & set(self.ids(data)):
            return status, data  # 籌備中、休季也寫著 main.prep，但選單不是那張卡（挑配比在籌備中只回一句）：開季之後的第一下才按
        fresh = self.clear_prep(who, data)
        chose = body.get("id", "") if isinstance(body, dict) and url == "/api/choose" else ""
        if (method == "GET" and url == "/api/main") or (chose and not chose.startswith(("growth:", "legacy:"))):
            return self.request(who, method, url, body)  # 卡接管選單時那一下沒按到（或讀到的是卡）：清掉之後照原本要做的再做一次
        return status, {**data, "main": fresh["main"]} if isinstance(data, dict) and "main" in data else data

    @staticmethod
    def prep_of(data):
        """回應裡的開季準備卡（main.prep；五項屬性的季、傳承才有，沒有這兩樣的根永遠是 None）。"""
        main = data.get("main", data) if isinstance(data, dict) else None
        return main.get("prep") if isinstance(main, dict) else None

    def clear_prep(self, who: str, data) -> dict:
        """按掉開季準備卡（合回 develop 第 0 段）：卡接管整個選單，不按的話之後每一步都被擋、兩邊一樣擋，比對等於空驗。
        配比照 default_preset、識海不帶。卡在人物第一次看到畫面就出現（建角色、跳過教學、換季後第一下），這幾下照樣寫進輸出。回最後一下的回應。"""
        for _ in range(4):  # 最多配比、識海兩步；再多是卡按不掉，直接停，不要空跑
            step = self.prep_of(data)["step"]
            pick = f"growth:{self.c.config.attributes.v2.default_preset}" if step == "growth" else "legacy:skip"
            _, data = self.request(who, "POST", "/api/choose", {"id": pick})
            if self.prep_of(data) is None:
                return data
        raise RuntimeError(f"{who} 的開季準備卡按不掉：{self.prep_of(data)}")

    def main(self, who: str):
        return self.call(who, "GET", "/api/main")[1]

    def choose(self, who: str, option_id: str):
        return self.call(who, "POST", "/api/choose", {"id": option_id})[1]

    def do(self, who: str, op: str, body: dict | None = None):
        return self.call(who, "POST", f"/api/do/{op}", body or {})[1]

    @staticmethod
    def ids(view) -> dict[str, dict]:
        main = view.get("main", view) if isinstance(view, dict) else {}
        return {o["id"]: o for o in main.get("options", [])} if isinstance(main, dict) else {}

    def settle_choices(self, who: str, rounds: int = 6) -> None:
        """待選的事件（開局三選一、投靠之後的入伍）：照第一個選項選掉。"""
        for _ in range(rounds):
            first = [i for i, o in self.ids(self.main(who)).items() if i.startswith("choice:") and o.get("enabled")]
            if not first:
                return
            self.choose(who, first[0])

    # ── 擺局面（直接改資料庫；伺服器每次進鎖重讀） ──

    def edit(self, name: str, fn) -> None:
        with self.world.action_lock():
            state = self.chars.load(name)
            fn(state.player)
            self.chars.save(state)

    def open_sects(self) -> dict:
        """開關關著的門派（Sect.switch，門派包）不算：情境照舊只挑玩家拜得到的門派。"""
        is_open = getattr(self.c, "sect_open", lambda _sid: True)
        return {sid: s for sid, s in self.c.sects.items() if is_open(sid)}

    def open_skills(self) -> dict:
        """只在關著的門派學得到的武學不算，同上。"""
        is_open = getattr(self.c, "sect_open", lambda _sid: True)
        return {sid: s for sid, s in self.c.skills.items() if s.learn is None or s.learn.sect is None or is_open(s.learn.sect)}

    def place(self, name: str, loc: str | None, faction: str | None = "keep") -> bool:
        if loc is not None and loc not in self.c.locations:
            fallback = sorted(i for i, x in self.c.locations.items() if x.enemies)  # 測試內容沒有正式的地點：換一處遊歷打得到人的
            emit(f"{name} → {loc}（這份內容沒有這個地點）→ {fallback[0] if fallback else '略過'}", None)
            if not fallback:
                return False
            loc = fallback[0]

        def fn(p):
            if loc is not None:
                p.location, p.journey = loc, None
                p.visited.add(loc)
            if faction != "keep":
                p.faction = faction
            p.stamina = float(self.c.config.stamina_max)
            p.joined_at = -1.0e9  # 過了新手期（截殺與混戰的保護）
        self.edit(name, fn)
        return True

    def set_duel(self, on: bool) -> None:
        if self.profile in DUEL_PROFILES:
            self.c.config.jianfa.sortie_duel = on and self.duel_default

    def contested(self, *locs: str) -> bool:
        """這份內容有地盤、這幾處都是區塊（出陣開著的季才走得到出陣那幾段；none、test 沒有地盤）。"""
        from tianxia import conquest, territory

        return territory.on(self.c) and all(loc in conquest.blocks(self.c) for loc in locs)

    def preset_bar(self, loc: str, side: str, value: float, by: str) -> None:
        """把這一塊 side 那一條進度直接擺到 value（推的人記 by；到過警報線就記警報，同 conquest.push）：只靠出陣推，十幾步推不到那麼高。"""
        from tianxia import conquest
        from tianxia.state import Bar, BlockFight

        def fn(s) -> None:
            if s.conquest is None:
                conquest.update(s, self.c)
            fight = s.conquest.fights.setdefault(loc, BlockFight())
            fight.bars[side] = Bar(value=value, pushers={by: value})
            fight.alarm = fight.alarm or value >= self.c.config.conquest.alarm_at

        self.world.mutate_season(fn)
        emit(f"擺進度 {loc} {side} {value}", None)

    @contextlib.contextmanager
    def winning(self):
        """這一下的仗照寫好的打贏：team.fight 帶 tier（同序章雪恥那一場：威力、難度、亂數照算，判定出來之後只把結果換成大勝）。
        要的是打贏之後出陣包那幾支（推滿易手、截糧打贏、一類一顆之前的三成），本人練到頂也只是「難分勝負」。"""
        from tianxia import team

        real = team.fight

        def fight(*args, **kwargs):
            if kwargs.get("tier") is None:
                kwargs["tier"] = "大勝"
            return real(*args, **kwargs)

        team.fight = fight
        try:
            yield
        finally:
            team.fight = real

    def relogin(self, who: str) -> None:
        """重新登入一個帳號（後半是新的行程，記憶體裡的工作階段都不在了；整段也照樣登入，兩邊的步數才對得上）。"""
        self.clients[who] = self.TestClient(self.server.app)
        self.call(who, "POST", "/api/login", {"login": self.login_of(who), "password": self.passwords[who]})

    def login_all(self) -> None:
        """重新登入每一個帳號（前半＋後半在這裡接）。"""
        for who in list(self.clients):
            self.relogin(who)

    @staticmethod
    def login_of(who: str) -> str:
        return "zhangmen" if who == ADMIN else "u" + hashlib.sha256(who.encode()).hexdigest()[:10]

    def phase_end(self, name: str) -> None:
        emit(f"段落 {name} 資料庫", hashlib.sha256(db_text(self.db).encode("utf-8")).hexdigest())

    # ── 情境 ──

    PLAYERS = {  # 名號：陣營（None＝散人；序章那一位另外）
        "沈浪": "guan", "李尋歡": "guan", "傅紅雪": "guan", "蕭十一郎": "guan",
        "楚留香": "huang", "陸小鳳": "huang", "花滿樓": "huang", "西門吹雪": "huang",
    }
    NEWBIE = "新人"
    CLASHES = [  # （黃巾先出陣的人, 官軍撞上去的人, 地點）：每一對只撞一次（冷卻、護身）
        ("陸小鳳", "李尋歡", "nanyang_road"), ("花滿樓", "傅紅雪", "nanyang_wilds"),
        ("西門吹雪", "蕭十一郎", "yu_river"), ("楚留香", "沈浪", "lulin_zhai"),
    ]
    NEWCOMER = ("韓青川", "huang")  # pull_mark 才來的黃巾：守時撞上的混戰要一個沒被撞過（沒有護身、沒有這一對的冷卻）的人
    # pull_mark、pull、host、flip、drill 是審查之後加的（dev/sortie-1 審查：守把對面拉下來、守時的混戰、推滿易手、截糧打贏、
    # 一類一顆之前的三成原本都沒走到）。前半切在 pull_mark 之後（審查：原本切點跨過去的只有今天的次數）：涿郡黃巾那一條是 90、
    # 韓青川剛在那裡攻過（混戰的窗口開著、還沒被撞），後半第一件事就是官軍在那裡守、撞上他——正式上線就是這種舊程式寫到一半的局面。
    PHASES_FIRST = ["setup", "prologue", "ranger", "join", "duel_on", "out_of_contest", "attack", "hold", "clash", "pull_mark"]
    PHASES_SECOND = ["pull", "resume", "used_up", "win", "host", "flip", "convoy", "drill", "judge", "season"]

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
        self.do(ADMIN, "open_season")
        for who in [self.NEWBIE, *self.PLAYERS]:
            self.clients[who] = self.TestClient(self.server.app)
            self.passwords[who] = "pw-" + self.login_of(who)
            self.call(who, "POST", "/api/register", {"login": self.login_of(who), "password": self.passwords[who],
                                                    "again": self.passwords[who]})
            self.call(who, "POST", "/api/character", {"name": who, "gender": "男"})
        for who in self.PLAYERS:
            self.do(who, "skip_tutorial")
            self.settle_choices(who)

    def prologue(self) -> None:
        """序章走到雪恥（出陣開著時 act:train 叫雪恥、不算出陣次數；關著叫遊歷）：照 tests/season/test_real_content._walk_the_hut 的步驟，全走 API。"""
        from tianxia.features.sense import sensing

        who = self.NEWBIE
        view = self.main(who)
        if not view.get("prologue"):
            emit("這一季沒有序章", None)  # season21、week7 開局是開局第一分鐘（opening），測試內容沒有序章
            self.settle_choices(who)
            return
        self.choose(who, "choice:0")
        self.choose(who, "choice:0")
        self.do(who, "view_tab", {"tab": "practice"})
        self.choose(who, "act:explore")
        senses = [i for i, o in self.ids(self.main(who)).items() if i.startswith("sense:") and i != sensing.LET_GO and o.get("enabled")]
        if senses:
            self.choose(who, senses[0])
        self.choose(who, sensing.LET_GO)
        got = [i for i in self.chars.load(who).player.insights if i in ("feng", "shan", "shui", "huo")]
        if got:
            self.call(who, "POST", "/api/menxia/slot", {"art": "jichu_quanjiao", "insight": got[0]})
            self.call(who, "POST", "/api/menxia/practice", {"kind": "武學"})
            self.call(who, "POST", "/api/menxia/practice", {"kind": "武學"})
            self.call(who, "POST", "/api/menxia/forge", {"insights": [got[0], f"{got[0]}~2"]})
        self.do(who, "pill")
        view = self.main(who)
        emit("序章的 act:train", self.ids(view).get("act:train"))
        self.choose(who, "act:train")

    def ranger(self) -> None:
        """散人站在區塊上：出陣灰著寫「散人不能出陣」、底下那一行寫原因（出陣關著的季照舊是遊歷）。"""
        if self.place("沈浪", "runan_wilds"):
            view = self.main("沈浪")
            emit("散人的 act:train", self.ids(view).get("act:train"))
            emit("散人那一行", (view.get("action_notes") or {}).get("act:train"))
        if "act:train" in self.ids(self.main("沈浪")) and self.ids(self.main("沈浪"))["act:train"].get("enabled"):
            self.choose("沈浪", "act:train")  # 出陣關著的季：遊歷

    def join(self) -> None:
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

    def duel_on(self) -> None:
        """約戰開著的季（season21、week7）照原樣：按出陣只打開出陣前那張卡（不寫紀錄）；截糧的運糧隊經過照舊攻打（_squad_encounter；
        這一場傅紅雪打輸，截糧打贏在 convoy）。"""
        if self.profile not in DUEL_PROFILES:
            return
        self.set_duel(True)
        if self.place("李尋歡", "runan_wilds"):
            view = self.main("李尋歡")
            emit("約戰的 act:train", self.ids(view).get("act:train"))
            self.choose("李尋歡", "act:train")
        self.intercept("guan", "yanshan_foot")
        if self.place("傅紅雪", "yanshan_foot"):
            view = self.main("傅紅雪")
            emit("約戰開著、截糧的 act:train", self.ids(view).get("act:train"))
            self.choose("傅紅雪", "act:train")
        self.clear_orders()
        for who in ("李尋歡", "傅紅雪"):
            self.place(who, None)

    def out_of_contest(self) -> None:
        self.set_duel(False)
        if self.place("沈浪", "huangjin_camp"):
            view = self.main("沈浪")
            emit("別人大本營的 act:train", self.ids(view).get("act:train"))
            emit("別人大本營那一行", (view.get("action_notes") or {}).get("act:train"))

    def attack(self) -> None:
        """中立地攻：鈕上寫對手與勝算、必敗先問（confirm）；打完的出陣回報（main.front）。"""
        self.set_duel(False)
        for loc in ("runan_wilds", "hilltop_wilds"):
            if self.place("沈浪", loc):
                view = self.main("沈浪")
                emit(f"{loc} 的 act:train", self.ids(view).get("act:train"))
                emit(f"{loc} 那一行", (view.get("action_notes") or {}).get("act:train"))
                out = self.choose("沈浪", "act:train")
                emit(f"{loc} 出陣回報", (out.get("main") or {}).get("front") if isinstance(out, dict) else None)

    def hold(self) -> None:
        """自家地守：黃巾先在官軍的涿郡攻一下，官軍守（零風險）。楚留香這一下推不動（進度照舊 0），守的回報是「對面的進度都已歸零」
        （推不動、不撞混戰）；把對面拉下來與守時撞上混戰在 pull_mark／pull。"""
        self.set_duel(False)
        if self.place("楚留香", "zhuo_county"):
            self.choose("楚留香", "act:train")
        if self.place("沈浪", "zhuo_county"):
            view = self.main("沈浪")
            emit("自家地的 act:train", self.ids(view).get("act:train"))
            out = self.choose("沈浪", "act:train")
            emit("守的出陣回報", (out.get("main") or {}).get("front") if isinstance(out, dict) else None)

    def clash(self) -> None:
        """混戰：黃巾先在那一塊出陣，官軍 clash_minutes 內跟著出陣就撞上（贏、輸、平各一次以上）。"""
        self.set_duel(False)
        for theirs, ours, loc in self.CLASHES:
            if not (self.place(theirs, loc) and self.place(ours, loc)):
                continue
            self.choose(theirs, "act:train")
            out = self.choose(ours, "act:train")
            main = out.get("main") if isinstance(out, dict) else None
            latest = (main or {}).get("latest")
            emit(f"混戰 {ours}→{theirs}", {"latest": latest, "front": (main or {}).get("front")})
            self.main(theirs)  # 被撞的那一方的紀錄

    def resume(self) -> None:
        # 記憶體裡的設定也要接上前半最後那一段（混戰：約戰關著）：後半是新的行程，CONTENT 是剛載入的（selftest 抓到過：
        # 沒接上的話 season21、week7 的江湖畫面多一個 sorties 鍵）
        self.set_duel(False)
        self.login_all()

    def used_up(self) -> None:
        """用完今天的次數：灰著寫「今日已出陣 N 次」、底下那一行補句號。"""
        self.set_duel(False)
        if not self.place("沈浪", "hilltop_wilds"):
            return
        for _ in range(8):
            option = self.ids(self.main("沈浪")).get("act:train")
            if not option or not option.get("enabled"):
                break
            self.place("沈浪", None)
            self.choose("沈浪", "act:train")
        view = self.main("沈浪")
        emit("用完的 act:train", self.ids(view).get("act:train"))
        emit("用完那一行", (view.get("action_notes") or {}).get("act:train"))

    def win(self) -> None:
        """打得贏的出陣（本人的武學、內功練到第九成）：攻推得動進度（出陣回報畫進度條）、拿戰利與經驗；楚留香在官軍的涿郡攻兩下，
        官軍守（守拿自家那一路的數字）。楚留香在涿郡打不贏，那一條照舊是 0，守的回報是「都已歸零」；拉下來在 pull。"""
        self.set_duel(False)
        for who in ("蕭十一郎", "楚留香"):
            self.edit(who, lambda p: (setattr(p.member, "wugong_level", 9), setattr(p.member, "neigong_level", 9)))
        for who, loc, times in (("蕭十一郎", "hilltop_wilds", 2), ("蕭十一郎", "lulin_zhai", 1), ("楚留香", "zhuo_county", 2),
                                ("李尋歡", "zhuo_county", 1)):
            for _ in range(times):
                if not self.place(who, loc):
                    break
                view = self.main(who)
                emit(f"{who} 在 {loc} 的 act:train", self.ids(view).get("act:train"))
                out = self.choose(who, "act:train")
                emit(f"{who} 在 {loc} 的出陣回報", (out.get("main") or {}).get("front") if isinstance(out, dict) else None)

    def front(self, tag: str, out) -> None:
        main = out.get("main") if isinstance(out, dict) else None
        emit(tag, {"latest": (main or {}).get("latest"), "front": (main or {}).get("front")})

    def newcomer(self, who: str, side: str) -> bool:
        """後來才進江湖的一位：註冊、建角色、略過引導、投靠（同 setup、join），過了新手期。"""
        factions = {f.id: f for f in self.c.scenario.factions}
        if side not in factions or not factions[side].join_at:
            return False
        self.clients[who] = self.TestClient(self.server.app)
        self.passwords[who] = "pw-" + self.login_of(who)
        self.call(who, "POST", "/api/register", {"login": self.login_of(who), "password": self.passwords[who], "again": self.passwords[who]})
        self.call(who, "POST", "/api/character", {"name": who, "gender": "男"})
        self.do(who, "skip_tutorial")
        self.settle_choices(who)
        if not self.place(who, factions[side].join_at[0]):
            return False
        self.choose(who, f"faction:{side}")
        self.choose(who, "faction:confirm")
        self.settle_choices(who)
        return self.place(who, None)

    def pull_mark(self) -> None:
        """守把對面拉下來的前半：官軍的涿郡，黃巾那一條擺到 90（十幾步推不到那麼高），新來的黃巾韓青川在那裡攻一下——推得動，
        記下他此刻在這一塊出陣過（混戰的對象；打輸也記一筆 0）。"""
        self.set_duel(False)
        if not self.contested("zhuo_county"):
            return
        who, side = self.NEWCOMER
        if not self.newcomer(who, side):
            return
        self.preset_bar("zhuo_county", side, 90.0, who)
        if self.place(who, "zhuo_county"):
            emit(f"{who} 在涿郡的 act:train", self.ids(self.main(who)).get("act:train"))
            self.front(f"{who} 在涿郡攻", self.choose(who, "act:train"))

    def pull(self) -> None:
        """守時撞上混戰、守把對面拉下來：傅紅雪在涿郡守（黃巾那一條 > 0，推得動）撞上 clash_minutes 內攻過的韓青川；李尋歡接著守
        （韓青川剛被撞過、有護身，不再撞）——兩下的回報都是「黃巾軍的進度被拉到 N／100」（撞輸的那一下白跑、照舊 90）。
        這是後半的第一段：混戰的窗口只有 clash_minutes（10 分＝10 步），所以先只登入這兩位、馬上守，其餘的人等 resume 再登入。"""
        self.set_duel(False)
        if not self.contested("zhuo_county"):
            return
        for who in ("傅紅雪", "李尋歡"):
            self.relogin(who)
        for who in ("傅紅雪", "李尋歡"):
            if self.place(who, "zhuo_county"):
                emit(f"{who} 守涿郡的 act:train", self.ids(self.main(who)).get("act:train"))
                self.front(f"{who} 守涿郡", self.choose(who, "act:train"))

    def host(self) -> None:
        """守拿自家那一路的數字（_sortie_host）：涿郡沒有駐著官軍那一路，前面的守都不拿；黃巾的大本營（不在爭奪之列、推不動）
        守照拿——黃巾渠帥那一路，一類一顆開著全額（hold_share 1.0）。"""
        self.set_duel(False)
        if not self.contested("huangjin_camp"):
            return
        if self.place("西門吹雪", "huangjin_camp"):
            emit("大本營守的 act:train", self.ids(self.main("西門吹雪")).get("act:train"))
            self.front("大本營守", self.choose("西門吹雪", "act:train"))

    def flip(self) -> None:
        """推滿易手：荒丘（中立）官軍那一條擺到 99，蕭十一郎這一下打贏（winning）就推滿——「被你這一下推滿，落入官軍之手」、
        小籤「易手・這一下是你推滿的」、易手的分紅。"""
        self.set_duel(False)
        if not self.contested("hilltop_wilds"):
            return
        self.preset_bar("hilltop_wilds", "guan", 99.0, "蕭十一郎")
        if self.place("蕭十一郎", "hilltop_wilds"):
            emit("推滿那一下的 act:train", self.ids(self.main("蕭十一郎")).get("act:train"))
            with self.winning():
                self.front("推滿那一下", self.choose("蕭十一郎", "act:train"))

    def drill(self) -> None:
        """一類一顆之前（precise_actions 關著，test_sortie.py 也這樣測）：攻打贏照操練拿對手三成（sortie_drill；銀兩是 sortie_silver_share），
        守在自家大本營拿 _sortie_host 那一路的三成（hold_share 是 None）。記憶體裡關掉、做完開回來（同 set_duel）。"""
        self.set_duel(False)
        if not self.contested("nanyang_wilds", "huangjin_camp"):
            return
        cfg = self.c.config
        before, cfg.precise_actions = cfg.precise_actions, False
        try:
            if self.place("花滿樓", "nanyang_wilds"):
                emit("三成的攻 act:train", self.ids(self.main("花滿樓")).get("act:train"))
                with self.winning():
                    self.front("三成的攻", self.choose("花滿樓", "act:train"))
            if self.place("陸小鳳", "huangjin_camp"):
                emit("三成的守 act:train", self.ids(self.main("陸小鳳")).get("act:train"))
                self.front("三成的守", self.choose("陸小鳳", "act:train"))
        finally:
            cfg.precise_actions = before

    def intercept(self, side: str, loc: str) -> None:
        from tianxia import orders, territory
        from tianxia.engine import Game
        from tianxia.state import Order

        if loc not in self.c.locations or not territory.on(self.c):
            return
        shell = Game.for_world(self.c, self.world)
        week = orders.period_of(shell.state, self.c)
        front = territory.line_of(self.c, loc)
        self.world.mutate_season(lambda s: (s.orders.clear(), s.orders.append(Order(
            id=f"sb:{side}:intercept", template="intercept", faction=side, week=week, front=front, location=loc, quota=99,
            text="（對照）"))))

    def clear_orders(self) -> None:
        self.world.mutate_season(lambda s: s.orders.clear())

    def convoy(self) -> None:
        """截糧的運糧隊經過自家的區塊：出陣就是去截它。第一下照打（李尋歡打不過，落敗）；第二下打贏（winning：截糧打贏、出陣的獎勵、
        軍令記功）。"""
        self.set_duel(False)
        self.intercept("guan", "yanshan_foot")
        if self.place("李尋歡", "yanshan_foot"):
            view = self.main("李尋歡")
            emit("截糧的 act:train", self.ids(view).get("act:train"))
            emit("截糧那一行", (view.get("action_notes") or {}).get("act:train"))
            self.choose("李尋歡", "act:train")
            if self.contested("yanshan_foot") and self.place("李尋歡", None):
                with self.winning():
                    self.front("截糧打贏", self.choose("李尋歡", "act:train"))
        self.clear_orders()

    def judge(self) -> None:
        """大場面判讀：難度門檻調低、模型換成回固定判讀的，act:train 走 server.may_judge_fight → prepare_fight（鎖外判讀、鎖內套用）。"""
        self.set_duel(False)
        self.c.config.big_fight_difficulty = 1
        MODEL["judge"] = True
        try:
            if self.place("傅紅雪", "hilltop_wilds"):
                view = self.main("傅紅雪")
                emit("大場面的 act:train", self.ids(view).get("act:train"))
                self.choose("傅紅雪", "act:train")
        finally:
            MODEL["judge"] = False
            self.c.config.big_fight_difficulty = self.big_default

    def season(self) -> None:
        """收季、開下一季：sortie_day、sorties_today 照帶（換季不能多出一輪陣），不看地盤開不開（dev/sortie-1 審查）——
        地盤關著的設定（none、test）這兩格本來沒人動，先擺成「今天出陣過 3 次」；接著再換一季、換季前把第一季規則關掉
        （休季換設定：地盤從開變關），照樣照帶。"""
        from tianxia import territory

        self.set_duel(self.duel_default is not None)
        if not territory.on(self.c):
            self.edit("沈浪", lambda p: (setattr(p, "sortie_day", int(CLOCK0 // 86400)), setattr(p, "sorties_today", 3)))
        self.do(ADMIN, "end_season")
        self.main("沈浪")
        self.do(ADMIN, "next_season")
        view = self.main("沈浪")
        emit("換季之後的 act:train", self.ids(view).get("act:train"))
        p = self.chars.load("沈浪").player
        emit("換季之後的次數", {"sortie_day": p.sortie_day, "sorties_today": p.sorties_today})
        self.main(self.NEWBIE)
        cfg = self.c.config
        self.do(ADMIN, "end_season")
        before, cfg.season_one = cfg.season_one, False
        try:
            self.do(ADMIN, "next_season")
            view = self.main("沈浪")
            emit("地盤關掉再換季之後的 act:train", self.ids(view).get("act:train"))
            p = self.chars.load("沈浪").player
            emit("地盤關掉再換季之後的次數", {"sortie_day": p.sortie_day, "sorties_today": p.sorties_today})
        finally:
            cfg.season_one = before

    def save_cut(self, state_file: Path) -> None:
        """切點：前半跑完那一刻（叫 save_cut 不叫 cut：map 軌有一個叫 cut 的段，同名會蓋掉這一支）。不在請求中間（harness.IN_CALL 是 0），寫下步數、密碼、登入過的人（後半接著用）。"""
        if harness.IN_CALL[0]:
            raise RuntimeError(f"切點在請求中間（深度 {harness.IN_CALL[0]}）：前半＋後半接不起來")
        state_file.write_text(json.dumps({"step": STEP[0], "passwords": self.passwords, "clients": list(self.clients)},
                                         ensure_ascii=False), encoding="utf-8")

    def run(self, part: str, out: Path, snapshot: Path | None = None, snapshot_out: Path | None = None) -> None:
        """snapshot（第 107 批，只配 part == "all"）：PHASES_FIRST 跑完那一刻把資料庫抄到 snapshot 的名字、寫它的 .state.json、
        當時的輸出寫進 snapshot_out（＝ --part first 會寫的那一份），再接著跑完整段；compare --crossover 的 head 後半從快照接。"""
        state_file = Path(str(self.db) + ".state.json")
        if part == "second":
            saved = json.loads(state_file.read_text(encoding="utf-8"))
            STEP[0], self.passwords = saved["step"], saved["passwords"]
            self.clients = {who: None for who in saved["clients"]}
            phases = self.PHASES_SECOND
        else:
            phases = self.PHASES_FIRST + (self.PHASES_SECOND if part == "all" else [])
        if part != "second":
            emit(f"設定 {self.profile}", None)  # 後半不寫：前半＋後半要跟整段一個位元組都不差
        cut_at = len(self.PHASES_FIRST) - 1 if snapshot is not None and part == "all" else None
        for i, name in enumerate(phases):
            getattr(self, name)()
            self.phase_end(name)
            if i == cut_at:
                harness.snapshot_db(self.db, snapshot)
                self.save_cut(Path(str(snapshot) + ".state.json"))
                snapshot_out.write_text(BUF.getvalue(), encoding="utf-8", newline="\n")
        if part == "first":
            self.save_cut(state_file)
        else:
            BUF.write("## 資料庫\n" + db_text(self.db))
        out.write_text(BUF.getvalue(), encoding="utf-8", newline="\n")
        print(self.profile, part, STEP[0], "步", len(BUF.getvalue()), "字")


class DuelScenario(Scenario):
    """出陣約戰（主動搬六包第 2 批；--track duel，自己一個資料庫）。照調查 survey_duel.json behavior_check 的十一步：
    /api/main 的 sortie_card、sorties 與 act:train 那一格；按 act:train 只回 PICK、不寫紀錄；sortie_go 封三招；對面看 can_answer 與
    duel:open、duel:answered 通知；sortie_answer、sortie_join（也走 /api/choose 的 sortie:* 那一條）；拒絕的路（散人貼、次數用完、應自己的、
    三招不對、散人應、別區、在路上、同一邊應戰、冷卻、不認得的動詞、已有人應戰、你已應戰、已經同去、不是同袍同去、同去的次數、在路上同去、
    在路上貼、暫停中）；
    時鐘推過窗分三條路結算——下一個人的 sync（D0、D4、D6）、沒有玩家的 world_tick（server.world_step：D1、D2、D5）、管理者快轉的
    Game.advance（D7：/api/do/fast_forward 先 sync，經 API 走不到 advance 裡那一處，這裡照 server 的做法拿鎖、只叫 advance）；
    沒人應戰時假人補位（D0）、連假人都沒有由守軍迎戰（D4）；暫停時窗往後挪（D5）；快轉到季末之後還沒打的作廢、退次數與體力（D8）；
    截糧與 /api/map/state 的 convoy；約戰開著時巡哨那一點貢獻（_duty_credit）。三回合有兩場照寫好的打（rounds，同
    tests/kit/duel_kit.rounds_go：單次判定換成給的結果、照樣用掉一次那一場的亂數）：守方贏拉回（D0）、推滿易手（D2）那兩支才走得到；
    其餘照那一場自己的亂數。
    season21、week7 約戰開著；none、weekend、test 關著，同一串 API 照打，證明關著時一個字都不變（鈕回「此刻無法這麼做」、main 沒有
    sortie_card、sorties 兩個鍵）。半舊半新切在 D6 剛貼出去、還沒人應戰的那一刻（批次表第二節；正式上線就是這種局面）：後半先只登入應戰的
    那一位、馬上應戰（窗只有 10 分＝10 步），其餘的人再登入、窗滿了結算。"""

    PLAYERS = {  # 名號：陣營（甲是官軍、乙是黃巾）
        "甲一": "guan", "甲二": "guan", "甲三": "guan", "甲四": "guan", "甲五": "guan", "甲六": "guan", "甲七": "guan", "甲八": "guan",
        "甲九": "guan",
        "乙一": "huang", "乙二": "huang", "乙三": "huang", "乙四": "huang", "乙五": "huang", "乙六": "huang", "乙七": "huang",
        "乙八": "huang",
    }
    NEWBIE = "丙一"  # Scenario.setup 註冊、不投靠的那一位：這一軌的散人
    BOT = ("假乙", "huang")  # 只有黃巾那一邊有一個假人：官軍貼的沒人應由他補位（D0），黃巾貼的連假人都沒有由守軍迎戰（D4）
    LOC, FAR = "runan_wilds", "nanyang_road"  # 汝南荒野（潁汝的中立地，兩軍開季都碰得到）、南陽官道（別區的中立地）
    MOVES = "強攻,固守,奇襲"
    PHASES_FIRST = ["setup", "join", "seat", "look", "pick", "refuse_post", "post_d0", "refuse_answer", "fill", "post_d1", "answer_d1",
                    "settle_tick", "flip", "garrison", "pause", "post_d6"]
    PHASES_SECOND = ["answer_d6", "settle_d6", "convoy", "duty", "advance_d7", "void_d8", "season"]

    # ── 小工具 ──

    def begin(self) -> None:
        """同 Scenario.begin，另外每個請求換一份空的勝算記憶（server.ODDS_MEMO）：伺服器整個行程共用那一份，前半＋後半是兩個行程，
        後半的第一下沒有前半記住的字（selftest 抓到過：weekend 的「尋敵」鈕整段寫「凶險」、後半重算寫「必敗」——同一個鍵、記住的字跟
        重算的不一樣，見回報）。出陣那一軌（第 1 批）沒碰到，照舊不換，雜湊跟第 1 批記的同一種算法。"""
        super().begin()
        from tianxia import team

        self.server.ODDS_MEMO = team.OddsMemo()

    def skip(self, steps: int) -> None:
        """時鐘推過 steps 分（不打 API；下一個請求的時鐘照步數算）。"""
        STEP[0] += steps
        emit(f"時鐘推過 {steps} 分", None)

    def duel_of(self, attacker: str) -> str:
        """這個人最近貼的那一張約戰的 id；約戰關著的季沒有，回一個不存在的 id（照樣打 API，證明關著）。"""
        duels = sorted(self.world.sortie_duels().values(), key=lambda d: (d.opened_at, d.id))
        return next((d.id for d in reversed(duels) if d.attacker.name == attacker), "s0-none")

    def duels(self, tag: str) -> None:
        """全服的約戰此刻的樣子（world.sorties，照開的先後）。"""
        rows = []
        for d in sorted(self.world.sortie_duels().values(), key=lambda d: (d.opened_at, d.id)):
            rows.append({"id": d.id, "status": d.status, "block": d.block, "attacker": d.attacker.name, "allies": list(d.attacker.allies),
                         "defender": None if d.defender is None else [d.defender.name, d.defender.garrison],
                         "expires_at": d.expires_at, "settled_at": d.settled_at, "tier": None if d.result is None else d.result.tier,
                         "report": d.report})
        emit(f"約戰 {tag}", rows)

    def notices(self, who: str) -> None:
        """手機通知那一串（notices.current：server 的通知看守讀同一份；duel:open、duel:answered）。"""
        from tianxia.features.notify import notices

        state = self.chars.load(who)
        state.world = self.world.get_season()
        got = notices.current(state, self.c, self.world.get_battle(), self.world.sortie_duels())
        emit(f"{who} 的通知", [n.model_dump() for n in got])

    def player(self, who: str, tag: str) -> None:
        """存檔裡跟約戰有關的那幾格（次數、冷卻、體力、貢獻、內傷、紀錄幾則）。"""
        state = self.chars.load(who)
        if state is None:
            emit(f"{who} {tag}（沒有這個人）", None)
            return
        p = state.player
        emit(f"{who} {tag}", {"stamina": p.stamina, "sortie_day": p.sortie_day, "sorties_today": p.sorties_today,
                              "answer_day": p.answer_day, "answers_today": p.answers_today, "sortie_cooldown_until": p.sortie_cooldown_until,
                              "answer_cooldown_until": p.answer_cooldown_until, "duty_day": p.duty_day, "duties_today": p.duties_today,
                              "contrib": p.contrib, "injury": p.member.injury, "journal": len(state.journal), "battles": len(state.battles)})

    def post(self, who: str, moves: str | None = None) -> None:
        self.do(who, "sortie_go", {"moves": moves or self.MOVES})

    def answer(self, who: str, attacker: str, moves: str = "固守,固守,固守") -> None:
        self.do(who, "sortie_answer", {"id": self.duel_of(attacker), "moves": moves})

    def join_duel(self, who: str, attacker: str) -> None:
        self.do(who, "sortie_join", {"id": self.duel_of(attacker)})

    def tick(self, tag: str) -> None:
        """伺服器排程的一下（server.world_step：那一份沒有玩家的 Game；每一下重建，同每個請求重建 Game）。"""
        self.begin()
        self.server.WORLD_GAME = None
        msgs = self.server.world_step(time.time)
        self.server.WORLD_GAME = None
        emit(f"排程 {tag}", msgs)

    @contextlib.contextmanager
    def rounds(self, tier: str):
        """這一下結算的三回合照 tier 打（攻方的角度；同 duel_kit.rounds_go：照樣用掉一次那一場的亂數）。"""
        from tianxia import encounter

        real = encounter.resolve_encounter

        def fake(ours, theirs, rng, *a, **k):
            rng.random()
            return encounter.EncounterResult(tier=tier, margin=10.0, our_power=ours, difficulty=theirs)

        encounter.resolve_encounter = fake
        try:
            yield
        finally:
            encounter.resolve_encounter = real

    def reports(self, *who: str) -> None:
        for name in who:
            self.call(name, "GET", "/api/reports")
            self.call(name, "GET", "/api/annals")

    def today(self) -> int:
        """此刻的回體丹那一天（Game._pill_day；台灣 00:00 換日）。"""
        from tianxia.engine import Game

        shell = Game.for_world(self.c, self.world)
        shell.now = CLOCK[0]
        return shell._pill_day()

    # ── 情境 ──

    def seat(self) -> None:
        """補位的假人（只寫進資料庫、沒有帳號；同 bots_run 的擺法），擺在汝南荒野。"""
        from tianxia.engine import Game
        from tianxia.state import BotProfile

        name, side = self.BOT
        self.begin()
        with self.world.action_lock():
            g = Game.new(self.c, name, world=self.world, graduated=True)
            g.client = None
            g.sync(time.time())
            p = g.state.player
            p.bot = BotProfile(personality="普通", seed=11, faction=side, season_number=self.world.get_season_number())
            p.faction = side
            if self.LOC in self.c.locations:
                p.location, p.journey = self.LOC, None
                p.visited.add(self.LOC)
            p.tutorial_step = len(self.c.tutorial.steps)
            p.joined_at = -1.0e9
            p.stamina = float(self.c.config.stamina_max)
            self.chars.save(g.state)
        emit(f"擺好 {name}", None)

    def look(self) -> None:
        """站在汝南荒野的兩軍與散人、站在南陽官道的黃巾：/api/main（sortie_card、sorties、act:train 那一格與底下那一行）。"""
        for who, loc in (("甲一", self.LOC), ("乙一", self.LOC), (self.NEWBIE, self.LOC), ("乙六", self.FAR)):
            if self.place(who, loc):
                view = self.main(who)
                emit(f"{who} 的 act:train", self.ids(view).get("act:train"))
                emit(f"{who} 那一行", (view.get("action_notes") or {}).get("act:train"))

    def pick(self) -> None:
        """約戰開著：按出陣那一格只打開出陣前那張卡（sortie_duel.PICK），不花體力、不寫紀錄。"""
        self.player("甲一", "按之前")
        self.choose("甲一", "act:train")
        self.player("甲一", "按了出陣那一格")

    def refuse_post(self) -> None:
        """貼不成的兩條（約戰還沒有之前）：散人貼、今天的次數用完（都不扣體力、不寫紀錄）。"""
        self.post(self.NEWBIE)
        if self.place("甲二", self.LOC):
            day = self.today()
            self.edit("甲二", lambda p: (setattr(p, "sortie_day", day), setattr(p, "sorties_today", 2)))
            self.post("甲二")
        for who in (self.NEWBIE, "甲二"):
            self.player(who, "貼不成之後")

    def post_d0(self) -> None:
        """乙五先上路（往南陽官道）；甲一在汝南荒野貼 D0；對面看得到應戰（can_answer）、手機通知「有人約戰」。"""
        self.place("乙五", self.LOC)
        self.call("乙五", "POST", "/api/travel", {"place": self.FAR, "mode": "walk"})
        self.post("甲一")
        self.duels("D0 貼了")
        self.player("甲一", "貼了 D0")
        self.main("乙一")
        self.notices("乙一")
        self.notices("甲一")

    def refuse_answer(self) -> None:
        """D0 還開著（窗 10 分＝10 步，這一段 8 下）：應戰拒絕的路——應自己的、三招不對、散人、別區、在路上、同一邊只能同去；再貼一張
        （冷卻）、不認得的動詞。都不扣次數、不扣體力、不寫紀錄。"""
        self.answer("甲一", "甲一")
        self.answer("乙一", "甲一", "強攻,強攻")
        self.answer(self.NEWBIE, "甲一")
        self.answer("乙六", "甲一")
        self.answer("乙五", "甲一")
        self.place("甲三", self.LOC)
        self.answer("甲三", "甲一")
        self.post("甲一")
        self.choose("甲一", "sortie:zzz")
        self.duels("拒絕之後")
        for who in ("甲一", "乙一", "乙五", "乙六", "甲三", self.NEWBIE):
            self.player(who, "拒絕之後")

    def fill(self) -> None:
        """D0 沒人應（官軍那一條先擺到 40）：窗滿了排程關著，下一個同步的人（站在別處的甲四）替它結算——補位的是黃巾的假人（卡上、戰報、
        行狀只寫名號），守方三回合全勝、把官軍那一條拉回。"""
        if self.contested(self.LOC):
            self.preset_bar(self.LOC, "guan", 40.0, "甲一")
        self.skip(11)
        self.place("甲四", "nanyang_wilds")
        with self.rounds("落敗"):
            self.main("甲四")
        self.duels("D0 結算了")
        self.reports("甲一")
        self.player("甲一", "D0 結算之後")
        self.player(self.BOT[0], "補位之後")
        self.main("甲一")

    def post_d1(self) -> None:
        """甲五在汝南荒野貼 D1（走 /api/choose 的 sortie:go）。"""
        if self.place("甲五", self.LOC):
            self.choose("甲五", f"sortie:go:{self.MOVES}")
        self.duels("D1 貼了")

    def answer_d1(self) -> None:
        """乙一應 D1（先到的那一位；攻方的通知「有人應了」）；乙二第二個應、乙一再應；甲三同去（走 /api/choose 的 sortie:join）、
        再按一次；乙二同去、甲二（次數用完）同去；甲六上路之後同去、貼（在路上，dev/sortie-2 審查：_duel_join_extra 在路上那一條原本沒走到）。
        D1 的窗 10 分＝10 步：同去都在貼之後第 9 步以內。"""
        self.place("乙一", self.LOC)
        self.answer("乙一", "甲五")
        self.notices("甲五")
        self.place("乙二", self.LOC)
        self.answer("乙二", "甲五")
        self.answer("乙一", "甲五")
        self.choose("甲三", f"sortie:join:{self.duel_of('甲五')}")
        self.join_duel("甲三", "甲五")
        self.join_duel("乙二", "甲五")
        self.join_duel("甲二", "甲五")
        if self.place("甲六", self.LOC):
            self.call("甲六", "POST", "/api/travel", {"place": self.FAR, "mode": "walk"})
        self.join_duel("甲六", "甲五")
        self.post("甲六")
        self.duels("D1 應了、同去了")
        for who in ("乙一", "乙二", "甲三", "甲二", "甲六"):
            self.player(who, "應戰、同去之後")

    def settle_tick(self) -> None:
        """D1 窗滿：沒有人同步，伺服器排程那一下（server.world_step）結算（照那一場自己的亂數）；兩邊與同去的各一份戰報、一則紀錄。"""
        self.skip(11)
        self.tick("D1")
        self.duels("D1 結算了")
        self.reports("甲五", "乙一", "甲三")
        for who in ("甲五", "乙一", "甲三"):
            self.player(who, "D1 結算之後")
        self.main("甲五")
        self.main("乙一")

    def flip(self) -> None:
        """D2：黃巾的乙二在南陽郊野貼（黃巾那一條擺到 99），甲四應；窗滿了排程那一下結算——攻方三回合全勝、推滿易手。"""
        if self.contested("nanyang_wilds"):
            self.preset_bar("nanyang_wilds", "huang", 99.0, "乙二")
        if self.place("乙二", "nanyang_wilds"):
            self.main("乙二")
            self.post("乙二")
        self.answer("甲四", "乙二")
        self.skip(11)
        with self.rounds("大勝"):
            self.tick("D2")
        self.duels("D2 結算了")
        self.reports("乙二", "甲四")
        self.main("乙二")
        self.main("甲四")

    def garrison(self) -> None:
        """D4：黃巾的乙三在涿郡（官軍的）貼，沒人應、官軍那一邊沒有假人：守軍迎戰；下一個同步的人結算（照那一場自己的亂數）。"""
        if self.place("乙三", "zhuo_county"):
            self.main("乙三")
            self.post("乙三")
        self.skip(11)
        self.main("甲九")
        self.duels("D4 結算了")
        self.reports("乙三")
        self.main("乙三")

    def pause(self) -> None:
        """D5：甲六在淯水河畔貼；管理者暫停賽季時鐘（暫停中應戰、貼約戰回「賽季暫停中」），停到 D5 的窗原本該滿了之後——暫停中到時的不結算：
        排程那一下、一個人的同步都不收（dev/sortie-2 審查：原本只停 5 分，暫停中沒有一張到時）；再停 5 分，繼續之後窗往後挪停的長度；
        乙四應（走 /api/choose 的 sortie:answer），窗滿了排程結算。"""
        if self.place("甲六", "yu_river"):
            self.post("甲六")
        self.duels("D5 貼了")
        self.do(ADMIN, "pause_clock")
        self.place("乙四", "yu_river")
        self.answer("乙四", "甲六")
        self.post("甲七")
        self.skip(11)  # D5 的窗（10 分）在暫停中滿了
        self.tick("暫停中")
        self.main("乙四")
        self.duels("暫停中到時")
        self.skip(5)
        self.do(ADMIN, "resume_clock")
        self.duels("繼續之後")
        self.main("乙四")
        self.choose("乙四", f"sortie:answer:{self.duel_of('甲六')}:奇襲,強攻,固守")
        self.skip(11)
        self.tick("D5")
        self.duels("D5 結算了")
        self.reports("甲六", "乙四")

    def post_d6(self) -> None:
        """前半的最後一下：甲七在綠林山寨貼 D6、還沒人應戰（半舊半新切在這裡）。"""
        if self.place("甲七", "lulin_zhai"):
            self.main("甲七")
            self.post("甲七")
        self.duels("D6 貼了")

    def answer_d6(self) -> None:
        """後半的第一段：只先登入乙七、站到綠林山寨、馬上應 D6（新程式應舊程式貼的那一張；整段也照樣在這裡登入，步數才對得上）；
        其餘的人再登入。"""
        self.relogin("乙七")
        self.place("乙七", "lulin_zhai")
        self.answer("乙七", "甲七", "奇襲,奇襲,撤退")
        self.duels("D6 應了")
        self.login_all()

    def settle_d6(self) -> None:
        """D6 窗滿：下一個同步的人結算（新程式結算舊程式貼、新程式應的那一張）。"""
        self.skip(11)
        self.main("甲七")
        self.duels("D6 結算了")
        self.reports("甲七", "乙七")
        self.main("乙七")

    def convoy(self) -> None:
        """約戰開著、截糧的運糧隊經過自家的燕山腳：出陣那一格是「出陣・截糧」、照舊打運糧隊；輿圖的疊層那一處帶 convoy。"""
        self.intercept("guan", "yanshan_foot")
        if self.place("甲九", "yanshan_foot"):
            view = self.main("甲九")
            emit("截糧的 act:train", self.ids(view).get("act:train"))
            emit("截糧那一行", (view.get("action_notes") or {}).get("act:train"))
            self.call("甲九", "GET", "/api/map/state")
            self.choose("甲九", "act:train")
            self.player("甲九", "截糧之後")
        self.clear_orders()

    def duty(self) -> None:
        """約戰開著：巡哨（act:duty）收進此地、不佔出陣的次數，一天第一次記一點貢獻（_duty_credit）；第二次不記。"""
        if self.place("甲九", "zhuo_county"):
            view = self.main("甲九")
            emit("守勢的 act:duty", self.ids(view).get("act:duty"))
            for _ in range(2):
                self.place("甲九", None)
                if (self.ids(self.main("甲九")).get("act:duty") or {}).get("enabled"):
                    self.choose("甲九", "act:duty")
            self.player("甲九", "巡哨之後")

    def advance_d7(self) -> None:
        """D7：甲八在白馬津貼、乙八應；窗滿了，管理者快轉那一條（Game.advance）結算。/api/do/fast_forward 先 sync（窗滿了的在 sync 就結算掉），
        經 API 走不到 advance 裡那一處；整季機器人（bot.play_season）只 advance、不 sync，走的就是它——這裡照 server 的做法拿鎖、重讀管理者，
        只叫 advance（不 sync），再存回。"""
        for who in ("甲八", "乙八"):
            self.place(who, "baima_ford")
        self.post("甲八")
        self.answer("乙八", "甲八")
        self.skip(11)
        self.begin()
        game = self.server.game_for(ADMIN)
        with self.server._locked(game):
            game.now = time.time()
            msgs = game.advance(60)
            self.server.open_characters().save(game.state)
        self.server.GAMES.clear()
        emit("管理者快轉（只 advance）D7", msgs)
        self.duels("D7 結算了")
        self.reports("甲八", "乙八")
        for who in ("甲八", "乙八"):
            self.player(who, "D7 結算之後")

    def void_d8(self) -> None:
        """D8：甲九在拒馬河畔貼、乙五應；管理者快轉到季末（/api/do/fast_forward：季收了），下一個同步的人（攻方自己）替還沒打的那一張作廢——
        攻方退一次出陣（同一天才退）與體力、應戰的人退一次應戰與體力，冷卻不退。"""
        for who in ("甲九", "乙五"):
            self.place(who, "juma_river")
            # 體力擺到一半：滿的話退回來的那一下被上限與之後的回體力蓋掉，退多退少都看不出來（突變「攻方少退 1 點」抓不到過）
            self.edit(who, lambda p: setattr(p, "stamina", 100.0))
        self.post("甲九")
        self.answer("乙五", "甲九")
        for who in ("甲九", "乙五"):
            self.player(who, "D8 之前")
        self.do(ADMIN, "fast_forward", {"hours": 24 * 60})
        self.duels("快轉到季末之後")
        self.main("甲九")
        self.duels("D8 作廢了")
        for who in ("甲九", "乙五"):
            self.player(who, "作廢之後")
        self.main("乙五")

    def season(self) -> None:
        """開下一季（快轉已經收了季）：約戰清掉（sqlite_world 換季）、新的一季沒有卡。"""
        self.do(ADMIN, "next_season")
        self.duels("下一季")
        self.main("甲一")
        self.main("乙一")


# ═══════════════════════════ 子行程：假人 ═══════════════════════════


def bots_run(root: Path, profile: str, out: Path, tmp: Path) -> None:
    """整季機器人（bot.play_season，種子 3）與伺服器假人（BotRunner＋bot_policy.take_turn，random.Random(7)、假時鐘）各跑 N 輪：
    寫存檔、世界與資料庫的雜湊、各種紀錄標題的次數（看得出出陣那幾段有沒有走到）。"""
    tmp.mkdir(parents=True, exist_ok=True)
    for f in tmp.glob("*.db*"):
        f.unlink()
    _setup_child(root, profile, tmp / "unused.db")
    from collections import Counter

    from tianxia import bot
    from tianxia.bot_runner import BotRunner
    from tianxia.characters import open_characters
    from tianxia.content import load_content
    from tianxia.engine import Game
    from tianxia.sqlite_world import open_world
    from tianxia.state import BotProfile

    def titles(states) -> dict:
        return dict(sorted(Counter(e.title for s in states for e in s.journal).items()))

    content = load_content(root / "content", profile=profile)
    world = open_world(tmp / "play.db")
    game = bot.play_season(content, seed=3, max_steps=int(os.environ.get("SB_PLAY_STEPS", "700")), world=world, now=CLOCK0)
    emit("整季機器人 存檔", hashlib.sha256(game.state.model_dump_json().encode("utf-8")).hexdigest())
    emit("整季機器人 紀錄標題", titles([game.state]))
    # 約戰開著的季（week7）它貼過一張（bot.pick 最後那一行的 duel_go）：紀錄只留最近 30 則（journal.MAX_ENTRIES）、標題裡看不到，這裡寫出來。
    # 現實時刻一直是開季那一刻（play_season 不動 game.now），那一張永遠不到時；只 advance 的結算在 duel_bots_run 那一段（推現實時鐘）
    emit("整季機器人 約戰", _duel_rows(world))
    emit("整季機器人 資料庫", hashlib.sha256(db_text(tmp / "play.db").encode("utf-8")).hexdigest())

    content = load_content(root / "content", profile=profile)
    content.config.bot_tick_seconds = 10 ** 6  # 在線的假人每一輪都動（act_chance 夾到 1）
    world = open_world(tmp / "runner.db")
    world.seed_first_season(content)
    world.open_season(content, now=CLOCK0)
    chars = open_characters(tmp / "runner.db")
    seats = [("假甲", "guan", "hilltop_wilds"), ("假乙", "guan", "runan_wilds"), ("假丙", "huang", "runan_wilds"),
             ("假丁", "huang", "nanyang_road")]
    for i, (name, side, loc) in enumerate(seats):
        g = Game.new(content, name, rng=random.Random(i), world=world, graduated=True)
        g.client = None
        g.sync(CLOCK0)
        p = g.state.player
        p.bot = BotProfile(personality="普通", seed=11 + i, faction=side, season_number=world.get_season_number())
        p.faction, p.location, p.journey = side, loc, None
        p.visited.add(loc)
        p.tutorial_step = len(content.tutorial.steps)
        p.joined_at = -1.0e9
        chars.save(g.state)
    clock = [CLOCK0]
    runner = BotRunner(content, world, chars, rng=random.Random(7), clock=lambda: clock[0])
    totals = Counter()
    for _ in range(int(os.environ.get("SB_RUNNER_TICKS", "120"))):
        clock[0] += 300.0
        report = runner.tick()
        totals.update(acted=report.acted, added=report.added, skipped=report.skipped, failed=report.failed, online=report.online)
    states = chars.all(bots_only=True)
    emit("假人程式 一輪一輪", dict(sorted(totals.items())))
    emit("假人程式 紀錄標題", titles(states))
    emit("假人程式 存檔", {s.player.name: hashlib.sha256(s.model_dump_json().encode("utf-8")).hexdigest() for s in states})
    emit("假人程式 資料庫", hashlib.sha256(db_text(tmp / "runner.db").encode("utf-8")).hexdigest())
    out.write_text(BUF.getvalue(), encoding="utf-8", newline="\n")
    print(profile, "假人", dict(totals))


def _duel_rows(world) -> list[dict]:
    """world.sorties 的每一張（照開的先後）：誰貼、誰應、同去幾人、補位還是守軍、結果、什麼時候結算。"""
    duels = sorted(world.sortie_duels().values(), key=lambda d: (d.opened_at, d.id))
    return [{"id": d.id, "status": d.status, "block": d.block, "attacker": d.attacker.name, "allies": list(d.attacker.allies),
             "defender": None if d.defender is None else [d.defender.name, d.defender.garrison], "filled": bool(d.report.get("filled")),
             "tier": None if d.result is None else d.result.tier, "settled_at": d.settled_at} for d in duels]


DUEL_SEATS = [  # 約戰（第 2 批）：兩軍各 4 個，擺在兩軍都約得到的區塊與它們的大區裡（汝南荒野、南陽三處、涿郡）
    ("甲兵一", "guan", "runan_wilds"), ("甲兵二", "guan", "runan_wilds"), ("甲兵三", "guan", "nanyang_road"), ("甲兵四", "guan", "yu_river"),
    ("乙兵一", "huang", "runan_wilds"), ("乙兵二", "huang", "runan_wilds"), ("乙兵三", "huang", "nanyang_wilds"),
    ("乙兵四", "huang", "zhuo_county"),
]


def duel_bots_run(root: Path, profile: str, out: Path, tmp: Path) -> None:
    """約戰的假人（--seats duel）兩段。
    一、整季機器人（bot.play_season，種子 3、SB_PLAY_STEPS 步）：observe 每一步把現實時鐘（game.now）往前推一分（同情境一步一分）——
    play_season 自己從不動現實時刻（bots 那一份的整季機器人在 week7 貼了一張、永遠不到時、冷卻也永遠不過），推了之後它照 bot.pick 最後那一行
    （duel_go）一張一張貼，窗滿了由它自己的 Game.advance 結算（整季機器人只 advance、不 sync、沒有排程：dev/sortie-2 審查，「只 advance 的
    結算組合」原本只有情境的 D7 一場）。寫 world.sorties 的每一張、存檔、戰報、紀錄標題與資料庫的雜湊。
    二、BotRunner＋bot_policy.take_turn（random.Random(7)、假時鐘、每一輪 +300 秒）兩軍各 4 個跑 N 輪——假人貼約戰（bot.duel_go）、應戰與同去
    （bot_policy.duel_play）、到時由 BotRunner._duel_tick 結算。寫 world.sorties 的每一張（誰貼、誰應、同去幾人、補位還是守軍、結果）、
    應戰與同去的次數、戰報、紀錄標題、存檔、各塊進度與資料庫的雜湊。"""
    tmp.mkdir(parents=True, exist_ok=True)
    for f in tmp.glob("*.db*"):
        f.unlink()
    _setup_child(root, profile, tmp / "unused.db")
    from collections import Counter

    from tianxia import bot
    from tianxia.bot_runner import BotRunner
    from tianxia.characters import open_characters
    from tianxia.content import load_content
    from tianxia.engine import Game
    from tianxia.sqlite_world import open_world
    from tianxia.state import BotProfile

    content = load_content(root / "content", profile=profile)
    play_world = open_world(tmp / "play.db")
    moved = [0]

    def observe(g) -> None:  # 開始之前叫一次、之後每一步叫一次
        moved[0] += 1
        g.now = CLOCK0 + moved[0] * STEP_SECONDS

    game = bot.play_season(content, seed=3, max_steps=int(os.environ.get("SB_PLAY_STEPS", "700")), world=play_world, now=CLOCK0,
                           observe=observe)
    rows = _duel_rows(play_world)
    emit("約戰整季機器人 約戰", rows)
    emit("約戰整季機器人 次數", dict(sorted(Counter(r["status"] for r in rows).items())))
    emit("約戰整季機器人 紀錄標題", dict(sorted(Counter(e.title for e in game.state.journal).items())))
    emit("約戰整季機器人 戰報", hashlib.sha256(json.dumps([r.model_dump(mode="json") for r in game.state.battles], ensure_ascii=False)
                                                 .encode("utf-8")).hexdigest())
    emit("約戰整季機器人 存檔", hashlib.sha256(game.state.model_dump_json().encode("utf-8")).hexdigest())
    emit("約戰整季機器人 資料庫", hashlib.sha256(db_text(tmp / "play.db").encode("utf-8")).hexdigest())
    print(profile, "約戰整季機器人", moved[0], "步", dict(Counter((r["status"], r["defender"][1] if r["defender"] else None) for r in rows)))

    content = load_content(root / "content", profile=profile)
    content.config.bot_tick_seconds = 10 ** 6  # 在線的假人每一輪都動（act_chance 夾到 1）
    world = open_world(tmp / "duel.db")
    world.seed_first_season(content)
    world.open_season(content, now=CLOCK0)
    chars = open_characters(tmp / "duel.db")
    for i, (name, side, loc) in enumerate(DUEL_SEATS):
        g = Game.new(content, name, rng=random.Random(i), world=world, graduated=True)
        g.client = None
        g.sync(CLOCK0)
        p = g.state.player
        p.bot = BotProfile(personality="積極", seed=21 + i, faction=side, season_number=world.get_season_number())
        p.faction, p.location, p.journey = side, loc, None
        p.visited.add(loc)
        p.tutorial_step = len(content.tutorial.steps)
        p.joined_at = -1.0e9
        chars.save(g.state)
    clock = [CLOCK0]
    runner = BotRunner(content, world, chars, rng=random.Random(7), clock=lambda: clock[0])
    totals = Counter()
    for _ in range(int(os.environ.get("SB_DUEL_TICKS", "120"))):
        clock[0] += 300.0
        report = runner.tick()
        totals.update(acted=report.acted, added=report.added, skipped=report.skipped, failed=report.failed, online=report.online)
    duels = sorted(world.sortie_duels().values(), key=lambda d: (d.opened_at, d.id))
    rows = [{"id": d.id, "status": d.status, "block": d.block, "attacker": d.attacker.name, "allies": list(d.attacker.allies),
             "defender": None if d.defender is None else [d.defender.name, d.defender.garrison], "filled": bool(d.report.get("filled")),
             "tier": None if d.result is None else d.result.tier} for d in duels]
    counts = Counter()
    for d in duels:
        counts["約戰"] += 1
        counts["同去"] += len(d.attacker.allies)
        if d.defender is not None:
            counts["守軍" if d.defender.garrison else "補位" if d.report.get("filled") else "應戰"] += 1
        counts[d.status] += 1
    states = chars.all(bots_only=True)
    emit("約戰假人 一輪一輪", dict(sorted(totals.items())))
    emit("約戰假人 約戰", rows)
    emit("約戰假人 次數", dict(sorted(counts.items())))
    emit("約戰假人 紀錄標題", dict(sorted(Counter(e.title for s in states for e in s.journal).items())))
    emit("約戰假人 戰報", {s.player.name: hashlib.sha256(json.dumps([r.model_dump(mode="json") for r in s.battles], ensure_ascii=False)
                                                                   .encode("utf-8")).hexdigest() for s in states})
    emit("約戰假人 存檔", {s.player.name: hashlib.sha256(s.model_dump_json().encode("utf-8")).hexdigest() for s in states})
    season = world.get_season()
    emit("約戰假人 各塊進度", hashlib.sha256((season.conquest.model_dump_json() if season.conquest is not None else "").encode("utf-8"))
         .hexdigest())
    emit("約戰假人 資料庫", hashlib.sha256(db_text(tmp / "duel.db").encode("utf-8")).hexdigest())
    out.write_text(BUF.getvalue(), encoding="utf-8", newline="\n")
    print(profile, "約戰假人", dict(totals), dict(counts))


# ═══════════════════════════ 登記：第 1 批的一軌（出陣）、第 2 批的一軌（約戰），各自一個資料庫、各自切一半 ═══════════════════════════

# 改一個字（selftest）：出陣回報打輸那一句
register_track("sortie", Scenario, (("tianxia/features/sortie/rules.py",), ("這一下沒推動。", "這一下沒推動！")), "week7",
               covers=("admin", "battle", "bounties", "bout", "checkin", "companions", "craft", "cultivation", "explore", "faction",
                       "feast", "figure_acts", "gear", "guide", "heroines", "hire", "legacy", "looks", "mall", "map",
                       "military", "notify", "outlets", "peers", "persona", "seal", "seclusion", "sense", "smithy", "socialize",
                       "sortie", "stamina_plays", "story", "tale", "tavern", "territory_acts", "travel", "zhuan"))
# 改一個字（selftest）：同去按第二次那一句
register_track("duel", DuelScenario, (("tianxia/features/sortie/duel_rules.py",),
                                      ('WHY_JOINED = "已經同去了"', 'WHY_JOINED = "已經同去了！"')), "week7",
               covers=("admin", "battle", "bounties", "bout", "checkin", "companions", "craft", "cultivation", "explore", "faction",
                       "feast", "figure_acts", "gear", "guide", "heroines", "hire", "legacy", "looks", "mall", "map",
                       "military", "notify", "outlets", "peers", "persona", "seal", "seclusion", "sense", "smithy", "socialize",
                       "sortie", "stamina_plays", "story", "tale", "tavern", "territory_acts", "travel", "zhuan"))
register_bots("sortie", BOT_PROFILES, bots_run)  # 出陣那一軌的假人（整季機器人＋BotRunner 四個）
register_bots("duel", DUEL_BOT_PROFILES, duel_bots_run)  # 約戰那一軌的（推現實時鐘的整季機器人＋BotRunner 兩軍各 4 個）
