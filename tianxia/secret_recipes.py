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

from . import insight_fx, insights
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
    return world.tianji()


def key(recipe: SecretRecipe) -> str:
    return PREFIX + recipe.id


# ── 合不合得上 ─────────────────────────────────────────


def _attrs(art: MartialArt) -> list[str]:
    """武學重構：秘方認武學的屬性照相容屬性（門面）；寫死的武學沒有相容屬性，照內容的屬性。兼容並蓄的沒有屬性，認不上寫了屬性的格子。"""
    return list(art.affinity) if art.affinity else ([art.attribute] if art.attribute else [])


def art_fits(pattern: ArtPattern, art: MartialArt, quality: str) -> bool:
    return (
        (pattern.attribute is None or pattern.attribute in _attrs(art))
        and (pattern.kind is None or art.kind == pattern.kind)
        and (pattern.lean is None or art.lean == pattern.lean)
        and (pattern.min_quality is None or QUALITIES.index(quality) >= QUALITIES.index(pattern.min_quality))
    )


def insight_fits(pattern: InsightPattern, insight: Insight, content: Content) -> bool:
    """私有意境（感悟悟來的，insights.is_own）沒有全服的 id：寫了 id 的格子照那個基本意境的屬性認，跟配方鍵認私有意境同一套
    （fusion.fuse_key）——大多數人手上的意境是自己悟的，不這樣認，秘方幾乎沒人合得上。"""
    if pattern.id is not None and insight_fx.base_id(insight.id) != pattern.id:  # 第二份起「feng~2」照那一種認
        known = content.insights.get(pattern.id)
        if not (insights.is_own(insight.id) and known is not None and known.attribute == insight.attribute):
            return False
    return ( (pattern.attribute is None or insight.attribute == pattern.attribute)
        and (pattern.lean is None or insight.lean == pattern.lean)
    )


def _quality(state: GameState, art_id: str, art: MartialArt) -> str:
    return state.player.art_quality.get(art_id, art.quality)


def match_slots(
    state: GameState, content: Content, world: WorldStateStore, art_id: str, art: MartialArt, slots: list,
) -> SecretRecipe | None:
    """武學重構：「屬性＋指定意境裝滿」——kind fuse 的秘方（以前是武學＋意境合成）改成：武學合得上那一格（相容屬性、種類、
    自己那一份的品級門檻），槽全部裝滿、其中一格是指定的意境，就暗合口訣（arts.apply 給那條特別功效，arts.slot 報一句）。
    art 是門面那一份（相容屬性）；先只看內容的形狀，對得上才讀天機。"""
    if not content.secret_recipes or not slots or None in slots:
        return None
    quality = _quality(state, art_id, art)
    resolved = [insights.resolve(i, content, world, state) for i in slots]
    if not art.affinity:  # 兼容並蓄：屬性照槽裡強度最高那一格（同 arts.apply），不照內容原本寫的
        top, best = "", 0
        for insight_id, ins in zip(slots, resolved):
            strength = insight_fx.strength(state, insight_id)
            if ins is not None and ins.attribute and strength > best:
                top, best = ins.attribute, strength
        art = art.model_copy(update={"affinity": [top] if top else [], "attribute": top})
    candidates = [
        r for r in content.secret_recipes
        if r.kind == "fuse" and r.art is not None and r.insight is not None and art_fits(r.art, art, quality)
        and any(ins is not None and insight_fits(r.insight, ins, content) for ins in resolved)
    ]
    if not candidates:
        return None
    live = {r.id for r in active(content, tianji_of(world))}
    return next((r for r in candidates if r.id in live), None)


def match_merge(content: Content, world: WorldStateStore, left: Insight, right: Insight) -> SecretRecipe | None:
    """兩個意境照爐子的左右兩格（Game.forge 的 insight_ids 的先後）：左右放反了合不上。"""
    if not content.secret_recipes:
        return None
    return next((
        r for r in active(content, tianji_of(world))
        if r.kind == "merge" and r.left is not None and r.right is not None
        and insight_fits(r.left, left, content) and insight_fits(r.right, right, content)
    ), None)


SET_LINE = "【{art}】的意境槽一裝滿，竟暗合口訣，使出來是一路【{name}】——多了一條「{special}」。"  # 待 joy 潤


def set_lines(state: GameState, content: Content, world: WorldStateStore, recipe: SecretRecipe, art_name: str) -> list[str]:
    """「裝滿」秘方暗合的那一下（arts.slot 裝滿最後一格時）：記進武學譜；這一季第一個暗合的人江湖上傳一句、寫進江湖史
    （WorldState.secret_sets 記誰先，跟著這一下動作最後的 _save_season 存）。拆了再裝回來照樣說一句，傳聞只有第一次。"""
    from .rules import add_chronicle, add_rumor

    cfg = content.config.secrets
    tianji = tianji_of(world)
    fresh = solve(state, tianji, recipe)
    sp = next((t for t in content.traits.special if t.id == special_for(content, recipe, tianji)), None)
    lines = [SET_LINE.format(art=art_name, name=recipe.name, special=sp.name if sp else "特別功效")]
    if fresh:
        lines += solved_lines(state, content, world)
    season = getattr(state, "world", None)
    if season is not None and recipe.id not in season.secret_sets:
        who = state.player.name
        season.secret_sets[recipe.id] = who
        thing = f"【{recipe.name}】"
        rumor = cfg.rumor.format(who=who, thing=thing)
        add_rumor(state, rumor, None, content=content, named=True)
        add_chronicle(state, cfg.chronicle.format(who=who, thing=thing))
        lines.append(rumor)
    return lines


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


