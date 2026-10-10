"""口訣與秘方（PM 2026-10-10 派工，企劃者選「甲乙都做」的甲：「我們合成要講究邏輯還有最好能隱含技巧都藏彩蛋，
不然沒有驚喜推動不了玩家的動力」）。

| 誰 | 做什麼 |
|---|---|
| 內容（content/secret_recipes.json） | 秘方池：配方的形狀、名號、一句說明、三句口訣 |
| 這裡 | 這一季挑哪幾條（照天機）、這一爐合不合得上、武學譜（聽過的口訣、合中過的秘方）、三種線索怎麼給 |
| fusion | 合中了怎麼登記、品質機率加多少、傳聞與江湖史 |

每季照天機從池子裡挑 Config.secrets.per_season 條（全服同一批）。秘方不認 id，認形狀（屬性、種類、正邪、品質門檻、
基本意境的 id）：玩家的武學多半是合出來的，id 每季都不一樣。合中了的配方鍵是「秘|秘方 id」，全服共用同一門，
別人再合中就是照著合；合中秘方先於「合到舊的」判定。
口訣三句（clues）：0 說書版（城裡的說書事件了結時偶爾多一句）、1 人物順口版（情誼夠了，模型的提示裡塞一句，
他原文引出來才算聽到）、2 殘譜版（探索最後擲一次）。玩家聽過的記在武學譜（PlayerState.manual），只記這一季的。
假人與整季機器人照舊隨機合，可能偶然撞到秘方，但不讀口訣。
擲骰一律用自己的亂數（種子是名號、時間與來源），不動 Game.rng：接上這一套之後，既有的固定種子序列不會位移。
"""
from __future__ import annotations

import hashlib
import random
import re

from . import insights
from .martial_arts import QUALITIES, Insight, MartialArt
from .models import ArtPattern, Content, InsightPattern, SecretRecipe
from .state import GameState, Manual
from .world_state import WorldStateStore

TALE, TALK, SCRAP = 0, 1, 2  # 口訣的三個版本（SecretRecipe.clues 的位置）
PREFIX = "秘|"
_PUNCT = re.compile(r"[\s，。、！？；：「」『』（）,.!?;:()…—]")


def _rank(tianji: int, recipe_id: str) -> bytes:
    return hashlib.sha256(f"{tianji}|{recipe_id}|秘方".encode("utf-8")).digest()


def active(content: Content, tianji: int) -> list[SecretRecipe]:
    """這一季（天機）的秘方：每一種照 per_season 挑幾條，同一季全服同一批、換季換一批。"""
    out: list[SecretRecipe] = []
    for kind, count in content.config.secrets.per_season.items():
        pool = sorted((r for r in content.secret_recipes if r.kind == kind), key=lambda r: _rank(tianji, r.id))
        out += pool[:count]
    return out


def tianji_of(world: WorldStateStore) -> int:
    return world.read().tianji


def key(recipe: SecretRecipe) -> str:
    return PREFIX + recipe.id


# ── 合不合得上 ─────────────────────────────────────────


def art_fits(pattern: ArtPattern, art: MartialArt, quality: str) -> bool:
    return (
        (pattern.attribute is None or art.attribute == pattern.attribute)
        and (pattern.kind is None or art.kind == pattern.kind)
        and (pattern.lean is None or art.lean == pattern.lean)
        and (pattern.min_quality is None or QUALITIES.index(quality) >= QUALITIES.index(pattern.min_quality))
    )


def insight_fits(pattern: InsightPattern, insight: Insight, content: Content) -> bool:
    """私有意境（感悟悟來的，insights.is_own）沒有全服的 id：寫了 id 的格子照那個基本意境的屬性認，跟配方鍵認私有意境同一套
    （fusion.fuse_key）——大多數人手上的意境是自己悟的，不這樣認，秘方幾乎沒人合得上。"""
    if pattern.id is not None and insight.id != pattern.id:
        known = content.insights.get(pattern.id)
        if not (insights.is_own(insight.id) and known is not None and known.attribute == insight.attribute):
            return False
    return ( (pattern.attribute is None or insight.attribute == pattern.attribute)
        and (pattern.lean is None or insight.lean == pattern.lean)
    )


def _quality(state: GameState, art_id: str, art: MartialArt) -> str:
    return state.player.art_quality.get(art_id, art.quality)


def match_fuse(
    state: GameState, content: Content, world: WorldStateStore, art_id: str, art: MartialArt, insight: Insight,
) -> SecretRecipe | None:
    if not content.secret_recipes:
        return None
    quality = _quality(state, art_id, art)
    return next((
        r for r in active(content, tianji_of(world))
        if r.kind == "fuse" and r.art is not None and r.insight is not None
        and art_fits(r.art, art, quality) and insight_fits(r.insight, insight, content)
    ), None)


def match_merge(content: Content, world: WorldStateStore, left: Insight, right: Insight) -> SecretRecipe | None:
    """兩個意境照爐子的左右兩格（Game.forge 的 insight_ids 的先後）：左右放反了合不上。"""
    if not content.secret_recipes:
        return None
    return next((
        r for r in active(content, tianji_of(world))
        if r.kind == "merge" and r.left is not None and r.right is not None
        and insight_fits(r.left, left, content) and insight_fits(r.right, right, content)
    ), None)


def match_blend(
    state: GameState, content: Content, world: WorldStateStore, a: str, art_a: MartialArt, b: str, art_b: MartialArt,
) -> SecretRecipe | None:
    """兩門武學不分先後。"""
    if not content.secret_recipes:
        return None
    qa, qb = _quality(state, a, art_a), _quality(state, b, art_b)
    for r in active(content, tianji_of(world)):
        if r.kind != "blend" or len(r.arts) != 2:
            continue
        one, two = r.arts
        if (art_fits(one, art_a, qa) and art_fits(two, art_b, qb)) or (art_fits(one, art_b, qb) and art_fits(two, art_a, qa)):
            return r
    return None


