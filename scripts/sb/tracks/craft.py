"""same_behavior 一軌一檔：craft（這一檔登記 craft）。"""
from __future__ import annotations

import contextlib
import hashlib
import os
import random
from pathlib import Path

from sb.base import Scenario
from sb.harness import ADMIN, CLOCK, MODEL, STEP, db_text, emit, register_track

# ═══════════════════════════ craft：煉製與自創一軌（全部拆包第 44 批，dev/craft-1） ═══════════════════════════
# 意境合成與揣摩（取名三段式 A、B、C：Game.forge_request／server.prepare_forge／Game.forge 的重驗；預覽 /api/forge_line）、自創五步
# （執器、擺式、立意〔三段式〕、成形、立名）、重悟帖（重骰形、重讀這句意〔三段式〕）、作罷的本體從 engine.py 與 tianxia/create.py 搬進
# tianxia/features/craft/（計畫 docs/superpowers/plans/2026-11-05-煉製自創包-第1批.md）。角色與意境、武學、招式的名字都是原創的（第 22 批 PM 認定第 3 條）。

CRAFT_READ = {"score": 82, "attributes": ["柔", "虛"], "lean": "正", "move": "拂雲式", "say": "身子一擰便繞了過去"}
CRAFT_REREAD = {"score": 71, "attributes": ["剛"], "lean": "邪", "move": "裂冰式", "say": "掌勢一沉便壓了下去"}
_CRAFT_CLIENTS: dict[type, type] = {}


def _craft_client(base: type) -> type:
    """煉製與自創的假模型（疊在 _setup_child 那一層上）：MODEL["craft_name"]（{name, description}）給了時 NameReply 回它（取名、挑一個）；
    MODEL["craft_read"]（IntentReading 的欄位）給了時 IntentReading 回它。沒給的照 base（立刻丟連線錯誤＝模型擋著）。"""
    if base not in _CRAFT_CLIENTS:
        class CraftClient(base):
            def chat_structured(self, messages, schema, *a, **k):
                if schema.__name__ == "NameReply" and MODEL.get("craft_name") is not None:
                    return schema(**MODEL["craft_name"])
                if schema.__name__ == "IntentReading" and MODEL.get("craft_read") is not None:
                    return schema(**MODEL["craft_read"])
                return super().chat_structured(messages, schema, *a, **k)

        _CRAFT_CLIENTS[base] = CraftClient
    return _CRAFT_CLIENTS[base]


