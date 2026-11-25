"""same_behavior 一軌一檔：yiwen（這一檔登記 yiwen）。"""
from __future__ import annotations

from pathlib import Path

from sb import harness
from sb.harness import ADMIN, MODEL, emit, register_track
from sb.tracks.peers import PeersScenario

# ── yiwen（異聞第 247 批；開關 Config.yiwen.enabled 預設關＋開季蓋章 WorldState.yiwen_on）：異聞一之一 ──────────────

# 第 269 批：假的說書人回的草稿（原創的字；不連網路）。鍵是（第幾步, 第幾次問：1 第一次、2 重問）；查不到的照 _setup_child 那一層丟連線錯誤（＝替身）。
# 丙（說書人段）：第一步三段、第三段空的、第二段八十字上下（整理後合格）；第二步第一次一段一百字以上（length）、重問合格；第三步合格。
SCRIBE_DRAFTS = {
    (1, 1): {"text": ["你順著那撐篙的人看去，霧裡那條小船停在灘頭，不再往前。",
                      "那啞巴放下竹篙，朝你比了個手勢，又指了指對岸的山腳。你看見山腳下有一間塌了半邊的草屋，屋前掛著一盞還沒熄的燈籠，夜風吹得它不住地左右搖晃，像是在等誰回去。",
                      ""],
             "options": ["跟他上船過去", "先問他從哪裡來", "繞到山腳去看"],
             "ledger": ["在場：你、撐篙的啞巴", "你手上：無", "你知道：對岸草屋有燈", "未了：那燈是給誰留的"]},
    (2, 1): {"text": ["你跨上小船，啞巴一言不發，撐著篙往對岸去。",
                      "船行到河心，水聲忽然大了起來，你低頭看見船底的木板裂開一道細縫，河水從縫裡慢慢滲上來。啞巴卻像沒看見似的，只顧著撐篙，你只好脫下外衫塞住那道縫，雙手按著，直到船頭碰上對岸的沙灘，才鬆了一口氣，抬頭望向那間草屋。"],
             "options": ["推門進草屋", "喊一聲屋裡的人", "守在門外等著"],
             "ledger": ["在場：你、撐篙的啞巴", "你手上：濕了的外衫", "你知道：草屋裡有人咳嗽", "未了：咳嗽的是誰"]},
    (2, 2): {"text": ["你跨上小船，啞巴一言不發，撐著篙往對岸去。",
                      "船頭碰上沙灘，你聽見草屋裡有人咳嗽，燈籠跟著晃了一下。"],
             "options": ["推門進草屋", "喊一聲屋裡的人", "守在門外等著"],
             "ledger": ["在場：你、撐篙的啞巴", "你手上：無", "你知道：草屋裡有人咳嗽", "未了：咳嗽的是誰"]},
    (3, 1): {"text": ["你推門進去，屋裡一個老婦人正替燈添油，見了你也不驚。",
                      "她說這盞燈是替撐船的兒子點的，你回頭，岸邊的船已經不見了。"]},
}
# 甲（接替段，新的一季）：第一步合格；第二步兩次都不合格（只有一段、做法只有兩個）＝替身；第三步合格。
RELAY_DRAFTS = {
    (1, 1): {"text": ["你撥開路旁的荊棘，看見一塊石碑半埋在土裡，碑上刻著模糊的字。",
                      "碑後有個背柴的少年探頭看你，手裡攥著一枚磨得發亮的銅片。"],
             "options": ["蹲下細看碑文", "問那少年銅片", "裝作沒看見走開"],
             "ledger": ["在場：你、背柴的少年", "你手上：無", "對方手上：銅片", "未了：碑上刻的是什麼"]},
    (2, 1): {"text": ["你蹲下身子，用袖子拂去碑上的塵土，那少年也湊過來看。"],
             "options": ["念出碑上的字", "問少年認不認得", "把碑扶正"],
             "ledger": ["在場：你、背柴的少年", "你手上：無", "未了：碑上刻的是什麼"]},
    (2, 2): {"text": ["你蹲下身子，用袖子拂去碑上的塵土。", "那少年也湊過來看，指著碑角一道刻痕。"],
             "options": ["念出碑上的字", "問少年認不認得"],
             "ledger": ["在場：你、背柴的少年", "你手上：無", "未了：碑上刻的是什麼"]},
    (3, 1): {"text": ["你照著碑上的刻痕往前走，在一棵老樹下停住腳步。",
                      "樹根底下壓著半截銅片，跟那少年手裡的正好合得上。"]},
}
_YIWEN_CLIENTS: dict[type, type] = {}


