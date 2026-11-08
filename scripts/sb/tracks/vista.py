"""same_behavior 一軌一檔：vista（這一檔登記 vista）。"""
from __future__ import annotations

import random

from sb.harness import ADMIN, emit, register_track
from sb.tracks.stack import StackScenario

# core_scene（第二輪第 91 批「場景卡收接縫」）：這一整檔是第 91 批加的，既有的軌一個字不動。
# stack 一軌把選單接管的先後疊滿再剝，順便走過頭目戰、擂台、有所感、答題、談著、投靠、叛投、求見、答話、在路上的場景與圖；它疊不到的是宴席、取名、
# 喊停、作廢的欄位，和「場景文字與圖各問各的」錯開的那幾格（圖靠 _own_scene_text != location_text 判斷，排錯整張圖不見）。這一軌只補這些。


class VistaScenario(StackScenario):
    """場景卡一軌（第二輪第 91 批；--track vista，自己一個資料庫）。借 stack 的站位（自家大本營、補上標籤、組一條答題的線）與小工具。每一層先「沒同步就讀」場景那五支
    （Game 一開就讀 _own_scene_text、scene_text、scene_art、location_text、place_state_view，丟什麼也寫進輸出），再打一次 /api/main。

    前半切在 pile：柳聞笛、白露行疊滿了還沒有任何一下請求讀過。後半新程式第一次讀（實跑讀過輸出）：
    - peel_own：柳聞笛照場景的先後剝。season21、week7 走到事件（事件的圖）→ 頭目戰 → 擂台（沒有圖）→ 宴席那一層（在路上敬不了酒，文字是底下的有所感，圖沒有）→ 有所感（沒有圖）→
      取名、答題（文字是這一張，圖卻是底下談著那個人的像：圖的判斷不看這兩層）→ 談著（人像）→ 還沒挑邊 → 投靠 → 叛投 → 求見（交友那張）→ 答話 → 在路上 → 喊停了（都沒有圖）→ 地點（地點的圖）。
    - peel_seated：白露行不在路上，宴席的文字走得到：擂台之下、有所感之上。
    - stale：鄭停舟一支一支擺作廢的。宴席散了：文字是地點、圖沒有（又談著也沒有），打一次畫面同步收掉才回地點的圖。取名的意境不在了：文字是空字串（空的也算接管，不往下掉），
      又談著時圖是人像。有所感、答題、答話、談著、投靠、叛投的作廢值：文字掉到地點、圖是地點的圖（談著、投靠、叛投那三個 Game 一開就收掉，走不到丟 KeyError 的那一下）。談著的人沒有像（卜己）：文字是談話、圖沒有。
    - machines：同 stack，兩位假人疊著 BotRunner 輪過，再讀一次場景（景甲坐在許劭的宴席上、景乙在答話；測試內容沒有陣營，假人不上線）。
    - closing：顧南枝疊著事件、談著、答話。收季之前是事件的圖；收季之後第一季規則的季文字寫地點，測試內容寫結局那兩行（「## 風雨飄搖」），圖都沒有。

    **這一軌走不到的**（實跑數過）：全服決戰蓋在場景上（start_showdown 這時候開不了；season21 開季頭一段 setup 的 /api/main 走到「戰場接在事件上面、圖沒有」；開打後在場上的人戰場整個取代畫面，這一軌不走，暫存比對擺過）；
    測試內容沒有頭目戰、有所感、取名、陣營、答話，宴席關著（擺了不接管，文字往下掉、圖沒有），求見擺了一讀就收，事件沒寫圖；場景各支直接丟 KeyError、LookupError 的那幾格（Game 一開就收，
    只有第 91 批的暫存比對把欄位直接擺在 Game 上才碰得到）。"""

    TOPPER, SEATED, STALER, CLOSER = "柳聞笛", "白露行", "鄭停舟", "顧南枝"
    BOT_SEATS = ["景甲", "景乙"]
    PHASES_FIRST = ["setup", "seat", "pile"]
    PHASES_SECOND = ["resume", "peel_own", "peel_seated", "stale", "machines", "closing"]
    OWN_ORDER = ("event", "duel", "arena", "feast", "sense", "naming", "story", "talk", "ally", "faction", "defect", "audience", "asking", "road")
    SEATED_ORDER = ("event", "duel", "arena", "feast", "sense", "naming", "story", "talk")  # 在路上的人敬不了酒，宴席那一層要另一個人才看得到

    # ── 多疊的幾層 ──

    def gentry_id(self) -> str | None:
        return next((f.id for f in self.c.scenario.factions if f.allies), None)

    def road_path(self) -> list[str]:
        path = sorted(self.c.locations[self.spot].connections)[:1]
        return [*path, next(i for i in sorted(self.c.locations) if i not in (self.spot, *path) and not self.c.locations[i].prologue_only)]

    def open_feast(self, who: str) -> bool:
        from tianxia.features.feast import rules as feasts
        from tianxia.state import Feast

        host = "xushao" if "xushao" in self.c.characters else next(iter(sorted(self.c.characters)), "")
        if not host:
            return False
        seat = []

        def opened(s) -> None:
            s.feast_seq += 1
            seat.append(s.feast_seq)
            s.feasts.append(Feast(id=s.feast_seq, host=host, place=self.spot, start=s.time, end=s.time + 48 * feasts.HOUR))

        self.world.mutate_season(opened)
        self.edit(who, lambda p: setattr(p, "feasting", seat[0]))
        return True

    def put(self, who: str, name: str) -> bool:
        from tianxia.state import GodNaming, Journey

        if name == "feast":
            return self.open_feast(who)
        if name == "naming":
            god = next(iter(self.c.traits.god), None)
            if god is None:
                return False
            self.edit(who, lambda p: setattr(p, "god_naming", GodNaming(line="景", god=god.id, attribute=god.attribute, lean=god.lean, place=p.location)))
            return True
        if name == "ally":
            gentry = self.gentry_id()
            if gentry is None:
                return False

            def unsided(p):
                p.faction, p.ally = gentry, None

            self.edit(who, unsided)
            return True
        if name == "road":
            self.edit(who, lambda p: setattr(p, "journey", Journey(mode="walk", path=self.road_path(), arrive_at=[4.0e9, 4.1e9])))
            return True
        return super().put(who, name)

    def take_off(self, who: str, name: str) -> None:
        if name == "feast":
            self.edit(who, lambda p: setattr(p, "feasting", None))
        elif name == "naming":
            self.edit(who, lambda p: setattr(p, "god_naming", None))
        elif name == "ally":
            self.edit(who, lambda p: setattr(p, "ally", "guan") if self.gentry_id() is not None else None)
        elif name == "road":
            self.edit(who, lambda p: setattr(p, "journey", None))
        else:
            super().take_off(who, name)

    # ── 讀 ──

    def raw(self, who: str, tag: str) -> None:
        """不同步、不問選單，直接讀場景那五支（作廢的欄位還沒被清失效參照收掉；這一下丟什麼也算行為）。"""
        from tianxia.engine import Game

        self.begin()
        game = Game(self.c, self.chars.load(who), random.Random(5), self.world)
        row = {}
        for key, read in (("own", game._own_scene_text), ("scene", game.scene_text), ("art", game.scene_art), ("place", game.location_text), ("mood", game.place_state_view)):
            try:
                row[key] = read()
            except Exception as exc:  # noqa: BLE001
                row[key] = f"丟 {type(exc).__name__}"
        emit(f"{who} {tag} 沒同步就讀", row)
        self.server.GAMES.clear()

    def look(self, who: str, tag: str) -> None:
        self.raw(who, tag)
        try:
            self.main(who)
        except Exception as exc:  # noqa: BLE001
            emit(f"{who} {tag} /api/main 丟", type(exc).__name__)

    # ── 前半 ──

    def pile(self) -> None:
        """切點：疊滿了，後面沒有任何一下請求讀過。"""
        for who in (self.TOPPER, self.SEATED, self.STALER, self.CLOSER):
            self.enroll_at(who, "guan")
        self.stack(self.TOPPER, self.OWN_ORDER)
        self.stack(self.SEATED, self.SEATED_ORDER)

    # ── 後半 ──

    def peel_own(self) -> None:
        """照場景的先後一層一層剝；路上那一層多看一次喊停。"""
        who = self.TOPPER
        for name in self.OWN_ORDER:
            if name == "road":
                self.look(who, "最上面是 road")
                self.edit(who, lambda p: setattr(p.journey, "stop_at", 1))
                self.look(who, "最上面是 road（喊停了）")
            else:
                self.look(who, f"最上面是 {name}")
            self.take_off(who, name)
        self.look(who, "全部拿掉")

    def peel_seated(self) -> None:
        """宴席那一層：坐著的人（不在路上），頭目戰、擂台在上面，有所感、取名、答題、談著在底下。"""
        for name in self.SEATED_ORDER:
            self.look(self.SEATED, f"最上面是 {name}")
            self.take_off(self.SEATED, name)
        self.look(self.SEATED, "全部拿掉")

    def stale_rows(self) -> list[tuple[str, str, object]]:
        from tianxia.state import GodNaming, Sensing

        rows: list[tuple[str, str, object]] = [
            ("宴席已經散了", "feasting", 999999),
            ("有所感的場景不在了", "sensing", Sensing(location=self.spot, scene="無此景", order=[0])),
            ("取名的意境不在了", "god_naming", GodNaming(line="景", god="無此境", attribute="柔")),
            ("答題的線不在了", "story_open", "無此線"),
            ("答話的那一趟不在了", "fs_asking", "無此趟"),
            ("談著的人不在了", "pending_companion", "無此人"),
            ("投靠的那一軍不在了", "pending_faction", "無此軍"),
            ("叛投的那一軍不在了", "pending_defect", "無此軍"),
        ]
        plain = next((cid for cid, ch in sorted(self.c.characters.items()) if not ch.image), None)
        if plain is not None:
            rows.append(("談著的人沒有像", "pending_companion", plain))
        return rows

    def stale(self) -> None:
        """髒存檔一支一支擺：場景文字往下掉、圖的判斷照舊看欄位在不在。擺一層，再疊在談著的人底下看一次（談著的人有像時圖會是人像）。"""
        who = self.STALER
        talk = self.value_of(who, "talk")
        for tag, field, value in self.stale_rows():
            self.edit(who, lambda p, field=field, value=value: setattr(p, field, value))
            self.raw(who, tag)
            if talk is not None and field != "pending_companion":
                self.edit(who, lambda p: setattr(p, "pending_companion", talk))
                self.raw(who, f"{tag}，又談著")
                self.edit(who, lambda p: setattr(p, "pending_companion", None))
            self.look(who, f"{tag}（打一次畫面）")
            self.edit(who, lambda p, field=field: setattr(p, field, None))

    def machines(self) -> None:
        super().machines()
        if self.factions_on():
            for name in self.BOT_SEATS:
                self.raw(name, "假人輪過之後")

    def closing(self) -> None:
        """收季：第一季規則的季場景寫所在的地方，其餘寫結局那兩行；圖一律沒有。"""
        who = self.CLOSER
        for name in ("asking", "talk", "event"):
            self.put(who, name)
        self.look(who, "收季之前")
        self.do(ADMIN, "end_season")
        self.look(who, "收季之後")
        self.take_off(who, "event")
        self.take_off(who, "talk")
        self.take_off(who, "asking")
        self.look(who, "收季之後，都拿掉")


# 改一個字（selftest）：談著的人那張圖的 kind（第 2 段搬進人物情誼包 talk_actions.py，這一句一字不動；搬到別的檔就補這裡的檔清單）。
# 正式內容才有像，測試內容的人物沒有像、走不到這一句。
register_track("vista", VistaScenario, (("tianxia/engine.py", "tianxia/features/companions/talk_actions.py"),
                                        ('"kind": "figure"', '"kind": "figurf"')), "season21",
               covers=("admin", "battle", "bounties", "bout", "checkin", "companions", "craft", "cultivation", "explore", "faction",
                       "feast", "figure_acts", "gear", "looks", "map", "military", "outlets", "peers", "sense", "smithy",
                       "socialize", "sortie", "stamina_plays", "story", "tavern", "travel", "zhuan"))
