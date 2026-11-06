"""same_behavior 一軌一檔：battle（這一檔登記 battle、muster、progress）。"""
from __future__ import annotations

import contextlib
import hashlib
import os
import random
from pathlib import Path

from sb.base import Scenario
from sb.harness import ADMIN, CLOCK, CLOCK0, STEP, db_text, emit, register_track

# ═══════════════════════════ battle：決戰一軌（主動搬六包第 5 批 dev/battle-1、全部拆包第 6 批 dev/battle-2） ═══════════════════════════
# 全服決戰「看」那一半（畫面、戰報、補送、放手一搏補劇情）搬進 tianxia/features/battle/（計畫 docs/superpowers/plans/2026-10-31-決戰包-第1批.md）；
# 第 6 批接著搬管理者的決戰工具與攻城（計畫 2026-11-01-決戰包-第2批.md：BattleScenario 加 admin、siege_*、resting 幾段）。
# 第 7 批搬集結、投效、挑同伴（計畫 2026-11-01-決戰包-第3批.md：BattleScenario 加 muster_*、late、wander 幾段與 bots 那一段的大區外假人，
# 同一套段落另外登記成 muster 一軌、切在集結中）。
# 第 8 批搬推進與結算、generals、收季的收兵（計畫 2026-11-01-決戰包-第4批.md：三軌的放手一搏穿著絕招〔回合首功〕；另開 progress 一軌
# ProgressScenario：三場決戰三種收場、時間到了在排隊的那一場、假人出招、份量快照補上、管理者收季、季自然收掉、開下一季時收兵，切在打到第三回合）。
# 這一段整塊是決戰的：四條拆包線並行，接在檔尾、最後一行登記（register_track），PM 合的時候不跟別人的行穿插。


# develop 0425589a 之後才要的兩個固定（註冊限流、資料庫第 9 版 sessions 的 token_hash 抹掉）：這一塊原本自己套一份，
# 合 develop（2026-11-01）時 develop 已經放在共用那一層（Scenario.__init__、db_text），只留那一份。


BATTLE_RATE = 60  # 假模型評的放手一搏成功率（server.battle_text 的 B 段，battle_instance.score_gamble）
BATTLE_STORY = "{name}一聲長嘯，提刀衝進陣中。"  # 假模型補的劇情（server.narrate_once 的 B 段；不寫數字、成敗都是這一句）
BATTLE_ULT = {"move": "m7", "name": "大佛一掌", "look": "moying", "weapon": "劍"}  # 第 8 批：放手一搏的人身上那一招（回合首功演它）
BATTLE_SURE = "一擊必中"  # 第 8 批：放手一搏那一句有這幾個字，假模型評 100（推進一軌第三回合那一搏；決戰、集結兩軍的那兩句沒有，照舊 BATTLE_RATE）
_BATTLE_CLIENTS: dict[type, type] = {}


def _battle_client(base: type) -> type:
    """放手一搏評分、補劇情的假模型（base 是 _setup_child 換好的 client 類別）：GambleScore 回 BATTLE_RATE、TaleBatch 照單子上的名號
    每人一句 BATTLE_STORY，其餘照 base（丟連線錯誤、大場面判讀）。這兩種回答之前先把送來的提示整份寫進輸出（messages 與其餘參數）：
    假模型不看提示，單子上的幕（act_index）、陣營名、原句、點名、性別、成敗改了，回的還是同一句，不寫進輸出就比不出來（審查 should；
    提示由 battle_instance.score_gamble／write_tales 照 view.battle_text_request／battle_tale_request 開的單子組，兩份程式組法一樣）。"""
    if base not in _BATTLE_CLIENTS:
        import re

        class BattleClient(base):
            def chat_structured(self, messages, schema, *a, **k):
                if schema.__name__ in ("GambleScore", "TaleBatch"):
                    emit(f"模型單子 {schema.__name__}", {"messages": messages, "rest": repr((a, sorted(k.items())))})
                if schema.__name__ == "GambleScore":  # 第 8 批：那一句寫了 BATTLE_SURE 的評 100（一定成：回合首功那一回合走得到）
                    return schema(success_rate=100 if BATTLE_SURE in messages[-1]["content"] else BATTLE_RATE)
                if schema.__name__ == "TaleBatch":
                    names = re.findall(r"^\d+\. (.+?)（", messages[-1]["content"], re.M)
                    return schema(lines=[{"name": n, "story": BATTLE_STORY.format(name=n)} for n in names])
                return super().chat_structured(messages, schema, *a, **k)

        _BATTLE_CLIENTS[base] = BattleClient
    return _BATTLE_CLIENTS[base]


def _still(phase):
    """第 7 批插進來的段落（BattleScenario.still）：這一段裡的每一個請求，決戰與攻城的期限都跟著時鐘往後挪那一步。"""

    def run(self, *a, **k):
        with self.still():
            return phase(self, *a, **k)

    run.__name__, run.__doc__ = phase.__name__, phase.__doc__
    return run