def special_for(content: Content, recipe: SecretRecipe, tianji: int) -> str | None:
    """秘方合出來的武學一定帶一條特別功效：內容寫了照寫的，沒寫照天機從共用清單挑。"""
    if recipe.special is not None:
        return recipe.special
    pool = sorted(t.id for t in content.traits.special if t.pool)
    if not pool:
        return None
    return pool[_rank(tianji, recipe.id)[0] % len(pool)]


# ── 武學譜 ─────────────────────────────────────────────


def manual(state: GameState, tianji: int) -> Manual:
    """這一季的武學譜：記的是別一季的就換一本新的（秘方每季換一批，舊的口訣對不上了）。"""
    if state.player.manual.tianji != tianji:
        state.player.manual = Manual(tianji=tianji)
    return state.player.manual


def solve(state: GameState, tianji: int, recipe: SecretRecipe) -> None:
    book = manual(state, tianji)
    if recipe.id not in book.solved:
        book.solved.append(recipe.id)


def _note(book: Manual, recipe: SecretRecipe, source: int) -> bool:
    """記下聽到這一句；本來就聽過回 False。"""
    heard = book.heard.setdefault(recipe.id, [])
    if source in heard:
        return False
    heard.append(source)
    heard.sort()
    return True


def hear(state: GameState, content: Content, tianji: int, source: int, seed: str) -> str | None:
    """說書與殘譜：挑這一季一條秘方的那一版口訣，記進武學譜，回那一句。先挑還沒合中、這一版還沒聽過的
    （聽得最少的優先）；都聽過了就重說一句聽過的（不記）。這一季沒有秘方回 None。"""
    recipes = active(content, tianji)
    if not recipes:
        return None
    book = manual(state, tianji)
    rng = random.Random(seed)
    fresh = [r for r in recipes if r.id not in book.solved and source not in book.heard.get(r.id, [])]
    if fresh:
        fewest = min(len(book.heard.get(r.id, [])) for r in fresh)
        recipe = rng.choice([r for r in fresh if len(book.heard.get(r.id, [])) == fewest])
        _note(book, recipe, source)
    else:
        recipe = rng.choice(recipes)
    return recipe.clues[source]


def roll(chance: float, seed: str) -> bool:
    """自己的亂數：機率是 0 不擲（測試內容全關）。"""
    return chance > 0 and random.Random(seed).random() < chance


def talk_clue(content: Content, tianji: int, companion_id: str) -> SecretRecipe | None:
    """這位人物這一季知道哪一條（照天機與人物 id 雜湊；同一個人聊再多次都是同一句，想聽別的要去找別人）。"""
    recipes = active(content, tianji)
    if not recipes:
        return None
    digest = hashlib.sha256(f"{tianji}|{companion_id}|口訣".encode("utf-8")).digest()
    return recipes[int.from_bytes(digest[:4], "big") % len(recipes)]


def talk_line(state: GameState, content: Content, world: WorldStateStore, companion_id: str, name: str) -> str:
    """人物對話的系統提示多一段：他聽過的一句口訣，只能不經意原文引出來。情誼不夠、這一季沒有秘方是空的。"""
    cfg = content.config.secrets
    if state.player.affinities.get(companion_id, 0) < cfg.talk_affinity:
        return ""
    recipe = talk_clue(content, tianji_of(world), companion_id)
    if recipe is None:
        return ""
    return (
        f"【{name}早年聽過的一句武林口訣（不要解釋它的意思，不要說這是口訣、秘方或配方；只有話題碰到武藝、修練、"
        f"江湖舊聞時才不經意原字原句引一次，像是隨口想起的老話）】「{recipe.clues[TALK]}」\n"
    )


def _plain(text: str) -> str:
    return _PUNCT.sub("", text)


def overheard(state: GameState, content: Content, world: WorldStateStore, companion_id: str, text: str) -> bool:
    """人物這一輪的話裡原字原句說出了他知道的那句口訣（不看標點）：記進武學譜，第一次聽到回 True。
    沒說、說走了樣、情誼不夠（提示裡沒有它）都不算。"""
    if state.player.affinities.get(companion_id, 0) < content.config.secrets.talk_affinity:
        return False
    tianji = tianji_of(world)
    recipe = talk_clue(content, tianji, companion_id)
    if recipe is None or _plain(recipe.clues[TALK]) not in _plain(text):
        return False
    return _note(manual(state, tianji), recipe, TALK)


def view(state: GameState, content: Content, world: WorldStateStore) -> list[dict]:
    """武學譜給畫面的資料：這一季聽過口訣或合中過的秘方，一條一筆——聽過的那幾句（照版本的先後）、合中了寫它的名號
    （沒合中是 None）。不寫秘方的種類與配方。"""
    tianji = tianji_of(world)
    book = state.player.manual if state.player.manual.tianji == tianji else Manual(tianji=tianji)
    rows = []
    for recipe in active(content, tianji):
        heard = book.heard.get(recipe.id, [])
        solved = recipe.id in book.solved
        if heard or solved:
            name = None
            if solved:  # 登記的名字（名號撞到時換過名字）：照全服登記的那一筆寫
                made = world.lookup_insight_recipe(key(recipe)) if recipe.kind == "merge" else world.lookup_recipe(key(recipe))
                name = made.name if made is not None else recipe.name
            rows.append({"clues": [recipe.clues[i] for i in heard], "solved": name})
    return rows