def _yiwen_client(base: type) -> type:
    """說書人的假模型（base 是 _setup_child 那一層換好的 client 類別；同 _arts_client）：MODEL["yiwen"] 開著時照（第幾步, 第幾次問）
    回寫死的草稿、收到的訊息記在 MODEL["yiwen"]["seen"]；查不到、或沒開著，照 base（丟連線錯誤）。不看 schema 名、不讀提示判第幾步。"""
    if base not in _YIWEN_CLIENTS:
        class YiwenClient(base):
            def chat_structured(self, messages, schema, *a, **k):
                fake = MODEL.get("yiwen")
                if fake is None:
                    return super().chat_structured(messages, schema, *a, **k)
                fake["seen"].append([dict(m) for m in messages])
                ask = sum(1 for m in messages if m.get("role") == "user")
                draft = fake["drafts"].get((fake["step"], ask))
                if draft is None:
                    return super().chat_structured(messages, schema, *a, **k)
                return schema(**draft)

        _YIWEN_CLIENTS[base] = YiwenClient
    return _YIWEN_CLIENTS[base]


class YiwenScenario(PeersScenario):
    """異聞的一軌（第 247 批；--track yiwen，自己一個資料庫）。借 peers 一軌的小工具（edit_state、begin 清榜單快取）。班底的名字都是原創。
    關著段（記憶體裡把開關關掉）：探索一段、/api/do/yiwen_step 回空、讀 /api/main 的 yiwen 鍵與存檔那一格。
    開著段（記憶體裡打開、這一季補蓋章、撞見機率調成 1）：甲在野地探索撞見、撞見卡、三步都按第一顆（每一幕是替身）、收起。
    後半第一件事無條件重新登入、再打開：乙在同一處重走（重走機率調成 1）、三步重放（回聲、第一步的朱批、同一個圓章）、別人沒走過的那一顆鎖著；
    收季、開下一季：眼前那一則清空、下一季照開關蓋章。
    說書人段（第 252 批，前半最後一段 scribe）：第 269 批起走真的 writer.write_scene（整理、檢查、重問的話），假的說書人換在
    OllamaClient.from_config 那一層（SCRIBE_DRAFTS 照第幾步、第幾次問回寫死的草稿，不連網路），server.screen_text 照字回 ok／bad；
    丙在山地探索撞見另一句（全服每天的名額記憶體調成 2），第一步自己說一句審得過的（草稿三段、第三段空的，整理後寫成）、第二步自己說一句審字擋的
    （refuse_typed、tries 1、什麼都沒寫）、再按第一顆（第一次一段太長，重問那一句印出來，重問寫成），第三步寫成（收場）；每一下印那一幕的 fallback。
    接替段（第 269 批，後半最後一段 relay，新的一季）：甲在野地撞見，第一步寫成、第二步自己說要等級的（ask 那一道擋：refuse_typed、tries 不加）、
    再按第一顆兩次都不合格＝替身（做法是第一步沒被選的兩顆加補位）、第三步寫成（提示裡的帳是第一步的，印出來）。
    這一軌走不到的：測試內容（test 設定）走舊探索，撞不到異聞（總計畫「對不上的」第 13 條）：那一種設定兩邊照樣一樣；
    真的模型、B 段排隊與 busy（佇列在測試裡守）、岔路與道具（異聞三）、定論與逾時（異聞四）。"""

    LEAD, TRAIL, SCRIBE = "霜橋客", "柳岸生", "墨池翁"
    PLAYERS = {LEAD: None, TRAIL: None, SCRIBE: None}
    SAID_OK, SAID_BAD = "一個撐篙的啞巴", "罵他是個蠢貨"  # 說書人段：自己說的兩句（後一句假的審字判 bad）
    NEWBIE = "遠客"
    PHASES_FIRST = ["setup", "seat", "closed", "meet", "walk", "scribe"]
    PHASES_SECOND = ["resume", "trail", "season", "relay"]
    SAID_ASK = "把我的等級加滿"  # 接替段：自己說一句要等級的（typed_problem 的 ask 那一道擋）

    def __init__(self, root: Path, profile: str, db: Path):
        super().__init__(root, profile, db)
        from tianxia import ollama_client

        inner = ollama_client.OllamaClient.from_config.__func__  # _setup_child 換好的那一層（不連網路）

        def from_config(cls, cfg):  # 第 269 批：假的說書人換在最外層（Game.client 每個請求都經這裡重建；within_budget 的複本保留類別）
            client = inner(cls, cfg)
            if client is not None:
                client.__class__ = _yiwen_client(type(client))
            return client

        ollama_client.OllamaClient.from_config = classmethod(from_config)

    def press(self, who: str, body: dict, step, drafts):
        """打一下 /api/do/yiwen_step；給了 drafts 就在這一個請求前後開著假的說書人（第幾步由這裡定）。回（回話, 假模型收到的訊息）。"""
        if drafts is None:
            return self.do(who, "yiwen_step", body), []
        MODEL["yiwen"] = {"step": step, "drafts": drafts, "seen": []}
        try:
            return self.do(who, "yiwen_step", body), MODEL["yiwen"]["seen"]
        finally:
            MODEL["yiwen"] = None

    def fallback_of(self, who: str) -> None:
        """剛寫的那一幕是寫成的（0）還是替身（1）：旁檔那個節點的 fallback（只印這一格，不印節點的其他欄）。"""
        from tianxia.features.yiwen import store

        w = self.chars.load(who).player.yiwen
        side = store.store_of_world(self.world)
        node = side.node(w.node) if side is not None and w is not None and w.node is not None else None
        emit(f"{who} 這一幕 fallback", node.get("fallback") if isinstance(node, dict) else None)

    def live(self) -> bool:
        """這一包進了 base 才比（波 AF 修正）：base 還沒有 Config.yiwen（新包那一波），或這一次是 compare --new yiwen（head 那一邊），
        兩邊都只寫同一行、不走異聞的段，免得 base 那一邊 AttributeError、head 那一邊整段都是新包的差異。selftest 與之後的波照整段跑。"""
        return hasattr(self.c.config, "yiwen") and "yiwen" not in harness.NEW["packages"]

    def switch(self, on: bool) -> None:
        t = self.c.config.yiwen
        t.enabled = on
        t.discover_chance = 1.0 if on else 0.0002
        t.rewalk_chance = 1.0 if on else 0.07
        if on:
            self.world.mutate(lambda st: setattr(st.season, "yiwen_on", True))

    def wild(self) -> str:
        from tianxia.core import explore_base

        if "yingchuan_wilds" in self.c.locations:  # 正式內容：潁川郊野（野地，沒有決戰的大區）
            return "yingchuan_wilds"
        return next((lid for lid, loc in sorted(self.c.locations.items()) if explore_base.kind_of(self.c.config.jianfa, loc).kind == "wild"),
                    self.hub())

    def yiwen_of(self, who: str, tag: str) -> None:
        main = self.main(who)
        main = main.get("main", main) if isinstance(main, dict) else {}
        emit(f"{who} {tag}：main.yiwen", main.get("yiwen") if isinstance(main, dict) else None)
        w = self.chars.load(who).player.yiwen
        emit(f"{who} {tag}：存檔", w.model_dump(mode="json") if w is not None else None)
        emit(f"{who} {tag}：選單", sorted(i for i in self.ids(main) if i.startswith("yiwen:")))

    def card(self, who: str):
        main = self.main(who)
        main = main.get("main", main) if isinstance(main, dict) else {}
        y = main.get("yiwen") if isinstance(main, dict) else None
        return y.get("card") if isinstance(y, dict) else None

    def explore(self, who: str) -> None:
        self.edit(who, lambda p: setattr(p, "stamina", float(self.c.config.stamina_max)))
        if "act:explore" not in self.ids(self.main(who)):
            emit(f"{who} 選單上沒有探索", sorted(self.ids(self.main(who)))[:20])
            return
        emit(f"{who} 探索", self.choose(who, "act:explore"))

    def steps(self, who: str, picks=(0, 0, 0), first=None, drafts=None):
        """照 picks 一步一步按；給了 drafts（第 269 批）就開著假的說書人，first 是第一下的第幾步，每一下多印 fallback。回最後一下假模型收到的訊息。"""
        seen = []
        for n, i in enumerate(picks):
            card = self.card(who)
            if card is None:
                emit(f"{who} 沒有撞見卡", None)
                return seen
            body = {"tale": card["tale"], "opening": card["opening"], "node": card["node"], "pick": i}
            got, seen = self.press(who, body, None if first is None else first + n, drafts)
            emit(f"{who} 按第 {i} 顆", got)
            emit(f"{who} 那一張卡", self.card(who))
            if drafts is not None:
                self.fallback_of(who)
        return seen

    # ── 段落 ──

    def seat(self) -> None:
        here = self.wild()
        for who in self.PLAYERS:
            self.place(who, here)
            self.edit(who, lambda p: setattr(p.member, "level", 20))
        emit("坐在", here)
        for who in self.PLAYERS:
            self.main(who)

    def closed(self) -> None:
        if not self.live():
            emit("異聞這一軌", "這一包還沒進 base（或 --new yiwen）：異聞的段不比")
            return
        self.switch(False)
        self.explore(self.LEAD)
        emit("關著按 yiwen_step", self.do(self.LEAD, "yiwen_step", {"tale": 1, "opening": "fog_figure", "node": 0, "pick": 0}))
        self.yiwen_of(self.LEAD, "關著")

    def meet(self) -> None:
        if not self.live():
            return
        self.switch(True)
        self.c.config.guard.enabled = False  # 親衛隊長第一段就撞見那個孩子（接管選單）：這一軌只看異聞
        self.explore(self.LEAD)
        self.yiwen_of(self.LEAD, "撞見")

    def walk(self) -> None:
        if not self.live():
            return
        self.steps(self.LEAD)
        self.yiwen_of(self.LEAD, "走完")
        emit("收起", self.choose(self.LEAD, "yiwen:drop"))
        self.yiwen_of(self.LEAD, "收起")

    def place_of(self, kind: str) -> str:
        from tianxia.core import explore_base

        return next((lid for lid, loc in sorted(self.c.locations.items()) if explore_base.kind_of(self.c.config.jianfa, loc).kind == kind),
                    self.hub())

    def say(self, who: str, text: str, step=None, drafts=None):
        card = self.card(who)
        if card is None:
            emit(f"{who} 沒有撞見卡", None)
            return []
        body = {"tale": card["tale"], "opening": card["opening"], "node": card["node"], "pick": "typed", "text": text}
        got, seen = self.press(who, body, step, drafts)
        emit(f"{who} 自己說「{text}」", got)
        emit(f"{who} 那一張卡", self.card(who))
        w = self.chars.load(who).player.yiwen
        emit(f"{who} 自己說之後 tries", w.tries if w is not None else None)
        if drafts is not None:
            self.fallback_of(who)
        return seen

    def scribe(self) -> None:
        if not self.live():
            return
        import server

        # 第 269 批：走真的 writer.write_scene（假的說書人換在 from_config，見 __init__ 與 press）；審字照舊用假的
        real = (server.screen_text, self.c.config.yiwen.free_daily_cap)
        server.screen_text = lambda game, text, kind: "bad" if "蠢" in text else "ok"
        self.c.config.yiwen.free_daily_cap = 2
        try:
            here = self.place_of("hill")
            self.place(self.SCRIBE, here)
            self.edit(self.SCRIBE, lambda p: setattr(p.member, "level", 20))
            emit("丙坐在", here)
            self.explore(self.SCRIBE)
            self.yiwen_of(self.SCRIBE, "撞見")
            self.say(self.SCRIBE, self.SAID_OK, 1, SCRIBE_DRAFTS)
            self.say(self.SCRIBE, self.SAID_BAD, 2, SCRIBE_DRAFTS)
            card = self.card(self.SCRIBE)
            if card is None:
                emit(f"{self.SCRIBE} 沒有撞見卡", None)
            else:
                body = {"tale": card["tale"], "opening": card["opening"], "node": card["node"], "pick": 0}
                got, seen = self.press(self.SCRIBE, body, 2, SCRIBE_DRAFTS)
                emit(f"{self.SCRIBE} 按第 0 顆", got)
                emit(f"{self.SCRIBE} 那一張卡", self.card(self.SCRIBE))
                self.fallback_of(self.SCRIBE)
                emit(f"{self.SCRIBE} 重問那一句", seen[-1][-1]["content"] if seen and len(seen[-1]) > 1 else None)
                self.steps(self.SCRIBE, (0,), 3, SCRIBE_DRAFTS)
            self.yiwen_of(self.SCRIBE, "說完")
        finally:
            server.screen_text, self.c.config.yiwen.free_daily_cap = real

    def resume(self) -> None:
        if not self.live():
            return
        # 後半是另一個行程：記憶體裡的設定先照前半收尾的樣子擺回去（不打請求），再無條件重新登入
        self.c.config.yiwen.enabled = True
        self.c.config.yiwen.discover_chance = 0.0
        self.c.config.yiwen.rewalk_chance = 1.0
        self.c.config.guard.enabled = False
        self.login_all()

    def trail(self) -> None:
        if not self.live():
            return
        self.explore(self.TRAIL)
        self.yiwen_of(self.TRAIL, "重走")
        card = self.card(self.TRAIL)
        if card is not None:
            emit("別人沒走過的那一顆", self.do(self.TRAIL, "yiwen_step", {"tale": card["tale"], "opening": card["opening"], "node": 0, "pick": 1}))
        self.steps(self.TRAIL)
        self.yiwen_of(self.TRAIL, "重走完")

    def season(self) -> None:
        if not self.live():
            return
        self.do(ADMIN, "end_season")
        self.main(self.TRAIL)
        self.do(ADMIN, "next_season")
        self.yiwen_of(self.TRAIL, "下一季")
        emit("下一季的章 yiwen_on", getattr(self.world.get_season(), "yiwen_on", None))

    def relay(self) -> None:
        """第 269 批：新的一季，甲撞見一則：第一步寫成、第二步先自己說要等級的（ask 擋）、再按第一顆兩次都不合格＝替身
        （寫成的一幕之後接替身）、第三步寫成（提示裡的帳是第一步的）。放在最後一段：前面每一段的步數都不動。"""
        if not self.live():
            return
        self.switch(True)
        t = self.c.config.yiwen
        real = (t.free_daily_cap, t.free_per_player)
        t.free_daily_cap, t.free_per_player = 9, 9
        try:
            self.main(self.LEAD)  # 新的一季第一次同步（開季準備卡、回起點）先過，再擺到野地
            self.place(self.LEAD, self.wild())
            self.edit(self.LEAD, lambda p: setattr(p.member, "level", 20))
            self.explore(self.LEAD)
            self.yiwen_of(self.LEAD, "接替撞見")
            self.steps(self.LEAD, (0,), 1, RELAY_DRAFTS)
            self.say(self.LEAD, self.SAID_ASK, 2, RELAY_DRAFTS)
            self.steps(self.LEAD, (0,), 2, RELAY_DRAFTS)
            seen = self.steps(self.LEAD, (0,), 3, RELAY_DRAFTS)
            prompt = seen[0][0]["content"] if seen else ""
            head = "【帳】（上一幕結束時）"
            tail = prompt.split(head, 1)[1].splitlines()[1:] if head in prompt else []
            ledger = []
            for line in tail:
                if not line.startswith("- "):
                    break
                ledger.append(line)
            emit(f"{self.LEAD} 第三步的帳", ledger)
            self.yiwen_of(self.LEAD, "接替")
        finally:
            t.free_daily_cap, t.free_per_player = real


# 改一個字（selftest）：重走的擲骰反過來，乙永遠撞不到那一則，season21 trail 那一段抓到
register_track("yiwen", YiwenScenario, (("tianxia/features/yiwen/actions.py",), ("if old and r_walk < t.rewalk_chance:", "if old and r_walk > t.rewalk_chance:")),
               "season21",
               covers=("admin", "battle", "bounties", "bout", "codex", "companions", "cultivation", "explore", "faction", "figure_acts",
                       "gear", "guard", "guide", "heroines", "hire", "horses", "legacy", "mall", "military", "outlets",
                       "peers", "seal", "sense", "smithy", "socialize", "sortie", "stamina_plays", "story", "tavern", "travel",
                       "yiwen", "zhuan", "zongmen"))
