"""女子與隱線的純規則（設計稿「三位女子出場」https://claude.ai/artifact/UBuM248hcNqTV9JWQsfUNb；Joy 2026-11-06「開工」，尺度「那先甲就好」）。

- 一位女子（content/heroines.json）走完她那一條奇事、而且收在 endings 裡的結局，才出現在她的 talk_at（figures.placed_characters 讀 placed）；
  沒走、走到別的結局、季末沒收，她不在任何地方（求見、交友、地圖都沒有她）。
- 隱線：玩家在設定頁開了成人內容（PlayerState.heroines_adult；確認過年滿十八歲）、結局在 hidden 裡、情誼到了，那一段（scenes）才端得出來。
  沒開的人什麼都看不到：選項不出、提示不帶、模型寫回來的照最嚴的一份過濾。假人永遠是關的。
- 給模型的：故事之後那一段（endings）、隱線走到哪的那一句（prompt）、分寸（雙方成年、雙方同意、不提別人；尺度照甲）。
- 模型寫回來的、玩家自己打的：clean 擋未成年、強迫、超過這一段尺度的字，擋到就換成固定的一句。

只 import 核心（models、state、rules）。玩家看得到的字都待 joy 潤。"""
from __future__ import annotations

from tianxia import rules
from tianxia import figures  # 過渡：待搬（大勢人物，總表第 40 批收進共用規則層）
from tianxia.models import Content, HeroineDef, HeroineScene
from tianxia.state import GameState, HeroineNotes

# 過濾的字（甲級：寫到熄燈為止）。未成年、強迫的不管開不開、到哪一段都擋；親密的到第四段也擋（甲不寫）；調情的沒開、或還沒到第三段擋
MINOR = ("幼女", "女童", "童女", "少女", "未成年", "孩童", "小女孩", "蘿莉", "稚女", "及笄")
FORCE = ("強迫", "強暴", "強姦", "迷姦", "下藥", "迷藥", "灌醉", "逼她", "硬要")
EXPLICIT = ("交合", "交歡", "雲雨", "床笫", "寬衣", "解帶", "脫衣", "赤裸", "裸身", "裸體", "酥胸", "乳房", "胸脯", "下體", "陽具",
            "陰部", "陰莖", "呻吟", "肉體", "春宮", "媾", "行房", "同房", "纏綿")
ROMANCE = ("親吻", "擁吻", "吻了", "吻你", "吻她", "相擁", "摟住", "摟著", "調情", "撫摸", "依偎", "投懷")

FALLBACK = "{name}沒有接這句話，低頭做自己手上的事。"  # 待 joy 潤：擋下來的那一輪
FALLBACK_OPTION = "換個話題"  # 待 joy 潤
ADULT_ON = "（已開啟成人內容。）"  # 待 joy 潤
ADULT_OFF = "（已關閉成人內容。）"  # 待 joy 潤
NO_BOT = "（此刻無法這麼做。）"
ROLE_REAL = "漢末真實歷史人物"
ROLE_OWN = "漢末的一位尋常女子（不是史書上的人物，是這個遊戲裡寫的人）"
AFTER = "【{name}的故事之後】{note}\n"
LIMIT_PLAIN = "【分寸】{name}與玩家之間只寫情誼、恩怨與往來，不寫調情、不寫親密的舉動。\n"
LIMIT_KISS = ("【分寸】{name}與玩家都是成年人，彼此情願。可以寫曖昧、眼神、牽手，最多到一個親吻；不寫更進一步的親密，"
              "不提任何其他人物的私事，不寫強迫或醉後的事。\n")
LIMIT_LOVERS = ("【分寸】{name}與玩家都是成年人，彼此情願，已是相好。可以寫私下的溫存與牽掛，提到親密的事只用一兩句帶過、"
                "寫到熄燈為止，不描寫身體與過程；不提任何其他人物的私事，不寫強迫或醉後的事。\n")


def on(content: Content) -> bool:
    return bool(content.heroines)


def notes(state: GameState) -> HeroineNotes:
    return state.player.heroines


def adult(state: GameState) -> bool:
    """這個人開了成人內容（假人永遠沒有）。"""
    return state.player.heroines_adult and not state.player.bot


def heroine(content: Content, cid: str) -> HeroineDef | None:
    return content.heroines.get(cid)


