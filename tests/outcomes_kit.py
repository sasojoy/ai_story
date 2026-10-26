"""減法季批 4 接線（隨口應對分岔、痕跡看得見）的測試建法。批 2 的 tests/jianfa_kit.py 同時在建（同名的檔不要在這一批建），
這一份只給批 4 的測試用：測試內容的「醉漢」（town）掛上五種後果（勸說 check、扭送 combat、周濟 cost、搜身是作惡、走開是 fallback）
與它們的痕跡規則，打開減法季（總開關＋這一季的章）。模型一律是假的：測試直接把歸類好的 outcome 交給 C 段，或 mock 掉 event_llm。"""
from __future__ import annotations

import random
from unittest import mock

from tianxia import team
from tianxia.encounter import EncounterResult
from tianxia.engine import Game
from tianxia.models import Effect, FactionDef, FreeTextChoice, MarkRule, Outcome

OLD = Effect(text="他全招了。", stats={"good": 1})  # 關著的季照舊套的那一組（沒有分岔時的 effect／fail_effect）
OLD_FAIL = Effect(text="被他溜了。")
TALK = Outcome(
    id="talk", tag="勸說：好言相勸、講道理", check={"stat": "best_of", "stats": ["str", "wis"], "difficulty": 4},
    effect=Effect(text="醉漢聽了你的話，自己找了個牆角坐下。", stats={"good": 2}, marks={"town:勸醒": 1}, contribution=2),
    fail_effect=Effect(text="醉漢根本聽不進去，還吐了你一身。", stamina=-10),
)
CHASE = Outcome(
    id="chase", tag="扭送：把他押去見官", combat="thug",
    effect=Effect(text="你把醉漢押到衙門口。", stats={"fame": 1}, marks={"town:扭送": 1}, contribution=4),
    fail_effect=Effect(text="醉漢的同夥一擁而上，你只好退開。", stamina=-15),
)
GIVE = Outcome(
    id="give", tag="周濟：給他幾個錢醒酒", cost={"silver": 10},
    effect=Effect(text="你塞給醉漢幾個錢，叫他去喝碗醒酒湯。", stats={"good": 1}, marks={"town:周濟": 1}, contribution=1),
)
ROB = Outcome(
    id="rob", tag="搜身：趁他醉倒摸他的錢袋", check={"stat": "agi", "difficulty": 5},
    effect=Effect(text="你從醉漢懷裡摸出一串錢。", stats={"good": -1, "silver": 5}, marks={"town:搜身": 1}),
    fail_effect=Effect(text="醉漢一把抓住你的手腕大叫。"),
)
LEAVE = Outcome(id="leave", tag="走開：不管、對不上的", effect=Effect(text="你繞開醉漢走了。"))
OUTCOMES = [TALK, CHASE, GIVE, ROB, LEAVE]
RULES = [
    MarkRule(mark="town:勸醒", describe="街角的醉漢少了，酒肆門口有人掃地。", rumor="小鎮的醉漢被人勸醒了好幾個，街上清靜多了。"),
    MarkRule(mark="town:扭送", describe="衙門口的木枷上常鎖著鬧事的醉漢。", rumor="小鎮鬧事的醉漢被人一個個押去見官。",
             trend={"kou": -1}),
    MarkRule(mark="town:周濟", describe="醒酒湯的攤子前排起了隊。", rumor="小鎮有人出錢給醉漢喝醒酒湯。"),
    MarkRule(mark="town:搜身", describe="醉倒街頭的人醒來，錢袋常是空的。", rumor="小鎮醉倒的人常被摸走錢袋。"),
]
PROMPT = "另想法子打發醉漢"


def branch_game(content, world, *, name="甲", on=True, parts=None, faction="guan", rng=None, silver=50) -> Game:
    """開一個停在「醉漢」上的角色：on 是減法季的總開關與這一季的章（一起開關）；parts 再改子開關（例 {"free_text_outcomes": False}）。
    劇本補兩個陣營（tests/test_fb223_evil_free_text.py 的做法），faction 是這個人的陣營（None＝散人：照推、不記貢獻）；打開行狀。
    rng 在開好之後才換上（擲骰從同一個地方開始）。同一個測試開第二個角色時換 name，內容已經改過一次也照樣改（冪等）。"""
    content.scenario.factions = [
        FactionDef(id="guan", name="官軍", join_at=["town"]),
        FactionDef(id="huang", name="黃巾", join_at=["lake"]),
    ]
    content.config.biography.enabled = True
    content.events["drunk"].free_text = FreeTextChoice(prompt=PROMPT, stat="str", effect=OLD, fail_effect=OLD_FAIL, outcomes=OUTCOMES)
    content.mark_rules = [rule.model_copy() for rule in RULES]
    content.config.jianfa.enabled = on
    for part, value in (parts or {}).items():
        setattr(content.config.jianfa, part, value)
    g = Game.new(content, name, rng=random.Random(0), world=world)
    g.client = None
    g.state.world.jianfa_on = on
    g._save_season()
    p = g.state.player
    p.faction = faction
    p.stats["silver"] = silver
    g.state.pending_event = "drunk"
    g.rng = rng or random.Random(0)
    return g


def fight(tier: str):
    """事件裡打的那一場照 tier 收（tests/test_engine.py::_forced 的做法）。"""
    return mock.patch.object(team, "fight", return_value=EncounterResult(tier=tier, margin=0, our_power=10, difficulty=5))


def answer(game: Game, text: str, outcome: str | None, rate: int = 50, moral: str | None = None) -> list[str]:
    """三段式的 C 段：B 段（server）歸好類、評好分之後交回來的樣子。"""
    return game.answer_event(game.free_text_request(text), rate, moral, outcome)
