"""same_behavior 一軌一檔：roadmate（這一檔登記 roadmate）。"""
from __future__ import annotations

import hashlib
import os
import random

from sb.harness import ADMIN, CLOCK, CLOCK0, STEP, emit, register_track
from sb.tracks.travel import TravelScenario

# ═══════════════════════════ roadmate（全部拆包第 48 批：移動二——出發與抵達的補算、在路上那一行字、結伴同行路上那一半、/api/party/leave） ═══════════════════════════
# 另開一軌（不接在 travel 那一軌後面）的理由：結伴要兩個人以上、五組人各走各的路（二十二個帳號），跟 travel 那一軌的十一個人互不相干，
# 合在一起每次改一組都要重比整個資料庫；另開一軌可以只重比這一軌，也各自切一半（TravelScenario 的 PHASES、PLAYERS 全換掉，借它的只有小工具）。

class RoadmateScenario(TravelScenario):
    """移動二一軌（全部拆包第 48 批；--track roadmate，自己一個資料庫）。結伴同行（Joy 2026-10-19 把結伴從玩家卡上拿掉，/api/peer/act 的 travel 回
    「沒有這個動作」，所以這一軌直接記一張 kind 是 travel 的邀請，帶頭的人發、跟著的人在選單上 invite:yes／invite:no 回；帶頭的人 invite:cancel 收回）、
    答應時重驗（已經跟著別人、身後已經有人跟著、帶頭的人已經跟著別人；「帶頭的人不在這裡了」被玩家互動包擋在前面，沒進到 party.join，見限制）、帶頭的人步行出發（跟著的人照抄同一趟，騎馬的照自己的坐騎再省）、
    疾行出發（體力不夠的跟不上，兩邊各記一句；手上有事、已經不在出發那一站的兩種沒走到，見限制）、結伴路上三樣小事分收穫（含收穫上限拿滿的對照）、帶頭的人喊停、折返
    （步行、疾行的 road:back:dash）、跟著的人在路上按 act:part、還在等時按 /api/party/leave（沒跟著誰時也按一次）、答應了卻自己先走、
    party_wait_seconds 內沒動身就散了、走到終點拱手作別、兩邊 /api/main 的 party；出發與抵達的補算（出發那一句的現實倒數、抵達）在這些路上一併走到，
    「剛出發就折返」「季落幕停在當下」兩支沒走到（見限制）。
    **前半停在四件寫到一半的事**：答應了結伴、帶頭的人還沒動身（湛長庚、戎棠）；結伴走在路上、做了一件小事（霍承嶼）；帶頭的人喊了停、還沒走到那一站（樊靖安）；
    跟著的人分道揚鑣之後自己還在路上（莘慕白）。後半：接著做完小事、跟著的人在路上按 /api/party/leave、折返再折返、等著的帶頭人動身（跟著的人照抄）、
    等太久散了、喊停的那一站、走到終點；假人（BotRunner 四個收到結伴邀請，其中一個已經跟著別人；整季機器人眼前的選單與挑法）；收季、開下一季。
    **這一軌的限制（不當成涵蓋了；第 48 批審查實跑 season21 量到）**：「你在路上」這一種答應時的拒絕（選單上在路上沒有邀請可按）只有單元測試；
    測試內容（test）的路最長 3 分鐘，前半切下去時在路上的人少（計畫第五節量到 test 3 個、season21 與 week7 各 7 個），「切在路上」以 season21、week7 為主（第 47 批認定第 6 條）。
    沒走到的支：(1) departure.depart 的「立刻折返」（at_once）；(2) arrivals 的「賽季落幕，停在」：收季之後情境只讀資料庫，沒有同步路上的人；
    (3) lead 裡「手上有事」（懸賞榜 block）：Game 建構時 engine 的 `if p.picking_bounty and not bounties.board_here(...)` 把直接寫進去的 picking_bounty 收掉
    （board_here 要過 week_unlock；測試內容沒有陣營），欒修遠照樣跟上；(4) 戚懷瑾「已經不在出發那一站」那一句：`_party` 先把他篩掉，鄂臨川的訊息沒提到他；
    (5) 答應時重驗的第四種「帶頭的人不在這裡了」：回的是玩家互動包 invite_actions.answer_invite 的 social.GONE（「對方已經不在這裡了。」，沒有括號），
    party.join 的 presence.GONE 那一支與 join_refusal 的 other is None 那一支都沒走到；(6) 霍承嶼「前半最後做了一件小事」的 leg_actions 沒交到新程式手上：
    後半第一個碰到他的請求（重新登入）補算一口氣過了兩站，leg_actions 被清掉，所以選單與 share_road 讀 leg_actions 的支只有單元測試；
    交接過去的只有複製的 journey 與 road_rewards_today（紀望舒上限滿）。這些支的 ast 搬前搬後一樣，風險低；要補的話另開情境（week7 可能走得到 (3)，未驗）。"""

    HUO, LIN, JI, TU = "霍承嶼", "藺知夏", "紀望舒", "屠宛然"  # 步行帶頭；騎馬跟著；收穫拿滿的對照；婉拒後改跟戎棠、還在等時分道揚鑣
    E, SANG, QI, LUAN, QIN = "鄂臨川", "桑若水", "祁雲岫", "欒修遠", "戚懷瑾"  # 疾行帶頭；跟上的（騎馬）；體力不夠；手上有事；已經不在這裡
    FAN, MI, RAN = "樊靖安", "莘慕白", "冉驚鴻"  # 喊停；在路上分道揚鑣；一直跟到停下來
    ZHAN, BI, TAI = "湛長庚", "畢雲書", "邰明遠"  # 先答應、後動身；答應了卻自己先走；等著、之後照抄
    RONG, YUE = "戎棠", "樂正初"  # 一直沒動身（等太久散了）
    QUE, MEI, HE, MU, XIAO = "闕子安", "梅疏影", "賀蘭澈", "沐春風", "蕭長歌"  # 重驗那幾種；闕子安也是假人邀請的帶頭人
    GHOST = "遠行客"  # 沒有這個人：記著「跟著他」的對照
    W1 = HUO  # 借 TravelScenario.rumor（沿途的傳聞掛在帶頭人的路上）
    NEWBIE = "初出茅廬"
    PLAYERS = {HUO: "guan", LIN: "guan", JI: "guan", TU: None, E: "huang", SANG: "huang", QI: "huang", LUAN: "huang", QIN: "huang",
               FAN: "guan", MI: "guan", RAN: None, ZHAN: "guan", BI: "guan", TAI: None, RONG: "huang", YUE: "huang",
               QUE: "guan", MEI: None, HE: "huang", MU: "huang", XIAO: "guan"}
    BOT_SEATS = ["行丙", "行丁", "行戊", "行己"]
    PHASES_FIRST = ["setup", "seat", "join_up", "reverify", "leave_wait", "go", "half"]
    PHASES_SECOND = ["resume", "tasks", "parts", "backs", "waits", "halts", "arrivals", "bots", "season"]
    WALKERS = (HUO, LIN, JI, FAN, MI, RAN, BI, ZHAN, TAI, RONG)
    WATCHED = (HUO, LIN, JI, E, SANG, QI, LUAN, QIN, FAN, MI, RAN, ZHAN, BI, TAI, RONG, YUE, TU)

    # ── 小工具 ──

    def reach(self, who: str, mode: str = "walk") -> str | None:
        """從這個人站的地方走得到（這個走法）、路程最長的地點（一樣長取 id 排前面的）。"""
        from tianxia import atlas

        with self.world.action_lock():
            state = self.chars.load(who)
        found = atlas.shortest_routes(state, self.c)
        best = None
        for loc_id, route in sorted(found.items()):
            if not route.path or loc_id == state.player.location or atlas.travel_refusal(state, self.c, loc_id, mode) is not None:
                continue
            if best is None or round(route.minutes, 6) > best[0]:
                best = (round(route.minutes, 6), loc_id)
        return best[1] if best else None

    def aside(self) -> str:
        """出發地以外的第一個地點（擺人「已經不在這裡」用）。"""
        return next((loc for loc in sorted(self.c.locations) if loc != self.hub()), self.hub())

    def invite(self, sender: str, target: str) -> None:
        """記一張結伴同行的邀請（kind 是 travel；玩家卡上沒有入口了，只剩舊的邀請照舊走完）。"""
        from tianxia.features.peers import invites

        with self.world.action_lock():
            loc = self.chars.load(sender).player.location
        self.begin()
        self.world.mutate_season(lambda w: invites.send(w, self.c, "travel", sender, target, loc))
        emit(f"{sender} 發結伴同行的邀請給 {target}", loc)

    def found(self, target: str, sender: str) -> list:
        return [i for i in self.world.get_season().invites if i.kind == "travel" and i.sender == sender and i.target == target]

    def reply(self, target: str, sender: str, verb: str) -> None:
        """選單上回他的邀請（invite:yes|no:<編號>，同真人按的那一顆）；先看一眼選單；沒有他發的邀請寫「沒有」。"""
        self.main(target)
        found = self.found(target, sender)
        if not found:
            emit(f"{target} 沒有 {sender} 的邀請", None)
            return
        self.choose(target, f"invite:{verb}:{found[0].id}")

    def cancel(self, sender: str, target: str) -> None:
        """帶頭的人在自己的選單上收回邀請（invite:cancel:<編號>）。"""
        self.main(sender)
        found = self.found(target, sender)
        if not found:
            emit(f"{sender} 沒有給 {target} 的邀請", None)
            return
        self.choose(sender, f"invite:cancel:{found[0].id}")

    def follow(self, who: str, leader: str) -> None:
        """直接擺成「跟著 leader」（對照用）；since 擺在很遠的未來，不會因為步數累積（每一步一分鐘）就散了。"""
        from tianxia.state import Tagalong

        self.edit(who, lambda p: setattr(p, "tagalong", Tagalong(leader=leader, since=CLOCK0 + 10 ** 7)))

    def unfollow(self, who: str) -> None:
        self.edit(who, lambda p: setattr(p, "tagalong", None))

    def keep(self, who: str) -> None:
        """答應之後把等的期限推到很遠（party_wait_seconds 只有 600 現實秒，十步就散了）；要測散掉的另外擺。"""
        def fn(p) -> None:
            if p.tagalong is not None:
                p.tagalong.since = CLOCK0 + 10 ** 7
        self.edit(who, fn)

    def cap_out(self, who: str) -> None:
        """這個人這個遊戲日路上小事的收穫已經拿滿了（跟著的人自己的上限，分收穫時照他的算）。"""
        from tianxia.rules import game_day

        with self.world.action_lock():
            state = self.chars.load(who)
            world = self.world.get_season()
            state.player.road_rewards_today["task"] = [game_day(self.c, world), self.c.config.road_reward_daily_cap]
            self.chars.save(state)

    def party_leave(self, who: str) -> None:
        """場景底下的「分道揚鑣」（POST /api/party/leave）：回 {main, message}。"""
        self.call(who, "POST", "/api/party/leave")

    def pick_view(self, who: str, tag: str) -> None:
        """整季機器人眼前的選單與挑法（有邀請的、跟著人在路上的）。"""
        import random as _random

        from tianxia import bot

        self.main(who)
        self.begin()
        game = self.server.game_for(who)
        opts = game.options(odds=False)
        emit(f"{who} 整季機器人眼前的選單 {tag}", [[o.id, o.enabled, o.label] for o in opts if o.id.startswith(("move:", "road:", "act:", "invite:"))])
        emit(f"{who} 整季機器人挑的 {tag}", sorted({str(bot.pick(game, opts, _random.Random(k))) for k in range(30)}))

    # ── 前半 ──

    def seat(self) -> None:
        from tianxia.state import Equipment

        for who, side in self.PLAYERS.items():
            self.place(who, self.hub(), side)
            self.edit(who, lambda p: p.stats.update({"silver": 400}))
        for who, mount_id in ((self.LIN, "騎:901"), (self.SANG, "騎:902")):  # 騎馬的跟著人（坐騎沒開的設定這一匹就只是帶著）
            self.edit(who, lambda p, mount_id=mount_id: setattr(p, "mount", Equipment(id=mount_id, slot="mount", name="棗騮馬", tier=1, quality="下品")))
        for who in self.PLAYERS:
            self.main(who)
        self.stock_view("坐定")

    def join_up(self) -> None:
        """五組人答應結伴（每一個答應完立刻把等的期限推遠）：帶頭的人看得到誰跟著他；一個婉拒、之後改跟戎棠。"""
        groups = ((self.HUO, (self.LIN, self.JI)), (self.E, (self.SANG, self.QI, self.LUAN, self.QIN)), (self.FAN, (self.MI, self.RAN)),
                  (self.ZHAN, (self.BI, self.TAI)), (self.RONG, (self.YUE,)))
        for lead, followers in groups:
            for who in followers:
                self.invite(lead, who)
                self.reply(who, lead, "yes")
                self.keep(who)
            self.main(lead)
        self.invite(self.HUO, self.TU)
        self.reply(self.TU, self.HUO, "no")
        self.main(self.HUO)

    def reverify(self) -> None:
        """收回邀請；答應時重驗的四種：已經跟著別人、身後已經有人跟著、帶頭的人已經跟著別人、帶頭的人已經不在這裡（第四種：邀請還在選單上，按下去才發現）。"""
        hub = self.hub()
        self.invite(self.QUE, self.XIAO)
        self.main(self.XIAO)
        self.cancel(self.QUE, self.XIAO)
        self.main(self.XIAO)
        self.follow(self.MEI, self.GHOST)
        self.invite(self.QUE, self.MEI)
        self.reply(self.MEI, self.QUE, "yes")
        self.unfollow(self.MEI)
        self.follow(self.MU, self.HE)
        self.invite(self.QUE, self.HE)
        self.reply(self.HE, self.QUE, "yes")
        self.unfollow(self.MU)
        self.follow(self.QUE, self.GHOST)
        self.invite(self.QUE, self.XIAO)
        self.reply(self.XIAO, self.QUE, "yes")
        self.unfollow(self.QUE)
        self.invite(self.QUE, self.XIAO)
        self.place(self.QUE, self.aside())
        self.reply(self.XIAO, self.QUE, "yes")
        self.place(self.QUE, hub, self.PLAYERS[self.QUE])
        for who in (self.QUE, self.XIAO, self.MEI, self.HE, self.MU):
            self.me(who, "重驗之後")

    def leave_wait(self) -> None:
        """還在等帶頭的人動身時按「分道揚鑣」（POST /api/party/leave）；沒跟著誰時也按一次。"""
        self.invite(self.RONG, self.TU)
        self.reply(self.TU, self.RONG, "yes")
        self.keep(self.TU)
        self.main(self.RONG)
        self.party_leave(self.TU)
        self.main(self.RONG)
        self.party_leave(self.TU)
        self.party_leave(self.XIAO)

    def go(self) -> None:
        """出發（世界時鐘一請求走一分鐘，所以這一段不插別的請求，前半切下去的時候人還在路上）：疾行的先走（祁雲岫體力 0、欒修遠手上有懸賞榜開著、
        戚懷瑾已經不在出發那一站、桑若水跟上），再接著霍承嶼、樊靖安步行（跟著的人照抄），霍承嶼做一件小事（紀望舒的上限已滿），樊靖安喊停，
        莘慕白在路上分道揚鑣，畢雲書答應了卻自己先走。"""
        dest = {self.HUO: self.far(self.HUO), self.FAN: self.far(self.FAN), self.BI: self.far(self.BI), self.E: self.reach(self.E, "dash")}
        emit("各人要去的遠處", dest)
        self.cap_out(self.JI)
        self.edit(self.QI, lambda p: setattr(p, "stamina", 0.0))
        self.edit(self.LUAN, lambda p: setattr(p, "picking_bounty", True))
        self.place(self.QIN, self.aside())
        if dest[self.E] is not None:
            self.travel(self.E, dest[self.E], "dash")
        for who in (self.E, self.SANG, self.QI, self.LUAN, self.QIN):
            self.me(who, "疾行之後")
        for who in (self.HUO, self.FAN):
            if dest[who] is not None:
                self.travel(who, dest[who], "walk")
        self.choose(self.HUO, "road:think")
        self.choose(self.FAN, "act:halt")
        self.choose(self.MI, "act:part")
        if dest[self.BI] is not None:
            self.travel(self.BI, dest[self.BI], "walk")
        for who in (self.HUO, self.LIN, self.JI, self.FAN, self.MI, self.RAN, self.BI, self.ZHAN, self.TAI):
            self.me(who, "出發之後")

    def half(self) -> None:
        for who in (self.HUO, self.LIN, self.JI, self.FAN, self.MI, self.RAN, self.BI, self.ZHAN, self.TAI, self.RONG, self.YUE):
            self.me(who, "前半最後")
        self.stock_view("前半最後")

    # ── 後半 ──

    def resume(self) -> None:
        """只先登入管理者和還在路上的人（每登入一個世界時鐘走一分鐘；整段也照這個順序登入，兩邊的步數才對得上）；其他人用到才登入。"""
        self.relogin(ADMIN)
        for who in (self.HUO, self.LIN, self.JI, self.FAN, self.MI, self.RAN, self.BI):
            self.relogin(who)
        self.rumor()

    def tasks(self) -> None:
        """霍承嶼接著做完小事（打聽、採集必中；做過的再按灰著、硬按）：跟著的藺知夏有一份，紀望舒的心得、素材上限已滿，聽說照樣有。"""
        with self.tune(road_gather_chance=1.0):
            for what in ("ask", "gather", "think", "gather"):
                self.choose(self.HUO, f"road:{what}")
        for who in (self.LIN, self.JI):
            self.me(who, "小事分完")

    def parts(self) -> None:
        """跟著的人在路上按場景底下的「分道揚鑣」（紀望舒；POST /api/party/leave 不管在不在路上都收），再看帶頭的人。"""
        self.party_leave(self.JI)
        self.main(self.HUO)
        self.me(self.JI, "分道揚鑣之後")

    def backs(self) -> None:
        """霍承嶼折返（步行）、緊接著再折返（跟著的藺知夏照抄每一趟）。"""
        for _ in range(2):
            self.choose(self.HUO, "road:back")
            for who in (self.HUO, self.LIN):
                self.me(who, "折返之後")
        self.ways(self.HUO, "折返完")

    def waits(self) -> None:
        """湛長庚（跟著的邰明遠一直在等）動身走遠處，邰明遠照抄；整季機器人眼前的選單；湛長庚做一件小事再疾行折返（立刻回到原地）；
        樂正初等太久散了（把期限擺回過去）；戎棠動身，沒有人跟著。這一段開頭先登入其餘的人（後半是新的行程；整段也照樣登入，兩邊的步數才對得上）。"""
        for who in (self.ZHAN, self.TAI, self.RONG, self.YUE, self.E, self.SANG, self.QI, self.LUAN, self.QIN, self.TU, self.QUE, self.XIAO,
                    self.MEI, self.HE, self.MU):
            self.relogin(who)
        far = self.far(self.ZHAN)
        if far is not None:
            self.travel(self.ZHAN, far, "walk")
        for who in (self.ZHAN, self.TAI):
            self.me(who, "動身之後")
        self.pick_view(self.TAI, "跟著人在路上")
        self.choose(self.ZHAN, "road:ask")
        self.call_mode(self.ZHAN, "POST", "/api/choose", {"id": "road:back:dash"}, "dash")
        for who in (self.ZHAN, self.TAI):
            self.me(who, "疾行折返之後")
        self.edit(self.YUE, lambda p: setattr(p.tagalong, "since", CLOCK0 - 10 ** 6) if p.tagalong is not None else None)
        self.main(self.YUE)
        self.main(self.RONG)
        far = self.far(self.RONG)
        if far is not None:
            self.travel(self.RONG, far, "walk")
        self.me(self.YUE, "散了之後")
        self.me(self.RONG, "動身之後")

    def halts(self) -> None:
        """樊靖安走到喊停的那一站就停下，冉驚鴻一路跟到這裡（拱手作別）；停下之後再喊停（不在路上了，硬按）。"""
        self.do(ADMIN, "fast_forward", {"hours": 1})
        for who in (self.FAN, self.RAN):
            self.main(who)
            self.me(who, "喊停的那一站")
        self.choose(self.FAN, "act:halt")

    def arrivals(self) -> None:
        """還在路上的一路走完（快轉六小時、同步一次）；每個人走完看一眼（江湖紀錄、party）。"""
        for _ in range(8):
            traveling = self.moving()
            if not traveling:
                break
            self.do(ADMIN, "fast_forward", {"hours": 6})
            for who in traveling:
                self.main(who)
        for who in self.WATCHED:
            self.main(who)
            self.me(who, "走完")
        self.stock_view("走完")

    def bots(self) -> None:
        """假人：BotRunner 四個（站在出發地，體力滿；乙已經跟著別人）收到闕子安的結伴邀請，若干輪；答應的原地等，闕子安動身時照抄。
        整季機器人眼前有結伴邀請的選單與挑法。"""
        from collections import Counter

        from tianxia import server_bots
        from tianxia.bot_runner import BotRunner
        from tianxia.engine import Game
        from tianxia.state import BotProfile

        on = bool(self.c.scenario.factions)
        hub = self.hub()
        made = []
        for i, name in enumerate(self.BOT_SEATS):
            self.begin()
            g = Game.new(self.c, name, rng=random.Random(i), world=self.world, graduated=True)
            p = g.state.player
            p.bot = BotProfile(personality="普通", seed=61 + i, faction="guan" if on else None, season_number=self.world.get_season_number())
            g.client = None
            g.sync(CLOCK[0])
            for _ in range(6):
                first = next((o.id for o in g.options(odds=False) if o.id.startswith("choice:") and o.enabled), None)
                if first is None:
                    break
                g.choose(first)
            p.faction, p.location, p.journey = p.bot.faction, hub, None
            p.visited.add(hub)
            p.tutorial_step = len(self.c.tutorial.steps)
            p.joined_at = -1.0e9
            p.stamina = float(self.c.config.stamina_max)
            self.chars.save(g.state)
            made.append(name)
        self.follow(self.BOT_SEATS[1], self.GHOST)
        self.place(self.QUE, hub, self.PLAYERS[self.QUE])
        self.main(self.QUE)
        for name in made:
            self.invite(self.QUE, name)
        runner = BotRunner(self.c, self.world, self.chars, rng=random.Random(43), clock=lambda: CLOCK[0])
        tick, online = self.c.config.bot_tick_seconds, server_bots.is_online
        seeds = {61 + i for i in range(len(made))}
        self.c.config.bot_tick_seconds = 10 ** 6
        server_bots.is_online = lambda profile, now: profile.seed in seeds or online(profile, now)
        totals = Counter()
        try:
            with self.tune(party_wait_seconds=10 ** 9):
                for _ in range(int(os.environ.get("SB_TRAVEL_TICKS", "8"))):
                    STEP[0] += 4
                    self.begin()
                    report = runner.tick()
                    totals.update(acted=report.acted, added=report.added, skipped=report.skipped, failed=report.failed, online=report.online)
        finally:
            self.c.config.bot_tick_seconds, server_bots.is_online = tick, online
        emit("假人 一輪一輪", dict(sorted(totals.items())))
        emit("假人 還在等的邀請", sorted([i.target, i.sender] for i in self.world.get_season().invites if i.kind == "travel"))
        self.invite(self.QUE, self.TU)
        self.pick_view(self.TU, "有結伴邀請")
        far = self.far(self.QUE)
        if far is not None:
            with self.tune(party_wait_seconds=10 ** 9):
                self.travel(self.QUE, far, "walk")
        self.me(self.QUE, "假人跟著之後")
        for name in made:
            s = self.chars.load(name)
            emit(f"假人 {name}", {"loc": s.player.location, "journey": None if s.player.journey is None else s.player.journey.model_dump(mode="json"),
                                  "tagalong": None if s.player.tagalong is None else s.player.tagalong.model_dump(mode="json"),
                                  "stamina": s.player.stamina, "journal": [[e.title, e.tag, list(e.lines)[:3]] for e in s.journal[:4]],
                                  "state": hashlib.sha256(s.model_dump_json().encode("utf-8")).hexdigest()})

    def season(self) -> None:
        self.do(ADMIN, "end_season")
        self.stock_view("收季之後")
        for who in (self.HUO, self.LIN, self.QUE):
            self.me(who, "收季之後")
        self.do(ADMIN, "next_season")
        self.main(self.HUO)
        for who in (self.HUO, self.LIN, self.QUE):
            self.me(who, "換季之後")
        self.stock_view("換季之後")


# 改一個字（selftest）：跟不上的那一句（_lead，第 48 批從 Game 搬進 tianxia/features/travel/party.py；base 上還在 engine.py，所以兩個檔都寫），week7 疾行那一組抓到
register_track("roadmate", RoadmateScenario, (("tianxia/features/travel/party.py", "tianxia/engine.py"), ("你們就此分開。", "你們就此分開！")), "week7")