def ending_of(state: GameState, content: Content, cid: str) -> str | None:
    """她那一條奇事收在哪一個留得下她的結局；沒走、還在走、收在別的結局（失敗、季末沒收）是 None（共用規則層那一份）。"""
    return figures.heroine_ending(state, content, cid)


def present(state: GameState, content: Content, cid: str) -> bool:
    """這位人物此刻出不出現：不是女子照舊出現；女子要走完她的奇事。"""
    return heroine(content, cid) is None or ending_of(state, content, cid) is not None


def step(state: GameState, cid: str) -> int:
    return notes(state).steps.get(cid, 0)


def next_scene(state: GameState, content: Content, cid: str) -> HeroineScene | None:
    """此刻端得出來的那一段隱線：開了成人內容、結局開得了隱線、上一段應下了、情誼到了、今天沒婉拒過。都不是就是 None。"""
    hd = heroine(content, cid)
    if hd is None or not adult(state):
        return None
    ending = ending_of(state, content, cid)
    if ending is None or ending not in hd.hidden:
        return None
    if notes(state).declined.get(cid) == rules.game_day(content, state.world):
        return None
    want = max(3, step(state, cid) + 1)
    scene = next((s for s in hd.scenes if s.step == want), None)
    if scene is None or state.player.affinities.get(cid, 0) < scene.affinity:
        return None
    return scene


def hidden_talk(state: GameState, content: Content, cid: str) -> bool:
    """這一輪交談算不算隱線（給交談點數那一份用：隱線只扣每天免費的那一份；Joy 11/6 心神設計稿第 3 版）。"""
    return heroine(content, cid) is not None and adult(state) and step(state, cid) >= 3


def role(content: Content, cid: str) -> str:
    """提示詞開頭那一句扮演的是誰：女子是我們寫的人，不是史書上的。"""
    return ROLE_OWN if heroine(content, cid) is not None else ROLE_REAL


def limit_step(state: GameState, content: Content, cid: str) -> int:
    """這一位此刻的尺度：0 只寫情誼（沒開、或還沒進隱線）、3 到親吻、4 相好（照甲，寫到熄燈）。"""
    return step(state, cid) if adult(state) else 0


def prompt_lines(state: GameState, content: Content, cid: str) -> str:
    """給模型的那幾行：故事之後、隱線走到哪、分寸。不是女子是空字串（提示一個字不多）。"""
    hd = heroine(content, cid)
    if hd is None:
        return ""
    name = content.characters[cid].name
    out = ""
    ending = ending_of(state, content, cid)
    if ending is not None:
        out += AFTER.format(name=name, note=hd.endings[ending])
    level = limit_step(state, content, cid)
    if level >= 3 and hd.prompt.get(level):
        out += f"【你們之間】{hd.prompt[level]}\n"
    limit = LIMIT_LOVERS if level >= 4 else LIMIT_KISS if level >= 3 else LIMIT_PLAIN
    return out + limit.format(name=name)


def banned(state: GameState, content: Content, cid: str) -> tuple[str, ...]:
    """這一位此刻要擋的字。"""
    words = MINOR + FORCE + EXPLICIT
    return words if limit_step(state, content, cid) >= 3 else words + ROMANCE


def hits(text: str, words: tuple[str, ...]) -> bool:
    return any(w in (text or "") for w in words)


def clean(state: GameState, content: Content, cid: str, narrative: str, options: list[str], said: str) -> tuple[str, list[str], str, bool]:
    """模型寫回來的這一輪、玩家這一句：不是女子原樣回；擋到的字整段換掉（敘事換成固定的一句、選項換成「換個話題」、玩家那句換成刪節號）。
    回 (敘事, 選項, 玩家那句, 擋了沒)。"""
    if heroine(content, cid) is None:
        return narrative, options, said, False
    words = banned(state, content, cid)
    name = content.characters[cid].name
    blocked = hits(narrative, words) or hits(said, words)
    narrative = FALLBACK.format(name=name) if blocked else narrative
    kept = [FALLBACK_OPTION if hits(o, words) else o for o in options]  # 照位置換（選項跟歸類一對一，不能少一個）
    blocked = blocked or kept != list(options)
    said = "……" if hits(said, words) else said
    return narrative, kept, said, blocked
