"""same_behavior 一軌一檔：roam（這一檔登記 roam）。"""
from __future__ import annotations

import contextlib
import hashlib

from sb.harness import emit, register_track
from sb.tracks.explore import _explore_rules
from sb.tracks.strip import StripScenario

# ═══════════════════════════ explore（全部拆包第 18 批「探索三」，dev/explore-3）：roam 一軌 ═══════════════════════════
# 序章草廬四景與探索的底：權重（_explore_weights、_explore_can）、野怪（_wild_foes、_here_squads）、自家營寨跟同袍比劃（_drills_with）、
# 練功分級（_practice_tier）、撿破境丹（_legend_find）、舊探索本身（_explore、_explore_outcome；不帶設定、weekend、測試內容走它，
# season21、week7 走出門一趟）。計畫 docs/superpowers/plans/2026-11-04-探索包-第3批.md。名字一律原創（第 22 批認定第 3 條）。


class RoamScenario(StripScenario):
    """探索三（全部拆包第 18 批；--track roam，自己一個資料庫）。小工具借拿掉一那一軌的（game、field、town、look_here、me 的位置、bots、season）
    與探索那一軌的（draws、fights、tweak、explore、settle、kind_places）。
    - 草廬（不帶、weekend）：阮青禾遇險、拜師、看修練頁，按探索——序章第 3 步（四景四選一的事件卡，或有所感版的卡）；這一下把破境丹的機率擺到 1，
      序章裡不撿（_explore 最前面那一條）。**前半停在卡上**（舊程式端出來的），後半新程式接著選。沒有草廬的季寫「沒有」。
    - 權重：每種地點、官軍、黃巾、散人各站一次——此刻站著哪幾路隊伍、哪幾路是自己人、野怪、三支的比重、做不做得了、分級，與選單、行動列底下那一行。
    - 野怪：城外按探索，舊探索這一下落在野怪那一支（_explore_weights 只回野怪；官軍打贏、黃巾落敗、散人照打）；出門一趟抽到遭遇。
    - 自家營寨：官軍站官軍的營寨、黃巾站黃巾的營寨（自己人不殺出來：舊探索一無所獲或別的支、出門一趟是跟同袍比劃）、官軍站黃巾的營寨。
    - 破境丹：機率 0／0.5／1（直接叫 _legend_find，連亂數序列一起寫）、帶寶物放大門檻、傳自己的亂數、真的按探索撿到。
    - 分級：每一處、三種身分的 _practice_tier；輿圖詳情最後那一句。
    - 假人、收季：借拿掉一那一軌的，換一批擺位（城外、官軍營寨、黃巾營寨、黃巾的祭壇）。"""

    BOT_SEATS = [("遊甲", "yingshui"), ("遊乙", "guan_camp"), ("遊丙", "huangjin_camp"), ("遊丁", "julu_altar")]
    PHASES_FIRST = ["setup", "weights", "wild", "camp", "legend", "grades", "hut"]
    PHASES_SECOND = ["resume", "answer", "again", "bots", "season"]
    WHO = ("韓墨川", "蘇映秋", "杜遠山")  # 官軍、黃巾、散人

    # ── 小工具 ──

    @contextlib.contextmanager
    def only(self, branch: str):
        """舊探索這一下只落在這一支（Game._explore_weights 換掉；兩份程式都在 Game 上，同一步換、同一步換回）。出門一趟不讀它。"""
        from tianxia.engine import Game

        real = Game._explore_weights
        Game._explore_weights = lambda game, loc: [(branch, 1.0)]
        try:
            yield
        finally:
            Game._explore_weights = real

    def spots(self) -> list[str]:
        """各種地點一處、兩邊的營寨、兩軍混站的野地、官軍與散人混站的野地（這份內容沒有的略過）。"""
        out = [loc for _, loc in self.kind_places()]
        for loc in ("guan_camp", "huangjin_camp", "nanyang_wilds", "juma_river", "baima_ford"):
            if loc in self.c.locations and loc not in out:
                out.append(loc)
        return out

    def stand(self, who: str, loc: str, tag: str) -> None:
        """站在某處：此刻站著的隊伍、自己人、野怪、三支的比重與做不做得了、練功分級；再看選單與行動列底下那一行。"""
        self.place(who, loc)
        game = self.game(who)
        here = self.c.locations[game.state.player.location]
        # base 上是 Game 的方法，搬進包之後 Game 不留（只有包裡自己叫）：沒有就叫包裡那一支，兩邊算的是同一件事
        if hasattr(game, "_here_squads"):
            squads = game._here_squads(here.id)
        else:
            from tianxia.features.explore import explore_base
            squads = explore_base.here_squads(game, here.id)
        emit(f"{who} {tag} {here.id}", {
            "squads": squads, "own": [sid for sid in squads if game._drills_with(self.c.squads[sid])],
            "wild": [f.id for f in game._wild_foes(here)], "weights": game._explore_weights(here),
            "can": {b: game._explore_can(b, here) for b in ("insight", "wild", "event")}, "tier": game._practice_tier(here)})
        self.look_here(who, tag)

    def show_legend(self, who: str, tag: str) -> None:
        p = self.chars.load(who).player
        emit(f"{who} {tag} 破境丹", {"items": p.legend_items, "explore_seq": p.explore_seq, "stamina": p.stamina})

    # ── 前半 ──

    def weights(self) -> None:
        """每種地點 × 官軍、黃巾、散人。"""
        for who in self.WHO:
            for loc in self.spots():
                self.stand(who, loc, "站著")

    def wild(self) -> None:
        """城外按探索：舊探索落在野怪那一支（打贏、落敗、照打）；出門一趟抽到遭遇。野怪帶不帶得出來都看真實的 _wild_foes。"""
        explore_one = _explore_rules()

        spot = self.field()
        for who, tier in (("蘇映秋", "大勝"), ("韓墨川", "落敗"), ("杜遠山", None)):
            self.place(who, spot)
            with self.only("wild"), self.draws(explore_one.ENCOUNTER), self.fights(tier):
                self.explore(who)
            self.me(who, "野怪之後")
        # 照真實的比重自己走（奇遇、頭目也擲）：每個身分在城外多走幾下
        for who in self.WHO:
            for k in range(3):
                self.place(who, spot)
                self.explore(who, k)
            self.me(who, "照真的走三下")

    def camp(self) -> None:
        """自家營寨（自己人不殺出來，跟同袍比劃）與對面的營寨。"""
        explore_one = _explore_rules()

        seats = (("韓墨川", "guan_camp"), ("蘇映秋", "huangjin_camp"), ("裴寒舟", "guan_camp"), ("韓墨川", "huangjin_camp"), ("蘇映秋", "guan_camp"))
        for who, loc in seats:
            if loc not in self.c.locations:
                emit(f"{who} {loc}（這份內容沒有）", None)
                continue
            for k in range(2):
                self.place(who, loc)
                with self.draws(explore_one.ENCOUNTER), self.fights("大勝"):
                    self.explore(who, k)
                self.me(who, f"在 {loc} 第 {k + 1} 下")

    def legend_pick(self, who: str, chance: float, tag: str) -> None:
        explore_one = _explore_rules()

        self.place(who, self.field())
        with self.tweak(self.c.config, explore_legend_chance=chance), self.draws(explore_one.MATERIAL):
            self.explore(who)
        self.me(who, tag)
        self.show_legend(who, tag)

    def legend(self) -> None:
        """撿破境丹：真的按探索（機率 0／1／0.5）、直接擲、帶寶物、傳自己的亂數。"""
        import random as rnd
        from tianxia import treasures

        for pick, chance in (("沈晚舟", 0.0), ("顧行之", 1.0), ("裴寒舟", 0.5)):
            self.legend_pick(pick, chance, f"機率 {chance}")
        game = self.game("程聽雪")
        for chance in (0.0, 0.5, 1.0):
            with self.tweak(self.c.config, explore_legend_chance=chance):
                got = game._legend_find()
                emit(f"直接擲 機率 {chance}", {"got": got, "items": game.state.player.legend_items,
                                                  "rng": hashlib.sha256(repr(game.rng.getstate()).encode("utf-8")).hexdigest()[:12]})
        fake = lambda st, ct, key: 2.0 if key == "legend" else 1.0  # noqa: E731
        with self.tweak(self.c.config, explore_legend_chance=0.3), self.tweak(treasures, amount=fake):
            for k in range(4):
                emit(f"帶寶物 第 {k + 1} 擲", {"got": game._legend_find(), "items": game.state.player.legend_items})
        with self.tweak(self.c.config, explore_legend_chance=0.5):
            for seed in (1, 2, 3, 4):
                before = hashlib.sha256(repr(game.rng.getstate()).encode("utf-8")).hexdigest()[:12]
                emit(f"傳自己的亂數 {seed}", {"got": game._legend_find(rnd.Random(seed)), "own_rng_untouched": before == hashlib.sha256(
                    repr(game.rng.getstate()).encode("utf-8")).hexdigest()[:12]})

    def grades(self) -> None:
        """每一處的分級（官軍、黃巾、散人各看一次：自己人不算對手）、輿圖詳情最後那一句。"""
        for who in self.WHO:
            game = self.game(who)
            emit(f"{who} 每一處的分級", {i: game._practice_tier(x) for i, x in sorted(self.c.locations.items())})
        spot = self.field()
        for who in self.WHO:
            status, view = self.call(who, "GET", f"/api/map?place={spot or ''}")
            game = self.game(who)
            emit(f"{who} 詳情", {"detail": view.get("detail") if isinstance(view, dict) else status,
                                 "text": game.place_detail(spot) if spot else None})

    def hut(self) -> None:
        """草廬（不帶、weekend）：遇險、拜師、看修練頁，按探索；破境丹的機率擺到 1，序章裡也不撿。**前半停在這一張卡上**。"""
        who = self.NEWBIE
        view = self.main(who)
        if not view.get("prologue"):
            emit("這一季沒有序章", None)
            self.settle_choices(who)
            return
        self.choose(who, "choice:0")
        self.choose(who, "choice:0")
        self.do(who, "view_tab", {"tab": "practice"})
        with self.tweak(self.c.config, explore_legend_chance=1.0):
            self.choose(who, "act:explore")
        self.me(who, "草廬探索這一下")
        self.show_legend(who, "草廬")
        view = self.main(who)
        emit("草廬卡上有哪些鈕", sorted(self.ids(view)))

    # ── 後半 ──

    def answer(self) -> None:
        """草廬那張卡：四景四選一挑最後一個（前半挑第一個的話這裡才有不一樣的路），或有所感版選第一個做法、順其自然。"""
        from tianxia.features.sense import sensing

        who = self.NEWBIE
        opts = self.options(who)
        picks = [i for i, o in opts.items() if i.startswith("choice:") and o.get("enabled")]
        if picks:
            self.choose(who, picks[-1])
        else:
            senses = [i for i, o in opts.items() if i.startswith("sense:") and i != sensing.LET_GO and o.get("enabled")]
            if senses:
                self.choose(who, senses[0])
            if sensing.LET_GO in self.options(who):
                self.choose(who, sensing.LET_GO)
        self.me(who, "草廬答完")
        self.show_legend(who, "草廬答完")
        self.main(who)

    def again(self) -> None:
        """接手之後：城外、官軍營寨、黃巾營寨各站一次再按探索。"""
        for who, loc in (("韓墨川", self.field()), ("蘇映秋", "huangjin_camp"), ("杜遠山", "guan_camp")):
            if loc is None or loc not in self.c.locations:
                continue
            self.stand(who, loc, "接手之後")
            self.explore(who)
            self.me(who, "接手之後探索")


register_track("roam", RoamScenario, (("tianxia/features/explore/explore_base.py", "tianxia/engine.py"), ('一枚——{cfg.legend_item_note}', '一枚——{cfg.legend_item_note}！')), "week7")
