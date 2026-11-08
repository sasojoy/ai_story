"""same_behavior 一軌一檔：portrait、zhuanframe（這一檔登記這兩軌；第二輪第 83 批，計畫 docs/superpowers/plans/2026-11-07-第二輪-第83批.md）。"""
from __future__ import annotations

import contextlib
import hashlib

from sb.harness import ADMIN, emit, page_script, register_track
from sb.tracks.here import HereScenario
from sb.tracks.zhuan import ZhuanScenario

# ═══════════════════════════ portrait、zhuanframe（第 83 批：殼的簡介與列傳畫面搬進包）═══════════════════════════
# 這一批搬 figure_intro 一串進 socialize、zhuan_view 一串進 zhuan。先量過現有的軌走到什麼（here、shelf、zhuan、relay），這兩軌只補它們走不到的分支。
# 角色的名字都是原創的；portrait 借 here 的小工具，zhuanframe 借 zhuan 的前半。


class PortraitScenario(HereScenario):
    """點大勢人物的簡介（/api/main 的 figures_here[].intro；--track portrait，自己一個資料庫）。here 一軌每一筆都是沒換過段（now 是 None、history 是空的），
    這一軌補其餘的：換過段（如今、變化紀錄、你勸過他 N 次，勸過的人與旁人各看一次）、拉鋸（眾說紛紜那一句）、簡介檔沒寫他卻有性子（只有如今與紀錄）、
    簡介檔沒寫他也沒有性子（intro 是 None）、換季歸回本性。
    **前半停在寫到一半的事**：兩個人今天勸了盧植、推力記在世界上，00:00 還沒結算。後半新程式接著：時間跳過 00:00，第一個同步的人替全服算，簡介才變。
    假人碰不到（只有畫面讀，bot.py、bot_policy、bot_runner 都不叫），不跑假人段。測試內容沒有大勢人物、沒有性子，同一串 API 照打，一排都是空的。"""

    URGER, ALLY, BYSTANDER = "沈渡雲", "韋青禾", "陸聞舟"
    NEWBIE = "初見山"
    PLAYERS = {who: "guan" for who in (URGER, ALLY, BYSTANDER)}
    STRAIGHT, TACT = "upright", "rites"  # 盧植的兩條（起點第 0 段、第 1 段）
    PHASES_FIRST = ["setup", "seat", "still", "urged", "half"]
    PHASES_SECOND = ["resume", "turned", "tugged", "unwritten", "season"]

    # ── 小工具 ──

    def spot(self) -> str | None:
        return next((loc for loc, figs in self.layout().items() if self.LUZHI in figs), None)

    def everyone(self, tag: str) -> None:
        for who in self.PLAYERS:
            self.glance(who, tag)

    def urge(self, who: str, axis_id: str, end: int) -> None:
        """記一筆「勸」（對話時模型歸一頭之後走的同一支 persona_rules.record；這一軌不開對話，那一條在 companions）。情誼 90 是最重的一檔。"""
        from tianxia import persona_rules

        if self.LUZHI not in self.c.personas:
            emit(f"{who} 勸", "這份內容沒有他的性子")
            return
        axis = next(a for a in self.c.personas[self.LUZHI] if a.id == axis_id)
        with self.world.action_lock():
            state = self.chars.load(who)
            state.world = self.world.get_season()
            got = persona_rules.record(state, self.c, self.LUZHI, axis.ends[end], 90)
            self.chars.save(state)
            self.world.save_season(state.world)
        emit(f"{who} 勸", [axis_id, axis.ends[end], got])

    def ledger(self, tag: str) -> None:
        w = self.world.get_season()
        emit(f"世界上的性子 {tag}", {"值": w.persona, "天": w.persona_day, "推": w.persona_push, "拉": w.persona_tug, "拉鋸": w.persona_torn,
                                  "紀錄": [e.model_dump(mode="json") for e in w.persona_log]})

    def past_midnight(self) -> None:
        self.do(ADMIN, "fast_forward", {"hours": 25})

    # ── 前半 ──

    def still(self) -> None:
        """三個人站到他面前：還沒換過段。"""
        loc = self.spot()
        for who in self.PLAYERS:
            self.stand(who, loc, 9999)
        self.everyone("還沒換過段")

    def urged(self) -> None:
        """他那一條差一點就換段（值擺在段的邊上，同 test_persona），兩個人今天往同一頭勸。"""
        if self.LUZHI in self.c.personas:
            self.world.mutate_season(lambda w: w.persona.setdefault(self.LUZHI, {}).update({self.STRAIGHT: -61}))
        self.urge(self.URGER, self.STRAIGHT, 1)
        self.urge(self.ALLY, self.STRAIGHT, 1)

    def half(self) -> None:
        self.ledger("前半停在這裡（推力記了、還沒結算）")
        self.everyone("前半停在這裡")

    # ── 後半 ──

    def turned(self) -> None:
        """跳過 00:00：第一個同步的人替全服算，換了段。如今、紀錄每個人都看得到；「你勸過他」只有勸過的人有。"""
        self.past_midnight()
        self.everyone("換過段")
        self.ledger("換過段")

    def tugged(self) -> None:
        """同一天兩頭都有人勸、淨推力不夠：拉鋸（紀錄後面多一句），勸過的次數跟著加。"""
        self.urge(self.URGER, self.TACT, 0)
        self.urge(self.ALLY, self.TACT, 1)
        self.past_midnight()
        self.everyone("拉鋸")
        self.ledger("拉鋸")

    def unwritten(self) -> None:
        """簡介檔少一筆（這一軌暫時從同一個 dict 拿掉，出來還原）：他有性子只畫如今與紀錄；沒有性子的人 intro 是 None。"""
        intros = self.server.FIGURE_INTROS
        saved = dict(intros)
        plain = next(((loc, cid) for loc, figs in sorted(self.layout().items()) for cid in sorted(figs) if cid not in self.c.personas), None)
        try:
            intros.pop(self.LUZHI, None)
            self.glance(self.BYSTANDER, "簡介檔沒寫他、他有性子")
            if plain is not None:
                intros.pop(plain[1], None)
                self.stand(self.BYSTANDER, plain[0], 9999)
                self.glance(self.BYSTANDER, f"簡介檔沒寫 {plain[1]}、他沒有性子")
        finally:
            intros.clear()
            intros.update(saved)

    def season(self) -> None:
        """收季、開下一季：全部歸回本性，簡介回到只有本性。"""
        self.do(ADMIN, "end_season")
        self.main(self.URGER)
        self.do(ADMIN, "next_season")
        for who in self.PLAYERS:
            self.main(who)
        loc = self.spot()
        for who in self.PLAYERS:
            self.stand(who, loc, 9999)
        self.everyone("換季之後")
        self.ledger("換季之後")