class CraftScenario(Scenario):
    """煉製與自創（全部拆包第 44 批；--track craft，自己一個資料庫）。
    - 籌備中（管理者還沒開季）：煉製頁與自創的每一顆都回「賽季籌備中」，開爐的 A 段（forge_request）是 None。
    - 煉製頁的預覽（/api/forge_line）：空爐、放一個、放兩個（合得了、合不了）、放武學、放不認得的、形狀不對的 body。
    - 開爐的取名三段式：被拒絕的幾種（爐裡一個、放武學、不在手上、同一種只有一份、心得不夠）不開單；兩種不同的意境首創——模型回了（名字進
      江湖）、模型擋著（走退路字表）、模型回的名字撞了現成的意境（C 段重驗過不了，走退路字表）；同一個配方第二個人合（已登記，不叫模型）；
      同一種的兩份是揣摩（不取名）；揣摩到極處被擋。
    - 自創五步：執器（種類不對、形不對）、擺式、立意〔三段式：太短、太長、模型回了、模型擋著走關鍵字表〕、成形、回頭（立意回擺式免費、成形回頭
      用掉一次重來、沒得回）、立名（名字太短、撞名、招名不合、做成了寫一則紀錄）、作罷（沒有單子、付過了的）；重悟帖（沒有帖、重骰形、重讀這句意
      〔三段式：模型回了、模型擋著不扣帖〕、骰滿了）。
    - **前半停在自創走到一半**：擺式那一步（剛執器）、立意那一步（剛擺好式）、成形還沒立名（手上有兩張重悟帖，已經重骰過一次）、舊存檔的三步單子
      （沒有 form，讀檔時收掉）、煉製頁的那一爐已經合好一個意境還沒再合。
    - 後半第一件事：新程式接著走——擺式的接著擺、立意的接著三段式、成形的重讀（模型回了）、重骰（骰滿）、回頭、立名；舊單子被收掉、重開；
      煉製頁接著合；煉製頁與門下頁的資料（create_view）。換季：走到一半的單子跟新角色重來。
    - 假人：BotRunner 兩個（心得多、手上有意境；bot_policy.tend_arts 的合一爐與自創一門）；整季機器人眼前的選單。
    沒有自創的內容（測試內容若關著）同一串 API 照打，寫被擋的那一句。"""

    FORGER, BLOCKED, DEEPER = "墨簷", "雲杪", "竹渚"
    MAKER, SECOND, REROLLER = "霜葉", "寒汀", "松檐"
    H_POSE, H_INTENT, H_NAME, H_OLD, H_FURNACE = "星砌", "石岫", "葦渡", "舊簿", "爐前"
    PLAYERS = [FORGER, BLOCKED, DEEPER, MAKER, SECOND, REROLLER, H_POSE, H_INTENT, H_NAME, H_OLD, H_FURNACE]
    BOT_SEATS = ["匠甲", "匠乙"]
    PHASES_FIRST = ["setup", "preview", "refused", "forge_first", "forge_again", "deepen", "create_steps", "create_name", "reroll", "half"]
    PHASES_SECOND = ["resume", "views", "bots", "season"]

    def __init__(self, root: Path, profile: str, db: Path):
        super().__init__(root, profile, db)
        from tianxia import ollama_client

        inner = ollama_client.OllamaClient.from_config.__func__  # _setup_child 換好的那一層（不連網路、大場面判讀）

        def from_config(cls, cfg):
            client = inner(cls, cfg)
            client.__class__ = _craft_client(type(client))
            return client

        ollama_client.OllamaClient.from_config = classmethod(from_config)

    # ── 小工具 ──

    @contextlib.contextmanager
    def model(self, name: dict | None = None, read: dict | None = None):
        """這幾下模型回的東西（取名／挑一個；讀這一句意）；出來就是擋著。"""
        MODEL["craft_name"], MODEL["craft_read"] = name, read
        emit("模型", {"name": name, "read": read})
        try:
            yield
        finally:
            MODEL["craft_name"] = MODEL["craft_read"] = None

    def mx(self, who: str, op: str, body: dict | None = None):
        return self.call(who, "POST", f"/api/menxia/{op}", body or {})[1]

    def menxia(self, who: str):
        return self.call(who, "GET", "/api/menxia")[1]

    def line(self, who: str, body: dict):
        return self.call(who, "POST", "/api/forge_line", body)[1]

    def forge(self, who: str, ids) -> None:
        self.mx(who, "forge", {"insights": ids})

    def give(self, who: str, insights: list[str], xinde: int = 20000) -> None:
        def fn(p):
            p.insights.extend(i for i in insights if i not in p.insights)
            p.stats["xinde"] = xinde
            p.stamina = float(self.c.config.stamina_max)
        self.edit(who, fn)

    def base_insights(self) -> list[str]:
        return sorted(self.c.insights)[:6]

    def state_of(self, who: str, tag: str) -> None:
        """存檔裡跟煉製與自創有關的那幾格與最新那一則紀錄。"""
        state = self.chars.load(who)
        p = state.player
        latest = state.journal[0] if state.journal else None
        emit(f"{who} {tag}", {
            "insights": list(p.insights), "own": sorted(p.own_insights), "arts": list(p.arts), "wugong": p.member.wugong_id,
            "quality": dict(sorted(p.art_quality.items())), "slots": dict(sorted(p.art_slots.items())),
            "xinde": p.stats.get("xinde"), "stamina": p.stamina, "created_count": p.created_count, "rerolls": p.create_rerolls,
            "creating": None if p.creating is None else p.creating.model_dump(),
            "latest": None if latest is None else latest.model_dump(mode="json"),
        })

    def recipes(self, tag: str) -> None:
        """全服登記的配方（名字進江湖）：整份資料庫的雜湊。"""
        emit(tag, hashlib.sha256(db_text(self.db).encode("utf-8")).hexdigest())

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
        for who in self.PLAYERS:
            self.clients[who] = self.TestClient(self.server.app)
            self.passwords[who] = "pw-" + self.login_of(who)
            self.call(who, "POST", "/api/register", {"login": self.login_of(who), "password": self.passwords[who],
                                                    "again": self.passwords[who]})
            self.call(who, "POST", "/api/character", {"name": who, "gender": "男"})
        # 籌備中：煉製頁與自創的每一顆都擋
        who = self.FORGER
        ins = self.base_insights()
        self.line(who, {"insights": ins[:2]})
        self.forge(who, ins[:2])
        self.mx(who, "create_begin", {"kind": "武學", "form": "拳腳"})
        self.mx(who, "create_pose", {"pose": {}})
        self.mx(who, "create_back", {"to": "pose"})
        self.mx(who, "create_name", {"name": "籌備中的名", "move": ""})
        self.mx(who, "create_cancel")
        self.mx(who, "create_reroll")
        self.do(who, "create_intent", {"text": "籌備中的一句意"})
        self.do(who, "create_reread", {"text": "籌備中的一句意"})
        self.menxia(who)
        self.do(ADMIN, "open_season")
        for who in self.PLAYERS:
            self.do(who, "skip_tutorial")
            self.settle_choices(who)
        for who in self.PLAYERS:
            self.place(who, None)  # 體力補滿、過了新手期
        ins = self.base_insights()
        for who in self.PLAYERS:
            self.give(who, ins)
        self.edit(self.DEEPER, lambda p: p.insights.extend(f"{ins[0]}~{n}" for n in (2, 3, 4) if f"{ins[0]}~{n}" not in p.insights))

    def preview(self) -> None:
        """煉製頁選了東西就更新說明（/api/forge_line）：空爐、一個、兩個不同的、兩份同一種、放武學、不認得的、形狀不對的。"""
        who, ins = self.FORGER, self.base_insights()
        art = self.chars.load(who).player.member.wugong_id or "jichu_quanjiao"  # 測試內容的人手上沒有武學
        for body in ({}, {"insights": []}, {"insights": ins[:1]}, {"insights": ins[:2]}, {"insights": [ins[0], ins[0]]},
                     {"insights": ins[1:3]}, {"insights": ins[2:4]}, {"art": art, "insights": ins[:1]}, {"insights": ["沒有這個意境"]},
                     {"insights": [ins[0], "沒有這個意境"]}, {"insights": "不是串列"}, {"insights": [ins[0], 3]}):
            self.line(who, body)
        self.line(self.DEEPER, {"insights": [ins[0], f"{ins[0]}~2"]})
        self.line(self.DEEPER, {"insights": [f"{ins[0]}~2", f"{ins[0]}~3"]})

    def refused(self) -> None:
        """開爐被拒絕的幾種（不開取名的單子、什麼都不收）：爐裡一個、三個、放武學、不在手上、同一種只有一份、心得不夠、體力不夠。"""
        who, ins = self.FORGER, self.base_insights()
        art = self.chars.load(who).player.member.wugong_id or "jichu_quanjiao"  # 測試內容的人手上沒有武學
        with self.model({"name": "不該用到的名", "description": "不會用到"}):
            self.forge(who, ins[:1])
            self.forge(who, ins[:3])
            self.forge(who, [])
            self.mx(who, "forge", {"art": art, "insights": ins[:2]})
            self.forge(who, [ins[0], "沒有這個意境"])
            self.forge(who, [ins[0], ins[0]])
            self.edit(who, lambda p: p.stats.__setitem__("xinde", 0))
            self.forge(who, ins[:2])
            self.edit(who, lambda p: (p.stats.__setitem__("xinde", 20000), setattr(p, "stamina", 0.0)))
            self.forge(who, ins[:2])
            self.edit(who, lambda p: setattr(p, "stamina", float(self.c.config.stamina_max)))
        self.state_of(who, "被拒絕之後")

    def forge_first(self) -> None:
        """兩種不同的意境首創：模型回了（名字進江湖）、模型擋著（退路字表）、模型回的名字撞了現成的意境（走退路字表）。"""
        ins = self.base_insights()
        with self.model({"name": "霧簷意", "description": "簷下霧氣不散的意思"}):
            self.forge(self.FORGER, ins[:2])
        self.state_of(self.FORGER, "模型回了之後")
        self.forge(self.BLOCKED, ins[2:4])  # 模型擋著
        self.state_of(self.BLOCKED, "模型擋著之後")
        clash = self.c.insights[ins[0]].name
        with self.model({"name": clash, "description": "撞名的說明"}):
            self.forge(self.DEEPER, ins[4:6])
        self.state_of(self.DEEPER, "撞名之後")
        self.recipes("首創之後")

    def forge_again(self) -> None:
        """同一個配方第二個人合（已登記，不叫模型）；同一個人再合一次（已經悟得）；合到舊的意境。"""
        ins = self.base_insights()
        with self.model({"name": "不該再取的名", "description": "不會用到"}):
            self.forge(self.MAKER, ins[:2])
            self.forge(self.MAKER, ins[:2])
            self.forge(self.SECOND, ins[2:4])
        self.state_of(self.MAKER, "第二個人合之後")
        self.state_of(self.SECOND, "第二個人合之後")

    def deepen(self) -> None:
        """同一種的兩份是揣摩（不取名）：揣摩幾次，揣摩到極處被擋。"""
        who, ins = self.DEEPER, self.base_insights()
        with self.model({"name": "不該取的名", "description": "不會用到"}):
            for _ in range(4):
                held = [i for i in self.chars.load(who).player.insights if i == ins[0] or i.startswith(f"{ins[0]}~")]
                if len(held) < 2:
                    break
                self.forge(who, held[:2])
                self.edit(who, lambda p: (p.stats.__setitem__("xinde", 20000), setattr(p, "stamina", float(self.c.config.stamina_max))))
        self.state_of(who, "揣摩之後")

    def create_steps(self) -> None:
        """自創的前三步：種類不對、形不對、沒執器就擺式、立意（太短、太長、模型回了）、回頭。"""
        from tianxia.features.craft import create

        who = self.MAKER
        self.mx(who, "create_pose", {"pose": create.preset(self.c, "進擊")})  # 沒執器
        self.mx(who, "create_back", {"to": "pose"})
        self.mx(who, "create_cancel")  # 沒有單子
        self.mx(who, "create_reroll")
        self.mx(who, "create_begin", {"kind": "不是內功也不是武學", "form": "拳腳"})
        self.mx(who, "create_begin", {"kind": "武學", "form": "沒有這種兵器"})
        self.mx(who, "create_begin", {"kind": "武學", "form": "拳腳"})
        self.do(who, "create_intent", {"text": "還沒擺式"})  # 擺式還沒做
        self.mx(who, "create_pose", {"pose": create.preset(self.c, "進擊")})
        self.mx(who, "create_pose", {"pose": "不是字典"})
        self.do(who, "create_intent", {"text": "短"})
        self.do(who, "create_intent", {"text": "這是一句寫得太長太長太長太長太長太長太長太長太長太長太長太長的意"})
        with self.model(read=CRAFT_READ):
            self.do(who, "create_intent", {"text": "風過林梢，影不留痕"})  # 三段式：模型回了
        self.state_of(who, "立意之後")
        self.mx(who, "create_back", {"to": "name"})  # 不能往前
        self.mx(who, "create_back", {"to": "intent"})  # 成形之後回頭：用掉一次重來
        self.mx(who, "create_back", {"to": "pose"})  # 沒有重來了（立意那一步不再走回頭用掉的）
        self.state_of(who, "回頭之後")
        self.mx(who, "create_pose", {"pose": create.preset(self.c, "起手")})
        self.do(who, "create_intent", {"text": "水落石出，不留餘地"})  # 模型擋著：關鍵字表
        self.state_of(who, "模型擋著立意之後")

    def create_name(self) -> None:
        """立名：太短、撞名（先有人用了）、招名不合、成功；另一個人模型擋著走完、作罷（付過了）。"""
        from tianxia.features.craft import create

        who = self.MAKER
        self.mx(who, "create_name", {"name": "拳", "move": ""})
        self.mx(who, "create_name", {"name": "霜葉掌", "move": "太長太長太長"})
        self.mx(who, "create_name", {"name": "霜葉掌", "move": "拂雲式"})
        self.state_of(who, "立名之後")
        self.mx(who, "create_name", {"name": "霜葉掌", "move": ""})  # 單子已經收了
        who = self.SECOND
        self.mx(who, "create_begin", {"kind": "內功", "form": self.inner_form()})
        self.mx(who, "create_pose", {"pose": create.preset(self.c, "起手")})
        self.do(who, "create_intent", {"text": "靜水深流，不爭一日"})
        self.mx(who, "create_name", {"name": "霜葉掌", "move": ""})  # 撞名
        self.mx(who, "create_cancel")  # 付過了：作罷
        self.state_of(who, "作罷之後")
        self.mx(who, "create_cancel")
        self.menxia(who)

    def inner_form(self) -> str:
        """內功的行功之法（表上第一個；沒有就空著，讓引擎回那一句）。"""
        from tianxia.features.craft import create

        forms = create.forms_of(self.c, "內功")
        return forms[0].key if forms else ""

    def reroll(self) -> None:
        """重悟帖：沒有帖、重骰形（模型不用）、重讀這句意（模型回了、模型擋著不扣帖、改寫太短）、骰滿了。"""
        from tianxia.features.craft import create

        who = self.REROLLER
        self.mx(who, "create_reroll")  # 沒有單子
        self.mx(who, "create_begin", {"kind": "武學", "form": "拳腳"})
        self.mx(who, "create_pose", {"pose": create.preset(self.c, "進擊")})
        self.mx(who, "create_reroll")  # 還沒成形
        self.do(who, "create_reread", {"text": "還沒成形的重讀"})
        with self.model(read=CRAFT_READ):
            self.do(who, "create_intent", {"text": "寒潭映月，一劍西來"})
        self.mx(who, "create_reroll")  # 沒有帖
        self.do(who, "create_reread", {"text": "寒潭映月，一劍西來"})
        self.edit(who, lambda p: setattr(p, "create_rerolls", 6))
        self.mx(who, "create_reroll")
        self.state_of(who, "重骰形之後")
        self.do(who, "create_reread", {"text": "寒潭映月，一劍西來"})  # 模型擋著：不扣帖
        self.do(who, "create_reread", {"text": "短"})
        with self.model(read=CRAFT_REREAD):
            self.do(who, "create_reread", {"text": "寒潭映月，劍氣橫秋"})
        self.state_of(who, "重讀之後")
        for _ in range(4):  # 骰到上限
            self.mx(who, "create_reroll")
        self.state_of(who, "骰滿之後")

    def half(self) -> None:
        """前半停在這裡：擺式那一步、立意那一步、成形還沒立名（兩張帖，重骰過一次）、舊存檔的三步單子、煉製頁那一爐合好一個。"""
        from tianxia.features.craft import create
        from tianxia.state import CreateDraft

        self.mx(self.H_POSE, "create_begin", {"kind": "武學", "form": "拳腳"})
        self.mx(self.H_INTENT, "create_begin", {"kind": "武學", "form": "拳腳"})
        self.mx(self.H_INTENT, "create_pose", {"pose": create.preset(self.c, "進擊")})
        self.mx(self.H_NAME, "create_begin", {"kind": "武學", "form": "拳腳"})
        self.mx(self.H_NAME, "create_pose", {"pose": create.preset(self.c, "進擊")})
        with self.model(read=CRAFT_READ):
            self.do(self.H_NAME, "create_intent", {"text": "蘆葦蕩裡，一葉渡江"})
        self.edit(self.H_NAME, lambda p: setattr(p, "create_rerolls", 2))
        self.mx(self.H_NAME, "create_reroll")
        self.edit(self.H_OLD, lambda p: setattr(p, "creating", CreateDraft(kind="武學", step="name")))  # 沒有 form：三步時代的單子
        ins = self.base_insights()
        with self.model({"name": "星砌意", "description": "階前星影的意思"}):
            self.forge(self.H_FURNACE, ins[:2])
        for who in (self.H_POSE, self.H_INTENT, self.H_NAME, self.H_OLD, self.H_FURNACE):
            self.state_of(who, "前半停在這裡")

    # ── 後半 ──

    def resume(self) -> None:
        """新程式接著走：擺式的接著擺、立意的接著三段式、成形的重讀與重骰再立名、舊單子收掉重開、煉製頁接著合。"""
        from tianxia.features.craft import create

        self.login_all()
        for who in (self.H_POSE, self.H_INTENT, self.H_NAME, self.H_OLD, self.H_FURNACE):
            self.state_of(who, "接手時")
        who = self.H_POSE
        self.mx(who, "create_pose", {"pose": create.preset(self.c, "起手")})
        with self.model(read=CRAFT_READ):
            self.do(who, "create_intent", {"text": "星河落處，萬籟俱寂"})
        self.mx(who, "create_name", {"name": "星砌拳", "move": ""})
        self.state_of(who, "走完之後")
        who = self.H_INTENT
        self.do(who, "create_intent", {"text": "石上清泉，流而不竭"})  # 模型擋著
        self.mx(who, "create_back", {"to": "pose"})
        self.mx(who, "create_cancel")
        self.state_of(who, "作罷之後")
        who = self.H_NAME
        with self.model(read=CRAFT_REREAD):
            self.do(who, "create_reread", {"text": "蘆葦蕩裡，一葉渡江"})
        self.mx(who, "create_reroll")  # 骰滿了
        self.mx(who, "create_name", {"name": "葦渡掌", "move": "裂冰式"})
        self.state_of(who, "走完之後")
        who = self.H_OLD
        self.menxia(who)
        self.mx(who, "create_name", {"name": "舊簿掌", "move": ""})  # 單子被收掉了
        self.mx(who, "create_begin", {"kind": "武學", "form": "拳腳"})
        self.state_of(who, "舊單子之後")
        who = self.H_FURNACE
        ins = self.base_insights()
        with self.model({"name": "星砌意", "description": "階前星影的意思"}):
            self.forge(who, ins[:2])  # 已經悟得
            self.forge(who, ins[2:4])
        self.state_of(who, "走完之後")
        self.recipes("接手之後")

    def views(self) -> None:
        """煉製頁與門下頁的資料（create_view、預覽）：每個人看一遍。"""
        ins = self.base_insights()
        for who in self.PLAYERS:
            self.menxia(who)
            self.line(who, {"insights": ins[:2]})
            self.main(who)

    def bots(self) -> None:
        """伺服器假人兩個（BotRunner：bot_policy.tend_arts 合一爐、自創一門）：心得多、手上有意境。"""
        from collections import Counter

        from tianxia import server_bots
        from tianxia.bot_runner import BotRunner
        from tianxia.engine import Game
        from tianxia.state import BotProfile

        ins = self.base_insights()
        for i, name in enumerate(self.BOT_SEATS):
            self.begin()
            g = Game.new(self.c, name, rng=random.Random(i), world=self.world, graduated=True)
            p = g.state.player
            p.bot = BotProfile(personality="普通", seed=61 + i, faction=None, season_number=self.world.get_season_number())
            g.client = None
            g.sync(CLOCK[0])
            p.insights.extend(i2 for i2 in ins if i2 not in p.insights)
            p.stats["xinde"] = 20000
            p.stamina = float(self.c.config.stamina_max)
            p.tutorial_step = len(self.c.tutorial.steps)
            p.joined_at = -1.0e9
            self.chars.save(g.state)
        runner = BotRunner(self.c, self.world, self.chars, rng=random.Random(23), clock=lambda: CLOCK[0])
        tick, online = self.c.config.bot_tick_seconds, server_bots.is_online
        seeds = {61 + i for i in range(len(self.BOT_SEATS))}
        self.c.config.bot_tick_seconds = 10 ** 6
        server_bots.is_online = lambda profile, now: profile.seed in seeds or online(profile, now)
        totals = Counter()
        try:
            for _ in range(int(os.environ.get("SB_CRAFT_TICKS", "12"))):
                STEP[0] += 4
                self.begin()
                report = runner.tick()
                totals.update(acted=report.acted, added=report.added, skipped=report.skipped, failed=report.failed, online=report.online,
                              named=report.named)
        finally:
            self.c.config.bot_tick_seconds, server_bots.is_online = tick, online
        emit("假人 一輪一輪", dict(sorted(totals.items())))
        for name in self.BOT_SEATS:
            s = self.chars.load(name)
            p = s.player
            emit(f"假人 {name}", {"insights": list(p.insights), "arts": list(p.arts), "created": p.created_count,
                                  "creating": None if p.creating is None else p.creating.model_dump(),
                                  "titles": dict(sorted(Counter(e.title.partition("・")[0] for e in s.journal).items())),
                                  "state": hashlib.sha256(s.model_dump_json().encode("utf-8")).hexdigest()})
        self.begin()
        from tianxia import bot

        solo = Game.new(self.c, "匠丙", rng=random.Random(5), world=self.world, graduated=True)
        solo.client = None
        solo.sync(CLOCK[0])
        p = solo.state.player
        p.insights.extend(i2 for i2 in ins if i2 not in p.insights)
        p.stats["xinde"] = 20000
        p.tutorial_step = len(self.c.tutorial.steps)
        emit("整季機器人挑的爐", sorted({str(bot.pick_forge(solo, random.Random(k))) for k in range(30)}))

    def season(self) -> None:
        """收季、開下一季：走到一半的單子跟新角色重來。"""
        self.do(ADMIN, "end_season")
        for who in (self.H_INTENT, self.H_OLD, self.REROLLER):
            self.menxia(who)
        self.do(ADMIN, "next_season")
        for who in (self.H_INTENT, self.H_OLD, self.REROLLER, self.MAKER):
            self.menxia(who)
            self.state_of(who, "換季之後（動作前的存檔）")
            self.main(who)  # status.create.draft 才看得到單子有沒有清掉（/api/menxia 沒有單子）
            self.mx(who, "create_name", {"name": "霜葉掌", "move": ""})  # 單子清了應回「你還沒起意」
            self.state_of(who, "換季之後（動作後）")
        self.line(self.MAKER, {"insights": self.base_insights()[:2]})


# 改一個字（selftest）：重悟帖沒有帖那一句（搬之前在 tianxia/create.py、之後在 tianxia/features/craft/ 的規則模組；第 2 項是之後的檔名，
# 搬的人照實際的檔名改這一個字串）。抓到的地方：松檐重骰形的第一下
register_track("craft", CraftScenario, (("tianxia/features/craft/create.py",),
                                        ('NO_REROLL = "手上沒有重悟帖：萬寶閣買得到。"', 'NO_REROLL = "手上沒有重悟帖：萬寶閣買得到！"')), "week7",
               covers=("admin", "battle", "bounties", "bout", "checkin", "companions", "craft", "cultivation", "explore", "faction",
                       "figure_acts", "gear", "guide", "heroines", "legacy", "looks", "mall", "military", "outlets", "peers",
                       "seal", "seclusion", "sense", "smithy", "socialize", "sortie", "stamina_plays", "story", "tavern", "travel",
                       "zhuan"))