class BattleScenario(Scenario):
    """全服決戰「看」那一半（主動搬六包第 5 批；--track battle，自己一個資料庫）。照 plan.json order 4 的 behavior_check：管理者開季、
    開戰（不帶設定：start_battle 黃巾決戰；weekend、season21、week7：start_showdown 長社火攻）；官軍、黃巾、豪強、散人各一人擺在決戰的大區，
    集結中看畫面（場景、戰局條、選單）、加入（兩軍 battle:join、散人與豪強照引擎給的鈕 join 或 enlist）；集結截止開打；第一回合官軍放手一搏
    （/api/do/battle_text，假模型評 BATTLE_RATE）、散人掛機到逾時、其餘出招——**這裡切一半**（那一回合結算了、劇情還沒補：
    批次表「舊程式寫到一半」）；後半重新登入，server.narrate_once 補劇情（假模型），打到收場（第二幕黃巾再搏一次、再補一次）；每個人打
    /api/main 收補送（江湖紀錄、戰報、軍餉、行狀、戰功）、/api/reports 與 ?id=；一位的決戰戰報從存檔拿掉、showdowns_restored 歸零，下一次
    同步補回來（RESTORED_NOTE，照收場時刻排進兩筆尋常的戰報中間）；伺服器假人（BotRunner）打另一場、整季機器人（week7）帶一場；收季、
    開下一季（battle_results_seen 照帶），那一場收場之後還沒同步過的假人換季之後才補到（上一季那一支）。季終收兵那一支（unfinished）
    走不到（時刻表的季開不出第三場：長社、廣宗開過了，宛城要等第 3 週那件大事結算才知道是哪一版），由 tianxia/features/battle/tests/test_showdown_delivery.py 守。
    序章裡的那一位（NEWBIE）一路看：序章不畫戰場。測試內容沒有決戰：同一串 API 照打（證明關著一個字都不變），假人那一段略過。

    第 6 批（決戰「打」a：管理者的決戰工具與攻城，dev/battle-2；計畫 docs/superpowers/plans/2026-11-01-決戰包-第2批.md）插進來的段：
    admin（開戰之前按得到的被拒）、admin_trial（第 5 批那一場收場之後：開了再取消，與那時候按得到的被拒）——管理者的決戰工具一樣一樣按，
    成的與被拒的各一次；siege_*（地盤開著的 weekend、season21、week7：六場攻城，見 SIEGES；none、test 沒有地盤，那幾段什麼都不打）；
    resting（收季之後再按一輪，season 那一段裡）。前半照舊停在 gamble：同一刻兩場攻城（A、B）打了一兩回合、還沒收場（round 接一行
    siege_round：決戰每一回合攻城的真人也各出一招）——後半由 head 打完兩場攻城、結算、補送。

    第 7 批（決戰「打」b：集結、投效、挑同伴，dev/battle-3；計畫 docs/superpowers/plans/2026-11-01-決戰包-第3批.md）插進來的段：muster_seat（六位新人
    MUSTER_PLAYERS 直接建進資料庫再登入、擺位置；秦朗月、顧長風、莫問天、石破浪名下各一位同伴）、muster_pick（挑同伴與「再想想」、臨時投效再改投、同一個
    大區兩場打得進去時照 @流水號加入——潁汝多一場攻城 G、集結被拒的路）、muster_more（顧長風挑好同伴加入、江映雪投靠豪強之後集結名單跟著換邊）、
    late（開打之後：停在挑同伴的才挑〔改成晚到〕、晚到、晚到臨時投效、再按另一邊被擋）、wander（參戰者走出大區、喊停）、muster_deliver（同伴回江湖、
    情誼減半、同一次同步清記號）；bots 那一段多一位名下有同伴、站在大區外的官軍假人（趕路、挑同伴的分數）。這一軌照舊切在 gamble；同一套段落另外
    登記成 muster 一軌（MusterScenario），切在 muster_pick 之後——舊程式寫到兩位按了加入、停在挑同伴（escort_pick 寫進存檔）就停，新程式接著挑。
    第 7 批插進來的請求不吃決戰與攻城的時間（審查 should：原本吃掉集結那 30 分鐘與第一回合的 180 秒——season21 的長社火攻在 muster_more 裡就開打、
    第一幕全是逾時；weekend、week7 的第一回合在 late 裡逾時，放手一搏落到第二回合）：上面那幾段（_still）、narrate 裡新人的重新登入、名下有第 7 批
    給的同伴的人按「不派」那一下，每一步之前把決戰與攻城的期限往後挪那一步（still、hold），G 在 muster_more 最後取消；第 5、6 批的集結截止、
    開打那一刻與每一回合的逾時照那幾段原本的請求算，跟第 6 批的情境一樣（有決戰的四種設定逐回合比過：哪幾回合逾時、第幾回合換幕、兩次放手一搏
    落在哪一回合、第九回合收場，都跟第 6 批那一版一樣；收場的勝負照多出來的參戰者變了）。第 7 批的人加入之後不出招（第一回合逾時代為固守，之後不再等他們），出招的照舊是第 5 批那三位與攻城的真人。gamble 開頭、
    siege_start 開頭、muster_more 最後各驗一次（expect）：放手一搏打的是第一回合、攻城截止之前決戰還在集結，不成立就停。"""

    PLAYERS = {"秦朗月": "guan", "韓雲起": "huang", "柳青崖": "haoqiang", "葉寒舟": None}
    NEWBIE = "白小樓"  # Scenario.setup 註冊、不略過引導的那一位
    GAMBLER, LATE_GAMBLER, IDLER = "秦朗月", "韓雲起", "葉寒舟"
    # 伺服器假人：兩軍各二，擺在第二場決戰的大區（bots 那一段）
    BOT_SEATS = [("假戊", "guan"), ("假己", "guan"), ("假庚", "huang"), ("假辛", "huang")]
    # 第 6 批：六場攻城（名字：(攻方, 地點)）。A 官軍攻中立的南陽官道：守將（那裡最強的一路隊伍）守住；B 黃巾攻官軍的涿郡：攻下、易手；
    # C 集結中管理者取消（_cancel_siege）；D 集結中收季（_shelve_siege）；E 伺服器假人那一場：黃巾守住自己的新野（守城軍令記一次，_siege_guards）；
    # F 黃巾攻官軍的洛陽官道、那一區沒有人、一個人都沒到：作罷（siege.void_absent 之後照樣經 _settle_siege）。結果是跑出來的（照兩份程式同一套
    # 亂數），寫在這裡是情境走到哪幾支：守將守住、攻下易手、陣營守住、作罷、取消、季終收兵。每一場自己一個大區（D 在決戰收場之後才開）：同一個
    # 大區兩場以上一起集結的話加入鈕帶 @流水號，第 5 批那幾位的加入會被改掉
    SIEGES = {"A": ("guan", "nanyang_road"), "B": ("huang", "zhuo_county"), "C": ("huang", "xiaquyang"), "D": ("guan", "runan_wilds"),
              "E": ("guan", "xinye"), "F": ("huang", "luoyang_road"),
              "G": ("huang", "hilltop_wilds")}  # 第 7 批：決戰的大區（潁汝）裡多一場，黃巾與散人在那一區看得到兩場（加入鈕帶 @流水號）
    # 攻城的真人（名號：(陣營, 哪一場, 每一回合出哪一招)）：A 兩位官軍攻、一位散人助守【守軍】；B 黃巾一位攻（固守）、官軍一位守（強攻）；C 黃巾一位
    SIEGE_PLAYERS = {"程破軍": ("guan", "A", "強攻"), "方定遠": ("guan", "A", "奇襲"), "孟無涯": (None, "A", "固守"),
                     "杜飛沙": ("huang", "B", "固守"), "季長安": ("guan", "B", "強攻"), "譚小滿": ("huang", "C", "強攻")}
    SIEGE_BOT_SEATS = [("假壬", "guan"), ("假癸", "guan"), ("假子", "huang"), ("假丑", "huang")]  # E 那一場的假人：兩軍各二
    # 戰書緊接在開戰之後下（siege_open）、攻城的真人之後才建（siege_seat）：攻城的集結截止跟決戰的差不到一分鐘，siege_start 把時鐘推過攻城的截止時
    # 決戰才剛開打（season21 的長社火攻開季就開了集結、截止得更早，一樣在這一下開打）——決戰第一回合照第 5 批的樣子在 gamble 打
    # （第 7 批插進來的段落照 still 不吃這段時間；gamble 開頭 expect 驗）
    # 第 7 批：六位新人（名號：(陣營, 擺在哪)）。region＝那一場決戰的大區（spot）、hilltop＝荒丘（同一個大區，G 那一塊）、away＝那一場決戰的大區外（away_spot）。
    # 顧長風按加入、挑同伴、再想想、再按加入停在挑，後半才挑；莫問天按加入停在挑，開打了才挑（改成晚到）；江映雪（散人）臨時投效官軍再改投黃巾，
    # 後半到曹氏莊院投靠豪強；石破浪在荒丘看得到兩場、先按 G 那一場的 @ 停在挑同伴、再想想，照 @流水號加入決戰；嚴不悔、沐晚晴集結時在大區外，開打之後才到（晚到、晚到臨時投效）
    MUSTER_PLAYERS = {"顧長風": ("guan", "region"), "莫問天": ("guan", "region"), "江映雪": (None, "region"), "石破浪": ("huang", "hilltop"),
                      "嚴不悔": ("huang", "away"), "沐晚晴": (None, "away")}
    # 名下各一位同伴（秦朗月集結時照舊按「不派」：muster 那一段本來就這樣按；石破浪是審查之後加的：先按 G 那一場停在挑、再想想）
    ESCORTERS = ("秦朗月", "顧長風", "莫問天", "石破浪")
    AWAY_BOT = ("假寅", "guan")  # bots 那一段：名下一位同伴、站在大區外的官軍假人
    PHASES_FIRST = ["setup", "join", "seat", "look", "admin", "open", "siege_open", "siege_seat", "muster_seat", "muster", "muster_pick",
                    "muster_more", "siege_muster", "siege_cancel", "siege_start", "start", "late", "gamble"]
    PHASES_SECOND = ["narrate", "wander", "fight", "siege_end", "deliver", "muster_deliver", "reports", "restore", "admin_trial", "siege_after",
                     "bots", "siege_bots", "siege_shelve", "season"]

    def __init__(self, root: Path, profile: str, db: Path):
        super().__init__(root, profile, db)
        from tianxia import ollama_client

        inner = ollama_client.OllamaClient.from_config.__func__  # _setup_child 換好的那一層（不連網路、大場面判讀）

        def from_config(cls, cfg):
            client = inner(cls, cfg)
            client.__class__ = _battle_client(type(client))
            return client

        ollama_client.OllamaClient.from_config = classmethod(from_config)
        # 第 8 批：放手一搏送出那一刻身上穿著絕招（形象包 actions.battle_ult；同 test_looks_mvp 換掉它的做法）——兩位放手一搏的人有一招，
        # 成了的那一回合挑回合首功（Game._advance_battle_round 包著 _round_mvp：回合紀錄多一行、畫面多 battle_mvp）。兩份程式都換同一個
        from tianxia.features.looks import actions as looks_actions

        wearers = {self.GAMBLER, self.LATE_GAMBLER}
        looks_actions.battle_ult = lambda ctx: dict(BATTLE_ULT) if ctx.state.player.name in wearers else None
        self.late_done = False
        self.stills = 0  # still() 疊了幾層：大於 0 時每一個請求都是第 7 批插進來的（begin 先挪期限）

    # ── 小工具 ──

    STEP_SECONDS = 10.0  # 這一軌一步只推十秒：決戰一回合最多等 180 秒（round_seconds），一步一分的話出招的請求還沒送齊回合就逾時了

    def begin(self) -> None:
        """同 Scenario.begin，只是一步 STEP_SECONDS（十秒）；同約戰那一軌，每個請求換一份空的勝算記憶（前半＋後半是兩個行程，集結中那幾位
        選單上的勝算字才對得上）。第 7 批插進來的請求（still 裡）先把決戰與攻城的期限往後挪這一步（hold）。"""
        STEP[0] += 1
        if self.stills:
            self.hold()
        CLOCK[0] = CLOCK0 + STEP[0] * self.STEP_SECONDS
        random.seed(STEP[0])
        self.server.GAMES.clear()
        from tianxia import team

        self.server.ODDS_MEMO = team.OddsMemo()

    def skip(self, steps: int) -> None:
        STEP[0] += steps
        emit(f"時鐘推過 {steps} 步", None)

    def expect(self, ok: bool, what: str) -> None:
        """情境自己驗的前提：不成立就停、不往下比（審查 should：第 7 批插進來的段落吃掉了集結的時間，第 5、6 批決戰那一段的節奏悄悄變了，
        base 與 head 跑同一套段落，比對照樣相等，看不出來）。"""
        if not ok:
            raise RuntimeError(f"情境的前提不成立（第 {STEP[0]} 步）：{what}")

    @contextlib.contextmanager
    def still(self):
        """這一段裡的請求是第 7 批插進來的（審查 should）：決戰與攻城的時鐘不走——每一步之前把期限往後挪那一步（hold），集結截止與每一回合的
        逾時照第 5、6 批那幾段的請求算，跟沒有這幾段時一樣（集結那 30 分鐘、一回合 180 秒放不下第 7 批的幾十個請求：season21 的長社火攻
        開季就開了集結、截止最早，原本在第 7 批的段落裡就開打了；late 那九個請求排在開打與放手一搏之間，第一回合在 late 裡逾時）。"""
        self.stills += 1
        try:
            yield
        finally:
            self.stills -= 1

    def hold(self) -> None:
        """還沒收場的決戰與攻城：期限往後挪一步（battle_instance.shift_deadlines，管理者暫停再繼續的同一個做法：集結中挪集結截止、開打了挪這一回合
        開放的時間）。賽季的時鐘照走。都收場了（或還沒開）什麼都不寫。"""
        from tianxia import battle_instance

        b = self.world.get_battle()
        if (b is None or b.phase == "ended") and all(s.phase == "ended" for s in self.world.get_sieges()):
            return

        def fn(state) -> None:
            for x in ([state.active_battle] if state.active_battle is not None else []) + list(state.sieges):
                battle_instance.shift_deadlines(x, self.STEP_SECONDS)

        self.world.mutate(fn)

    def relogin(self, who: str) -> None:
        """同 Scenario.relogin；第 7 批的新人（MUSTER_PLAYERS）重新登入那一下照第 7 批插進來的請求算（still：narrate 那一段的 login_all）。"""
        with self.still() if who in self.MUSTER_PLAYERS else contextlib.nullcontext():
            super().relogin(who)

    def no_escort(self, who: str) -> None:
        """有挑同伴那一步就按「不派」。名下的同伴是第 7 批給的（ESCORTERS）：那一下照第 7 批插進來的請求算（still）。"""
        if "battle:escort:none" in self.ids(self.main(who)):
            with self.still() if who in self.ESCORTERS else contextlib.nullcontext():
                self.choose(who, "battle:escort:none")

    def skip_past(self, deadline: float) -> None:
        """時鐘推到下一個請求剛過 deadline（begin 的時刻是 CLOCK0 + 步數 × STEP_SECONDS）。"""
        self.skip(max(0, int((deadline - CLOCK0) // self.STEP_SECONDS) - STEP[0]))

    def target(self) -> tuple[str, str]:
        """管理者開的那一場：(管理者工具, 決戰 id)。"""
        return ("start_battle", "huangjin_showdown") if self.profile in ("none", "test") else ("start_showdown", "changshe_fire")

    def second(self) -> tuple[str, str]:
        """假人打的第二場（bots 那一段）：不帶設定照樣是黃巾決戰（收場了可以再開），時刻表的季開廣宗（另一個大區）。"""
        return ("start_battle", "huangjin_showdown") if self.profile in ("none", "test") else ("start_showdown", "guangzong")

    def spot(self, battle_id: str) -> str | None:
        """那一場決戰的大區裡挑一處（長社在潁汝就站長社，不然照 id 排第一個）；這份內容沒有那一場是 None。"""
        from tianxia import atlas

        definition = self.c.battles.get(battle_id)
        if definition is None or definition.region is None:
            return None
        spots = sorted(i for i in self.c.locations if (r := atlas.region_of(self.c, i)) is not None and r.id == definition.region)
        return "changshe" if "changshe" in spots else (spots[0] if spots else None)

    def battle_row(self, tag: str) -> None:
        """共用狀態裡那一場決戰此刻的樣子（整份的雜湊與看得懂的那幾格；整份資料庫每一段另有雜湊）。"""
        from tianxia import battle_instance

        b = self.world.get_battle()
        if b is None:
            emit(f"決戰 {tag}", None)
            return
        emit(f"決戰 {tag}", {
            "id": b.battle_id, "record": b.record_id, "phase": b.phase, "round": b.round_number, "act": b.act_index,
            "outcome": [b.outcome_title, b.outcome_side, b.outcome_margin], "tales": [[t.round, t.name, t.won] for t in b.tales],
            "log": len(b.narrative_log), "unfinished": b.unfinished,
            "who": {n: [q.faction, q.eliminated, battle_instance.idle(q), q.acted_rounds] for n, q in sorted(b.participants.items())},
            "sha": hashlib.sha256(b.model_dump_json().encode("utf-8")).hexdigest()})

    def me(self, who: str, tag: str) -> None:
        """存檔裡決戰補送動到的那幾格：銀兩、經驗、名望、心得、這一季參戰幾場與首功、補過的決戰、戰報、行狀、最近的紀錄標題。"""
        state = self.chars.load(who)
        if state is None:
            emit(f"{who} {tag}（沒有這個人）", None)
            return
        p = state.player
        emit(f"{who} {tag}", {
            "stats": dict(sorted(p.stats.items())), "level": p.member.level, "exp": p.member.exp, "points": p.stat_points,
            "showdowns": p.showdowns, "top_merits": p.top_merits, "seen": p.battle_results_seen, "restored": p.showdowns_restored,
            "card": state.battle_card,
            "battles": [[r.id, r.kind, r.event, r.tier, r.side, r.notes, r.changes, r.gauge, len(r.log), r.battle_ref] for r in state.battles],
            "annals": [a.model_dump(mode="json") for a in p.annals][-6:], "journal": [e.title for e in state.journal][:10]})

    def join_pick(self, who: str, ids: dict[str, dict]) -> str | None:
        """集結時這個人按哪一顆：自己陣營的 battle:join；散人臨時投效官軍、豪強臨時投效黃巾（豪強分屬兩軍的季照引擎給的 join）。"""
        side = self.PLAYERS.get(who)
        live = sorted(i for i, o in ids.items() if (i.startswith("battle:join:") or i.startswith("battle:enlist:")) and o.get("enabled"))
        for want in (f"battle:join:{side}", "battle:enlist:guan" if side is None else "battle:enlist:huang"):
            if want in live:
                return want
        return live[0] if live else None

    def round(self, gamblers: dict[str, str]) -> None:
        """一回合：gamblers 裡的人放手一搏（/api/do/battle_text），掛機的那一位不按，其餘照回合數挑三招之一；回合沒結（第一回合在等掛機的）
        就把時鐘推過這一回合的期限、再輪詢一次（逾時代為固守，之後不再等他）。"""
        b = self.world.get_battle()
        if b is None or b.phase != "active":
            return
        n = b.round_number
        for who in self.PLAYERS:
            if who == self.IDLER:
                continue
            if who in gamblers:
                self.do(who, "battle_text", {"text": gamblers[who]})
                continue
            moves = sorted(i for i, o in self.ids(self.main(who)).items() if i.startswith("battle:act:") and o.get("enabled"))
            if moves:
                self.choose(who, moves[n % len(moves)])
        self.siege_round()  # 第 6 批：同時在打的攻城，攻城的真人也出這一回合（沒有開打中的攻城什麼都不打）
        b = self.world.get_battle()
        if b is not None and b.phase == "active" and b.round_number == n:
            self.skip_past(b.round.opened_real + self.c.battles[b.battle_id].round_seconds)
            self.main(self.GAMBLER)
        self.battle_row(f"第 {n + 1} 回合之後")

    def tell(self, tag: str) -> None:
        """放手一搏的劇情：照伺服器出了鎖之後的那一條（server.narrate_once：A 鎖內開單、B 鎖外假模型一整批寫、C 鎖內補），寫到沒有等著的。"""
        for _ in range(4):
            self.begin()
            got = self.server.narrate_once(self.server.game_for(self.GAMBLER))
            emit(f"{tag}：補了幾句", got)
            if got is None:
                break
        self.main(self.GAMBLER)

    # ── 情境 ──

    def seat(self) -> None:
        """四個人擺在那一場決戰的大區（體力補滿、過了新手期）。這份內容沒有那一場（測試內容）就照原地補體力。第二幕放手一搏的那一位
        是女子（Scenario.setup 一律建男的）：補劇情的單子上有「女子」那一格，提示寫進輸出之後性別改了才比得出來。"""
        loc = self.spot(self.target()[1])
        for who in self.PLAYERS:
            self.place(who, loc)
        self.edit(self.LATE_GAMBLER, lambda p: setattr(p, "gender", "女"))
        emit(f"{self.LATE_GAMBLER} 改成女子", None)

    def look(self) -> None:
        """開戰之前：畫面上沒有戰局條、沒有攻城條、輸入框是空的；戰報頁是空的。"""
        for who in [*self.PLAYERS, self.NEWBIE]:
            self.main(who)
        self.call(self.GAMBLER, "GET", "/api/reports")
        self.do(self.GAMBLER, "battle_text", {"text": "火燒連營"})  # 沒有決戰：送不出去、模型一次都不叫

    def open(self) -> None:
        op, battle_id = self.target()
        self.do(ADMIN, op, {"id": battle_id})
        self.battle_row("開了集結")

    def muster(self) -> None:
        """集結中：每個人先看一次（集結中、選陣營加入）、按加入（有挑同伴那一步就不派），再看一次（你已加入、職位、還剩幾分）。"""
        for who in self.PLAYERS:
            pick = self.join_pick(who, self.ids(self.main(who)))
            emit(f"{who} 集結時按的", pick)
            if pick is None:
                continue
            self.choose(who, pick)
            self.no_escort(who)  # 秦朗月名下有第 7 批給的同伴：按「不派」那一下照第 7 批插進來的請求算
        for who in [*self.PLAYERS, self.NEWBIE]:
            self.main(who)
        self.battle_row("集結中")

    def start(self) -> None:
        """集結截止：第一個輪詢的人把它推到開打（options 順便推進、一次請求只推一次）；每個人看開打的畫面（回合、三招的份量、輸入框）。"""
        b = self.world.get_battle()
        if b is not None and b.phase == "muster":
            self.skip_past(b.muster_deadline_real)
        for who in [*self.PLAYERS, self.NEWBIE]:
            self.main(who)
        self.battle_row("開打")

    def gamble(self) -> None:
        """第一回合：官軍放手一搏、散人掛機（回合等到逾時、代為固守）、其餘出招；這一回合結算之後劇情還沒補（場景上是固定句，等
        narrate_once）——前半停在這裡。這一回合是第一回合（第一幕、還沒有一回合逾時），不然就停。"""
        b = self.world.get_battle()
        self.expect(b is None or (b.phase == "active" and b.round_number == 0 and b.act_index == 0),
                    "放手一搏打的是第一回合" + ("" if b is None else f"（此刻 {b.phase}、第 {b.round_number + 1} 回合、第 {b.act_index + 1} 幕）"))
        self.round({self.GAMBLER: "火燒連營，直搗敵陣"})
        self.main(self.GAMBLER)

    def narrate(self) -> None:
        self.login_all()
        self.tell("第一回合補劇情")

    def fight(self) -> None:
        """打到收場：第二幕的第一回合黃巾放手一搏、有等著補的劇情就補；其餘照回合數出招，掛機的一直不按。"""
        for _ in range(40):
            b = self.world.get_battle()
            if b is None or b.phase != "active":
                break
            gamblers = {}
            if b.act_index >= 1 and not self.late_done:
                gamblers, self.late_done = {self.LATE_GAMBLER: "繞到敵後，放火燒糧"}, True
            self.round(gamblers)
            b = self.world.get_battle()
            if b is not None and b.tales:
                self.tell(f"第 {b.round_number} 回合補劇情")
        self.battle_row("收場")

    def deliver(self) -> None:
        """收場之後每個人打 /api/main：下一次同步把那一場補到自己手上（江湖紀錄、戰報、軍餉、名望、行狀、戰功；「剛剛」是那一場的卡片與
        收場那一刻的戰局條）。序章裡的那一位不在名單上，什麼都不補。第一位要經同步才補到那一場的人（crossing_who）同步之前先擺 crossing
        （核心收接縫，全部拆包第 11 批）。"""
        who_x = self.crossing_who()
        for who in [*self.PLAYERS, self.NEWBIE]:
            if who == who_x:
                self.crossing(who)
            self.main(who)
            self.me(who, "收補送之後")

    def crossing_who(self) -> str:
        """名單上第一位還沒補到收場那一場的人：自己最後一手收了場的那一位在 _battle_choose 那一下就補了（_settle_showdown 叫補送，不經
        sync；第 11 批審查：原本擺在秦朗月身上，他那一則「長社火攻」不是 deliver_results 那一格補的，挪動那一格比不出差），其餘參戰的人
        要等自己下一次同步，才經 sync 的 deliver_results 補到。內容裡沒有決戰（測試內容）照舊是秦朗月。"""
        b = self.world.get_battle()
        if b is not None and b.phase == "ended":
            for who in self.PLAYERS:
                state = self.chars.load(who)
                if who in b.participants and state is not None and b.record_id not in state.player.battle_results_seen:
                    return who
        return self.GAMBLER

    def crossing(self, who: str) -> None:
        """同一次同步收好幾包的補送（核心收接縫，全部拆包第 11 批；計畫 docs/superpowers/plans/2026-11-01-核心收接縫.md 1.3）：收場之後
        這個人（crossing_who：還沒補到那一場、這一下同步才經 deliver_results 補到的那一位）同步之前，季上替他擺一筆護衛補帳（還在 engine
        的 _deliver_guard_credits）、一則酒肆的風聲、一張他雇的過期殺手單。那一下同步依序補：決戰的補送（決戰包，deliver_results 的位置：
        補份量快照之後、玉璽碎片之前）→ 護衛 → 風聲、殺手單（酒肆包，deliver_notices 的位置：護衛之後、領地爭奪換天之前）。deliver 那一行
        me 的江湖紀錄標題看得出三格的先後：決戰的補送挪過護衛、挪到酒肆後面，酒肆那三個挪過護衛、挪到決戰前面，都抓得到；沒越過護衛的
        看不出來（決戰的補送只在補份量快照與護衛之間挪、越過玉璽碎片與改名那幾格，它們這一下什麼都不寫）。三個 deliver 不看酒肆開關，
        測試內容沒有酒肆也照擺照送；測試內容沒有決戰，只看得出護衛與酒肆兩格。"""
        from tianxia import figure_aid
        from tianxia.characters import name_key
        from tianxia.state import TavernHit, Whisper

        other = self.LATE_GAMBLER if who == self.GAMBLER else self.GAMBLER
        state = self.chars.load(who)
        place = state.player.location if state is not None else self.c.scenario.start_location
        now = CLOCK0 + STEP[0] * self.STEP_SECONDS

        def fn(s) -> None:
            s.guard_credits.setdefault(who, []).append(figure_aid.CREDIT_LINE.format(name="某人", who=other))
            s.tavern_whispers.setdefault(name_key(who), []).append(Whisper(kind="seek", who=other, place=place, time=s.time, named=True))
            s.tavern_hit_seq += 1
            s.tavern_hits.append(TavernHit(id=s.tavern_hit_seq, client=who, target=other, tier=0, price=20, place=place,
                                           placed_real=now - 7200, until_real=now - 60))

        self.world.mutate_season(fn)
        emit(f"季上替{who}擺一筆護衛補帳、一則風聲、一張過期的殺手單（同一下同步收三個位置的補送）", place)

    def reports(self) -> None:
        """戰報頁：列表、預設那一筆（決戰的完整戰況與收場那一刻的戰局條）、再點最舊的那一筆——這時每個人只有那一場決戰一筆，點的就是
        預設那一筆；列表裡決戰排在最上面、補回來的照時刻排進去，在 restore 那一段擺了兩筆尋常的戰報才走得到（審查 nit）。"""
        for who in self.PLAYERS:
            _, data = self.call(who, "GET", "/api/reports")
            rows = [r["id"] for r in data.get("list", [])] if isinstance(data, dict) else []
            for rid in rows[-1:]:
                self.call(who, "GET", f"/api/reports?id={rid}")

    def restore(self) -> None:
        """被洗掉的決戰戰報補回來（_restore_showdowns，一季查一次）：官軍那一位的決戰戰報從存檔拿掉、showdowns_restored 歸零，下一次同步
        照 battles 表重建一筆（軍餉與名望不再發，RESTORED_NOTE）。拿掉的同時擺兩筆尋常的戰報（收場前後各一分鐘）：補回來的那一筆要照
        收場時刻排進兩筆中間（restore_showdowns 的 sort），戰報頁的列表決戰排最上面，再點最舊的那一筆（審查 nit：原本每人只有一筆）。"""
        from tianxia import battlelog
        from tianxia.state import BattleRecord

        with self.world.action_lock():
            state = self.chars.load(self.GAMBLER)
            if state is not None:
                gone = [r for r in state.battles if r.kind in battlelog.SHOWDOWN_KINDS]
                state.battles = [r for r in state.battles if r.kind not in battlelog.SHOWDOWN_KINDS]
                at = gone[0].time if gone else state.world.time
                for dt in (60.0, -60.0):  # 存檔裡新的在前
                    state.battle_seq += 1
                    state.battles.append(BattleRecord(id=state.battle_seq, time=at + dt, location="某地", kind="train", opponent="山賊",
                                                      ours=[], tier="大勝", our_power=1.0, difficulty=1.0))
                state.player.showdowns_restored = 0
                self.chars.save(state)
        self.main(self.GAMBLER)
        self.me(self.GAMBLER, "補回戰報之後")
        _, data = self.call(self.GAMBLER, "GET", "/api/reports")
        rows = [r["id"] for r in data.get("list", [])] if isinstance(data, dict) else []
        for rid in rows[-1:]:
            self.call(self.GAMBLER, "GET", f"/api/reports?id={rid}")

    def bots(self) -> None:
        """伺服器假人（BotRunner＋bot_policy，random.Random(7)、時鐘一輪推一分）：另開一場（second），四個假人擺在那一場的大區，跑到加入、出招
        （battle_tick）、收場，收場之後再跑三輪就停——這三輪裡輪到動的假人才同步、收到補送（week7、none 只有一位，weekend、season21 三位；
        審查 nit），其餘的在換季之後（season 那一段）同步一次，走 file_showdown 上一季的那一支。整季機器人（bot.play_season，week7、種子 5）：observe 第一步替它投靠官軍、擺進長社、開一場長社火攻，
        之後每一步把它的現實時鐘推一分，讓它自己打完一場。測試內容沒有決戰：略過。"""
        from collections import Counter

        from tianxia import server_bots
        from tianxia.bot_runner import BotRunner
        from tianxia.engine import Game
        from tianxia.state import BotProfile

        op, battle_id = self.second()
        loc = self.spot(battle_id)
        if loc is None:
            emit("這份內容沒有決戰：假人那一段略過", None)
            return
        self.do(ADMIN, op, {"id": battle_id})
        self.battle_row("假人那一場開了集結")
        for i, (name, side) in enumerate(self.BOT_SEATS):
            self.begin()
            g = Game.new(self.c, name, rng=random.Random(i), world=self.world, graduated=True)
            g.client = None
            g.sync(CLOCK[0])
            for _ in range(6):  # 開局待選的事件：選掉
                first = next((o.id for o in g.options(odds=False) if o.id.startswith("choice:") and o.enabled), None)
                if first is None:
                    break
                g.choose(first)
            p = g.state.player
            p.bot = BotProfile(personality="普通", seed=41 + i, faction=side, season_number=self.world.get_season_number())
            p.faction, p.location, p.journey = side, loc, None
            p.visited.add(loc)
            p.tutorial_step = len(self.c.tutorial.steps)
            p.joined_at = -1.0e9
            self.chars.save(g.state)
        away = self.away_bot(battle_id, 41 + len(self.BOT_SEATS))  # 第 7 批：大區外、名下有同伴的那一位（趕路、挑同伴）
        runner = BotRunner(self.c, self.world, self.chars, rng=random.Random(7), clock=lambda: CLOCK[0])
        online = server_bots.is_online
        seeds = {41 + i for i in range(len(self.BOT_SEATS))} | away
        # 擺好的四個一直在線（作息照種子，可能正好不在）；一輪動不動照舊擲 act_chance（集結三十分鐘夠他們走到「加入」），出招照 battle_tick
        server_bots.is_online = lambda profile, now: profile.seed in seeds or online(profile, now)
        totals = Counter()
        try:
            for _ in range(int(os.environ.get("SB_BATTLE_TICKS", "90"))):
                STEP[0] += 5  # 一輪推一分（這一軌一步十秒）
                self.begin()
                for report in (runner.tick(), runner.battle_tick()):
                    totals.update(acted=report.acted, added=report.added, skipped=report.skipped, failed=report.failed, online=report.online)
                b = self.world.get_battle()
                if b is not None and b.phase == "ended" and totals["after_end"] >= 3:
                    break
                if b is not None and b.phase == "ended":
                    totals["after_end"] += 1
        finally:
            server_bots.is_online = online
        self.battle_row("假人那一場")
        states = self.chars.all(bots_only=True)
        emit("決戰假人 一輪一輪", dict(sorted(totals.items())))
        emit("決戰假人 紀錄標題", dict(sorted(Counter(e.title for s in states for e in s.journal).items())))
        emit("決戰假人 存檔", {s.player.name: hashlib.sha256(s.model_dump_json().encode("utf-8")).hexdigest() for s in states})
        for s in states:
            self.me(s.player.name, "假人收補送之後")
        if self.profile == "week7":
            self.season_bot()

    def season_bot(self) -> None:
        """整季機器人（bot.play_season）打一場：自己一個資料庫（這一軌的資料庫旁邊），種子 5、SB_BATTLE_PLAY_STEPS 步。"""
        from collections import Counter

        from tianxia import bot
        from tianxia.content import load_content
        from tianxia.sqlite_world import open_world
        from tianxia.world import open_showdown

        path = self.db.with_name(self.db.stem + "-play.db")
        for suffix in ("", "-wal", "-shm", "-push.sqlite"):
            p = Path(str(path) + suffix)
            if p.exists():
                p.unlink()
        content = load_content(self.root / "content", profile=self.profile)
        world = open_world(path)
        spot = self.spot("changshe_fire")
        seen = {"opened": False}

        def observe(g) -> None:
            g.now += 60.0  # 現實時鐘一步推一分（play_season 自己不推）：集結會截止、回合會逾時
            if seen["opened"] or g.state.world.ended:
                return
            seen["opened"] = True
            p = g.state.player
            p.faction, p.location, p.journey = "guan", spot, None
            p.visited.add(spot)
            open_showdown(g.world, g.content, "changshe_fire", g.now)
            g.state.world = g.world.get_season()

        game = bot.play_season(content, seed=5, max_steps=int(os.environ.get("SB_BATTLE_PLAY_STEPS", "160")), world=world, now=CLOCK0,
                               observe=observe)
        battle = world.get_battle()
        emit("整季機器人的決戰", None if battle is None else {
            "phase": battle.phase, "round": battle.round_number, "outcome": battle.outcome_title,
            "who": sorted(battle.participants), "sha": hashlib.sha256(battle.model_dump_json().encode("utf-8")).hexdigest()})
        emit("整季機器人 紀錄標題", dict(sorted(Counter(e.title for e in game.state.journal).items())))
        emit("整季機器人 戰報", [[r.kind, r.event, r.tier, r.notes, r.changes] for r in game.state.battles if r.kind == "showdown"])
        emit("整季機器人 存檔", hashlib.sha256(game.state.model_dump_json().encode("utf-8")).hexdigest())
        emit("整季機器人 資料庫", hashlib.sha256(db_text(path).encode("utf-8")).hexdigest())

    def season(self) -> None:
        """收季、開下一季：補過的決戰照帶（battle_results_seen，不再補一次）、這一季參戰幾場與首功跟著新角色重來。假人那一場收場之後
        還沒同步過的假人，換季之後第一次同步才補到（審查 nit）：file_showdown 上一季那一支——紀錄與戰報標「第 N 季・」、不發軍餉、
        行狀接在存起來的上一季後面（add_saved_annal）。"""
        from tianxia.engine import Game

        self.do(ADMIN, "end_season")
        for who in self.PLAYERS:
            self.main(who)
        self.resting()  # 第 6 批：休季時管理者的決戰工具一律被擋；季終收兵的那一場攻城（D）
        self.do(ADMIN, "next_season")
        for who in [*self.PLAYERS, self.NEWBIE]:
            self.main(who)
            self.me(who, "換季之後")
        last = self.world.get_season_number() - 1
        for name, _ in self.BOT_SEATS:  # 照假人程式的做法：鎖裡讀存檔、建 Game、同步、存回去（測試內容沒有擺假人：略過）
            self.begin()
            with self.world.action_lock():
                state = self.chars.load(name)
                if state is None:
                    continue
                g = Game(self.c, state, random.Random(STEP[0]), self.world)
                g.client = None
                g.sync(CLOCK[0])
                self.chars.save(g.state)
            self.me(name, "換季之後同步")
            book = self.world.biography(last, name)
            emit(f"{name} 第 {last} 季存起來的行狀", None if book is None else [[a["kind"], a["text"]] for a in book["annals"]][-4:])

    # ── 第 6 批：管理者的決戰工具（admin、resting）──

    def live_showdown(self) -> bool:
        b = self.world.get_battle()
        return b is not None and b.phase != "ended"

    def trial(self) -> str | None:
        """admin_trial 開了再取消的那一場（立刻開戰的 id）：不帶設定是黃巾決戰（world.start_battle 那一支）；時刻表的季是宛城（時刻表那一支：
        world.open_showdown）——還不知道是哪一版的季（weekend、week7）先按開它被擋（要等張曼成那一件結算），「定結果」定了張曼成（GET /api/admin
        的 results 第一個），那一版才出現在立刻開戰的選單上；season21 開季就知道了。測試內容沒有決戰是 None。"""
        if not self.c.battles:
            return None
        if self.target()[0] == "start_battle":
            return self.target()[1]
        from tianxia import timetable

        event = timetable.find(self.c, "wancheng")
        _, data = self.call(ADMIN, "GET", "/api/admin")
        found = next((b["id"] for b in data.get("battles", []) if b["id"].startswith(event.id)), None)
        if found is not None:
            return found
        self.do(ADMIN, "start_showdown", {"id": event.id})  # 要等張曼成那一件結算了才知道是哪一版
        value = next((r["value"] for r in data.get("results", []) if r["value"].startswith(f"{event.version_from}|")), None)
        if value is not None:
            eid, key = value.split("|", 1)
            self.do(ADMIN, "resolve_event", {"id": eid, "key": key})
        _, data = self.call(ADMIN, "GET", "/api/admin")
        return next((b["id"] for b in data.get("battles", []) if b["id"].startswith(event.id)), None)

    def admin(self) -> None:
        """管理者的決戰工具，開戰之前按得到的那幾種被拒（GET /api/admin 看立刻開戰的選單〔admin_battles〕、三場大戲的鈕〔admin_showdowns、
        _showdown_refusal〕、時刻表那幾列〔cancelled_showdowns〕）：不是管理者按開戰（伺服器擋）；暫停中按開戰、開這一場、取消決戰
        （_admin_refusal），繼續；立刻開戰沒有這一場；開這一場時刻表上沒有（不帶設定：這一季沒有時刻表）；沒有進行中的決戰時取消決戰被擋——
        season21 的長社火攻開季就開了集結：改成另開廣宗被擋（已經有一場戰鬥在進行），不取消它（第 5 批那一場照打）。成的那幾顆在 open（開這一場、
        立刻開戰）、admin_trial（開了再取消）、bots（開這一場）。"""
        op, target = self.target()
        self.call(ADMIN, "GET", "/api/admin")
        self.do(self.GAMBLER, "start_battle", {"id": target})  # 不是管理者：伺服器擋
        self.do(ADMIN, "pause_clock")
        self.do(ADMIN, "start_battle", {"id": target})
        self.do(ADMIN, "start_showdown", {"id": target})
        self.do(ADMIN, "cancel_battle")
        self.do(ADMIN, "resume_clock")
        self.do(ADMIN, "start_battle", {"id": "no_such_battle"})
        self.do(ADMIN, "start_showdown", {"id": "no_such_event"})
        if self.live_showdown():
            second = self.second()[1]
            self.do(ADMIN, "start_battle", {"id": second})
            self.do(ADMIN, "start_showdown", {"id": second})
        else:
            self.do(ADMIN, "cancel_battle")

    def admin_trial(self) -> None:
        """開了再取消（第 5 批那一場收場、補送完之後）：取消決戰被擋（沒有進行中的）、開這一場長社被擋（已經結算了；不帶設定：沒有時刻表）；
        試開一場（trial），再開一次、開別場都擋（已經有一場戰鬥在進行、已經開打過了），取消（不算勝負、天下大事一句、記進 showdowns_cancelled），
        之後開這一場宛城被擋（開打後被取消，要收尾用定結果）；前後 GET /api/admin（時刻表那幾列的「開打後取消」）。"""
        op, target = self.target()
        self.do(ADMIN, "cancel_battle")
        self.do(ADMIN, "start_showdown", {"id": target})
        trial = self.trial()
        emit("試開的那一場", trial)
        if trial is None:
            return
        self.do(ADMIN, "start_battle", {"id": trial})
        # 那一場的大區裡有一位加入（不帶設定：秦朗月在潁川汝南；時刻表的季：A 那一場打完的程破軍在南陽）：取消之後他補一則「不算勝負」——
        # file_showdown 沒打完那一支（第 5 批的情境走不到，見 docstring 開頭）
        joiner = self.GAMBLER if op == "start_battle" else next(iter(self.SIEGE_PLAYERS))
        joined = joiner in self.clients
        if joined:
            ids = self.ids(self.main(joiner))
            pick = next((i for i in sorted(ids) if i.startswith("battle:join:") and ids[i].get("enabled")), None)
            emit(f"{joiner} 試開那一場按的", pick)
            if pick is not None:
                self.choose(joiner, pick)
                self.no_escort(joiner)
        self.battle_row("試開")
        self.do(ADMIN, "start_battle", {"id": trial})
        if op == "start_showdown":
            self.do(ADMIN, "start_battle", {"id": self.second()[1]})
            self.do(ADMIN, "start_showdown", {"id": self.second()[1]})
            self.do(ADMIN, "start_showdown", {"id": "wancheng"})
        self.call(ADMIN, "GET", "/api/admin")
        self.do(ADMIN, "cancel_battle")
        self.battle_row("取消之後")
        self.call(ADMIN, "GET", "/api/admin")
        if op == "start_showdown":
            self.do(ADMIN, "start_showdown", {"id": "wancheng"})
        if joined:
            self.main(joiner)
            self.me(joiner, "試開那一場取消之後")

    def resting(self) -> None:
        """收季之後（休季）管理者的決戰工具一律被擋（賽季沒有在進行）；季終收兵的那一場攻城（D）收起來了，秦朗月補一則不算勝負。"""
        op, target = self.target()
        self.do(ADMIN, "start_battle", {"id": target})
        self.do(ADMIN, "start_showdown", {"id": target})
        self.do(ADMIN, "cancel_battle")
        if self.siege_on():
            self.siege_row("季終收兵之後", ("D",))
            self.me(self.GAMBLER, "季終收兵之後")

    # ── 第 6 批：攻城（地盤開著的季；SIEGES、SIEGE_PLAYERS）──

    def siege_on(self) -> bool:
        from tianxia import territory

        return territory.on(self.c)

    def recruit(self, who: str, side: str | None, loc: str) -> bool:
        """攻城的真人：兩軍的照 Scenario.newcomer（註冊、建角色、略過引導、投靠）；散人只註冊、建角色、略過引導。擺到 loc（體力補滿、過了新手期）。"""
        if side is not None:
            if not self.newcomer(who, side):
                return False
        else:
            self.clients[who] = self.TestClient(self.server.app)
            self.passwords[who] = "pw-" + self.login_of(who)
            self.call(who, "POST", "/api/register", {"login": self.login_of(who), "password": self.passwords[who],
                                                    "again": self.passwords[who]})
            self.call(who, "POST", "/api/character", {"name": who, "gender": "男"})
            self.do(who, "skip_tutorial")
            self.settle_choices(who)
        return self.place(who, loc)

    def slot_of(self, key: str):
        """時程表上那一場（最後排的那一筆：SIEGES 的那一塊、攻方有那一軍）；沒有是 None。"""
        side, loc = self.SIEGES[key]
        season = self.world.get_season()
        if season.conquest is None:
            return None
        return next((s for s in reversed(season.conquest.schedule) if s.loc == loc and side in s.attackers), None)

    def siege_row(self, tag: str, keys=None) -> None:
        """這幾場攻城此刻的樣子：時程表那一筆（狀態、流水號、誰拿下）、那一塊歸誰與兩軍的進度、那一場（還在共用狀態裡的，或已經拿掉、
        從 battles 表讀的）的回合、戰局、結果、名單、SiegeInfo 與整份的雜湊。"""
        from tianxia import conquest

        season = self.world.get_season()
        live = {b.record_id: b for b in self.world.get_sieges()}
        out = {}
        for key in keys or self.SIEGES:
            slot = self.slot_of(key)
            if slot is None:
                continue
            loc = self.SIEGES[key][1]
            b = None if slot.record_id is None else live.get(slot.record_id) or self.world.ended_battle(slot.record_id)
            out[key] = {
                "slot": [slot.id, slot.status, slot.record_id, slot.winner, slot.attackers],
                "holder": conquest.holder(season, self.c, loc),
                "bars": {s: round(v, 3) for s, v in sorted(conquest.bars(season, loc).items())},
                "battle": None if b is None else {
                    "id": b.battle_id, "phase": b.phase, "round": b.round_number, "trend": b.trend,
                    "outcome": [b.outcome_title, b.outcome_side, b.outcome_margin], "unfinished": b.unfinished,
                    "who": {n: [q.faction, q.eliminated, q.acted_rounds] for n, q in sorted(b.participants.items())},
                    "siege": None if b.siege is None else b.siege.model_dump(mode="json"),
                    "sha": hashlib.sha256(b.model_dump_json().encode("utf-8")).hexdigest()},
            }
        emit(f"攻城 {tag}", out)

    def siege_pick(self, who: str, ids: dict[str, dict]) -> str | None:
        """攻城集結時這個人按哪一顆：兩軍的按自己那一軍的加入、散人按助守【守軍】；同一個大區有兩場打得進去時鈕帶「@流水號」，按自己那一場的。"""
        side, key, _ = self.SIEGE_PLAYERS[who]
        slot = self.slot_of(key)
        rid = None if slot is None else slot.record_id
        live = sorted(i for i, o in ids.items() if (i.startswith("battle:join:") or i.startswith("battle:enlist:")) and o.get("enabled"))
        mine = [i for i in live if "@" not in i or i.endswith(f"@{rid}")]
        if side is not None:
            return next((i for i in mine if i.split("@")[0] == f"battle:join:{side}"), mine[0] if mine else None)
        return next((i for i in mine if "助守" in ids[i].get("label", "")), mine[0] if mine else None)

    def siege_round(self) -> None:
        """攻城這一回合：還在場上的攻城真人各出一招（SIEGE_PLAYERS 寫的那一招；鈕上沒有就照第一顆）。沒有開打中的攻城什麼都不打。"""
        if not self.siege_on():
            return
        live = [b for b in self.world.get_sieges() if b.phase == "active"]
        for who, (_, _, move) in self.SIEGE_PLAYERS.items():
            b = next((x for x in live if who in x.participants), None)
            if b is None or b.participants[who].eliminated:
                continue
            ids = self.ids(self.main(who))
            acts = sorted(i for i, o in ids.items() if i.startswith("battle:act:") and o.get("enabled"))
            if acts:
                self.choose(who, next((i for i in acts if f"（{move}" in ids[i].get("label", "")), acts[0]))
        if live:
            self.siege_row("這一回合之後", ("A", "B"))

    def siege_seat(self) -> None:
        """攻城的真人建好角色（一位十來個請求，攻城與決戰都還在集結），擺在各自那一場的地點。"""
        if not self.siege_on():
            return
        for who, (side, key, _) in self.SIEGE_PLAYERS.items():
            self.recruit(who, side, self.SIEGES[key][1])
        self.siege_row("人到齊了", ("A", "B", "C", "F"))

    def siege_open(self) -> None:
        """開戰之後管理者立刻下四張戰書（admin_conquest_letter：不看階與門檻、集結馬上開）——A、B、C、F；下一個同步的人（GET /api/admin）把它們
        開成集結（siege.open_waiting）。F 在洛陽，那一區沒有人：沒有人加入。"""
        if not self.siege_on():
            emit("這一季沒有地盤：攻城那幾段略過", None)
            return
        for key in ("A", "B", "C", "F"):
            side, loc = self.SIEGES[key]
            self.do(ADMIN, "admin_conquest_letter", {"id": loc, "side": side})
        self.call(ADMIN, "GET", "/api/admin")  # 領地爭奪那一組的 sieges（取消一場攻城的下拉選單）
        self.siege_row("開了集結", ("A", "B", "C", "F"))

    def siege_muster(self) -> None:
        """攻城集結中：每一位看一次、按加入（散人按助守；有挑同伴那一步就不派），再看一次。"""
        if not self.siege_on():
            return
        for who in self.SIEGE_PLAYERS:
            pick = self.siege_pick(who, self.ids(self.main(who)))
            emit(f"{who} 攻城集結時按的", pick)
            if pick is None:
                continue
            self.choose(who, pick)
            self.no_escort(who)
        for who in self.SIEGE_PLAYERS:
            self.main(who)
        self.siege_row("集結中", ("A", "B", "C"))

    def siege_cancel(self) -> None:
        """集結中管理者「取消一場攻城」（admin_conquest_cancel → _cancel_siege → _shelve_siege：不算勝負、不發軍餉、不易手），C 那一位補一則；
        再按一次被擋（已經作罷）。"""
        if not self.siege_on():
            return
        slot = self.slot_of("C")
        if slot is None:
            emit("C 那一場沒排上", None)
            return
        self.do(ADMIN, "conquest_cancel", {"id": slot.id})
        self.do(ADMIN, "conquest_cancel", {"id": slot.id})
        self.main("譚小滿")
        self.me("譚小滿", "攻城取消之後")
        self.siege_row("取消之後", ("C",))

    def siege_start(self) -> None:
        """攻城的集結截止（戰書比決戰晚幾步下，截止也晚幾步）：時鐘推過最晚的那一場，攻城的真人各看一次——第一個同步的人把決戰與每一場攻城都
        推到開打（_battle_status：先決戰、再每一場攻城各推一次，_tick_siege；沒人到的作罷）；start 那一段接著看決戰開打的畫面。
        到這裡為止決戰還在集結（season21 的長社火攻開季就開了集結、截止最早：集結那幾段要放得進去），不然就停。"""
        b = self.world.get_battle()
        self.expect(b is None or b.phase == "muster", f"攻城截止之前決戰還在集結（此刻 {None if b is None else b.phase}）")
        if not self.siege_on():
            return
        mustering = [b for b in self.world.get_sieges() if b.phase == "muster"]
        if mustering:
            self.skip_past(max(b.muster_deadline_real for b in mustering))
        for who in self.SIEGE_PLAYERS:
            self.main(who)
        self.siege_row("開打", ("A", "B", "F"))

    def siege_end(self) -> None:
        """攻城打到收場（決戰收場時還沒收場的：照回合出招，回合沒結就把時鐘推過期限）：A 守將守住、B 攻下易手；收場之後攻城的真人各打一次
        /api/main 收補送（戰報 kind siege、軍餉與貢獻乘 pay_share），存檔那幾格寫進輸出。"""
        if not self.siege_on():
            return
        first = next(iter(self.SIEGE_PLAYERS))
        for _ in range(12):
            live = [b for b in self.world.get_sieges() if b.phase != "ended"]
            if not live:
                break
            before = {b.record_id: b.round_number for b in live}
            self.siege_round()
            stuck = [b for b in self.world.get_sieges() if b.phase == "active" and before.get(b.record_id) == b.round_number]
            if stuck:
                self.skip_past(max(b.round.opened_real + self.c.battles[b.battle_id].round_seconds for b in stuck))
                self.main(first)
        self.siege_row("收場")
        for who in self.SIEGE_PLAYERS:
            self.main(who)
            self.me(who, "攻城收補送之後")

    def siege_after(self) -> None:
        """易手之後的地盤與管理者那一頁：GET /api/admin（長社結算了、宛城開打後取消；領地爭奪那一組的此刻歸誰、冷卻）、輿圖的狀態
        （/api/map/state）、戰報頁攻城那一筆；替黃巾再對涿郡下一張戰書被擋（B 攻下之後已經是黃巾的了）。"""
        self.call(ADMIN, "GET", "/api/admin")
        if not self.siege_on():
            return
        self.call(next(iter(self.SIEGE_PLAYERS)), "GET", "/api/map/state")
        for who in self.SIEGE_PLAYERS:
            _, data = self.call(who, "GET", "/api/reports")
            rows = [r["id"] for r in data.get("list", [])] if isinstance(data, dict) else []
            for rid in rows[:1]:
                self.call(who, "GET", f"/api/reports?id={rid}")
        side, loc = self.SIEGES["B"]
        self.do(ADMIN, "admin_conquest_letter", {"id": loc, "side": side})

    def siege_bots(self) -> None:
        """伺服器假人打一場攻城（照 bots 那一段的寫法：BotRunner＋bot_policy，random.Random(9)、時鐘一輪推一分）：E 官軍攻黃巾的新野，
        四個假人（兩軍各二）擺在那一塊，管理者下戰書，跑到加入、出招（battle_tick）、收場，收場之後再跑三輪就停。"""
        if not self.siege_on():
            emit("這一季沒有地盤：攻城的假人那一段略過", None)
            return
        from collections import Counter

        from tianxia import server_bots
        from tianxia.bot_runner import BotRunner
        from tianxia.engine import Game
        from tianxia.state import BotProfile

        side, loc = self.SIEGES["E"]
        for i, (name, faction) in enumerate(self.SIEGE_BOT_SEATS):
            self.begin()
            g = Game.new(self.c, name, rng=random.Random(20 + i), world=self.world, graduated=True)
            g.client = None
            g.sync(CLOCK[0])
            for _ in range(6):  # 開局待選的事件：選掉
                first = next((o.id for o in g.options(odds=False) if o.id.startswith("choice:") and o.enabled), None)
                if first is None:
                    break
                g.choose(first)
            p = g.state.player
            p.bot = BotProfile(personality="普通", seed=61 + i, faction=faction, season_number=self.world.get_season_number())
            p.faction, p.location, p.journey = faction, loc, None
            p.visited.add(loc)
            p.tutorial_step = len(self.c.tutorial.steps)
            p.joined_at = -1.0e9
            self.chars.save(g.state)
        self.do(ADMIN, "admin_conquest_letter", {"id": loc, "side": side})
        runner = BotRunner(self.c, self.world, self.chars, rng=random.Random(9), clock=lambda: CLOCK[0])
        online = server_bots.is_online
        seeds = {61 + i for i in range(len(self.SIEGE_BOT_SEATS))}
        server_bots.is_online = lambda profile, now: profile.seed in seeds or online(profile, now)
        totals = Counter()
        try:
            for _ in range(int(os.environ.get("SB_SIEGE_TICKS", "90"))):
                STEP[0] += 5  # 一輪推一分（這一軌一步十秒）
                self.begin()
                for report in (runner.tick(), runner.battle_tick()):
                    totals.update(acted=report.acted, added=report.added, skipped=report.skipped, failed=report.failed, online=report.online)
                slot = self.slot_of("E")
                done = slot is not None and slot.status in ("done", "void")
                if done and totals["after_end"] >= 3:
                    break
                if done:
                    totals["after_end"] += 1
        finally:
            server_bots.is_online = online
        self.siege_row("假人那一場", ("E",))
        names = {n for n, _ in self.SIEGE_BOT_SEATS}
        states = [s for s in self.chars.all(bots_only=True) if s.player.name in names]
        emit("攻城假人 一輪一輪", dict(sorted(totals.items())))
        emit("攻城假人 紀錄標題", dict(sorted(Counter(e.title for s in states for e in s.journal).items())))
        emit("攻城假人 存檔", {s.player.name: hashlib.sha256(s.model_dump_json().encode("utf-8")).hexdigest() for s in states})
        for s in states:
            self.me(s.player.name, "假人攻城收補送之後")

    def siege_shelve(self) -> None:
        """季終收兵那一場（D）：官軍攻中立的汝南荒野，秦朗月擺過去加入；集結中就收季（season 那一段，admin_end_season → _shelve_siege）。"""
        if not self.siege_on():
            return
        side, loc = self.SIEGES["D"]
        self.place(self.GAMBLER, loc)
        self.do(ADMIN, "admin_conquest_letter", {"id": loc, "side": side})
        ids = self.ids(self.main(self.GAMBLER))
        pick = next((i for i in sorted(ids) if i.split("@")[0] == f"battle:join:{side}" and ids[i].get("enabled")), None)
        emit(f"{self.GAMBLER} 季終之前加入的", pick)
        if pick is not None:
            self.choose(self.GAMBLER, pick)
            self.no_escort(self.GAMBLER)
        self.siege_row("季終之前", ("D",))

    # ── 第 7 批：集結、投效、挑同伴（MUSTER_PLAYERS、ESCORTERS、AWAY_BOT）──

    def enroll(self, who: str, side: str | None) -> None:
        """一位新人直接建進資料庫（同假人那一段：Game.new graduated、開局待選的事件選掉、過了新手期；兩軍的人直接記陣營）、綁一個帳號，
        再照 API 登入——一位只花兩步，集結那 30 分鐘才放得下第 7 批的幾段（照 API 註冊、略過引導、投靠一位要十來步）。"""
        from tianxia.accounts import AccountStore
        from tianxia.engine import Game

        self.begin()
        g = Game.new(self.c, who, rng=random.Random(STEP[0]), world=self.world, graduated=True, sex="男")
        g.client = None
        g.sync(CLOCK[0])
        for _ in range(6):  # 開局待選的事件：選掉
            first = next((o.id for o in g.options(odds=False) if o.id.startswith("choice:") and o.enabled), None)
            if first is None:
                break
            g.choose(first)
        p = g.state.player
        p.tutorial_step = len(self.c.tutorial.steps)
        p.joined_at = -1.0e9
        if side is not None and any(f.id == side for f in self.c.scenario.factions):
            p.faction = side
        self.passwords[who] = "pw-" + self.login_of(who)
        store = AccountStore(self.world.db)
        with self.world.db.transaction():
            self.chars.save(g.state)
            store.register(self.login_of(who), self.passwords[who])
            store.bind_character(self.login_of(who), who)
        emit(f"{who} 建進資料庫", {"faction": p.faction, "location": p.location})
        self.clients[who] = self.TestClient(self.server.app)
        self.call(who, "POST", "/api/login", {"login": self.login_of(who), "password": self.passwords[who]})

    def mate_for(self, side: str | None) -> str | None:
        """還沒有主的同伴裡挑一位（照 id 排第一個；不是大勢人物、陣營寫的是 side 或沒寫）；歷史武將同行關著（測試內容）是 None。"""
        from tianxia import roster

        if not roster.on(self.c):
            return None
        return next((cid for cid in sorted(self.c.characters) if cid not in self.c.figures and self.c.characters[cid].side in (None, side)
                     and getattr(self.c.characters[cid], "hire_type", None) is None  # 一般 NPC 同伴（features/hire）不算
                     and self.world.get_companion(cid).owner is None), None)

    def give_mate(self, who: str, side: str | None) -> None:
        """名下一位同伴（招進來、放進隊伍、情誼 80），同 tianxia/features/battle/tests/test_companions_battle._ride_in。"""
        cid = self.mate_for(side)
        if cid is None:
            emit(f"{who} 名下的同伴（歷史武將同行關著）", None)
            return
        ok = self.world.try_recruit(cid, who, cap=3)

        def fn(p) -> None:
            if cid not in p.team:
                p.team.append(cid)
            p.affinities[cid] = 80

        self.edit(who, fn)
        emit(f"{who} 名下的同伴", [cid, ok])

    def mates(self, who: str, tag: str) -> None:
        """同伴那幾格：隊伍、情誼、減過了沒（parted_done）、還在挑的那一下（escort_pick），全服那一份的主人與從誰身邊回江湖。"""
        state = self.chars.load(who)
        if state is None:
            emit(f"{who} {tag}（沒有這個人）", None)
            return
        p = state.player
        cids = sorted(set(p.team) | set(p.affinities) | {c for c, pr in self.world.companions().items() if who in (pr.owner, *pr.parted_from)})
        emit(f"{who} 同伴 {tag}", {
            "team": list(p.team), "affinities": {c: p.affinities.get(c) for c in cids}, "parted_done": list(p.parted_done),
            "escort_pick": p.escort_pick,
            "world": {c: [self.world.get_companion(c).owner, list(self.world.get_companion(c).parted_from)] for c in cids}})

    def escorts_row(self, tag: str) -> None:
        """那一場決戰上每一位隨你出陣的同伴（份量、氣血、敗走、回江湖了沒）與每個人站哪一邊、在不在場（away）。"""
        b = self.world.get_battle()
        emit(f"決戰的同伴與在場 {tag}", None if b is None else {
            n: [q.faction, q.away, None if q.escort is None else [q.escort.cid, q.escort.score, round(q.escort.neili, 1), q.escort.fallen_round,
                                                                   q.escort.released]]
            for n, q in sorted(b.participants.items())})

    def showdown_ref(self) -> int | None:
        b = self.world.get_battle()
        return None if b is None else b.record_id

    def pick_of(self, ids: dict[str, dict], want: str) -> str | None:
        """選單上那一顆（want 是不帶 @ 的 id）：同一個大區兩場以上時鈕帶「@流水號」，挑決戰那一場的；按不下去的不算。"""
        rid = self.showdown_ref()
        return next((i for i in sorted(ids) if i.split("@")[0] == want and ids[i].get("enabled")
                     and ("@" not in i or i.endswith(f"@{rid}"))), None)

    def press(self, who: str, want: str, tag: str) -> str | None:
        ids = self.ids(self.main(who))
        pick = self.pick_of(ids, want)
        emit(f"{who} {tag}", pick)
        if pick is not None:
            self.choose(who, pick)
        return pick

    def away_spot(self) -> str | None:
        """大區外的一處：照 id 排第一個、不在那一場決戰的大區（審查 should：原本連每一場攻城的大區也避開，攻城開著的季五個大區全佔滿——
        決戰與 G 在潁汝、A 南陽、B 幽州、C 冀州、F 洛陽——一處都找不到、照舊站在潁川〔潁汝〕，「集結時人在大區外」只有不帶設定走到）。
        正式內容排第一的是冀州的白馬津：攻城開著的季那裡有 C 在集結（集結中就取消、不開打），嚴不悔、沐晚晴站在那裡不按 C 的鈕、不會加進 C
        （集結截止不拉旁人進來，battle_instance.close_muster 只分已報名、沒選邊的人）。那一場決戰有大區、卻找不到大區外的一處就停（expect）。"""
        from tianxia import atlas

        def region(loc: str | None) -> str | None:
            r = atlas.region_of(self.c, loc) if loc in self.c.locations else None
            return None if r is None else r.id

        d = self.c.battles.get(self.target()[1])
        busy = d.region if d is not None else None
        found = next((i for i in sorted(self.c.locations) if region(i) != busy), None)
        emit("大區外的一處", found)
        self.expect(d is None or d.region is None or found is not None, "那一場決戰的大區外找得到一處（嚴不悔、沐晚晴集結時站在那裡）")
        return found

    @_still
    def muster_seat(self) -> None:
        """第 7 批的六位新人建好、擺好（region：那一場決戰的大區；hilltop：荒丘，同一個大區；away：那一場決戰的大區外）；秦朗月、顧長風、
        莫問天、石破浪名下各一位同伴（歷史武將同行開著的季）。"""
        spots = {"region": self.spot(self.target()[1]), "hilltop": "hilltop_wilds", "away": self.away_spot()}
        for who, (side, where) in self.MUSTER_PLAYERS.items():
            self.enroll(who, side)
            self.place(who, spots[where])
        for who in self.ESCORTERS:
            self.give_mate(who, self.PLAYERS.get(who, self.MUSTER_PLAYERS.get(who, (None,))[0]))

    @_still
    def muster_pick(self) -> None:
        """集結中第 7 批的加入那幾種與被拒的路——攻城開著的季先在潁汝多開一場（G：黃巾攻中立的荒丘）：黃巾與散人站在那一區看得到兩場、
        加入與投效的鈕帶 @流水號（_battle_menu），官軍那一格是守將、站不進去。
        顧長風：按加入 → 挑同伴那一步（名下每一位一顆、「不派」「再想想」）→ 再想想 → 再按加入，停在挑；莫問天：按加入，停在挑。
        江映雪（散人）：臨時投效官軍 → 改投黃巾。石破浪：先按一顆壞掉的 @，再按 G 那一場的 @（名下有同伴：停在挑、escort_pick 記著 @G）→
        再想想，再照決戰那一場的 @ 加入（不派）。被拒：韓雲起按官軍的加入（不在選單上）、
        沐晚晴在大區外按投效（看不到戰場）。集結一軌的前半停在這一段之後。"""
        if self.siege_on():
            side, loc = self.SIEGES["G"]
            self.do(ADMIN, "admin_conquest_letter", {"id": loc, "side": side})
            self.call(ADMIN, "GET", "/api/admin")  # 下一個同步的人把它開成集結
            self.siege_row("潁汝多一場", ("G",))
        who = "顧長風"
        pick = self.press(who, "battle:join:guan", "集結時按的")
        if pick is not None and "battle:escort:back" in self.ids(self.main(who)):
            self.choose(who, "battle:escort:back")
            self.main(who)
            self.choose(who, pick)
        self.mates(who, "按了加入、停在挑")
        self.press("莫問天", "battle:join:guan", "集結時按的")
        self.mates("莫問天", "按了加入、停在挑")
        for want in ("battle:enlist:guan", "battle:enlist:huang"):
            if self.press("江映雪", want, "集結時按的") is not None and "battle:escort:none" in self.ids(self.main("江映雪")):
                self.choose("江映雪", "battle:escort:none")
        who = "石破浪"
        emit(f"{who} 看到的戰鬥鈕", sorted(i for i in self.ids(self.main(who)) if i.startswith("battle:")))
        self.choose(who, "battle:join:huang@abc")  # 壞掉的流水號：不在選單上
        g = self.slot_of("G") if self.siege_on() else None
        if g is not None and g.record_id is not None:
            # 照 @流水號按 G 那一場（不是排第一的決戰：審查 nit，按 @1 的話不帶流水號也落在同一場，@ 整個被忽略也比不出來）——名下有同伴，
            # 停在挑，記下的那一下帶著 @G（PlayerState.escort_pick）；再想想，回頭照決戰那一場的 @ 加入
            self.choose(who, f"battle:join:huang@{g.record_id}")
            self.mates(who, "按了 G 那一場的加入、停在挑")
            self.choose(who, "battle:escort:back")
        self.press(who, "battle:join:huang", "集結時按的")
        self.no_escort(who)
        self.choose("韓雲起", "battle:join:guan")  # 只能站自己陣營那一邊：選單上沒有
        self.main("沐晚晴")
        # 人在大區外：看不到戰場、沒有決戰的投效鈕。按的是決戰那一顆在潁汝的 id（攻城開著的季潁汝有決戰與 G 兩場，鈕帶 @流水號）——她站的冀州
        # 有 C 在集結，不帶 @ 的那一顆是 C 的，按了就加進 C
        self.choose("沐晚晴", "battle:enlist:guan" + (f"@{self.showdown_ref()}" if self.siege_on() else ""))
        self.battle_row("第 7 批的人加入之後")
        self.escorts_row("集結中")

    @_still
    def muster_more(self) -> None:
        """集結一軌的後半從這裡接（重新登入）：顧長風挑好同伴加入（集結中，照加入帶著那一位）；江映雪到曹氏莊院（同一個大區）投靠地方豪強，
        豪強分屬兩軍的季挑了依附哪一軍、集結名單跟著換到那一邊（_ally_follows_battle，FB-273）；豪強不分屬兩軍的季照舊臨時投效著。
        最後管理者取消 G（同 C：admin_conquest_cancel）——G 只為了集結時潁汝有兩場，留著的話 siege_start 要把時鐘推過它的截止（比 A、B、F 晚
        將近一個集結），第 5、6 批的決戰與攻城就晚那麼久才開打。"""
        self.login_all()
        who = "顧長風"
        ids = self.ids(self.main(who))
        pick = next((i for i in sorted(ids) if i.startswith("battle:escort:") and i not in ("battle:escort:none", "battle:escort:back")), None)
        emit(f"{who} 挑的同伴", pick)
        if pick is not None:
            self.choose(who, pick)
        self.mates(who, "挑好同伴之後")
        who = "江映雪"
        hq = next((f for f in self.c.scenario.factions if f.id == "haoqiang"), None)
        if hq is None or "cao_manor" not in hq.join_at or not self.place(who, "cao_manor"):
            emit("投靠豪強那一段略過（這份內容沒有地方豪強或曹氏莊院）", None)
        else:
            self.choose(who, "faction:haoqiang")
            b = self.world.get_battle()
            now_side = b.participants[who].faction if b is not None and who in b.participants else None
            ally = next((i for i in sorted(self.ids(self.main(who))) if i.startswith("faction:ally:") and i.rpartition(":")[2] != now_side), None)
            emit(f"{who} 選邊", ally)
            if ally is not None:
                self.choose(who, ally)
            self.choose(who, "faction:confirm")
            self.settle_choices(who)
        self.battle_row("第 7 批後半的人加入之後")
        self.escorts_row("集結中（後半）")
        b = self.world.get_battle()
        self.expect(b is None or b.phase == "muster", f"第 7 批集結那幾段做完時決戰還在集結（此刻 {None if b is None else b.phase}）")
        slot = self.slot_of("G") if self.siege_on() else None
        if slot is not None:
            self.do(ADMIN, "conquest_cancel", {"id": slot.id})
            self.siege_row("G 取消之後", ("G",))

    @_still
    def late(self) -> None:
        """開打之後才到：莫問天集結時按了加入、停在挑同伴，現在才挑（改成晚到、帶著那一位）；嚴不悔（黃巾）擺進決戰的大區，按「加入戰局」；
        沐晚晴（散人）擺進大區，晚到臨時投效官軍——人多的那一邊（晚到照投效的那一軍記，不照「補人少的那一邊」分；Task 5 的單點突變抓到
        原本投效黃巾時兩種一樣），再按黃巾那一顆被擋（開打之後鈕上沒有改投）。"""
        who = "莫問天"
        ids = self.ids(self.main(who))
        pick = next((i for i in sorted(ids) if i.startswith("battle:escort:") and i not in ("battle:escort:none", "battle:escort:back")), None)
        emit(f"{who} 開打之後才挑的同伴", pick)
        if pick is not None:
            self.choose(who, pick)
        self.mates(who, "開打之後挑了")
        loc = self.spot(self.target()[1])
        for who, want in (("嚴不悔", "battle:join_late"), ("沐晚晴", "battle:enlist:guan")):
            self.place(who, loc)
            if self.press(who, want, "開打之後按的") is not None and "battle:escort:none" in self.ids(self.main(who)):
                self.choose(who, "battle:escort:none")
        self.choose("沐晚晴", "battle:enlist:huang")
        self.battle_row("晚到之後")
        self.escorts_row("開打")

    @_still
    def wander(self) -> None:
        """參戰者走出決戰的大區、再喊停（_sync_battle_presence：出發那一下記離開；喊停那一下這一趟只剩下一站，落回大區就不算離開；抵達時
        再記一次）：顧長風（帶著同伴：主人離開大區時同伴也不在場上）往大區外的一處走（照 id 排、第一站還在大區裡的第一處），喊停。之後
        照回合輪詢，抵達那一下照路程。"""
        from tianxia import atlas

        who = "顧長風"
        b = self.world.get_battle()
        d = self.c.battles.get(b.battle_id) if b is not None else None
        if b is None or b.phase != "active" or d is None or d.region is None or who not in b.participants:
            emit("走出大區那一段略過（沒有開打中、有大區的決戰）", None)
            return
        state = self.chars.load(who)
        inside = {i for i in self.c.locations if (r := atlas.region_of(self.c, i)) is not None and r.id == d.region}
        dest = None
        for cand in sorted(i for i in self.c.locations if i not in inside):
            route = atlas.way_to(state, self.c, cand)
            if route is not None and len(route.path) >= 2 and route.path[0] in inside:
                dest = cand
                break
        emit(f"{who} 往大區外走", dest)
        if dest is None:
            return
        self.call(who, "POST", "/api/travel", {"place": dest, "mode": "walk"})
        self.escorts_row("走出大區之後")
        if "act:halt" in self.ids(self.main(who)):
            self.choose(who, "act:halt")
        self.escorts_row("喊停之後")

    @_still
    def muster_deliver(self) -> None:
        """第 7 批的新人收補送（下一次同步）：帶著同伴的顧長風、莫問天——同伴打完回江湖（file_showdown → escort_home：拿出隊伍、一句、情誼減半，
        settle_partings(write=False) 那一句併進決戰那一則紀錄），同一次同步後段的 settle_partings 看到 parted_done、清掉全服的記號（FB-361）；
        再同步一次什麼都不變（照實寫，審查 nit：另起一則「同伴回江湖」、同步時才減半的那一支——收場在輪詢組畫面時、角色沒存——四種設定都沒走到）。
        秦朗月、石破浪不派，沒有那一句。"""
        for who in self.MUSTER_PLAYERS:
            self.main(who)
            self.me(who, "收補送之後")
        for who in self.ESCORTERS:
            self.mates(who, "收補送之後")
            self.main(who)
            self.mates(who, "再同步一次之後")

    @_still
    def away_bot(self, battle_id: str, seed: int) -> set[int]:
        """假人那一場：一位官軍假人站在那一場的大區外、名下一位同伴（BotRunner 的 _toward_battle 照 rally_region 趕路，到了按加入、停在挑同伴：
        battle:escort:* 照決戰包的分數〔None：不按〕）。回它的種子（一直在線），這份內容沒有那一場是空的。"""
        from tianxia import atlas
        from tianxia.engine import Game
        from tianxia.state import BotProfile

        d = self.c.battles.get(battle_id)
        if d is None or d.region is None:
            return set()
        name, side = self.AWAY_BOT
        inside = {i for i in self.c.locations if (r := atlas.region_of(self.c, i)) is not None and r.id == d.region}
        start = self.c.scenario.start_location
        loc = start if start not in inside else next(i for i in sorted(self.c.locations) if i not in inside)
        self.begin()
        g = Game.new(self.c, name, rng=random.Random(30), world=self.world, graduated=True)
        g.client = None
        g.sync(CLOCK[0])
        for _ in range(6):
            first = next((o.id for o in g.options(odds=False) if o.id.startswith("choice:") and o.enabled), None)
            if first is None:
                break
            g.choose(first)
        p = g.state.player
        p.bot = BotProfile(personality="普通", seed=seed, faction=side, season_number=self.world.get_season_number())
        p.faction, p.location, p.journey = side, loc, None
        p.visited.add(loc)
        p.tutorial_step = len(self.c.tutorial.steps)
        p.joined_at = -1.0e9
        self.chars.save(g.state)
        emit(f"{name} 站在大區外", loc)
        self.give_mate(name, side)
        return {seed}


class MusterScenario(BattleScenario):
    """集結一軌（全部拆包第 7 批；--track muster）：決戰一軌同一套段落（整段一模一樣），半舊半新切在集結中——base 開了集結、幾位加入、
    顧長風與莫問天按了加入停在挑同伴（PlayerState.escort_pick 寫進存檔）就停，head 接著挑、投效、投靠豪強換邊、開打、晚到、收場。"""

    PHASES_FIRST = BattleScenario.PHASES_FIRST[:BattleScenario.PHASES_FIRST.index("muster_pick") + 1]
    PHASES_SECOND = BattleScenario.PHASES_FIRST[BattleScenario.PHASES_FIRST.index("muster_pick") + 1:] + BattleScenario.PHASES_SECOND


class ProgressScenario(BattleScenario):
    """推進與結算一軌（全部拆包第 8 批；--track progress，自己一個資料庫；計畫 docs/superpowers/plans/2026-11-01-決戰包-第4批.md 第三節 Task 1）。
    同一班人（PLAYERS、序章裡的 NEWBIE）與決戰一軌的小工具，段落自己一套：
    - 第一季 A（target：時刻表的季是長社火攻，不帶設定與測試內容是黃巾決戰）：四位與兩位伺服器假人（PACE_BOTS：直接照 Game 按加入；每一回合
      真人出完招 BotRunner.battle_tick 一次——bot_policy.battle_move → game.battle_now()、決戰包的 bots.score）加入、開打；第一回合官軍放手一搏
      （身上那一招：回合首功）、韓雲起的份量快照擦掉（決戰打到一半上線那一版：他下一次同步補上，_backfill_battle_scores）、再打兩回合（第三回合
      韓雲起放手一搏）、第四回合秦朗月先出招——**這裡切一半**（第四回合收了一部分的招、還沒結算，expect 驗）。後半：補劇情、收齊第四回合的招、打到收場（第五回合起擺一位龍頭上陣的人物陣前敗走、
      最後一擊記在秦朗月身上：收場扣聲威、天下大事、他的補送多名望）、每個人與兩位假人收補送（戰報、紀錄、軍餉、天下大事的最有戲與論功、時間軸）。
    - 第一季 B（時刻表的季：照張曼成那一件定宛城的版本、開宛城；不帶設定：再開黃巾決戰）：秦朗月、韓雲起加入。時刻表的季替官軍擺伏筆鎖定
      （WorldState.locks：收場那一下才讀，戰場上輸了照樣官軍勝、敗因寫鎖定那一句），開打之後廣宗擺進排隊（showdowns_waiting：時間到了、前一場
      還在打），宛城一收場就開（_open_waiting_showdown，expect 驗）；不帶設定開打之後把戰局擺到官軍那一邊（官軍勝）。
    - 第一季 C（時刻表的季：排隊開成的廣宗；不帶設定：再開一場）：秦朗月加入；攻城開著的季管理者替黃巾對汝南荒野下戰書（SIEGES 的 S），韓雲起加入；
      管理者收季——決戰與攻城一起收兵（admin_end_season），兩位收「不算勝負」。
    - 第二季（開下一季、重新投靠）：長社（不帶設定是黃巾決戰）沒人加入——集結截止那一下開打、這一回合逾時那一下保底收場（end_without_fighters：
      時刻表決戰照起點判、不帶設定是兩軍膠著，expect 驗收場了）；再開一場（宛城或黃巾決戰）秦朗月加入、攻城韓雲起加入，時鐘推過季末、這段時間
      **沒人輪詢**，第一個輪詢的人（葉寒舟，沒參戰）那一下補算到季收了、決戰與攻城收兵（_battle_status 季收了那一支；不帶設定沒有攻城，
      _showdown_status 那一支）。
    - 第三季：開一場（長社或黃巾決戰：攻城開著的季跟汝南荒野那一場在同一個大區，鈕帶 @流水號）、秦朗月加入、攻城韓雲起加入，時鐘推過季末、
      沒人輪詢，管理者直接按開下一季（admin_next_season：他那一下同步補算到季收了，看到休季、決戰沒打完——讀回季、收兵；攻城——讀回季、收兵；
      再開下一季）；之後每個人輪詢，收上一季的那一則。
    測試內容沒有決戰（也沒有攻城）：同一串 API 照打，決戰那幾步略過；不帶設定沒有時刻表與攻城。"""

    PACE_BOTS = [("假卯", "guan"), ("假辰", "huang")]  # A 那一場的伺服器假人：兩軍各一
    SIEGES = {**BattleScenario.SIEGES, "S": ("huang", "runan_wilds")}  # 收兵的那幾場攻城：黃巾攻中立的汝南荒野（每一季一場，集結中就收兵）
    SIEGE_PLAYERS = {"韓雲起": ("huang", "S", "強攻")}  # siege_pick 照這一張挑（韓雲起按黃巾那一顆）
    FELL_ROUND = 5  # A 那一場這一回合起擺一位龍頭上陣的人物陣前敗走
    PHASES_FIRST = ["setup", "join", "seat", "pace_bots", "open", "muster", "start", "gamble", "pace"]
    PHASES_SECOND = ["narrate", "finish", "paid", "lock_open", "lock_fight", "close_open", "close", "next_one", "bare", "natural_open",
                     "natural", "next_two", "quiet_open", "quiet", "after"]

    # ── 小工具 ──

    def call(self, who: str, method: str, url: str, body: dict | None = None):
        """同 Scenario.call，另外驗登入沒過期（審查 should：season21 第三季那兩段原本全是 401，開下一季收兵與之後的補送都沒走到，比對是 401 對 401）。"""
        status, data = super().call(who, method, url, body)
        self.expect(status != 401, f"{who} 的登入過期了（{method} {url}）")
        return status, data

    def shelved(self, tag: str, rid: int | None) -> None:
        """那一場收兵了（battles 表裡是沒打完的那一種）；這份內容沒有那一場（rid 是 None）不驗。"""
        b = None if rid is None else self.world.ended_battle(rid)
        self.expect(rid is None or (b is not None and b.unfinished), f"{tag}收兵了（沒打完）")

    def live(self):
        """此刻還沒收場的那一場決戰；收場了、沒有是 None。"""
        b = self.world.get_battle()
        return b if b is not None and b.phase != "ended" else None

    def timetabled(self, b) -> bool:
        d = self.c.battles.get(b.battle_id) if b is not None else None
        return d is not None and d.timetable_event is not None

    def season_row(self, tag: str) -> None:
        """季上收場動到的那幾格：天下大事、江湖史最後幾則、時間軸、伏筆鎖定、排隊與開過的決戰、大勢、旗標、大勢人物此刻的聲威。"""
        s = self.world.get_season()
        emit(f"季 {tag}", {
            "number": self.world.get_season_number(), "phase": self.world.season_phase(), "ended": s.ended, "time": s.time,
            "rumors": [r.text for r in s.rumors][-8:], "chronicle": [r.text for r in s.chronicle][-4:],
            "timeline": {k: [v.key, v.text, v.locked_by] for k, v in sorted(s.timeline.items())},
            "locks": {k: v.side for k, v in sorted(s.locks.items())}, "waiting": list(s.showdowns_waiting),
            "opened": dict(sorted(s.showdowns_opened.items())), "cancelled": list(s.showdowns_cancelled),
            "trends": dict(sorted(s.trends.items())), "flags": sorted(s.flags),
            "figures": {fid: [f.status, f.prestige] for fid, f in sorted(s.figures.items())}})

    def ended_row(self, tag: str, rid: int | None) -> None:
        """battles 表裡那一場（收場、收兵之後從共用狀態拿掉的也讀得到）：結果、沒打完、收兵那一句、收場的季時間、名單與整份的雜湊。"""
        b = None if rid is None else self.world.ended_battle(rid)
        emit(f"那一場 {tag}", None if b is None else {
            "id": b.battle_id, "record": b.record_id, "phase": b.phase, "round": b.round_number, "trend": b.trend,
            "outcome": [b.outcome_title, b.outcome_side, b.outcome_margin, b.outcome_reason], "unfinished": b.unfinished,
            "text": b.unfinished_text, "end": b.end_time, "who": sorted(b.participants),
            "mvps": [[m.round, m.name, m.move] for m in b.mvps],
            "commanders": [[c.fid, c.fallen_round, c.felled_by, c.settled] for c in b.commanders],
            "sha": hashlib.sha256(b.model_dump_json().encode("utf-8")).hexdigest()})

    def join_live(self, who: str, tag: str) -> str | None:
        """這個人按那一場決戰的加入（自己陣營那一顆；同一個大區兩場時鈕帶 @，照決戰那一場的）；有挑同伴那一步就不派。"""
        pick = self.pick_of(self.ids(self.main(who)), f"battle:join:{self.PLAYERS.get(who)}")
        emit(f"{who} {tag}", pick)
        if pick is not None:
            self.choose(who, pick)
            self.no_escort(who)
        return pick

    def siege_join(self, tag: str) -> None:
        """攻城開著的季：管理者替黃巾對汝南荒野下戰書（下一個同步的人把它開成集結），韓雲起擺過去按加入（siege_pick；同一個大區兩場時照 @）。"""
        if not self.siege_on():
            return
        side, loc = self.SIEGES["S"]
        self.place(self.LATE_GAMBLER, loc)
        self.do(ADMIN, "admin_conquest_letter", {"id": loc, "side": side})
        self.call(ADMIN, "GET", "/api/admin")
        pick = self.siege_pick(self.LATE_GAMBLER, self.ids(self.main(self.LATE_GAMBLER)))
        emit(f"{self.LATE_GAMBLER} {tag}按的攻城", pick)
        if pick is not None:
            self.choose(self.LATE_GAMBLER, pick)
            self.no_escort(self.LATE_GAMBLER)
        self.siege_row(tag, ("S",))

    def open_b(self) -> None:
        """B 那一場：時刻表的季照張曼成那一件定宛城的版本（GET /api/admin「定結果」的第一個；已經結算了就不定）、開宛城；不帶設定再開黃巾決戰。"""
        op, battle_id = self.target()
        if op == "start_battle":
            self.do(ADMIN, op, {"id": battle_id})
            return
        from tianxia import timetable

        event = timetable.find(self.c, "wancheng")
        _, data = self.call(ADMIN, "GET", "/api/admin")
        value = next((r["value"] for r in data.get("results", []) if r["value"].startswith(f"{event.version_from}|")), None)
        if value is not None and event.version_from not in self.world.get_season().timeline:
            eid, key = value.split("|", 1)
            self.do(ADMIN, "resolve_event", {"id": eid, "key": key})
        self.do(ADMIN, "start_showdown", {"id": event.id})

    def skip_season(self) -> None:
        """時鐘推過季末（world.season_end_time；照最後一次補算的季時間算剩多少，多推 30 步）：這段時間沒有請求。"""
        from tianxia.world import season_end_time

        s = self.world.get_season()
        left = max(0.0, season_end_time(s, self.c) - s.time) / self.c.config.time_scale
        self.skip(int(left // self.STEP_SECONDS) + 30)

    def bot_act(self, name: str, want: str, tag: str) -> None:
        """照假人程式的做法替一位假人按一顆（鎖裡讀存檔、建 Game、同步、按、存回去）：選單上 id（不看 @）是 want 的那一顆。"""
        from tianxia.engine import Game

        self.begin()
        pick = None
        with self.world.action_lock():
            state = self.chars.load(name)
            if state is None:
                emit(f"{name} {tag}（沒有這個人）", None)
                return
            g = Game(self.c, state, random.Random(STEP[0]), self.world)
            g.client = None
            g.sync(CLOCK[0])
            pick = next((o.id for o in g.options(odds=False) if o.enabled and o.id.split("@")[0] == want), None)
            if pick is not None:
                g.choose(pick)
            self.chars.save(g.state)
        emit(f"{name} {tag}", pick)

    def bot_sync(self, name: str, tag: str) -> None:
        """照假人程式的做法同步一位假人（收補送），存檔那幾格寫進輸出。"""
        from tianxia.engine import Game

        self.begin()
        with self.world.action_lock():
            state = self.chars.load(name)
            if state is None:
                return
            g = Game(self.c, state, random.Random(STEP[0]), self.world)
            g.client = None
            g.sync(CLOCK[0])
            self.chars.save(g.state)
        self.me(name, tag)

    def bot_tick(self) -> None:
        """BotRunner.battle_tick 一次（在場還沒出招的假人出招；真人都送出了就不等 BATTLE_DELAY）：每一下新建一份 runner、亂數照步數（前半＋後半是兩個行程）。"""
        from tianxia.bot_runner import BotRunner

        self.begin()
        runner = BotRunner(self.c, self.world, self.chars, rng=random.Random(STEP[0]), clock=lambda: CLOCK[0])
        report = runner.battle_tick()
        emit("假人出招", {"acted": report.acted, "online": report.online, "skipped": report.skipped, "failed": report.failed})

    def round(self, gamblers: dict[str, str]) -> None:
        """同決戰一軌的 round（gamblers 放手一搏、掛機的那一位不按、其餘照回合數挑三招之一；回合沒結就推過期限再輪詢一次），只是真人出完招之後
        假人在場的話 BotRunner.battle_tick 一次；不打攻城（這一軌的攻城都在集結中就收兵）。"""
        b = self.live()
        if b is None or b.phase != "active":
            return
        n = b.round_number
        for who in self.PLAYERS:
            if who == self.IDLER:
                continue
            if who in gamblers:
                self.do(who, "battle_text", {"text": gamblers[who]})
                continue
            moves = sorted(i for i, o in self.ids(self.main(who)).items() if i.startswith("battle:act:") and o.get("enabled"))
            if moves:
                self.choose(who, moves[n % len(moves)])
        if any(name in b.participants for name, _ in self.PACE_BOTS):
            self.bot_tick()
        b = self.world.get_battle()
        if b is not None and b.phase == "active" and b.round_number == n:
            self.skip_past(b.round.opened_real + self.c.battles[b.battle_id].round_seconds)
            self.main(self.GAMBLER)
        self.battle_row(f"第 {n + 1} 回合之後")

    def fight_out(self, tag: str, fell: bool = False) -> None:
        """打到收場（最多 40 回合）；fell：第 FELL_ROUND 回合起、還沒有人敗走時擺一位龍頭上陣的人物陣前敗走（最後一擊記在秦朗月身上）；有等著補的劇情就補。"""
        for _ in range(40):
            b = self.live()
            if b is None or b.phase != "active":
                break
            if fell and b.round_number >= self.FELL_ROUND and b.commanders and all(c.fallen_round is None for c in b.commanders):
                fid, n = b.commanders[0].fid, b.round_number

                def down(x, fid=fid, n=n) -> None:
                    for c in x.commanders:
                        if c.fid == fid:
                            c.fallen_round, c.felled_by = n, self.GAMBLER

                self.world.mutate_battle(down)
                emit("龍頭上陣的人物陣前敗走", [fid, n])
            self.round({})
            b = self.world.get_battle()
            if b is not None and b.tales:
                self.tell(f"{tag}第 {b.round_number} 回合補劇情")
        self.battle_row(f"{tag}收場")

    def new_season(self, tag: str) -> None:
        """管理者開下一季；每個人同步（換成新的角色）、開局待選的事件選掉、重新投靠（join：體力補滿、過了新手期）。"""
        self.do(ADMIN, "next_season")
        for who in [*self.PLAYERS, self.NEWBIE]:
            self.main(who)
        for who in self.PLAYERS:
            self.settle_choices(who)
        self.join()
        self.season_row(tag)

    # ── 情境（前半）──

    def pace_bots(self) -> None:
        """兩位伺服器假人（兩軍各一）建進資料庫、擺在 A 那一場的大區（同決戰一軌 bots 那一段的做法）。測試內容沒有決戰：略過。"""
        from tianxia.engine import Game
        from tianxia.state import BotProfile

        loc = self.spot(self.target()[1])
        if loc is None:
            emit("這份內容沒有決戰：假人那一段略過", None)
            return
        for i, (name, side) in enumerate(self.PACE_BOTS):
            self.begin()
            g = Game.new(self.c, name, rng=random.Random(50 + i), world=self.world, graduated=True)
            g.client = None
            g.sync(CLOCK[0])
            for _ in range(6):  # 開局待選的事件：選掉
                first = next((o.id for o in g.options(odds=False) if o.id.startswith("choice:") and o.enabled), None)
                if first is None:
                    break
                g.choose(first)
            p = g.state.player
            p.bot = BotProfile(personality="普通", seed=71 + i, faction=side, season_number=self.world.get_season_number())
            p.faction, p.location, p.journey = side, loc, None
            p.visited.add(loc)
            p.tutorial_step = len(self.c.tutorial.steps)
            p.joined_at = -1.0e9
            self.chars.save(g.state)
            emit(f"{name} 擺在 A 那一場的大區", [side, loc])

    def muster(self) -> None:
        """同決戰一軌的集結（四位按加入、再看一次），之後兩位假人照 Game 按自己那一軍的加入。"""
        super().muster()
        if self.live() is None:
            return
        for name, side in self.PACE_BOTS:
            self.bot_act(name, f"battle:join:{side}", "集結時按的")
        self.battle_row("假人加入之後")

    def pace(self) -> None:
        """前半的最後一段：韓雲起的份量快照擦掉，他下一次同步就補上（_backfill_battle_scores：只在自己的請求路徑補）；再打兩回合（第三回合韓雲起
        放手一搏，身上那一招）；第四回合秦朗月先出招（同 round 的挑法），別人還沒按。前半停在這裡：第三回合結算過了、第四回合收了一部分的招
        （BattleRound.pending_actions 寫在資料庫裡；不成立就停）——後半由新程式接著收齊、結算這一回合（審查 nit：原本切在第四回合剛開、
        一招都還沒收，接手的只有補劇情）。"""
        b = self.live()
        if b is None:
            emit("沒有開打中的決戰：前半那兩回合略過", None)
            return
        name = self.LATE_GAMBLER
        if name in b.participants:
            self.world.mutate_battle(lambda x: setattr(x.participants[name], "scores", {}))
            emit(f"{name} 的份量快照擦掉", None)
        self.main(name)
        self.battle_row("補上份量快照之後")
        self.round({})
        self.round({name: f"{BATTLE_SURE}：繞到敵後，放火燒糧"})  # 評 100、一定成，身上那一招：這一回合挑回合首功
        b = self.live()
        if b is not None and b.phase == "active":
            first = self.GAMBLER
            moves = sorted(i for i, o in self.ids(self.main(first)).items() if i.startswith("battle:act:") and o.get("enabled"))
            if moves:
                self.choose(first, moves[b.round_number % len(moves)])
        b = self.world.get_battle()
        pending = [] if b is None else sorted(b.round.pending_actions)
        emit("前半停在這裡：這一回合已經出招的", pending)
        self.battle_row("前半停下")
        self.expect(b is not None and b.phase == "active" and b.round_number >= 3 and self.GAMBLER in pending
                    and len(pending) < sum(1 for q in b.participants.values() if not q.eliminated),
                    "前半停在一回合收了一部分的招" + ("" if b is None else f"（此刻 {b.phase}、打過 {b.round_number} 回合、已出招 {pending}）"))

    # ── 情境（後半）──

    def finish(self) -> None:
        """A 打到收場（第五回合起一位龍頭陣前敗走）；季上那幾格。"""
        rid = None if self.live() is None else self.live().record_id
        self.fight_out("A ", fell=True)
        self.ended_row("A 收場", rid)
        self.season_row("A 收場之後")

    def paid(self) -> None:
        """收場之後每個人與兩位假人（照假人程式的做法同步一次）收補送；秦朗月的戰報頁與最上面那一筆。"""
        for who in [*self.PLAYERS, self.NEWBIE]:
            self.main(who)
            self.me(who, "A 收補送之後")
        if self.c.battles:
            for name, _ in self.PACE_BOTS:
                self.bot_sync(name, "A 收補送之後")
        _, data = self.call(self.GAMBLER, "GET", "/api/reports")
        rows = [r["id"] for r in data.get("list", [])] if isinstance(data, dict) else []
        for rid in rows[:1]:
            self.call(self.GAMBLER, "GET", f"/api/reports?id={rid}")

    def lock_open(self) -> None:
        """B：開宛城（不帶設定是黃巾決戰）、秦朗月與韓雲起擺過去加入、集結截止開打；時刻表的季替官軍擺伏筆鎖定、廣宗擺進排隊；不帶設定把戰局
        擺到官軍那一邊。"""
        if not self.c.battles:
            emit("這份內容沒有決戰：B、C 那兩場略過", None)
            return
        self.open_b()
        b = self.live()
        if b is None:
            emit("B 那一場沒開成", None)
            return
        loc = self.spot(b.battle_id)
        for who in (self.GAMBLER, self.LATE_GAMBLER):
            self.place(who, loc)
            self.join_live(who, "B 那一場按的")
        if self.timetabled(b):
            from tianxia.state import Lock

            event = self.c.battles[b.battle_id].timetable_event

            def lock(s) -> None:
                s.locks[event] = Lock(side="guan", name=self.GAMBLER, time=s.time)

            self.world.mutate_season(lock)
            emit("伏筆鎖定", [event, "guan"])
        self.start()
        b = self.live()
        if b is not None and b.phase == "active":
            if self.timetabled(b):
                def wait(s) -> None:
                    if "guangzong" not in s.showdowns_waiting and "guangzong" not in s.showdowns_opened and "guangzong" not in s.timeline:
                        s.showdowns_waiting.append("guangzong")

                self.world.mutate_season(wait)
                emit("廣宗擺進排隊", list(self.world.get_season().showdowns_waiting))
            # 戰局擺到一邊：時刻表的季擺到黃巾那一邊（戰場上黃巾佔上風，收場照伏筆鎖定官軍勝、敗因寫鎖定那一句）；不帶設定擺到官軍那一邊（官軍勝）
            trend = 30 if self.timetabled(b) else 88
            self.world.mutate_battle(lambda x: setattr(x, "trend", trend))
            emit("戰局擺到一邊", trend)
        self.battle_row("B 開打")

    def lock_fight(self) -> None:
        """B 打到收場：時刻表的季照伏筆鎖定官軍勝（戰場上輸了是險勝、敗因寫鎖定那一句），收場那一下開排隊的廣宗（expect 驗）；兩位收補送。"""
        b = self.live()
        if b is None:
            return
        rid, timed = b.record_id, self.timetabled(b)
        self.fight_out("B ")
        self.ended_row("B 收場", rid)
        self.season_row("B 收場之後")
        for who in (self.GAMBLER, self.LATE_GAMBLER):
            self.main(who)
            self.me(who, "B 收補送之後")
        nxt = self.live()
        emit("B 收場之後開的那一場", None if nxt is None else [nxt.battle_id, nxt.phase, nxt.record_id])
        self.expect(not timed or (nxt is not None and nxt.battle_id == "guangzong"), "宛城一收場就開了排隊的廣宗")

    def close_open(self) -> None:
        """C：時刻表的季是排隊開成的廣宗（不帶設定再開一場黃巾決戰）；秦朗月擺過去加入。攻城那一場韓雲起加入。"""
        if self.c.battles and self.live() is None and self.target()[0] == "start_battle":
            self.do(ADMIN, "start_battle", {"id": self.target()[1]})
        b = self.live()
        if b is not None:
            self.place(self.GAMBLER, self.spot(b.battle_id))
            self.join_live(self.GAMBLER, "C 那一場按的")
        self.siege_join("收季之前")
        self.battle_row("收季之前")

    def close(self) -> None:
        """管理者收季（admin_end_season：讀回收季那一份季之後，沒打完的決戰與每一場攻城收兵，再補大事）；四位收「不算勝負」。"""
        b = self.live()
        rid = None if b is None else b.record_id
        slot = self.slot_of("S") if self.siege_on() else None
        self.do(ADMIN, "end_season")
        self.ended_row("收季收兵的決戰", rid)
        self.ended_row("收季收兵的攻城", None if slot is None else slot.record_id)
        self.shelved("管理者收季：決戰", rid)
        self.shelved("管理者收季：攻城", None if slot is None else slot.record_id)
        self.siege_row("收季之後", ("S",))
        self.season_row("收季之後")
        for who in self.PLAYERS:
            self.main(who)
            self.me(who, "收季之後")

    def next_one(self) -> None:
        self.new_season("第二季開季")

    def bare(self) -> None:
        """第二季：長社（不帶設定是黃巾決戰）沒人加入——集結截止那一下開打（場上一個人都沒有）、這一回合逾時那一下保底收場（不成立就停）。"""
        if not self.c.battles:
            emit("這份內容沒有決戰：沒人加入的那一場略過", None)
            return
        op, battle_id = self.target()
        if self.live() is None:
            self.do(ADMIN, op, {"id": battle_id})
        b = self.live()
        if b is None:
            emit("沒人加入的那一場沒開成", None)
            return
        rid = b.record_id
        if b.phase == "muster":
            self.skip_past(b.muster_deadline_real)
            self.main(self.IDLER)
        b = self.live()
        if b is not None and b.phase == "active":
            self.skip_past(b.round.opened_real + self.c.battles[b.battle_id].round_seconds)
            self.main(self.IDLER)
        self.ended_row("沒人加入的那一場", rid)
        self.season_row("保底收場之後")
        self.expect(self.live() is None, "沒人加入的那一場保底收場了")

    def natural_open(self) -> None:
        """第二季再開一場（宛城；不帶設定黃巾決戰），秦朗月加入；攻城那一場韓雲起加入。"""
        if self.c.battles and self.live() is None:
            self.open_b()
        b = self.live()
        if b is not None:
            self.place(self.GAMBLER, self.spot(b.battle_id))
            self.join_live(self.GAMBLER, "季末之前按的")
        self.siege_join("季末之前")
        self.battle_row("季末之前")

    def natural(self) -> None:
        """時鐘推過季末、沒人輪詢；第一個輪詢的人（葉寒舟，沒有參戰）那一下補算到季收了，選單推決戰時看到季收了：沒打完的決戰與每一場攻城收兵
        （_battle_status 季收了那一支；沒有攻城的季走 _showdown_status）。之後兩位收「不算勝負」。"""
        b = self.live()
        rid = None if b is None else b.record_id
        slot = self.slot_of("S") if self.siege_on() else None
        self.skip_season()
        self.battle_row("推過季末、還沒人輪詢")
        self.main(self.IDLER)
        self.ended_row("季收了收兵的決戰", rid)
        self.ended_row("季收了收兵的攻城", None if slot is None else slot.record_id)
        self.shelved("季自然收掉：決戰", rid)
        self.shelved("季自然收掉：攻城", None if slot is None else slot.record_id)
        self.season_row("季自然收掉之後")
        for who in (self.GAMBLER, self.LATE_GAMBLER):
            self.main(who)
            self.me(who, "季自然收掉之後")

    def next_two(self) -> None:
        self.new_season("第三季開季")

    def quiet_open(self) -> None:
        """第三季開一場（長社；不帶設定黃巾決戰），秦朗月加入；攻城那一場韓雲起加入（攻城開著的季跟長社在同一個大區，鈕帶 @）。
        開之前每個人重新登入一次：登入狀態認 accounts.SESSION_SECONDS（30 天，照登入那一刻算），後半開頭那一次登入到第三季季末，season21
        已經超過了（審查 should：原本 quiet、after 兩段全是 401）。放在季末之前：登入會輪詢一次，季末之後才登入就變成「第一個輪詢的人收兵」，
        不是管理者開下一季那一下收。"""
        self.login_all()
        op, battle_id = self.target()
        if self.c.battles and self.live() is None:
            self.do(ADMIN, op, {"id": battle_id})
        b = self.live()
        if b is not None:
            self.place(self.GAMBLER, self.spot(b.battle_id))
            self.join_live(self.GAMBLER, "第三季按的")
        self.siege_join("第三季")
        self.battle_row("第三季季末之前")

    def quiet(self) -> None:
        """時鐘推過季末、沒人輪詢；管理者直接按開下一季（admin_next_season：他那一下同步補算到季收了，看到休季、決戰沒打完——讀回季、收兵；攻城——讀回季、
        收兵；再開下一季）。"""
        b = self.live()
        rid = None if b is None else b.record_id
        slot = self.slot_of("S") if self.siege_on() else None
        self.skip_season()
        self.battle_row("推過季末、還沒人輪詢")
        self.do(ADMIN, "next_season")
        self.ended_row("開下一季收兵的決戰", rid)
        self.ended_row("開下一季收兵的攻城", None if slot is None else slot.record_id)
        self.shelved("開下一季：決戰", rid)
        self.shelved("開下一季：攻城", None if slot is None else slot.record_id)
        self.season_row("第四季開季")

    def after(self) -> None:
        """每個人輪詢：收上一季的那一則（不算勝負；上一季那一支）。"""
        for who in [*self.PLAYERS, self.NEWBIE]:
            self.main(who)
            self.me(who, "第四季開季之後")


# 改一個字（selftest）：第 7 批換成這一批搬的一句（晚到的人趕到戰場；搬之前在 engine.py、之後在 features/battle/muster.py）——決戰一軌
# 前半走到（late）、集結一軌後半走到。第 5、6 批那兩句（view.py 的「軍餉發下來了。」、admin.py 的「（沒有進行中的決戰。）」）在計畫第五節
# 的單點突變裡照樣驗
_BATTLE_MUTATION = (("tianxia/features/battle/muster.py", "tianxia/engine.py"), ("你趕到了戰場，這一回合就能出手。", "你趕到了戰場，這一回合就能出手！"))
register_track("battle", BattleScenario, _BATTLE_MUTATION, "week7")
register_track("muster", MusterScenario, _BATTLE_MUTATION, "week7")  # 第 7 批：同一套段落，切在集結中
# 第 8 批：推進一軌（ProgressScenario），改一個字是論功那一則（搬之前在 engine.py 的 _merit_line、之後在 features/battle/progress.py）——
# 後半 A 收場那一下寫進天下大事（season_row 寫出來）。找的那一句要連 f-string 的尾巴（`name}論功：" + `）：progress.py 的模組說明也有
# 「收場與論功：」，只寫「論功：」在搬完的檔裡有兩處、_mutant 找不到剛好一處就停（第 8 批審查）
_PROGRESS_MUTATION = (("tianxia/features/battle/progress.py", "tianxia/engine.py"), ('name}論功：" + ', 'name}論功！" + '))
register_track("progress", ProgressScenario, _PROGRESS_MUTATION, "week7")