def solve(state: GameState, tianji: int, recipe: SecretRecipe) -> bool:
    """記下合中了這一條；這一季第一次參透回 True（照著合第二次回 False）。"""
    book = manual(state, tianji)
    if recipe.id in book.solved:
        return False
    book.solved.append(recipe.id)
    return True


def progress(state: GameState, content: Content, world: WorldStateStore) -> tuple[int, int]:
    """（這一季參透了幾條, 這一季全服共有幾條）：分母是這一季挑出來的那一批，不是「你聽過的」（玩家回報 2026-10-25）。"""
    tianji = tianji_of(world)
    live = {r.id for r in active(content, tianji)}
    book = state.player.manual
    done = sum(1 for r in book.solved if r in live) if book.tianji == tianji else 0
    return done, len(live)


def solved_name(world: WorldStateStore, recipe: SecretRecipe) -> str:
    """合中了寫它的名號：照全服登記的那一筆（名號撞到時換過名字）。"""
    made = world.lookup_insight_recipe(key(recipe)) if recipe.kind == "merge" else world.lookup_recipe(key(recipe))
    return made.name if made is not None else recipe.name


def solved_lines(state: GameState, content: Content, world: WorldStateStore) -> list[str]:
    """剛參透一條：結果多一句這一季的進度（Config.secrets.solved_note）。"""
    note_line = content.config.secrets.solved_note
    if not note_line:
        return []
    done, total = progress(state, content, world)
    return [note_line.format(n=done, total=total)]


def solved_card(state: GameState, content: Content, world: WorldStateStore, recipe: SecretRecipe) -> dict:
    """參透那一下跳的視窗（Game.secret_solved → 伺服器的 secret，網頁 secretPop；企劃者 2026-10-25「應該是跳顯出個視窗比較明顯」）：
    朱印寫它的名號、聽過的口訣、這一季的進度。"""
    cfg = content.config.secrets
    done, total = progress(state, content, world)
    heard = state.player.manual.heard.get(recipe.id, [])
    return {
        "title": cfg.solved_title.format(n=done, total=total),
        "name": solved_name(world, recipe),
        "clues": [recipe.clues[i] for i in heard],
        "solved": done,
        "total": total,
        "note": cfg.solved_note.format(n=done, total=total) if cfg.solved_note else "",
    }


def note(book: Manual, recipe: SecretRecipe, source: int) -> bool:
    """記下聽到這一句（武學譜與鑄譜共用，recipe 只要有 id）；本來就聽過回 False。"""
    heard = book.heard.setdefault(recipe.id, [])
    if source in heard:
        return False
    heard.append(source)
    heard.sort()
    return True


def hear_from(recipes: list, book: Manual, source: int, seed: str) -> str | None:
    """說書與殘譜的挑法（武學譜與鑄譜共用；打造隱藏配方設計 6.1）：先挑還沒合中（打中）、這一版還沒聽過的（聽得最少的優先），
    記進那一本譜；都聽過了就重說一句聽過的（不記）。池子空的回 None。recipes 的每一條要有 id 與三句 clues。"""
    if not recipes:
        return None
    rng = random.Random(seed)
    fresh = [r for r in recipes if r.id not in book.solved and source not in book.heard.get(r.id, [])]
    if fresh:
        fewest = min(len(book.heard.get(r.id, [])) for r in fresh)
        recipe = rng.choice([r for r in fresh if len(book.heard.get(r.id, [])) == fewest])
        note(book, recipe, source)
    else:
        recipe = rng.choice(recipes)
    return recipe.clues[source]


def hear(state: GameState, content: Content, tianji: int, source: int, seed: str) -> str | None:
    """說書與殘譜：挑這一季一條秘方的那一版口訣，記進武學譜，回那一句（挑法見 hear_from）。這一季沒有秘方回 None。"""
    recipes = active(content, tianji)
    if not recipes:
        return None
    return hear_from(recipes, manual(state, tianji), source, seed)


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
    return note(manual(state, tianji), recipe, TALK)


def view(state: GameState, content: Content, world: WorldStateStore) -> list[dict]:
    """武學譜給畫面的資料：這一季聽過口訣或合中過的秘方，一條一筆——聽過的那幾句（照版本的先後）、合中了寫它的名號
    （沒合中是 None）、種類（kind：fuse 裝滿武學的意境槽、merge 兩個意境合成；Joy 2026-10-25「兩個應該分開放，或是有標示種類，
    不然很容易搞混」，武學譜照它分兩段）。不寫配方。"""
    tianji = tianji_of(world)
    book = state.player.manual if state.player.manual.tianji == tianji else Manual(tianji=tianji)
    rows = []
    for recipe in active(content, tianji):
        heard = book.heard.get(recipe.id, [])
        solved = recipe.id in book.solved
        if heard or solved:
            name = solved_name(world, recipe) if solved else None
            rows.append({"clues": [recipe.clues[i] for i in heard], "solved": name, "kind": recipe.kind})
    return rows