class ZhuanFrameScenario(ZhuanScenario):
    """列傳的畫面（--track zhuanframe，自己一個資料庫）：前半跟 zhuan 一軌一樣（休季、票買了用了一半、有人寫成了有人沒寫），後半只補它走不到的：
    season 認不得（「哪一季？」：缺、None、字、清單；認得的 "1"、1.9 照舊走下去）、圖檔不在（殼的 WEB 暫時指到空資料夾：畫面的 illustration_src 是 None、公開頁沒有插畫、紀念印還在）、
    公開頁的插畫與紀念印各自在不在（看那一段標記，zhuan 一軌只看整頁的雜湊）、列傳為終點關掉（公開頁什麼都不多）、商城關掉（票照沒有算）。
    假人段在 zhuan 一軌（假人不讀這幾個畫面）。測試內容行狀關著：每一條都回不能，公開頁「沒有網址」。"""

    PHASES_SECOND = ["resume", "odd_seasons", "no_files", "public_bits"]

    @contextlib.contextmanager
    def tuned(self, owner, **values):
        before = {k: getattr(owner, k) for k in values}
        for k, v in values.items():
            setattr(owner, k, v)
        emit("這一下的設定", values)
        try:
            yield
        finally:
            for k, v in before.items():
                setattr(owner, k, v)

    def bits(self, tag: str, url: str | None) -> None:
        if not url:
            emit(f"公開頁 {tag}", "沒有網址")
            return
        self.begin()
        r = self.TestClient(self.server.app).get("/zhuan/" + url.rsplit("/zhuan/", 1)[-1])
        emit(f"公開頁 {tag}", {"status": r.status_code, "插畫": '<figure class="zh-art"' in r.text, "紀念印": '<div class="zh-mark"' in r.text,
                             "sha": hashlib.sha256(page_script(r.text).encode("utf-8")).hexdigest()})

    def odd_seasons(self) -> None:
        who = self.RULE
        for body in ({}, {"season": None}, {"season": "三"}, {"season": []}, {"season": "1"}, {"season": 1.9}):
            self.zwrite(who, body)
            self.call(who, "POST", "/api/zhuan/share", {**body, "public": False})
        self.call(who, "GET", "/api/zhuan?season=abc")

    def no_files(self) -> None:
        who = self.MODEL_W
        url = self.share(who, True, "公開")
        real = self.server.WEB
        empty = self.db.parent / (self.db.name + ".noweb")
        empty.mkdir(exist_ok=True)
        self.server.WEB = empty
        try:
            self.call(who, "GET", f"/api/zhuan?season={self.number(who)}")
            self.main(who)
            self.bits("圖檔不在", url)
        finally:
            self.server.WEB = real

    def public_bits(self) -> None:
        url = self.share(self.MODEL_W, True, "公開")
        self.bits("插畫與紀念印", url)
        with self.tuned(self.c.config.jianfa, zhuan_end=False):
            self.bits("列傳為終點關掉", url)
        with self.tuned(self.c.config.mall, enabled=False):
            self.bits("商城關掉", url)


# 改一個字（selftest）：簡介檔沒寫他那一支才看得到（who 的預設值）；「哪一季？」只有 season 認不得才看得到。兩句都是這一批搬的，搬之前在 server.py。
register_track("portrait", PortraitScenario, (("tianxia/features/socialize/intro.py", "server.py"),
                                              ('"who": row.get("who", "")', '"who": row.get("who", "？")')), "season21",
               covers=("admin", "battle", "bounties", "bout", "checkin", "companions", "craft", "cultivation", "explore", "faction",
                       "feast", "figure_acts", "gear", "guide", "heroines", "legacy", "mall", "military", "outlets", "peers",
                       "seal", "seclusion", "socialize", "sortie", "stamina_plays", "story", "territory_acts", "travel", "zhuan"))
register_track("zhuanframe", ZhuanFrameScenario, (("tianxia/features/zhuan/routes.py", "server.py"), ('"哪一季？"', '"哪一季?"')), "season21",
               covers=("admin", "battle", "bounties", "bout", "companions", "explore", "faction", "gear", "looks", "mall",
                       "socialize", "sortie", "zhuan"))
