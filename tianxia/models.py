"""內容資料模型：content/ 底下所有 JSON 設定的結構定義。"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, GetCoreSchemaHandler, field_validator, model_serializer, model_validator
from pydantic_core import core_schema

from .jianfa_numbers import ExploreMix, JianfaNumbers

STATS = ("str", "agi", "con", "wis", "lore", "silver", "good", "evil", "fame", "xinde")
ActionKind = Literal["explore", "train", "socialize"]
TravelMode = Literal["walk", "hurry", "dash"]  # 步行／趕路／疾行（地圖擴充設計 3.2）；趕路 2026-10-12 拿掉，只留給拿掉之前出發、還在路上的那一趟
# sanguo-companions 合併：同伴不再分天地玄黃品階，改成「龍頭人物」（劇情鎖定，不可招募，
# 見設計文件四.4）跟「可招募」兩種，決定要不要出現在招募流程裡。
CompanionKind = Literal["locked", "recruitable"]
MartialKind = Literal["內功", "武學"]
Attribute = Literal["陰", "陽", "剛", "柔", "快", "慢", "虛", "實"]  # 見 tianxia/martial_arts.py
WeaponKind = Literal["劍", "刀", "槍", "棍", "弓弩", "拳腳"]  # 兵器種類（兵器設計 2.3）；內功不配兵器
WEAPON_KINDS: tuple[str, ...] = ("劍", "刀", "槍", "棍", "弓弩", "拳腳")
Quality = Literal["下品", "中品", "上品", "絕學"]  # 見 tianxia/martial_arts.py 的 QUALITIES
Lean = Literal["正", "邪", "無"]  # 武學與成長設計 7.3
TRAIT_HOOKS = (  # 一般功效掛在遭遇戰的哪一步（武學與成長設計 13.2）；程式照這幾個實作
    "big_win", "luck_narrow", "difficulty_cut", "toll_cut", "win_reward", "win_heal", "luck_widen", "condition_floor",
    # 意境效果池（武學重構第二批，Joy 2026-10-20「每個意境可能有3-4種效果」）：每一路第二個一般功效，只在回合裡起作用
    "fx_shadow", "fx_heavy", "fx_mend", "fx_steady", "fx_tide", "fx_disarm", "fx_foresight", "fx_wall",
)
SPECIAL_HOOKS = (  # 特別功效的掛點（13.4）：一個掛點只能有一個特別功效（身上的特別功效照掛點記，validate 擋共用）。
    # 這 7 個掛點現在都被初版的 7 個特別功效佔了，所以新的特別功效要嘛換掉掛同一點的那一個、要嘛加新的掛點（要寫程式）
    "double_luck", "no_injury", "no_loss", "win_xinde", "power_from_difficulty", "heal_after", "train_stamina",
)


class _Strict(BaseModel):
    """內容檔的欄位拼錯時直接報錯，而不是被默默忽略。"""
    model_config = ConfigDict(extra="forbid")


def _drop_unset(data: Any, keys: tuple[str, ...]) -> Any:
    """新加的欄位還是預設值（0、空的）時不寫進序列化（減法季批 4：沒有分岔的事件、沒有貢獻的效果，鍵一個都不多）。
    不用 Field(exclude_if=…)：那是 Pydantic 2.11 才有的，requirements.txt 寫 pydantic>=2.6（同 world_state.SealRegistry）。"""
    if isinstance(data, dict):
        for key in keys:
            if key in data and not data[key]:
                del data[key]
    return data


class Condition(_Strict):
    """所有欄位都是「且」的關係（any_of 內部是「或」）；空的欄位不檢查。"""

    min_stats: dict[str, int] = Field(default_factory=dict)
    max_stats: dict[str, int] = Field(default_factory=dict)
    flags_all: list[str] = Field(default_factory=list)
    flags_none: list[str] = Field(default_factory=list)
    sects: list[str] = Field(default_factory=list)
    no_sect: bool = False
    skills_all: list[str] = Field(default_factory=list)
    skills_none: list[str] = Field(default_factory=list)
    trend_min: dict[str, int] = Field(default_factory=dict)
    trend_max: dict[str, int] = Field(default_factory=dict)
    world_flags_all: list[str] = Field(default_factory=list)
    world_flags_none: list[str] = Field(default_factory=list)
    day_min: int | None = None
    day_max: int | None = None
    revealed_all: list[str] = Field(default_factory=list)
    revealed_none: list[str] = Field(default_factory=list)
    flag_age_hours: dict[str, int] = Field(default_factory=dict)  # 世界旗標成立後至少經過幾小時
    members_none: list[str] = Field(default_factory=list)  # 這些人物都還沒入門（結識事件用它排除已入門的人）
    # 地方痕跡（「地點 id:痕跡名」→ 次數，全服共用、每季清空）：至少／至多幾次。數字在載入時乘上
    # Config.mark_threshold_scale（無條件進位，見 content.load_content），所以這裡寫的是「開發期小伺服器」的門檻
    marks_min: dict[str, int] = Field(default_factory=dict)
    marks_max: dict[str, int] = Field(default_factory=dict)
    # ── 伏筆的準備事件、片段事件用（計畫 T7）；預設都是不限 ──
    factions: list[str] = Field(default_factory=list)  # 玩家的陣營在裡面才成立；空的＝不限（散人也行）
    # 玩家的陣營在裡面就不成立（散人一律成立）：替有立場的事件選項分邊用——黃巾的人看不到「打黃巾」那一顆（企劃者 2026-10-08）
    factions_none: list[str] = Field(default_factory=list)
    controlled_by: list[str] = Field(default_factory=list)  # 這裡此刻歸誰控制（territory.controller）在裡面才成立；空的＝不限（出陣探索與地盤設計 4.3 第 4 點）
    # 遊俠名號（ranger.py）：散人、劇本有陣營、名號到這一階才成立（投靠了陣營一律不成立；每季都有）；ranger_path 是「俠」或「寇」（不寫＝不限）
    ranger_min: int | None = None
    ranger_path: Literal["俠", "寇"] | None = None
    # 名聲：名望到這一季的第幾段（renown.fame_tier，照季長倍數；1～4）。要 content 才判得出，沒給、名聲關著一律不成立
    fame_tier: int | None = Field(default=None, ge=1, le=4)
    # 名聲 5.2、5.3：走哪一條路（renown.path）、善惡稱號到第幾段（renown.virtue_tier，照季長倍數）；要 content、名聲開著才成立。
    # 跟 ranger_* 不同：投靠了陣營的人一樣看（俠寇是每個人都有的稱號）
    virtue_path: Literal["俠", "寇"] | None = None
    virtue_min: int | None = Field(default=None, ge=1, le=4)
    # 季曆（calendar）的時刻：第一季開關關著（或這一季開季時沒開）時，寫了這三個的條件一律不成立——beta 季沒有季曆
    night: bool | None = None  # calendar.is_night 要等於它（True＝只在夜裡，False＝只在白天）
    week_min: int | None = None  # calendar.point(...).week 至少／至多第幾週
    week_max: int | None = None
    # 21 天季（Config.season21，正式季整合設計 1.2 給開發 6）照天數另寫：季曆第幾天（從 1 起，calendar.point(...).cal_day）至少／至多；
    # 21 天季只看這兩個、不看週，其他季只看週、不看這兩個（上面的 day_min／day_max 是世界天，給 beta 主線）。寫了週的條件在 21 天季的
    # 內容裡也要寫這兩個（content.validate）
    cal_day_min: int | None = Field(default=None, ge=1)
    cal_day_max: int | None = Field(default=None, ge=1)
    # 7 天濃縮季（Config.season_segments）照天數另寫的那一份（開季那天是第 1 天）：7 天濃縮季只看這兩個；寫了週的條件在 7 天的內容裡也要寫
    cal_day_min7: int | None = Field(default=None, ge=1, le=7)
    cal_day_max7: int | None = Field(default=None, ge=1, le=7)
    clue_items: dict[str, int] = Field(default_factory=dict)  # 伏筆專用物品至少幾個（原數字，不照伺服器規模換算）
    grain_min: int = Field(default=0, ge=0)  # 糧草至少幾份（基準量，照 foreshadow.need 換算；0＝不檢查；正式版丙二的帶糧選項）
    # 戰後事件用：這次行動打的那一場（戰鬥卡片 state.battle_card 指著的那筆）的結果（大勝／險勝／僵持／落敗）在清單裡才成立；
    # 這次行動沒打架（卡片已清掉）一律不成立。文字假設打贏了的戰後事件寫 ["大勝", "險勝"]。載入時只准寫在 actions 剛好是 ["train"] 的事件的條件上
    fight_tiers: list[str] = Field(default_factory=list)
    # 一條線的記號至少到幾（「線 id:記號」→ 數；tianxia/storyline.py）：那條線沒開過算 0。給段落事件的選項分邊用（例：帶了符水才有「倒進井裡」）
    story_marks: dict[str, int] = Field(default_factory=dict)
    story_marks_max: dict[str, int] = Field(default_factory=dict)  # 同上，至多到幾（寫 0 是「沒記過」：例 沒跟蘇掌櫃交心的人才要檢定）
    level_min: int | None = Field(default=None, ge=1)  # 本人等級至少幾級（事件分級，企劃者 2026-10-26）
    any_of: list[Condition] = Field(default_factory=list)  # 非空時，至少一個子條件成立


Condition.model_rebuild()


FRONT_KEY = "front"  # Effect.trend／Location.train_trend 的特殊鍵：效果發生地所在大區的戰線（rules.resolve_trend）


class EventMod(_Strict):
    """一般伏筆（伏筆文件 4.4）：event 那件大事 side 那一方的成功率 +amount；那件大事還沒結算才算，全服合計夾在 ±0.20
    （timetable.add_mod）。只有擲骰的大事（有 roll_side）才有意義，content.validate 擋別的。"""

    event: str
    side: Literal["guan", "huang"]
    amount: float


class StoryStep(_Strict):
    """一條線（特殊事件、特殊頓悟，tianxia/storyline.py）的一步：寫在那一條線某一段事件的選項效果上。
    marks 加進這一條線自己的記號（「醫」「符」「攻」「正」…，只在這條線裡算）；go 是接下來往哪一段（段 id）或哪一個結局（結局 id），
    沒寫就照那一段的 routes／next 走。line 是哪一條線；載入時照段落的事件自動補上（content.load_content），手寫可以省。"""

    line: str = ""
    marks: dict[str, int] = Field(default_factory=dict)
    go: str | None = None
    # 紀念物（長篇奇事，企劃者 2026-10-27）：沒有效果、不能賣，收進 PlayerState.keepsakes 跟著角色跨季；drop 是交出去（例：粟送到了）
    keepsake: str | None = None
    keepsake_drop: str | None = None


class Effect(_Strict):
    text: str = ""
    stats: dict[str, int] = Field(default_factory=dict)
    stamina: int = 0
    flags_add: list[str] = Field(default_factory=list)
    flags_remove: list[str] = Field(default_factory=list)
    learn_skills: list[str] = Field(default_factory=list)
    trend: dict[str, int] = Field(default_factory=dict)
    world_flags_add: list[str] = Field(default_factory=list)
    rumor: str = ""  # 地方傳聞；{name} 會換成玩家名號（匿名時為「某位少俠」）
    chronicle: str = ""  # 寫入江湖史，同樣支援 {name}，但一律寫名號（江湖史不能匿名，傳聞分層設計第七節）
    join_sect: str | None = None
    leave_sect: bool = False
    next_event: str | None = None
    recruit: str | None = None  # 結識某人（同伴 id）：入門；已入門時改給心得（見 roster.recruit）
    materials: dict[str, int] = Field(default_factory=dict)  # 給素材（素材 id -> 數量）；手寫劇情是天品素材的主要來源
    insights: list[str] = Field(default_factory=list)  # 悟得的意境 id（奇遇給的，武學與成長設計 3.2.2）；只能是靠探索悟的基本意境
    # 在地方上留下痕跡（「地點 id:痕跡名」→ 1～3，只能加）：全服共用、每季清空；同一個人對同一個痕跡一天只算一次
    marks: dict[str, int] = Field(default_factory=dict)
    # 伏筆（計畫 T7）的準備事件用；第一季開關關著時兩個都不發生（不給也不寫任何字）
    clue_items: dict[str, int] = Field(default_factory=dict)  # 伏筆專用物品（foreshadows.json 的 items）：正數給、負數收走
    fs_counters: dict[str, int] = Field(default_factory=dict)  # 伏筆的隱藏計數（例：豪強兩頭賣糧的起點 two_buyers）：加多少，不寫字
    # ── 晉升（計畫 T5）：只寫在晉升奇遇的選項上（content.validate 檢查）──
    promote: int | None = None  # 演完晉升到第幾階（清掉召見、接結尾那一句、記進當天的彙整）
    followers: list[str] = Field(default_factory=list)  # 給的部下（followers.json 的模板 id）
    affinity: dict[str, int] = Field(default_factory=dict)  # 人物 id → 情誼增減（夾在 0～100，訊息「皇甫嵩情誼 +10」）
    # ── 第 3、4 階晉升（正式版丙一）：同樣只寫在晉升奇遇的選項上，各自的規則見 content.check_promotions ──
    summons_next: str | None = None  # 寫這一則事件自己的 id：演完這一段，召見往下一段（只有最後一段以前的奇遇可以）
    event_mods: list[EventMod] = Field(default_factory=list)  # 一般伏筆：某件擲骰大事的成功率修正（暗中的，不寫字）
    patron: Literal["yuan", "cao", "self"] | None = None  # 豪強升第 3 階時記下的靠山（PlayerState.patron）
    # ── 黃巾的第 3、4 階奇遇（正式版丙二）；份量與片段數都是基準量／序號，載入時檢查（content.check_effect） ──
    donate_grain: dict[str, int] = Field(default_factory=dict)  # 捐糧：據點 id → 基準量（照 foreshadow.need 換算）；同護糧送到，記捐獻與一次推動的貢獻
    fs_fragments: list[str] = Field(default_factory=list)  # 直接給一則伏筆片段：「鏈 id:片段序號」（0 起）；做得了那條鏈的人才給、聽過的不再給
    runic: int = Field(default=0, ge=0)  # 符文殘片幾片（基準量，PlayerState.runic_pieces；玉璽大勢任務讀它，plan 玉璽碎片-2 用同一個名字）
    # 奇遇給的寶物或良駒（裝備四欄 6.4）：content/gear.json 掉落池的 id，或 GOOD_HORSE（一匹良駒）；名將贈禮與名駒不准
    # （content.check_effect），隨口應對不准（check_free_text），路上見聞只准屬性與素材
    gear: str | None = None
    # 陣營貢獻幾點（減法季整合設計 5.3：痕跡一筆記一筆貢獻；每天上限是接線那一批的事）。現在只准寫在隨口應對分岔的後果上
    # （content.check_outcomes）：rules.apply_effect 不讀它，接線之前寫在別處會靜靜沒作用。0 的時候不寫進序列化
    contribution: int = Field(default=0, ge=0, le=6)
    # 一條線的一步（特殊事件，tianxia/storyline.py）：只准寫在一條線的段落事件上（content.validate）。None 的時候不寫進序列化
    story: StoryStep | None = None

    @model_serializer(mode="wrap")
    def _drop_new_defaults(self, handler):
        return _drop_unset(handler(self), ("contribution", "story"))


class Material(_Strict):
    """素材：一個屬性 × 一個階（見 docs/superpowers/specs/2026-10-01-無限煉製-design.md §三）。
    不再拿去煉製（Task 8），現在是糧草（慢屬性的算糧）與伏筆用的。
    """

    id: str
    name: str
    attribute: Attribute
    tier: int = Field(ge=1, le=4)  # 1 凡品、2 靈品、3 天品、4 神品（神器的料，正式季整合 4.4）
    description: str = ""


class CraftNames(_Strict):
    """合成、合併時模型不可用（或產出的名字過不了過濾）的決定性組名字表，見無限煉製設計 §5.6、武學與成長設計 3.6。

    用配方鍵的雜湊挑 prefix × suffix，所以同一個配方永遠組出同一個名字——離線也能玩，
    而且 `tests/season/test_real_content.py` 整季模擬（LLM 被 mock）走的就是這條路。

    兵器、防具的一般組合不照雜湊挑：字首照主料、中間字照輔料在素材表的位置取（打造隱藏配方設計 4.1、PM 2026-10-12 決定第 1 條），
    所以 prefixes、weapon、armor 的前「素材數」個字不能重複；新素材加在 materials.json 最後，不然後面幾種素材的字會位移。
    """

    prefixes: list[str]
    wugong: list[str]  # 武學的字尾
    neigong: list[str]  # 內功的字尾
    insight: list[str] = Field(default_factory=lambda: ["意", "勢", "韻", "境"])  # 意境的退路字尾（武學與成長設計 3.2）
    # 兵器一般組合的中間字（打造隱藏配方設計 4.1）：照輔料在素材表的位置取；不能放兵器字、不能放「鐵」（「沉鐵劍」會撞架上的名字）
    weapon: list[str] = Field(default_factory=lambda: list("霜霆雷星月嵐濤岳燼鳴影紋芒魄痕翎"))
    # 防具一般組合的中間字（四欄設計 4.7、打造隱藏配方設計 4.1）：字首＋這一個字（照輔料在素材表的位置取）＋防具字（armor.FORGE_NOUNS）。
    # 不能放兵器字、防具字（content.validate 用 armor.word_problem 驗）；前「素材數」個字不能重複（待 joy 潤）
    armor: list[str] = Field(default_factory=lambda: list("鱗錦雲紋羽絮岩霜嵐濤影翎霞綾磐蟬"))


class CombatLines(_Strict):
    """回合演出的句型（武學與成長設計 8.2，content/combat_lines.json）：照出手那門武學的屬性挑一句。
    ours 是我方出手、theirs 是對手出手；bare 給沒學武學的人，theirs_any 給沒有屬性（或那個屬性沒寫句子）的對手。
    句子是接在人名（或「以【武學】」）後面、沒有主詞的動詞片語，只寫怎麼出手（內容表：打發話與回合句型 §二）。"""

    ours: dict[Attribute, list[str]]
    theirs: dict[Attribute, list[str]] = Field(default_factory=dict)
    bare: list[str] = Field(min_length=1)
    theirs_any: list[str] = Field(min_length=1)


class Drop(_Strict):
    """一筆掉落：打贏這支隊伍時有 chance 的機率掉 count 個這種素材。

    敵方隊伍沒寫 drops 時走 materials.py 的預設掉落表（依難度），內容不必每隻都填。
    """

    material: str
    chance: float = Field(default=1.0, ge=0.0, le=1.0)
    count: int = Field(default=1, ge=1)


BEST_OF = "best_of"  # Check.stat 寫它：看 Check.stats 裡最高的那一項（隨口應對分岔的後果用，減法季整合設計 5.9「出力」那一種）


class Check(_Strict):
    stat: str
    difficulty: int
    # 讀得進來、不再有作用（企劃者 2026-10-05「探索應該沒有本人跟夥伴之分了」）：以前 team 派隊伍中這項屬性最高的人、
    # self 只看本人；現在每一個事件檢定都看本人的屬性（rules.check_outlook）。留著這個欄位，舊內容與 joy 寫好的事件照樣載入。
    by: Literal["team", "self"] = "team"
    # 熟練（企劃者 2026-10-05「你常常做壞事，因為很熟練所以也增加成功率」）：寫了 "evil" 時，
    # 本人的檢定值再加上由惡名換算的加成（Config.practice_bonus）。
    practice: str | None = None
    # stat 是 BEST_OF 時取這幾項裡最高的（至少兩項；rules.check_stat_value）；別的 stat 不寫。現在只有分岔的後果用得到
    # （固定選項的 stat 要是一項屬性，content.validate 擋）。空的時候不寫進序列化
    stats: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _best_of_names_its_stats(self) -> Check:
        if self.stat == BEST_OF and len(self.stats) < 2:
            raise ValueError(f"stat 是 {BEST_OF} 時，stats 要寫至少兩項屬性")
        if self.stat != BEST_OF and self.stats:
            raise ValueError(f"stats 只跟 stat「{BEST_OF}」一起寫")
        return self

    # 這一個檢定出自第幾階的事件（事件分級，企劃者 2026-10-26）：載入時照事件的 tier 蓋（content.load_content），內容不寫。
    # 第一階才吃減法季的放寬（Config.jianfa.event_ease，rules.check_outlook）；1 的時候不寫進序列化
    tier: int = Field(default=1, ge=1, le=3)

    @model_serializer(mode="wrap")
    def _drop_new_defaults(self, handler):
        data = _drop_unset(handler(self), ("stats",))
        if isinstance(data, dict) and data.get("tier") == 1:
            del data["tier"]
        return data


class PracticeBonus(_Strict):
    """熟練加成：這項名聲每 per 點，本人的檢定值 +1，最多 +cap（rules.practice_bonus）。"""

    per: int = Field(gt=0)
    cap: int = Field(ge=0)
    line: str = ""  # 吃到加成時併進選項括號裡的那一句（events.choice_label），{who} 換成「你」
    line_explained: str = ""  # 名聲 explain 開著時用這一句（說出是惡名讓你手熟，名聲設計 6.3）；沒寫照舊用 line


class FuseQuality(_Strict):
    """合成品質的機率怎麼跟著這一爐的搭配走（企劃者 2026-10-06：「每個武學搭配不同的意境或是其他的東西都應該要有
    不同的機率吧，這是一整套系統，不要套死固數值」）。fusion.quality_odds 把這一爐的組成加成一個「造化分」，
    從 Config.fuse_quality_odds（普通搭配的平均）往上或往下推：上品每分 +up_per_point、下品每分 −low_per_point，
    中品是剩下的。上品夾在 up_range、下品夾在 low_range，所以沒有必出、也沒有必不出的組合。"""

    up_per_point: float = Field(default=0.5, ge=0)
    low_per_point: float = Field(default=1.0, ge=0)
    up_range: tuple[float, float] = (5, 45)  # 上品最少、最多幾 %
    low_range: tuple[float, float] = (15, 80)  # 下品最少、最多幾 %
    # ── 合成即設計（Joy 2026-10-19「戰力應該更重要」「試試看這樣吧」；/mnt/project-files/plan/合成即設計定案.md 第一節）：
    # fixed 開著時不擲骰，造化分過 mid_from 是中品、過 up_from 是上品，其餘下品——同樣的底、同樣的意境一定合出同一品。
    # 分數的量級（base_quality 下品 −5／上品 12、成數每成 1.5、同屬性 8、合併的意境 6、天時地利 8～10）：
    # 上品的底七成融同屬性合併意境約 29（上品）、中品的底五成融基本意境約 5（中品邊緣）、下品的底一成不相干約 −11（下品）。
    # 絕學照舊只靠修練與契機。near 是說明那一句「再講究些」的門檻：離下一品不到這麼多分才提。測試內容關著（舊測試照機率）。
    fixed: bool = False
    mid_from: float = 6
    up_from: float = 24
    near: float = Field(default=8, ge=0)
    # 底（武學＋武學時是兩門的平均）自己那一份的品質：好的底比較容易合出好品質（回應企劃者「中品的底合出下品，那我幹嘛合成」）
    base_quality: dict[str, float] = Field(
        default_factory=lambda: {"下品": -5, "中品": 5, "上品": 12, "絕學": 20},
    )
    level_center: int = 5  # 底練到第幾成算「普通」
    level_point: float = Field(default=1.5, ge=0)  # 比 level_center 每多（少）一成加（扣）幾分
    # 意境的來歷：內容寫好的基本意境 0；善名惡名悟來的（有正邪）；合併出來的；自己首悟的再加 own
    insight_lean: float = 4
    insight_merged: float = 6
    insight_own: float = 4
    same_attribute: float = 8  # 底與意境（或兩門武學）同屬性
    counter_attribute: float = -10  # 相剋的一對
    wis_weight: float = Field(default=0.5, ge=0)  # 悟性：stat_factor 多出來的百分點 × 這個（跟修練同一套 stat_factor）
    shown_from: float = Field(default=3, ge=0)  # 說明那一句只寫分數絕對值到這麼多的因素，最多兩個
    # ── 天時地利（PM 2026-10-10 派工、企劃者選「甲乙都做」的乙）：同一爐換時間地點，造化分不一樣；規則不寫給玩家看，
    # 只在合成前的說明（lines）與結果（setting_good／setting_bad）留一句含蓄的話。預設全是 0（測試內容不開），正式值在 config.json。
    # 一爐最多算 setting_max 條（照分數的絕對值挑），fusion.setting_points 算。
    terrain: float = 0  # 在探索悟得到同屬性意境的地方融這個意境（跟修練的 home_ground 同一個判斷）
    night_match: float = 0  # 有正邪的那一爐：邪的在夜裡、正的在白天
    night_clash: float = 0  # 反過來：邪的在白天、正的在夜裡（負的）
    battlefield: float = 0  # 合出剛的武學、人在營寨類地點或（第一季）正在亂局的大區
    calm: float = 0  # 出關之後 calm_hours 遊戲小時之內開爐
    calm_hours: float = Field(default=2, ge=0)  # 一個時辰
    setting_max: int = Field(default=2, ge=0)
    setting_good: str = ""  # 天時地利合起來是加分時，結果多一句
    setting_bad: str = ""  # 合起來是扣分時，結果多一句
    # 說明那一句的寫法：因素 → [加分時, 扣分時]（語氣照企劃者「不要那麼直白」，不寫成攻略）
    lines: dict[str, list[str]] = Field(default_factory=lambda: {
        "quality": ["底子厚實", "底子尚淺"],
        "level": ["火候已足", "火候還淺"],
        "insight": ["意境來歷不凡", ""],
        "attribute": ["兩股氣息相投", "兩股氣息相衝"],
        "wis": ["你心思靈透", "你心思還不夠靈透"],
        "terrain": ["此地氣象與這股意相合", ""],
        "night": ["時辰正對", "時辰不對"],
        "battlefield": ["殺伐之氣未散", ""],
        "calm": ["出關未久，心如止水", ""],
    })


class Breakthrough(_Strict):
    """絕學要契機（企劃者 2026-10-07 選 PR #28 方案 C）：上品往絕學不再擲骰。在上品反覆修練只累積火候（Player.art_mastery，
    一次 +1），火候滿 heat、成數也到了，剩下那一步要等契機——拿身上這一門打贏一場不輕鬆的仗（對手難度 ÷ 我方威力 ≥ min_ratio），
    或在全服決戰裡出手滿 showdown_rounds 回合（當成難度比 showdown_ratio 的一仗）。每個契機擲一次頓悟：
    chance ×（難度比 ÷ par_ratio）× 悟性，夾在 1～max_chance。破境丹不等契機：服丹強行衝關（legend_item_bonus × 悟性，
    cultivation.force_odds）。武學重構之後火候（heat）沒有地方讀：絕學那一步只看上品、第十成、槽裝滿（cultivation.ready）。"""

    heat: int = Field(default=8, ge=0)
    chance: float = Field(default=25, ge=0, le=100)
    par_ratio: float = Field(default=0.5, gt=0)
    min_ratio: float = Field(default=0.3, ge=0)
    max_chance: float = Field(default=60, ge=0, le=100)
    showdown_rounds: int = Field(default=3, ge=1)
    showdown_ratio: float = Field(default=1.0, ge=0)


class FrontLines(_Strict):
    """戰況變化的說法（content/front_lines.json，FB-064）。第一季規則開著時，推動戰線的那一行寫成一句話：
    「{戰線}：{陣營}{句子}」，例「潁川汝南：官軍步步進逼」，不寫數字。句子分三段（tianxia/front_lines.py 的 BANDS：
    1、2-3、4+，變動的大小），一段可以寫好幾句，同一則紀錄永遠挑同一句。
    sides：陣營 id → 寫在句子前面的名字（黃巾軍簡稱「黃巾」）；沒寫的陣營用劇本裡的陣營名。
    generic：每一段都要有，兩個陣營共用；by_side：某一方自己的說法（陣營 id → 段 → 句子），可以只寫其中幾段，沒寫的退回 generic。
    geju：豪強割據漲（up）、落（down）的整句話，已經有「豪強」兩字，不再接陣營名、也不冠戰線名。"""

    sides: dict[str, str] = Field(default_factory=dict)
    generic: dict[str, list[str]]
    by_side: dict[str, dict[str, list[str]]] = Field(default_factory=dict)
    geju: dict[str, list[str]]


class VirtueNeed(_Strict):
    """要走哪一條路、善惡稱號到第幾段（名聲設計 5.1、5.3：正邪武學誰肯教、俠寇選項要什麼稱號；renown.meets 判）。"""

    path: Literal["俠", "寇"]
    tier: int = Field(ge=1, le=4)


class Choice(_Strict):
    text: str
    condition: Condition = Field(default_factory=Condition)
    check: Check | None = None
    combat: str | None = None  # 敵方隊伍 id：選了就自動開打
    effect: Effect = Field(default_factory=Effect)  # 檢定成功／戰鬥勝利（或無檢定時）
    fail_effect: Effect = Field(default_factory=Effect)  # 檢定失敗／戰鬥落敗
    # 名聲 5.3：俠才有、寇才有的做法（路與段）。稱號不夠的人看得到、灰掉寫要什麼；名聲的 virtue_choices 關著不出現（Game.options）
    needs: VirtueNeed | None = None


FREE_TEXT_MAX = 20  # 隨口應對最多幾個字（跟決戰的放手一搏一樣）


OutcomeKind = Literal["check", "combat", "cost", "fallback"]


class Outcome(_Strict):
    """隨口應對的一種後果（減法季整合設計 5.1、5.9；主機側計畫 Task 4-1）：模型把玩家寫的那句話歸到其中一種、評一個成功率，
    引擎照這一種的判法走——check 擲骰（成套 effect、敗套 fail_effect）、combat 打這一路（贏套 effect、輸套 fail_effect）、
    cost 掏這麼多銀兩、必成（企劃者 2026-10-24 第 8 件 c；不夠就不做、不扣次數）；三樣都沒寫的是 fallback（只套 effect）。
    effect.stats 的 good 為負的是作惡的那一種（第 8 件 a）。其餘規矩在 content.check_outcomes。"""

    id: str
    tag: str  # 「短名：給模型看的說明」——模型歸類看整句；給玩家看的（欄位表、江湖紀錄、行狀）只用冒號前的短名（outcomes.short_name，FB-800）；永遠不寫數字
    check: Check | None = None
    combat: str | None = None  # 敵方隊伍 id：這則事件固定選項裡打的那一路
    cost: dict[str, int] | None = None  # 只能是 {"silver": 正數}
    effect: Effect = Field(default_factory=Effect)
    fail_effect: Effect = Field(default_factory=Effect)

    @model_validator(mode="after")
    def _one_way(self) -> Outcome:
        ways = [name for name, used in (("check", self.check), ("combat", self.combat), ("cost", self.cost)) if used is not None]
        if len(ways) > 1:
            raise ValueError(f"後果 {self.id} 的判法只能寫一種（check／combat／cost），寫了 {'、'.join(ways)}")
        return self

    @property
    def kind(self) -> OutcomeKind:
        if self.check is not None:
            return "check"
        if self.combat is not None:
            return "combat"
        if self.cost is not None:
            return "cost"
        return "fallback"

    @property
    def evil(self) -> bool:
        """作惡的那一種：效果扣善名（企劃者 2026-10-24 第 8 件 a）。"""
        return self.effect.stats.get("good", 0) < 0


class FreeTextChoice(_Strict):
    """隨口應對（探索的多人與LLM玩法 §8.1）：事件多一個自己寫一句話的選項。LLM 只評估成功率，
    引擎再按 stat 修正、夾在 5%～85% 之後擲骰：成功套 effect，失敗套 fail_effect。
    outcomes（減法季分岔，整合設計 5.1）：寫了的事件在分岔開著的季照後果走（歸類、各自的判法）；最後一種是對不上時的 fallback。
    關著的季照舊用 stat、effect、fail_effect，所以兩組都留著。"""

    prompt: str  # 選單上的標籤，例如「自己想辦法……」
    stat: Literal["str", "agi", "con", "wis", "lore"]
    by: Literal["team", "self"] = "team"  # 跟 Check.by 一樣：讀得進來、不再有作用，隨口應對也只看本人的屬性
    effect: Effect = Field(default_factory=Effect)
    fail_effect: Effect = Field(default_factory=Effect)
    outcomes: list[Outcome] = Field(default_factory=list)  # 空的時候不寫進序列化
    # 只在分岔開著的季才有這一顆（PM 2026-10-25 第 7 件：人拉犁原本沒有隨口應對，關著的季不多一顆鈕）；要寫 outcomes。False 時不寫進序列化
    outcomes_only: bool = False

    @model_serializer(mode="wrap")
    def _drop_new_defaults(self, handler):
        return _drop_unset(handler(self), ("outcomes", "outcomes_only"))


class Event(_Strict):
    id: str
    title: str
    text: str
    # 事件卡的插圖（減法季批 8 圖像版）：20 類場景的類型鍵（content/art.json 的 events；圖檔是 web/img/events/<鍵>.webp）。
    # 沒寫就沒圖、卡片一字不變；伺服器另看圖檔在不在（server.scene_art）
    image: str | None = None
    actions: list[ActionKind] = Field(default_factory=lambda: ["explore"])  # 空清單＝只能由 next_event 串接
    locations: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    weight: float = 1.0
    once: bool = False
    qiyu: bool = False
    fortune: bool = False  # 新立門戶福緣：不會被隨機抽到，由 engine 在交友時觸發（actions 必須是空的）
    condition: Condition = Field(default_factory=Condition)
    choices: list[Choice] = Field(min_length=1)
    free_text: FreeTextChoice | None = None
    # 事件分級（企劃者 2026-10-26，事件分級設計稿）：第幾階（1 是現有的事件；2「州郡大事」、3「天下大事」）與從哪一道門進來
    # （武事看等級、名流看名望、俠義看善名、綠林看惡名、擂主看擂台名次；門檻在 Config.jianfa.tier_doors，tiers.door_open）。
    # 第二、三階一定要寫門；減法季的 event_tiers 關著時第二、三階一則都抽不到。預設值不寫進序列化
    tier: int = Field(default=1, ge=1, le=3)
    door: Literal["武事", "名流", "俠義", "綠林", "擂主"] | None = None

    @model_serializer(mode="wrap")
    def _drop_new_defaults(self, handler):
        data = handler(self)
        if isinstance(data, dict):
            if data.get("tier") == 1:
                del data["tier"]
            if data.get("door") is None:
                data.pop("door", None)
        return data


class StoryPlace(_Strict):
    """一條線的一段在哪裡做得了（任一項符合就算；三樣都空的是哪裡都行）：地點 id、地點的標籤、大區（Location.region）。"""

    locations: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    regions: list[str] = Field(default_factory=list)

    def empty(self) -> bool:
        return not (self.locations or self.tags or self.regions)


class StoryAnswer(_Strict):
    text: str
    marks: dict[str, int] = Field(default_factory=dict)  # 選了這一個，這條線的記號加多少（「攻」「守」「變」「心」「正」「邪」…）


class StoryQuestion(_Strict):
    text: str
    answers: list[StoryAnswer] = Field(min_length=2)


class StoryRoute(_Strict):
    """一段走完往哪裡：when 的每一個記號都至少到那個數才算（空的是一定成立）；照寫的順序第一個成立的。"""

    when: dict[str, int] = Field(default_factory=dict)
    go: str


StoryStageKind = Literal["event", "quiz", "fight", "task"]


class StoryFail(_Strict):
    """fight 段打輸、還能再打時跳的那一張卡（特殊頓悟的心魔，Joy 2026-10-28「心魔挑戰失敗沒有明顯提示」）：title 是卡的標題，
    card 是卡上的話、log 是江湖紀錄那一行、annal 是行狀那一行（{name} 換名號）；card 與 log 的 {days} 換成 retry_days 寫成的「N 天」或「N 個時辰」（storyline.wait_text）。"""

    title: str
    card: str
    log: str = ""
    annal: str = ""
    image: str | None = None


class StoryStage(_Strict):
    """一條線的一段（特殊事件設計稿「一條線」的底座）。四種：
    event 端出一則事件（Event，actions 寫 []），選項的 effect.story 寫記號與往哪裡；
    quiz 一題一題答（questions），每一個答案加記號，答完照 routes／next；
    card 有字時進這一段跳一張卡（kind="stage"，圖是 image）。
    fight 打 squad 這一路，打贏往 win、打輸過了 retry_days 可以再打，輸滿 retries 次往 lose（打完那一下叫這條線種類的 fight 鉤子）；
    task 等一件事做成：until 這個條件成立，或 task 這個名字登記的判斷（storyline.TASKS）回真，往 next。
    where 是這一段在哪裡做得了；days 是期限（這一季的遊戲日，照季長，rules.day_seconds），過了往 late。
    immediate：上一段走完、人剛好站在這一段做得了的地方時直接端出來（不必再按一次）；只有 event 用得到。"""

    id: str
    kind: StoryStageKind = "event"
    event: str | None = None
    questions: list[StoryQuestion] = Field(default_factory=list)
    squad: str | None = None
    retries: int = Field(default=2, ge=1)
    retry_days: float = Field(default=1 / 12, ge=0)  # 一個時辰
    task: str | None = None
    until: Condition | None = None
    where: StoryPlace = Field(default_factory=StoryPlace)
    hint: str = ""  # 「未了之事」那一行寫的這一步要做什麼（例：「去山裡找藥」）
    days: float | None = Field(default=None, gt=0)
    late: str | None = None
    next: str | None = None
    routes: list[StoryRoute] = Field(default_factory=list)
    win: str | None = None
    lose: str | None = None
    immediate: bool = True
    card: str = ""  # 進這一段時跳一張卡（StoryCard kind="stage"）寫的那一句；空的不跳（例：特殊頓悟心魔那一關打之前）
    image: str | None = None  # 那張卡的圖（同 StoryDef.image）；事件段端出事件時場景卡也用它（storyline.stage_art）
    # fight 段的對手是自己的影子（特殊頓悟的心魔）：給了就不讀 squad，難度＝你此刻的全隊威力 × mirror，屬性照你武學的主屬性，名字是 mirror_name
    mirror: float | None = Field(default=None, gt=0)
    mirror_name: str = "心魔"
    # 重複挑戰時削弱：難度的倍數＝max(mirror_floor, mirror − mirror_weaken × 輸過幾次)；
    # mirror_weaken 是 0 就照舊不削（別的 mirror 戰一個字都不變）
    mirror_weaken: float = Field(default=0.0, ge=0)
    mirror_floor: float = Field(default=0.0, ge=0)
    # 長篇奇事的多日段（企劃者 2026-10-27）：進這一段之後要再過幾個遊戲日才按得下去（照季長，rules.day_seconds）；
    # 中間做別的事，時候到了、人在那裡才接下一段（例：營裡的第二天、第三天）。期限 days 從等完那一刻起算
    wait_days: float = Field(default=0, ge=0)
    fail: StoryFail | None = None  # fight 段打輸、還能再打時跳一張卡、記一行紀錄與行狀；沒寫就照舊什麼都不跳


class StoryAfter(_Strict):
    """結局之後的一段餘波（長篇奇事，企劃者 2026-10-27）：收了之後過 days 個遊戲日、人走到 where，跳一張卡、記一則江湖紀錄，一段只一次。
    within 是過了幾天就不再出現（None 是一季都等）；when 是這條線的記號都到了才有（空的是一定有）；keepsake_drop 是這一段收走的紀念物。"""

    days: float = Field(default=0, ge=0)
    within: float | None = Field(default=None, gt=0)
    where: StoryPlace = Field(default_factory=StoryPlace)
    when: dict[str, int] = Field(default_factory=dict)
    title: str = ""
    text: str
    image: str | None = None
    keepsake_drop: str | None = None


class StoryEnding(_Strict):
    """一個結局：一定寫進傳（annals，份量 weight）。failed 是失敗的收法（一樣入傳）。effect 是收在這裡給的東西。"""

    id: str
    title: str
    text: str
    annal: str  # 寫進行狀的那一句（{name} 換成名號）
    image: str | None = None
    effect: Effect = Field(default_factory=Effect)
    failed: bool = False
    weight: int = Field(default=5, ge=1, le=5)
    after: list[StoryAfter] = Field(default_factory=list)  # 餘波（長篇奇事）
    keepsakes: list[str] = Field(default_factory=list)  # 收在這裡給的紀念物（同 StoryStep.keepsake）
    lasting: list[str] = Field(default_factory=list)  # 跨季的旗標（PlayerState.lasting；例：隆中藏書），同時立成這一季的 flags


class StoryStart(_Strict):
    """內容寫的線怎麼開頭：在 where 做得了的地方探索，條件成立，擲中 chance 就開（一季一條線只開一次）。"""

    where: StoryPlace = Field(default_factory=StoryPlace)
    condition: Condition = Field(default_factory=Condition)
    chance: float = Field(default=0.08, ge=0, le=1)


class ChapterSpec(_Strict):
    """章回主線的一回（tianxia/chapters.py）：哪一方、第幾回、什麼時候開、收在哪一件大事、做成了推誰。
    side 是陣營 id（guan、huang、haoqiang）；after 是同一方前面要先做完（或已經收了）的那幾回的線 id；after_beat 是還要等哪一件大事結算了才開。
    beat 是收在哪一件時刻表大事（結算的那一刻沒做完就收成 missed）；做成＝走進最後一段 wait（task「chapter_beat」，等 beat 結算）。
    sway 是做成推哪一方（None：豪強照此刻幫的那一軍；side_marks 的記號先算）；sway_marks 是帶著某個記號的人份量另加（可以是負的，份量最低 0）。"""

    side: str
    no: int = Field(ge=1)
    after: list[str] = Field(default_factory=list)
    after_beat: str | None = None
    beat: str
    sway: Literal["guan", "huang"] | None = None
    sway_marks: dict[str, float] = Field(default_factory=dict)
    side_marks: dict[str, Literal["guan", "huang"]] = Field(default_factory=dict)  # 帶著這個記號就推這一軍（豪強賣給誰；先於 sway）


class StoryDef(_Strict):
    """一條線（content/storylines.json，或程式在跑的時候自己組的，storyline.start）。kind 分開算同時開著幾條
    （Config.jianfa.story_caps：「奇事」兩條、「頓悟」一條），也決定叫哪一組鉤子（storyline.FIGHT_HOOKS、END_HOOKS）。
    unfinished 是季末還沒收的那一句（寫進傳，{name} 換成名號）。"""

    id: str
    title: str
    kind: str = "奇事"
    image: str | None = None
    intro: str = ""
    start: StoryStart | None = None  # None：只有程式開得了（storyline.start）
    stages: list[StoryStage] = Field(min_length=1)
    endings: list[StoryEnding] = Field(min_length=1)
    unfinished: str = "{name}手上的一件事，到季末還沒有了結。"
    chapter: ChapterSpec | None = None  # 章回主線的一回（kind「章回」）；別種線是 None，不寫進序列化（_drop_no_chapter）

    @model_serializer(mode="wrap")
    def _drop_no_chapter(self, handler):
        """chapter 是 None 時不寫這個鍵：存檔裡程式組的線（特殊頓悟）跟加這一欄之前一個位元組都一樣。"""
        data = handler(self)
        if isinstance(data, dict) and data.get("chapter", 0) is None:
            del data["chapter"]
        return data

    def stage(self, stage_id: str) -> StoryStage | None:
        return next((st for st in self.stages if st.id == stage_id), None)

    def ending(self, ending_id: str) -> StoryEnding | None:
        return next((e for e in self.endings if e.id == ending_id), None)


RoadKind = Literal["官道", "路", "山路"]
ROADS: tuple[RoadKind, ...] = ("官道", "路", "山路")  # 路的種類（地圖擴充設計 3.1）；沒標的是一般的「路」


class _ConnectionSpec(_Strict):
    """內容檔裡寫成物件的一條路：{"to": 地點 id, "road": 路的種類}。"""

    to: str
    road: RoadKind = "路"


class Connection(str):
    """一條路（Location.connections 的一筆）：字串本身就是目的地的地點 id，另外帶路的種類 road。

    做成 str 的子類別，是為了讓既有把 connections 當成地點 id 清單用的程式（大地圖、視野、假人、
    內容檢查）一行都不用改；要路的種類讀 .road，要純字串的地點 id 讀 .to。內容檔裡寫成字串（一般路）
    或 {"to": 地點 id, "road": "官道"|"路"|"山路"}（地圖擴充設計 3.1），寫回去也是同一個樣子。
    注意：不支援產生 JSON schema（Location.model_json_schema() 會報錯）；目前沒有任何地方用到。"""

    road: RoadKind

    def __new__(cls, to: str, road: RoadKind = "路") -> Connection:
        obj = super().__new__(cls, to)
        obj.road = road
        return obj

    @property
    def to(self) -> str:
        return str(self)

    def __repr__(self) -> str:
        return f"Connection({self.to!r}, {self.road!r})"

    def __reduce__(self):
        return (type(self), (self.to, self.road))

    @classmethod
    def _parse(cls, value: Any) -> Connection:
        if isinstance(value, Connection):
            return value
        if isinstance(value, str):
            return cls(value)
        if isinstance(value, dict):
            spec = _ConnectionSpec(**value)  # 欄位拼錯、路的種類寫錯時這裡就報錯
            return cls(spec.to, spec.road)
        raise ValueError('連線要寫成地點 id，或 {"to": 地點 id, "road": 路的種類}')

    @staticmethod
    def _dump(value: str) -> str | dict[str, str]:
        road = getattr(value, "road", "路")  # 程式或測試直接塞進清單的一般字串也當一般路
        return str(value) if road == "路" else {"to": str(value), "road": road}

    @classmethod
    def __get_pydantic_core_schema__(cls, source: Any, handler: GetCoreSchemaHandler) -> core_schema.CoreSchema:
        return core_schema.no_info_plain_validator_function(
            cls._parse, serialization=core_schema.plain_serializer_function_ser_schema(cls._dump),
        )


class LocationText(_Strict):
    """地點描寫的一個版本：這個世界旗標成立時改用 text（例：宛城第 3 週起依版本換，計畫 T8）。"""

    world_flag: str
    text: str


class MarkText(_Strict):
    """地點描寫照痕跡多接的一段（減法季整合設計 5.2；marks.describe）：這個地點的痕跡 mark 全服累計到 min，描寫後面接 text。
    同一個痕跡可以寫好幾段（門檻不同）；跟痕跡規則（MarkRule.describe）一起比，挑門檻最高的那一段。min 照 Config.mark_threshold_scale 換算。"""

    mark: str  # 「地點 id:痕跡名」，地點要是寫它的那個地點
    min: int = Field(ge=1)
    text: str


class MarkRule(_Strict):
    """地方痕跡過門檻（減法季整合設計 5.2；主機側計畫 Task 4-3，content/mark_rules.json）：全服累計到 threshold 那一刻
    （marks.fire_due）發一則地方傳聞（不列名字；世界層那一句 PM 2026-10-25 修正輪拿掉，江湖史在季末寫，marks.close_season），有寫 trend 的
    照原本的量推一次線（企劃者 2026-10-24 第 8 件 b：只有「趕走散兵」那一類）；之後地點描寫多接 describe 那一段（marks.describe），〈天下形勢〉照 xingshi 寫一句（marks.xingshi_facts）。只發一次
    （WorldState.marks_fired）。threshold 照 Config.mark_threshold_scale 換算（同條件的 marks_min）。字都待 joy 潤。"""

    mark: str  # 「地點 id:痕跡名」
    threshold: int = Field(default=20, ge=1)  # 【預設】全服累計幾筆過門檻
    describe: str  # 過了門檻之後接在地點描寫後面的一段
    rumor: str  # 過門檻那一刻的地方傳聞
    xingshi: str = ""  # 〈天下形勢〉的一句；空的照 rumor
    chronicle: str = ""  # 江湖史；空的照 rumor
    trend: dict[str, int] = Field(default_factory=dict)  # 過門檻那一刻推的線（front＝這個地點所在大區的戰線）；空的不推


class Location(_Strict):
    id: str
    name: str
    description: str
    desc_when: list[LocationText] = Field(default_factory=list)  # 照順序第一個成立的世界旗標勝出；都不成立時用 description
    connections: list[Connection]  # 相鄰的地點，每一筆是一條路（見 Connection）
    x: int
    y: int
    tags: list[str] = Field(default_factory=list)
    danger: int = Field(default=1, ge=1, le=3)
    important: bool = False
    # 江湖頁站在這裡時場景卡上面的圖（減法季批 8）：web/img/ 底下不含副檔名的路徑（例 places/yingru）；
    # 沒寫就退回所屬大區的 places/<大區 id>（atlas.region_of），沒有大區是 places/world
    image: str | None = None
    enemies: list[str] = Field(default_factory=list)
    train_trend: dict[str, int] = Field(default_factory=dict)  # 遊歷打贏／操練推大勢的量；正負是散人的方向，有陣營目標的人照自己的目標推（Game._train_push）
    materials: list[str] = Field(default_factory=list)  # 路邊採集（兩頭的地點）出什麼屬性的素材：採到的是那些屬性的一階；探索不再撿素材（探索改悟意境，見 insights）
    insights: list[str] = Field(default_factory=list)  # 探索「悟意境」那一支悟得到的意境 id（武學與成長設計附錄 C）
    insight_strong: str | None = None  # 這裡最濃的意境 id（意境提示設計第一節）：要是 insights 裡悟得到的；Config.insight_strong 開著才有作用
    unlock_flag: str | None = None  # 設定後，需該世界旗標成立才能前往
    # 序章（新手引導計畫一）的草廬：只有站在這裡的人看得到、到得了（atlas.is_unlocked）；序章走完離開後誰都回不去。
    # 一份內容最多一個，而且就是 Tutorial.location（content.validate）
    prologue_only: bool = False
    # 照痕跡多接的一段（減法季整合設計 5.2；marks.describe 讀，接線之前沒人讀）：空的時候不寫進序列化
    desc_marks: list[MarkText] = Field(default_factory=list)
    # 減法季探索一顆（整合設計 4.1，批 2）：這一處自己的四欄（事件、遭遇、素材、感悟），寫了就不照標籤對到的那一張表的四欄
    # （explore_one.weights）；算哪一種地點照舊看標籤。沒寫是 None，不寫進序列化
    explore_mix: ExploreMix | None = None

    @model_serializer(mode="wrap")
    def _drop_new_defaults(self, handler):
        return _drop_unset(handler(self), ("desc_marks", "explore_mix"))

    def describe(self, world_flags: set[str]) -> str:
        """此刻的描寫：desc_when 裡第一個旗標成立的那一版，都不成立時是 description。"""
        return next((d.text for d in self.desc_when if d.world_flag in world_flags), self.description)

    def road_to(self, dest: str) -> RoadKind:
        """到相鄰地點 dest 的路的種類；清單裡是一般字串（測試直接塞的）或沒連到 dest 時當一般路。"""
        for conn in self.connections:
            if conn == dest:
                return getattr(conn, "road", "路")
        return "路"


class RoadSight(_Strict):
    """路上見聞的一則（路上設計第五節）：每抵達一站有機會寫進自己的江湖紀錄的一兩句話。純敘事，沒有選項。
    內容在 content/road_sights.json，載入時 content.validate 檢查組合夠不夠、收穫有沒有超標、是不是繁體。"""

    id: str
    text: str  # 一兩句；「聽說……」直接寫在這裡。收穫照慣例自動接在後面（「銀兩 +5」），文字裡不用寫
    roads: list[RoadKind] = Field(default_factory=list)  # 適用的路的種類；空的＝哪種路都可以
    regions: list[str] = Field(default_factory=list)  # 適用的大區（照剛抵達的那一站算）；空的＝哪個大區都可以
    # 小收穫，最多一種，也可以沒有：stats 只能是 silver（≤10）或 xinde（≤5），materials 只能是一階 1 個。
    # 不發全服傳聞（每人每站都可能觸發，發到傳聞板會洗版），Effect.text 也留空。
    effect: Effect = Field(default_factory=Effect)


class LearnRule(_Strict):
    """基礎武學在哪裡學、誰肯教（武學與成長設計附錄 B）：武館與江湖人看名望、收銀兩；
    陣營營地只教投靠了那個陣營的人；門派只教那個門派的弟子；正邪武學（名聲 5.1）看善惡稱號（title）。"""

    at: str  # 地點 id
    fame: int = 0
    silver: int = 0
    faction: str | None = None
    sect: str | None = None
    title: VirtueNeed | None = None  # 名聲 5.1：走這條路、到這一段才肯教；名聲的 lessons 關著時這一門不教（library.lessons_here 不列）


TACTIC_TIMINGS = ("起手", "出招", "乘勢", "心法", "騎戰", "應招")  # 戰法什麼時候發動（tianxia/tactics.py）；應招是兩邊的招都定了之後
TACTIC_KINDS = (  # 本命戰法做什麼：一個戰法一種，程式照它找做法（tactics.KINDS）；數字在 TacticDef.params
    "chase_disarm", "opening_ward", "disarm", "rally", "heavy_blow", "cleanse", "roar", "unbroken", "vanguard", "tiger",
    "awe", "waver", "rebound_guard", "veil", "thunder", "curse", "sand", "fog", "bloodrage", "oath", "butcher", "marshal",
    "fire", "steady", "surge", "tide", "foresight", "ward_all", "cavalry", "brutal", "night_raid", "reinforce", "divine",
    "sacrifice", "hold_city", "gatekeep",
    # 第三批（玩家自己的武學功效、神器與名將本命兵器的特技，定案 /mnt/project-files/plan/武學與兵器戰法定案.md）
    "shadow", "mist", "drain", "mend", "borrow", "break", "momentum", "insight", "immune", "last_stand", "assault", "pierce",
    "quake", "first_shot", "zhaoyi", "flawless",
    # 玩家武學追上本命（定案 /mnt/project-files/plan/玩家武學追上本命定案.md）：自己合成的武學練成絕學時的絕招（一般功效的 ultimate）
    "swift", "shatter", "streak", "leech", "haze", "last_rally",
    # 武學技能分檔（Joy 2026-10-17）：合成擲得到的高階技能（content/traits.json 的 high）
    "flash", "bulwark", "scorch", "elude", "golden",
)


class TacticDef(_Strict):
    """本命戰法（tianxia/tactics.py；企劃者 2026-10-15 認可的定案 /mnt/project-files/plan/本命戰法定案.md）：一門本命武學一個，
    那位人物獨有、合成擲不到。在一般的仗（遊歷、出陣、探索野怪、劇情戰、挑戰本人）的回合裡發動，讓對手陷入某種狀態或改這一回合的氣勢；
    身上練著的與同伴練著的都會發動（連招）。

    - timing：起手（開打前 rounds 回合，每回合擲 rate）、出招（每回合擲 rate；prep 1 是要先蓄力一回合）、乘勢（你的招剋中對手之後才擲）、
      心法（條件成立就一直在；rounds 寫了只在前幾回合）、騎戰（騎著馬才有）。
    - kind：做什麼（tactics.KINDS），params 是它的數字（鍵以 _pct 結尾的是比例，卡上寫成百分比）；desc 是卡上那一句，{鍵} 換成數字。
    - allies：仁義聚眾那一種讓哪幾位人物的戰法更常發動（人物 id）；foe_faction：火攻那一種對哪個陣營加倍。"""

    name: str
    timing: Literal[TACTIC_TIMINGS]
    kind: Literal[TACTIC_KINDS]
    desc: str
    rate: float = Field(default=1.0, ge=0, le=1)
    rounds: int = Field(default=0, ge=0)  # 起手、心法只在前幾回合；0＝每回合
    prep: int = Field(default=0, ge=0, le=1)
    params: dict[str, float] = Field(default_factory=dict)
    allies: list[str] = Field(default_factory=list)
    foe_faction: str | None = None
    # 發動時那一句（名字後面接的話）；{foe} 換成對手、{鍵} 換成 params 的數字。空的照 tactics.KINDS 那一種自己的句子
    say: str = ""
    # 本命底蘊（玩家武學追上本命，Joy 2026-10-15「本命還是強一點點」）：本人身上練著這一門時，擂台、奪璽單挑（玩家對玩家，Bout.pvp）每一回合推力多這麼多
    # （跟發動率無關、一直在；一般的仗、頭目戰、決戰、同伴練的、大勢人物本人當對手時都不算）。每一位照擂台量表對滿配絕學的贏面各調，內外兩門各一半
    might: float = Field(default=0.0, ge=0, le=3)
    # 小戰法（Joy 2026-10-21 決策卡「小戰法」：學來的武學要有特色、不然沒有學的必要）：寫在各地教的、事件給的下品內容武學上，
    # 跟本命戰法同一套做法、數字約本命的五到六成；不算本命（不乘本命的威力、不從第七成起、熔得掉、卡上寫「小戰法」，signature.of 不認）
    minor: bool = False


class TacticBond(_Strict):
    """人器合一（名將本命兵器，第三批）：身上也練著那位名將的本命武學或內功時，他那一門戰法改強：發動率、蓄力、回合各加多少，
    params 各加多少（沒有的鍵當 0 加上去）。desc 是卡上那一句。
    tactic：加強的是那位名將的哪一門戰法（名字，卡上寫的那一門；PM 2026-10-16：以前兩門都加，袁紹的回合 +1 把名門心法的「一直在」
    變成只有第 1 回合）。名將本命兵器一定要寫（content 驗）；以器配招（GeneralTrait.ultimate_bond）、名器同氣不寫，加的就是那一門絕招。"""

    desc: str
    tactic: str = ""
    rate: float = 0.0
    prep: int = 0
    rounds: int = 0
    params: dict[str, float] = Field(default_factory=dict)


class TraitTactic(_Strict):
    """一般功效在回合裡的樣子（第三批）：timing、kind 同 TacticDef；rate 與 params 的值可以寫 "value"／"extra"，
    換成這一門（或身上兩門）照層數算出來的數字（GeneralTrait 的 per_layer／cap 與 extra_per_layer／extra_cap）。"""

    timing: Literal[TACTIC_TIMINGS]
    kind: Literal[TACTIC_KINDS]
    say: str = ""
    rate: float | Literal["value", "extra"] = 1.0
    rounds: int = Field(default=0, ge=0)
    params: dict[str, float | Literal["value", "extra"]] = Field(default_factory=dict)


class SkillDef(_Strict):
    """內容手寫的武學/內功：本命武學（歷史人物的固定武學，品質是絕學，見 martial_arts.historical_art）、
    部下用的通用武學（企劃者 2026-10-05 定上品，計畫 T5）與基礎武學（下品，開局送或在各地學，
    武學與成長設計附錄 B）。合成出來的武學不進這份內容檔，存在全服（world.get_skill）。
    """

    id: str
    name: str
    kind: MartialKind
    attribute: Attribute
    desc: str = ""
    quality: Quality = "絕學"
    learn: LearnRule | None = None  # 在各地學得到的基礎武學才填；開局送的看 Config.starter_skills
    special: str | None = None  # 名將本命絕學的獨特特別功效（content/traits.json 裡 pool 是 false 的那一個，13.5）
    weapon: WeaponKind | None = None  # 這門武學配哪一種兵器（兵器設計 2.3）；內功是 None。正式內容的武學一律要填（test_weapons 鎖住）
    # 本命武學（企劃者 2026-10-15）：一般功效（屬性的清單，第一個是自己的屬性，最多 3 個，同 MartialArt.traits）與人物專屬的本命戰法
    traits: list[Attribute] = Field(default_factory=list, max_length=3)
    tactic: TacticDef | None = None
    # 名聲 5.1：正邪（正派吃善名、邪派吃惡名，team.resonance）。只有新的四門正邪武學寫；現有的不加，免得手上那一門威力季中途變了
    lean: Literal["正", "邪", "無"] = "無"
    # 基礎武學的相容屬性（武學重構，Joy 2026-10-20）：意境槽只收這幾種屬性的意境；沒寫＝兼容並蓄（什麼都收）。
    # 追風步寫快與快的複合（陽、虛）：「只能塞風跟快的意境」
    affinity: list[Attribute] = Field(default_factory=list)


class GeneralTrait(_Strict):
    """一般功效（content/traits.json，13.2）：一個屬性一個。每層 per_layer、疊加到 cap 為止；desc 的 {value} 換成數字。"""

    attribute: Attribute
    name: str
    hook: Literal[TRAIT_HOOKS]
    # 意境效果池（第二批）：一路有兩個一般功效，第一個（id 空著）的鍵就是屬性（舊存檔、內容武學的 traits 照舊寫屬性），
    # 第二個寫 id。意境身上記的、武學 traits 清單裡的都是這個鍵（key）
    id: str = ""
    per_layer: float = Field(ge=0)
    cap: float = Field(ge=0)
    desc: str
    # 第三批：回合裡的戰法（tactics.py）；desc 的 {extra} 換成 extra_per_layer × 層數（夾在 extra_cap）。沒寫是只改單次判定或氣血的那幾個（厚）
    extra_per_layer: float = Field(default=0.0, ge=0)
    extra_cap: float = Field(default=0.0, ge=0)
    tactic: TraitTactic | None = None
    # 絕學立招（玩家武學追上本命）：自己合成的武學練成絕學時，那一門層數最多的功效升成這一招（名字換成那門絕學的名字）；
    # bond 是神器原品「以器配招」綁了那一門時加強多少（發動率或回合，照招挑一種）
    ultimate: TacticDef | None = None
    ultimate_bond: TacticBond | None = None

    @property
    def key(self) -> str:
        return self.id or self.attribute


class SpecialTrait(_Strict):
    """特別功效（13.4、13.5）：不分品質、強度固定（amount）。pool 是 false 的只屬於一門內容武學（名將本命絕學），
    合成擲不到。"""

    id: str
    name: str
    hook: Literal[SPECIAL_HOOKS]
    amount: float = Field(ge=0)
    pool: bool = True
    desc: str
    tactic: TacticDef | None = None  # 第三批：回合裡的戰法（強度固定，不分品質）


class HighTrait(_Strict):
    """高階技能（武學技能分檔，Joy 2026-10-17；草案 https://claude.ai/artifact/3rLJgnmA7m8BiEsXGcBDUX）：一個屬性一個，照武學的主屬性給；
    不同意境合出來的意境裝進槽就是這一招（arts.apply），一門最多一個。強度固定、不分品質，約本命戰法的六成，對電腦對手也有效。"""

    id: str
    attribute: Attribute
    name: str
    desc: str
    tactic: TacticDef


GodForm = Literal["攻", "守", "變", "心"]
GOD_FORMS: tuple[GodForm, ...] = ("攻", "守", "變", "心")


class GodTrait(_Strict):
    """神品意境的模板（特殊頓悟，Joy 2026-10-26；設計稿 https://claude.ai/artifact/EBUqqzK3dPMpjwYTdRzLs3）：十路（八種屬性，
    加上正〔陽〕、邪〔陰〕）× 四型（攻守變心）。效果與數字寫死、先量好平衡；玩家頓悟時引擎照這一次的路與型挑一個，名字由模型取
    （name 只是內容裡的代稱）。裝進槽跟大獎走同一條路（InsightFx.grand 記模板 id），另帶 general 那個一般功效三重。"""

    id: str
    attribute: Attribute
    lean: Lean = "無"  # 正路是陽＋正、邪路是陰＋邪，其餘無
    form: GodForm
    name: str
    general: str  # 帶的一般功效（GeneralTrait.key，要是同一個屬性的），三重
    desc: str
    tactic: TacticDef


class TraitBook(_Strict):
    general: list[GeneralTrait] = Field(default_factory=list)
    special: list[SpecialTrait] = Field(default_factory=list)
    high: list[HighTrait] = Field(default_factory=list)
    god: list[GodTrait] = Field(default_factory=list)  # 神品意境模板（特殊頓悟）


class InsightGrant(_Strict):
    """靠名聲悟得的意境（浩然、血煞，設計 7.2）：這項名聲第一次到門檻就悟得。"""

    stat: Literal["good", "evil"]
    at: int


class InsightDef(_Strict):
    """內容手寫的意境（武學與成長設計附錄 A）：四個基本意境靠探索悟得；浩然、血煞靠名聲。
    合併出來的意境不在這裡，存在全服（world.get_insight）。"""

    id: str
    name: str
    attribute: Attribute
    lean: Lean = "無"
    desc: str = ""
    grant: InsightGrant | None = None
    strong_line: str = ""  # 在它最濃的地方悟到它時多的那一句（意境提示設計第二節；句子由我們寫）


SenseAttribute = Literal["剛", "柔", "快", "慢"]  # 有所感的做法、畫出來的那一筆只分這四種（基本意境的屬性）


class SenseMethod(_Strict):
    """有所感那張卡上的一個做法（悟意境設計 3.1）：做這件事是在體會哪一種屬性。"""

    attribute: SenseAttribute
    text: str  # 選項上那一行（例：「順著水流走一段，看它怎麼繞開石頭」）


class InsightScene(_Strict):
    """有所感的一段場景（悟意境設計第零節、3.1；content/insight_scenes.json）。探索落在「悟意境」那一支時，
    照地點挑一段：寫了 locations 的先用（那幾處專用）；沒有就用 tags 跟地點標籤有交集的；再沒有才用 tags、locations 都空的通用場景。
    選的做法屬性在這個地點悟得到的意境裡（insights.explore_gives）才算選對（第四節）。"""

    id: str
    title: str  # 卡片的標題（例：「水繞石」）；卡上寫成「有所感・{title}」
    text: str  # 場景；可以寫 {痕跡}，換成在這一處悟成過的模糊人數（「還沒有人」「幾個人」…，悟意境設計第五節）
    tags: list[str] = Field(default_factory=list)  # 適用的地點標籤（河畔、山林…）；跟地點的 tags 有交集就算
    locations: list[str] = Field(default_factory=list)  # 指定的地點 id；寫了就是那幾處專用，優先於 tags
    # 場景的線索指向哪幾種屬性（劇情寫的時候自己標）：用得到這段場景的每一個地點，悟得到的意境裡至少要有一個是這幾種之一
    # （content.validate 擋「河邊的場景用在只悟得到火的地方」）。通用場景可以不寫
    hints: list[SenseAttribute] = Field(default_factory=list)
    methods: list[SenseMethod]  # 三到四個做法，屬性各不相同；卡上的順序每次洗牌
    flags_add: list[str] = Field(default_factory=list)  # 悟成時加的旗標（序章草廬那一段用，例「序章:悟」）
    prologue: bool = False  # 序章草廬用：只在 TutorialStep.explore_scene 指到時出現，做法都算對、必中，畫完落回做法那個意境


class Sect(_Strict):
    id: str
    name: str
    location: str
    alignment: Literal["正", "邪", "中"]
    desc: str = ""


class CharacterDef(_Strict):
    """人物（同伴或敵人）。stats 是第 1 級的屬性，growth 是每升一級增加的量，仍給 Check
    系統（辦事/修行類事件選項的屬性判定）使用，跟遭遇/劇情戰的判定（encounter.py）無關。"""

    id: str
    name: str
    background: str = ""  # 出身
    situation: str = ""  # 此時處境
    personality: str = ""  # 性格基礎模板，companion_agent.py 的 system prompt 錨點
    kind: CompanionKind | None = None  # 同伴才填：locked（龍頭人物，不可招募）／recruitable；敵人不填
    stats: dict[str, float]
    growth: dict[str, float] = Field(default_factory=dict)
    sect: str | None = None
    desc: str = ""
    # 起始武學與內功：品質是絕學的才是本命（tactics.figure_arts）；歷史武將同行補的是各地教的內容武學，不是本命（FB-640）
    starting_wugong: str | None = None  # 起始武學 id（指向 SkillDef，kind 必須是「武學」）
    starting_neigong: str | None = None  # 起始內功 id（指向 SkillDef，kind 必須是「內功」）
    deep_interaction: bool = False  # 是否走 companion_agent.py 的即時 LLM 對話（見設計文件四.3）
    recruit_at: str | None = None  # 可招募的同伴在哪個地點找得到他（龍頭人物不填，用 talk_at）
    talk_at: str | None = None  # kind=locked 的龍頭人物在哪個地點可以深度對話（不可招募，見上一輪「還要改進」5）
    image: str | None = None  # 跟他談話時場景卡上面的人物像（減法季批 8）：web/img/ 底下不含副檔名的路徑（例 figures/luzhi）；沒寫就沒圖
    affinity_tag_deltas: dict[str, int] | None = None  # 覆寫 companion_agent.AFFINITY_TAG_DELTAS 的個別項目；None／缺的 tag 用預設值
    audience_fame: int = 0  # 求見門檻：名望要到多少才見得到他（透過他的「結識」劇情事件認識的人不受限制）
    brush_off: list[str] = Field(default_factory=list)  # 名望不夠時打發人的話（他自己的口吻，最多三句，武學與成長設計 9.1）
    # 名聲 5.2：對哪一種人有看法（敬俠：俠見面情誼起步、遇上寇冷淡；喜狠：寇見面情誼起步）；None 是不偏。對話提示也帶一行
    regard: Literal["敬俠", "喜狠"] | None = None
    # 人物活起來（FigureLifeTuning）：他常在的幾個地點（第一個是 talk_at／recruit_at，每日行事在這幾處之間走）；空的就站著不動。
    # follows：跟著誰走（關羽、張飛跟著劉備）；side：站哪一方（陣營 id；大勢人物照人物表的 faction，這一欄是給其他人物的，風聞照它找盟友仇敵）
    haunts: list[str] = Field(default_factory=list)
    follows: str | None = None
    side: str | None = None
    # 歷史武將同行（Config.companions）：開關開著時招得進名下（kind 照舊 locked：深度對話、走動、贈禮、本命都不變）。十六位大勢人物
    # 不准標（content.validate）；寫了 side 的只有投靠了那個陣營的人招得到，沒寫的誰都招得到
    recruitable: bool = False


class PlanContest(_Strict):
    """行程裡的一站是「盤算」（tianxia/plans.py）：提前公告，side 那一方的人可以助他一臂、交戰的另一方可以壞他的事（散人兩樣都行、
    豪強照此刻幫的那一軍），到點照兩邊各幾人擲骰。trends 的正數是往黃巾推（同時刻表）。"""

    side: str  # 想讓這件事成的那一方（陣營 id）
    announce: str  # 公告：「{name}打算…」（{name} 換成人物名、{place} 換成地點名）
    win: str  # 成了的天下大事
    lose: str  # 不成的天下大事
    base: float = Field(default=0.6, ge=0, le=1)  # 沒人插手時成的機會
    trends_win: dict[str, int] = Field(default_factory=dict)
    trends_lose: dict[str, int] = Field(default_factory=dict)
    flag_win: str | None = None  # 成了立的世界旗標
    lose_place: str | None = None  # 不成時他退到哪（沒寫就留在原地）


class ItineraryStop(_Strict):
    """行程的一站（content/itineraries.json）。day 照 7 天季寫（1.0 是第 1 天 00:00、2.5 是第 2 天 12:00），別的季長照比例。
    沒有 contest 的一站到時間就做：人走到 place、發一則天下大事 text。if_won／if_lost 列的站（可以是別人的）辦成了、沒辦成，這一站才有。"""

    id: str
    day: float = Field(ge=1, le=8)
    place: str
    text: str = ""  # 一般的一站：天下大事（{name}、{place} 照換）；盤算照 contest 的字
    contest: PlanContest | None = None
    if_won: list[str] = Field(default_factory=list)
    if_lost: list[str] = Field(default_factory=list)


class Itinerary(_Strict):
    """一位人物這一季的行程（content/itineraries.json）：照史書排的幾站。有行程的人不再在常去的地方之間隨機晃（figure_life._act）。"""

    who: str  # 對話人物 id（characters.json）
    stops: list[ItineraryStop]


class RelationDef(_Strict):
    """人物之間的一條關係（content/relations.json；大勢人物擴充第二批）。kind：brother 兄弟、mentor 師生、chief 上下（head 是師長、上司，
    members 是學生、部屬）、foe 仇敵（members 兩兩為敵；寫了 faction 的是 members 跟那一方的每一位為敵，例：唐周與黃巾）。
    兄弟、師生、上下都算盟友：一位倒下，盟友悲憤、往那一區趕、掛一張復仇懸賞；仇敵得意（figure_life.on_fall）。"""

    kind: Literal["brother", "mentor", "chief", "foe"]
    members: list[str]
    head: str | None = None
    faction: str | None = None


class Squad(_Strict):
    """遭遇/劇情戰的對手：一個抽象的難度值＋屬性，不是完整的人物陣容（見 encounter.py 的單次判定）。"""

    id: str
    name: str
    difficulty: float
    attribute: Attribute | None = None
    reward_silver: int = 0
    reward_xinde: int = 0
    exp: int = 0
    drops: list[Drop] = Field(default_factory=list)  # 留空則走 materials.py 依難度的預設掉落表
    faction: str | None = None  # 這支隊伍屬於哪個陣營（Scenario.factions 的 id）；自己陣營的人遇到時改成操練、不開打
    desc: str = ""  # 一句描述（運糧隊這類有特別來歷的對手才寫；遇上時接在戰鬥那一行後面，濃縮版內容表 3.3）
    boss: bool = False  # 頭目：遊歷、劇情戰遇上它算大場面，先請模型判讀（武學與成長設計 8.3）


class Trend(_Strict):
    id: str
    name: str
    desc: str = ""
    start: int = Field(default=0, ge=0, le=100)
    hidden: bool = False
    # 衍生線（第一季濃縮版的黃巾聲勢）：來源線 id → 權重，加起來是 1。開關（Config.season_one）開著時它的值一律是
    # 來源線的加權和（rules.recompute_trends），不能直接推；開關關著時它是一般的線，照 start 起算
    derived: dict[str, float] = Field(default_factory=dict)
    season_one: bool = False  # 第一季濃縮版才有的線（三條戰線、豪強割據）：開關關著時不顯示、不推（rules.trend_shown）


class Threshold(_Strict):
    id: str
    trend: str
    op: Literal[">=", "<="]
    value: int
    text: str
    world_flags_add: list[str] = Field(default_factory=list)
    ends_season: bool = False
    starts_battle: str | None = None  # 指向 Content.battles 的 id：觸發時開一場全服即時戰鬥，不是立刻套用效果
    location: str | None = None  # 發生地：傳聞記在這裡，大地圖劇情層標 ✦；None＝不在特定地點


class SimRumor(_Strict):
    """虛擬玩家的一則傳聞，連同它發生的地點（傳聞裡寫明了在哪裡時用）。"""

    text: str
    location: str


class SimPlayer(_Strict):
    name: str
    actions_per_day: float
    trend: dict[str, int] = Field(default_factory=dict)
    requires_revealed: str | None = None  # 這條隱藏線浮現之前不會行動
    # 傳聞：寫成字串的記在第一個常出沒處；寫成 {"text", "location"} 的記在它寫的地點
    rumors: list[str | SimRumor] = Field(default_factory=list)
    rumor_chance: float = 0.3
    condition: Condition = Field(default_factory=Condition)
    haunts: list[str] = Field(default_factory=list)  # 常出沒的地點（固定不動）


StanceSide = Literal["guan", "huang", "haoqiang"]  # 三方態勢（rules.stances，第一季設計 4.4）


class Ending(_Strict):
    id: str
    title: str
    text: str  # 結局的一句；第一季接在季末公告的開頭後面（時刻表結算第 12 週）
    storyline: str | None = None  # 只在這條主線下成立；None＝任何主線
    hint: str = ""  # 顯示在任務區塊：怎麼達成這個結局
    hint_season21: str = ""  # 21 天季（不提前收季，正式季整合設計 1.1）換掉 hint 的那一句；沒寫照 hint（guide.ending_hint）
    condition: Condition = Field(default_factory=Condition)
    # ── 第一季濃縮版（計畫 T9）：只在 rules.season_one 成立時算；beta 季只看沒標的那幾筆。同一季清單的最後一筆是保底 ──
    season_one: bool = False
    stance_min: dict[StanceSide, int] = Field(default_factory=dict)  # 態勢至少（決定性勝利：季中一到就收季）
    stance_max: dict[StanceSide, int] = Field(default_factory=dict)  # 態勢至多（同上）
    stance_top: StanceSide | None = None  # 季末比態勢：這一方最高（平手時照清單順序，排前面的先成立）
    mandate: bool = False  # 天命結局（玉璽二）：只在天命之爭有一方得天命時由 world.evaluate_ending 照時刻表的 mandate_endings 挑，不進一般的清單與保底
    # 三陣營四勝利（減法季整合設計 3.1、3.3；wins.winner_of／settle）：這個結局是哪一軍贏；None 是和局（豪強的兩種結局）或 beta 的結局
    winner: Literal["guan", "huang"] | None = None


class MapLabel(_Strict):
    text: str
    x: int
    y: int


HEX_COLOR = r"^#[0-9A-Fa-f]{6}$"


class MapRegion(_Strict):
    """地圖上的一塊大區（例如江北、金陵一帶），以多邊形著色；地點依座標落在哪一區自動歸屬（見 atlas.region_of）。"""

    id: str
    name: str
    trends: list[str] = Field(default_factory=list)  # 對應的大勢線：大地圖局勢層依它上色
    front: str | None = None  # 這一區的戰況算在哪條戰線（第一季濃縮版）；洛陽這類沒有戰況的大區是 None
    points: list[list[int]]
    fill: str = Field(pattern=HEX_COLOR)
    text_fill: str = Field(pattern=HEX_COLOR)
    label_x: int
    label_y: int


class MapRiver(_Strict):
    """一條河（輿圖美術設計第四節）：points 從上游寫到下游，畫的時候照這個方向由 width[0] 漸寬到 width[1]。
    舊格式（每條河只是一串 [x, y] 點）照樣讀，當成藍色、寬 4→8（見 MapLayout._legacy_rivers）。"""

    name: str = ""  # 只給寫內容的人看；河名照舊寫在 MapLayout.labels
    points: list[list[int]]
    width: tuple[float, float] = (4, 8)  # 上游寬、下游寬
    color: Literal["blue", "yellow"] = "blue"  # yellow 只給黃河


TerrainKind = Literal["mountains", "hills", "forest"]  # 山脈、丘陵、林地


class Terrain(_Strict):
    """輿圖上的一片地形（輿圖美術設計第四節，純裝飾：不改路程也不改視野）。山脈、丘陵沿 spine（山腳線）排山頭，
    size 是山頭高度；林地在 points 圍成的多邊形裡排樹叢。山頭與樹自己讓開地點、路與河（mapart.terrain）。"""

    kind: TerrainKind
    name: str = ""  # 選填：畫成淡綠小字
    spine: list[list[int]] = Field(default_factory=list)  # 山脈、丘陵用
    size: int = 0  # 山脈、丘陵用，8～40
    points: list[list[int]] = Field(default_factory=list)  # 林地用


class MapLayout(_Strict):
    width: int = 680
    height: int = 420
    background: str = Field(default="#E9E2CC", pattern=HEX_COLOR)  # 紙色（輿圖美術設計 2.1）
    unheld: str = Field(default="#D2CBBC", pattern=HEX_COLOR)  # 天下圖上沒人佔的地面（輿圖簡化設計 3.3：顏色跟著劇本、不寫死）
    regions: list[MapRegion] = Field(default_factory=list)
    rivers: list[MapRiver] = Field(default_factory=list)
    terrain: list[Terrain] = Field(default_factory=list)
    compass: tuple[int, int] | None = None  # 指北針的位置；不寫就不畫
    labels: list[MapLabel] = Field(default_factory=list)
    mini_window: tuple[int, int] = (270, 180)  # 小地圖以所在地為中心截多寬、多高（地圖單位）；地圖畫得越疏，要截得越大才看得到一兩站路

    @field_validator("rivers", mode="before")
    @classmethod
    def _legacy_rivers(cls, rivers: Any) -> Any:
        """舊格式的河是一串 [x, y] 點（純陣列）：包成 {"points": ...}，其餘照預設（藍色、寬 4→8）。"""
        if isinstance(rivers, list):
            return [{"points": river} if isinstance(river, list) else river for river in rivers]
        return rivers


class WorldEvent(_Strict):
    """以任意條件觸發、只觸發一次的世界事件。"""

    id: str
    condition: Condition
    text: str
    world_flags_add: list[str] = Field(default_factory=list)
    ends_season: bool = False
    starts_battle: str | None = None  # 同 Threshold.starts_battle
    location: str | None = None  # 發生地，同 Threshold.location


class Act(_Strict):
    id: str
    title: str
    text: str
    goal: str
    advance_when: Condition | None = None  # 最後一幕為 None
    places: list[str] = Field(default_factory=list)  # 這一幕的目標地點：大地圖劇情層標 ★


class Storyline(_Strict):
    id: str
    name: str
    intro: str = ""
    acts: list[Act] = Field(min_length=1)
    replaces_when: Condition | None = None  # 支線主線：條件成立時取代主線


class Milestone(_Strict):
    id: str
    text: str
    condition: Condition


class TutorialGoal(_Strict):
    """每一項都要符合才算完成；空的（或 False 的）欄位不檢查。"""

    # order：替軍令記到一次（計畫 T6）。choice～melt：序章（新手引導計畫一）那幾步要的動作：選了事件的選項、打開修練／煉製頁、
    # 修練、打坐、遊歷、配點、熔煉
    action: Literal[
        "explore", "socialize", "move", "view_map", "recruit", "practice", "order",
        "choice", "view_tab", "cultivate", "rest", "train", "allocate", "melt", "sense",
        "view_orders",  # 入伍段（新手引導計畫二）：軍令卡出現在畫面上
        "heal", "shop",  # 初入江湖（新手引導第四段）：醫館療傷；進一間店（鐵匠鋪、懸賞榜、馬市、擂台）
        # 新手引導重做（2026-10-22）：城裡操練、城外練功打贏、服回體丹、出店（進了店再出來）、改練（換上功法庫的一門）
        "drill", "field_win", "pill", "leave_shop", "switch",
    ] | None = None
    # 這幾個行動任一個都算（action 是 None 時才看）：例 序章「比一比，換上或熔掉」寫 ["melt", "switch"]；
    # 「leave_town」只在這裡用：走到城外的地點（Game 抵達時記），初入江湖逛鋪子那一步寫 ["leave_shop", "leave_town"]
    any_action: list[str] = Field(default_factory=list)
    wild: bool = False  # 這一下要在城外（不是城鎮的地點）做：初入江湖「在野外探索」
    locations: list[str] = Field(default_factory=list)
    condition: Condition = Field(default_factory=Condition)
    # 初入江湖（新手引導第四段）：身上沒有內傷，或這一下就是療傷（銀兩不夠全治時治一部分也算，不卡住）
    healthy: bool = False
    has_wugong: bool = False  # 身上要有一門武學才算（沒有武學威力是 0，出城只有挨打的份）
    # 序章（武學重構）：有一門裝了意境的武學（fused）、它至少第幾成（fused_level）；有一個意境揣摩到二重以上（deepened）
    fused: bool = False
    fused_level: int = 0
    deepened: bool = False


# 序章每一步 reveal 可以寫的畫面元件（網頁照它藏／亮，見 web/app.js 的 pro()）；content.validate 擋拼錯的
REVEAL_KEYS = frozenset({
    "all",  # 全部亮齊（出師那一步）
    "stamina", "hp", "silver", "xinde", "stats",  # 狀態列：體力、氣血、銀兩、心得、點名號展開屬性與配點
    "tab:jianghu", "tab:practice", "tab:craft", "tab:map", "tab:news",  # 底下的分頁
    "tab:mall",  # 商城的兩個入口（底部第六格、齒輪旁的錠子鈕；網頁的 data-glow，商城開著才畫）：序章裡寫了才亮，出了草廬一律在（web/app.js 的 mallShown）
    "act:explore", "act:train", "act:rest", "act:social", "act:move",  # 江湖頁行動列的五格
    "act:practice",  # 行動列的操練／練功那一格（新手引導重做，Config.training）
    "board", "quest", "fronts", "orders", "minimap",  # 江湖頁的公告卡、主線與目標、戰況、軍令卡、小地圖
    "stances",  # 江湖頁最上面那一排小標裡的「態勢」（第一季才有）；跟公告卡（board）一起亮，見 Task 6 的 shown("stances")
})
# 序章每一步 glow 可以寫的鍵（網頁的 data-glow，見 web/app.js 的 applyGlow）：亮得起來的元件加上修練頁、煉製頁裡的幾顆鈕。
# 「all」是全部亮齊的意思，沒有東西可發光，不收。寫錯的鍵悄悄什麼都不亮，帶引號或括號的還會讓 applyGlow 的選擇器丟例外
# pick:art、pick:insight 是煉製頁挑選清單裡這一步要放進爐子的那門武學與意境（Game.art_rows／insight_rows 的 glow 標出來）
GLOW_KEYS = (REVEAL_KEYS - {"all"}) | frozenset({
    "forge", "practice", "switch", "cultivate", "melt", "allocate", "pick:insight", "slot",
    "pill",  # 狀態列體力條上的「丹」（新手引導重做：序章服回體丹那一步）
})


# 序章每一步 allow 可以寫的選單 id（TutorialStep.allow 是前綴比對，見 prologue.allowed）：照 Game._everyday_options 與它叫的
# 幾個函式真的做得出來的 id 列。固定的整串寫在 ALLOW_FIXED；帶參數的（尾巴是地點、人物、武學的 id）只列到冒號，在 ALLOW_FAMILIES，
# allow 可以寫到整個家族（"move:"）或家族加上 id（"move:town"）。兩道檢查，都不是萬全的：
#   tests/core/test_prologue.py::test_the_allow_lists_only_name_ids_the_code_really_makes 只查「這裡列的每一筆都真的出現在原始碼」（不憑空多寫）；
#   tests/season/test_real_content.py::test_every_idle_menu_id_is_one_the_prologue_allow_list_knows 整季隨機玩、對照每個閒著的選單，
#   查「引擎做得出來的有沒有漏列」，但只看得到那一季玩到的 id。引擎多了閒著選單的行動，記得手動補進這兩個。
ALLOW_FIXED = frozenset({
    "act:explore", "act:train", "act:socialize", "act:rest", "act:summons", "act:call", "act:recruit", "act:duty", "act:convoy",
    "act:rank2",  # 第 2 階守勢行動（正式版乙一）
    "act:bounties",  # 懸賞榜（城鎮類的地點、有看得到的單；每季都有）
    "act:smith",  # 鐵匠鋪（兵器設計，城鎮類的地點）
    "act:market",  # 馬市（裝備四欄 5.5，帶「馬市」標籤的地點）
    "act:arena",  # 擂台（城鎮類的地點；tianxia/arena.py）
    "act:heal",  # 醫館療傷（帶「醫館」標籤的地點，有內傷時）
    "act:donate",  # 自家大本營捐軍備（素材與經濟設計第六節）
    "act:dadian",  # 打點（21 天季的銀兩出口收成一間店）
    "act:tavern",  # 酒肆（帶「酒肆」標籤的城鎮；tianxia/tavern.py）
    "act:drill",  # 城裡操練（新手引導重做；tianxia/training.py）
    "ambush:lift", "works:stockpile",  # 後期體力玩法：收伏、屯糧練兵
})
# opp: 是機緣的交東西與天時地利（opp:deliver:<id>、opp:try:<id>，正式版乙一）；對話選單的 talk:opp: 不是閒著的選單，不列
# act:rank: 是第 3、4 階的行動（act:rank:<行動 id>，正式版戊一）
ALLOW_FAMILIES = (
    "act:challenge:", "act:rank:", "call:", "move:", "learn:", "faction:", "defect:", "opp:", "fs:",
    "explore:",  # 探索三選一的三顆（explore_modes.PREFIX；序章裡不出現）
    "sect:",  # 拜入門派（一類一顆開著時從交友搬出來，sect:<事件 id>；序章裡不出現）
    "ambush:set:",  # 設伏劫道（ambush:set:<另一頭>；序章裡不出現）
    "aid:guard:", "aid:rally:", "aid:visit:",  # 護著大勢人物（figure_aid；序章裡沒有陣營，不出現）
    "act:recruit:",  # 招募歷史武將（act:recruit:<人物>，歷史武將同行；序章裡不出現）
    "feast:join:",  # 入席（宴客，tianxia/feasts.py；序章裡不出現）
    "plan:help:", "plan:block:",  # 盤算（世界活起來，tianxia/plans.py；序章裡不出現）
)


def allow_known(entry: str) -> bool:
    """TutorialStep.allow 的一筆是不是選單上真的有的行動（content.validate 擋拼錯的：拼錯的前綴整步會把選單清空）。"""
    return entry in ALLOW_FIXED or any(entry.startswith(family) for family in ALLOW_FAMILIES)


class GiveArt(_Strict):
    """序章完成某一步時給的一門內容武學與成數（雪恥之後掉出來的雜學：第五成，熔了才退得回心得）。"""

    id: str
    level: int = Field(default=1, ge=1, le=10)


class TutorialStep(_Strict):
    id: str
    text: str  # 對話框裡說的話；空字串＝這一步沒有對話框（序章第一步：還沒遇到師父）
    done_when: TutorialGoal
    reward: Effect = Field(default_factory=Effect)
    season_one: bool = False  # 只在第一季濃縮版才有的步驟（開關開著、這一季也蓋了章，計畫 T6）；一律排在最後（content.validate）
    speaker: str | None = None  # 框上寫的人；None＝Tutorial.speaker
    # ── 序章（新手引導計畫一，設計第三、六節）：只寫在前 Tutorial.prologue_steps 步（content.validate）──
    scene: str = ""  # 旁白，對話框裡排在話的前面
    line: str = ""  # 對話框收起後那一行（例：「師父：回『江湖』按『探索』」）；空的＝用 text
    reveal: list[str] = Field(default_factory=list)  # 這一步起畫面上亮起來的元件（REVEAL_KEYS）；前面幾步亮的照舊亮著
    glow: list[str] = Field(default_factory=list)  # 這一步要發光的鈕（網頁的 data-glow，見計畫 Task 6）
    # 在草廬閒著時選單只留這些（前綴比對，例："act:explore"、"move:"）。初入江湖的步驟（序章之後、不分季的）也可以寫：
    # 那裡不是只留這些，而是行動列那幾樣（prologue.ONBOARD_CORE）照留，「此地還能做」只多留教到這一步為止寫過的（prologue.onboard_allowed）
    allow: list[str] = Field(default_factory=list)
    explore_event: str | None = None  # 在草廬探索時一定端出這則事件（四景四選一）
    explore_scene: str | None = None  # 在草廬探索時一定端出這段有所感（InsightScene，prologue 要是 true；跟 explore_event 二選一）
    enemies: list[str] = Field(default_factory=list)  # 這一步草廬的對手（遊歷才出現）
    force_tier: str | None = None  # 這一步的遊歷結果照寫好的（雪恥：險勝）
    deepen: bool = False  # 這一步准揣摩（同一個意境合兩個，層數 +1；武學重構）；序章裡別的步驟不准開爐
    instant_rest: str = ""  # 非空：這一步的打坐一坐就回滿，說這一句
    fuse_base: str | None = None  # 這一步只准把意境裝進這一門的意境槽（武學重構；以前是合成的底）
    melt_only: str | None = None  # 這一步只准熔這一門
    give_art: GiveArt | None = None  # 完成這一步時給的武學
    give_pills: int = 0  # 完成這一步時給幾顆回體丹（序章「服一顆回體丹」那一步先送，身上沒丹的人也走得下去）
    give_piece: bool = False  # 完成這一步時再給一份手上那個意境（揣摩要同一種意境兩份；效果照第一份抄，序章才合得成二重）
    # 師父的話太長、一次放不下時分頁（T7 審查 I1）：網頁照 \n\n 切成幾頁、一頁一頁按「下一段 ▸」，最後一頁是要做的事；話整段都在、不切。
    # 只有 reveal 之後這一步的行動列落到分頁列底下才用得到（量測見 Task 7 報告）；至少要有兩段
    paged: bool = False
    # 這一步的動作做成之後，結果那一句（設計 10.3 的「…之後（場景）」）：草廬裡合成、修練、熔煉成功時用它取代引擎的一般那句。
    # {意境}、{武學}、{心得} 換成這一次真的合出來的／修練的／退回的（prologue.after_line）
    after: str = ""


class ArtPattern(_Strict):
    """秘方（content/secret_recipes.json）裡的一門武學：寫了的每一項都要對得上。武學多半是合出來的、每季 id 都不一樣，
    所以秘方不認 id，認形狀（屬性、種類、正邪、自己那一份至少什麼品）。"""

    attribute: str | None = None
    kind: str | None = None  # 內功／武學
    lean: str | None = None  # 正／邪／無
    min_quality: str | None = None


class InsightPattern(_Strict):
    """秘方裡的一個意境：id（內容的六個基本意境）或屬性、正邪；寫了的每一項都要對得上。"""

    id: str | None = None
    attribute: str | None = None
    lean: str | None = None


class SecretRecipe(_Strict):
    """秘方（PM 2026-10-10 派工「口訣與秘方」，企劃者「合成要講究邏輯，最好能隱含技巧都藏彩蛋」）：每季照天機挑一批
    （Config.secrets.per_season，tianxia/secrets.py）。合中了出一門內容寫好名號的武學或意境：品質機率好一截、一定帶一條特別功效，
    首創的人江湖上傳一句、寫進江湖史。線索是三句口訣（clues：說書版、人物順口版、殘譜版），只講意象，不點名意境或屬性。
    fuse：art＋insight（裝滿）；merge：left、right 兩格分左右。武學＋武學（blend）2026-10-21 隨武學合成一起拿掉。"""

    id: str
    kind: Literal["fuse", "merge"]
    art: ArtPattern | None = None
    insight: InsightPattern | None = None
    left: InsightPattern | None = None
    right: InsightPattern | None = None
    name: str
    note: str = ""
    special: str | None = None  # 特別功效 id（traits.json 的 special）；沒寫照天機挑一條。合出意境的秘方不用
    clues: list[str] = Field(min_length=3, max_length=3)


class ForgeSide(_Strict):
    """隱藏配方的一樣料（打造隱藏配方設計 3.1）：認屬性＋階，不認素材 id（joy 之後多加一種「三階剛」的素材，舊配方照樣認得、口訣照樣對）。
    主料一定寫死階（tier，定這一件的階與工錢）；輔料可以改寫 min_tier（不低於幾階）。"""

    attribute: str
    tier: int | None = Field(default=None, ge=1, le=4)  # 4：神器配方（正式季整合 5.5）
    min_tier: int | None = Field(default=None, ge=1, le=3)  # 「幾階以上」只算到三階：四階是神器的料（forge_secrets.covers）


class ForgeSecret(_Strict):
    """打造的隱藏配方（content/forge_secrets.json；打造隱藏配方設計 3.1）：某種兵器（或防具）＋主料＋輔料（主輔不交換），打中了出有專名的
    名器（tianxia/forge_secrets.py）。divine 是神器配方（打造第二批：一爐必出神器，第一把原品、之後仿品；name 是譜名）。clues 三句口訣：0 說書版、1 鐵匠版、2 殘譜版，三句合起來定得出
    這一條，單看一句只能縮小範圍（3.5）。"""

    id: str
    slot: Literal["weapon", "armor"]
    kind: str | None = None  # 兵器種類（WEAPON_KINDS）；防具不寫
    main: ForgeSide
    aux: ForgeSide
    divine: bool = False
    name: str  # 名器的專名（神器配方是「譜名」，第二批）
    note: str = ""  # 打出來那一句下面的一句說明
    clues: list[str] = Field(min_length=3, max_length=3)
    tactic: TacticDef | None = None  # 神器的特技（第三批）：原品照寫，仿品發動率乘 Config.tactics.copy_rate
    # 神器的批次（正式季整合 5.6、5.7）：1 是一開始的九件（這個伺服器第一季全開），2 是新神器第一批（第二季起才輪得到）
    wave: int = Field(default=1, ge=1)


class Tier4Named(_Strict):
    """四階名器名字表的一條（content/tier4_named.json；正式季整合 5.2）：主料四階、沒打中神器配方時照機率出名器，名字照這一爐的種子
    從合欄位、合種類、合屬性的那幾條挑一個（four_tiers.pick_named）。不登記、不佔名字空間，不同的人可以撞名（跟一般組合一樣）。
    打出來的那一件記 Equipment.named_entry＝這一條的 id；名字讀檔時照內容重寫（forge_secrets.refresh_names）。"""

    id: str
    slot: Literal["weapon", "armor"]
    kind: str | None = None  # 兵器種類（WEAPON_KINDS）；防具不寫
    attribute: Attribute
    name: str
    note: str = ""  # 打出來那一句下面的一句說明（待 joy 潤）


class PresetRecipe(_Strict):
    """師門配方（content/preset_recipes.json，新手引導設計 3.3）：這個底融這個意境，名字與說明由內容寫好，
    第一個合出來的人不等模型（fusion.fuse）。每季配方清空，下一季照樣用它，所以不用每季重放。"""

    base: str  # 內容武學 id
    insight: str  # 基本意境 id
    name: str
    note: str = ""
    # 師門傳下來時改過的屬性（FB-092）：沒寫就跟意境（一般的合成規則）。火（剛）融出來會跟開局的內功（柔）相剋，
    # 師父教的那一門不能讓新人一照做就 −20%，所以烈爐拳寫成陽；載入時檢查每一門都不跟開局送的另一門相剋
    attribute: str | None = None


RECRUITER_ALLIED_FIELDS = ("intro", "briefing", "order_hint", "done", "rejoin")  # Recruiter.allied 能換的欄位（content.validate 驗）


class Recruiter(_Strict):
    """入伍段（新手引導計畫二，設計第四節）一個陣營的引薦人：框上的名字與他說的話。"""

    name: str  # 老石、青禾、季伯平
    intro: str  # 入營（r1）：投靠的當下，排在第一步的話前面
    briefing: str  # 看戰局（r2）
    order_hint: str  # 第一道軍令（r3）還沒做時，框裡那一句
    done: str  # 第一道軍令做完，引薦人的結尾（按「知道了」收起）
    lines: list[str] = Field(default_factory=list)  # 每一步收起後那一行，照 Enlist.steps 的順序；不帶名字（框上的名字另外寫）
    rejoin: str = ""  # 第二季起再投靠時打的招呼（新手引導計畫三用）
    # 豪強分屬兩軍的季（allied.on，企劃者 2026-10-15）換掉的幾句（新寫）：鍵是上面的欄位名（intro／briefing／order_hint／done／rejoin），
    # 只寫要換的；enlist.line 照它讀
    allied: dict[str, str] = Field(default_factory=dict)


class EnlistStep(_Strict):
    id: str
    done_when: TutorialGoal


class Enlist(_Strict):
    steps: list[EnlistStep] = Field(default_factory=list)
    recruiters: dict[str, Recruiter] = Field(default_factory=dict)  # 陣營 id → 引薦人
    drifter_line: str = ""  # 「主線與目標」裡散人那一行：三邊各在哪裡收人（設計 6.3）


class OpeningSender(_Strict):
    """開局三選一的一個選項對到的那位人物（content/opening.json）：選了帶 flag 的那一顆，就是他在城門口開口、託你送信。"""

    flag: str  # 事件那一顆選項 flags_add 裡的旗標（例「開局:投軍」）
    figure: str  # 對話人物 id（content/characters.json；要是大勢人物，信才寫得出他在哪）
    text: str  # 信的固定句（模型寫不出來時照它；{hero} 換成少俠／女俠，{end} 換成送到的地名）


class Opening(_Strict):
    """開局第一分鐘（減法季整合設計 6.7，批 7 前半；tianxia/opening.py）：減法季的新角色不進草廬，站在起點看一段旁白、
    三選一定起手的屬性，接著照選的那一顆由一位人物開口託付第一件事（把一封信送到 end），本週卡才出現。沒有這個檔就沒有這一段。"""

    event: str  # 開局那一則事件（旁白＋三選一；每一顆選項 flags_add 要帶 senders 其中一個 flag）
    end: str  # 第一個託付：把信送到這個地點（護送委託，到了就算）
    senders: list[OpeningSender] = Field(min_length=1)
    days: float = Field(default=3.0, gt=0)  # 第一件託付幾個遊戲日內要送到（書信委託平常是 figure_life.commission_days 1 天；新人多給幾天）【預設】
    arrived: str = "{who}在城門口叫住你，託你把一封信送到{end}。"  # 江湖紀錄那一句（待 joy 潤）


class Tutorial(_Strict):
    speaker: str = "老說書人"
    steps: list[TutorialStep] = Field(default_factory=list)
    outro: str = ""
    enlist: Enlist | None = None  # 入伍段（新手引導計畫二）；第一季才開始
    # ── 序章（新手引導計畫一）：location 是 None 就沒有序章，下面三個都不看 ──
    location: str | None = None  # 草廬（Location.prologue_only）
    prologue_steps: int = 0  # 前幾步是序章（都在草廬）；走完就出師
    start_event: str | None = None  # 新角色一進來就端出的事件（遇險）
    leave_text: str = ""  # 走完序章、抵達起點時接在抵達那一則（「剛剛」）的一句


class HintDef(_Strict):
    """碰到才說的一條（新手引導設計第五節）：mentor 寫成「想起師父說過」（框上的字是 Hints.head）；recruiter 由自己那一邊的引薦人說，
    texts 是陣營 id → 那一位說的話，drifter 是散人時師父說的版本（沒有就散人不說，也不記成說過）。"""

    id: str
    by: Literal["mentor", "recruiter"]
    text: str = ""
    texts: dict[str, str] = Field(default_factory=dict)
    drifter: str = ""
    # 第一季的規則開著時師父改說這一句（只有師父的條能寫；空的就照 text）：有些事只有第一季才是真的（explain-1 的 h_bond：
    # 情誼夠深人物會透露伏筆、機緣的風聲），beta 那一季說了就是假話
    season_one: str = ""
    # 減法季探索一顆開著時（rules.jianfa 的 explore_one）師父改說這一句（只有師父的條能寫；空的就照 text；先於 season_one）：
    # 那一季沒有「尋敵」那顆鈕了（h_drill_done，FB-816 同一類）。待 joy 潤
    explore_one: str = ""
    # 豪強分屬兩軍的季（allied.on）引薦人改說的那一句：陣營 id → 句子（新寫；只寫要換的，例：豪強不再臨時投效）
    allied: dict[str, str] = Field(default_factory=dict)


class Hints(_Strict):
    """碰到才說（content/hints.json，新手引導計畫三）：沒有這個檔就是沒有提示。"""

    head: str = "想起師父說過"  # 師父那幾條框上寫的字
    hints: list[HintDef] = Field(default_factory=list)
    season_return: str = ""  # 第二季起開季時師父的一句（設計 7.1）；空的就沒有


class FactionInk(_Strict):
    """一方在輿圖上的樣子（輿圖簡化設計 3.3：幾方、每一方的顏色都從劇本讀，程式不寫死；環形版 dev/map-2 搬過來）。
    color 是印、紅線兩邊、年表、勢力條；soft 是天下圖的地面；tint 是大區的淡底色（soft、tint 沒寫照 color 往紙色淡）。
    short 是一個字（天下圖大區名底下「官 N」那種）；label 是輿圖上寫的名字（沒寫照 FactionDef.name）。"""

    color: str = Field(pattern=HEX_COLOR)
    soft: str | None = Field(default=None, pattern=HEX_COLOR)
    tint: str | None = Field(default=None, pattern=HEX_COLOR)
    short: str = ""
    label: str = ""


class FactionDef(_Strict):
    """一季的玩家陣營（第一季設計第五節）：在 join_at 的地點可以投靠；拜入 sects 裡的門派也算投靠這個陣營。
    goals 是這個陣營想把各條大勢線往哪推（伺服器假人照它打分數）。"""

    id: str
    name: str
    join_at: list[str] = Field(default_factory=list)
    sects: list[str] = Field(default_factory=list)
    goals: dict[str, int] = Field(default_factory=dict)  # 大勢線 id → 1 推高／-1 壓低；伺服器假人照這個行動
    defect_text: str = ""  # 叛投到這個陣營那一刻的一句敘事（計畫甲；content/scenario.json 的三句是初稿，待 joy 潤，joy 會走自己的 PR）
    # 豪強分屬兩軍（企劃者 2026-10-15）：這個陣營在依附的季（allied.on）要依附其中一軍；寫的是可以依附的陣營 id（暫名）。
    # 空的＝這個陣營本身就是一軍
    allies: list[str] = Field(default_factory=list)
    ink: FactionInk | None = None  # 輿圖上的顏色與字（輿圖第三版第 3 批）；沒寫的照 mapdata.FALLBACK_INKS 的順序挑
    # 列傳為終點（減法季批 7b-2，整合設計 3.3、第九章）：季末論功拿到第一、二階的人，列傳的評曰由這一方的哪幾位人物寫（characters 的 id；
    # 跟他情誼最高的那一位寫，一樣高照寫的順序）。官軍皇甫嵩、盧植，黃巾張角、波才，豪強曹操；空的是沒有（不寫進序列化）
    verdict_by: list[str] = Field(default_factory=list)

    @model_serializer(mode="wrap")
    def _drop_new_defaults(self, handler):
        return _drop_unset(handler(self), ("verdict_by",))


class SeasonOneOff(_Strict):
    """第一季不觸發的 beta 內容（控制者與地圖擴充 T4 說好的格式，2026-10-04）：只在 rules.season_one 成立時生效
    （開關開著、這一季開季時也蓋了「開」的章）；開關關著時 beta 那一季照舊。四種各自是那一種內容的 id。
    - thresholds：大勢門檻不觸發（管理者也觸發不了）；
    - storylines：主線不推進，「主線與目標」不顯示那條主線；
    - battles：大勢門檻的 starts_battle 不開，管理者「立刻開戰」的選單不列；
    - events：探索的事件抽選跳過（T4 做；這裡只定欄位，id 一樣在載入時檢查）；
    - milestones：「主線與目標」的個人目標不列（做不到的 beta 目標，例如擊敗波才、平定黃巾）；
    - world_events：世界事件不觸發（管理者也觸發不了）；
    - unlocks：地點第一季直接開放（不看 unlock_flag；玉璽碎片設計 11.2 第 3 條）。"""

    thresholds: list[str] = Field(default_factory=list)
    storylines: list[str] = Field(default_factory=list)
    battles: list[str] = Field(default_factory=list)
    events: list[str] = Field(default_factory=list)
    milestones: list[str] = Field(default_factory=list)
    world_events: list[str] = Field(default_factory=list)
    unlocks: list[str] = Field(default_factory=list)


class BlockDef(_Strict):
    """領地爭奪的一個區塊（設計 3.1：一塊＝一個地點）。kind 是開季歸哪一種：neutral 中立（高階獎勵、兩軍爭奪），guan／huang 是那一方的
    陣營領地（大本營也寫在這裡，種類要是自己陣營的）；line 是佔領算進哪一條戰線的大勢值（null＝不算進任何一條，洛陽那一帶）。"""

    kind: Literal["neutral", "guan", "huang"]
    line: str | None = None


class TerritoryDef(_Strict):
    """地盤易手（出陣探索與地盤設計第四節；tianxia/territory.py）。大本營（陣營的 join_at）不寫在這裡，永遠歸那一方。"""

    lines: dict[str, list[str]] = Field(default_factory=dict)  # 戰線 id → 可易手的地點，從目標往 0 推的那一方（官軍）那頭排到另一頭（待 joy 對）
    fixed: dict[str, str] = Field(default_factory=dict)  # 不參與拔河、只照大事（TimetableOutcome.control）易手的地點 → 開季的控制方（廣宗）
    garrison: dict[str, dict[str, list[str]]] = Field(default_factory=dict)  # 地點 → 控制方 → 站的隊伍；流寇野獸照 Location.enemies 裡無陣營的
    # ── 領地爭奪（第 38 項改版，docs/superpowers/specs/2026-10-20-領地爭奪-design.md；tianxia/conquest.py；Config.conquest 開著才讀）──
    blocks: dict[str, BlockDef] = Field(default_factory=dict)  # 地點 → 區塊（開季歸哪一種、算進哪條戰線）；不寫的地點不是區塊
    neutral_garrison: dict[str, list[str]] = Field(default_factory=dict)  # 開季中立的區塊 → 另一套駐軍（無陣營的強對手，設計 3.3；待 joy）
    # 陣營區塊沒寫 garrison 時，出陣攻打碰上的控制方巡邏（陣營 → 隊伍；conquest.sortie_foes；待 joy）：城鎮這類沒有兵的區塊也攻得了
    side_garrison: dict[str, list[str]] = Field(default_factory=dict)


class Scenario(_Strict):
    id: str
    name: str
    intro: str
    era_note: str = ""  # 給對話模型的時代背景：這一季是哪一年、各人物此時的身分、哪些事還沒發生（避免扯到之後的年代）
    start_location: str
    factions: list[FactionDef] = Field(default_factory=list)  # 空的＝這個劇本不分陣營，全服決戰維持集結時選邊
    trends: list[Trend]
    thresholds: list[Threshold] = Field(default_factory=list)
    sim_players: list[SimPlayer] = Field(default_factory=list)
    world_events: list[WorldEvent] = Field(default_factory=list)
    storylines: list[Storyline] = Field(min_length=1)
    endings: list[Ending]
    milestones: list[Milestone] = Field(default_factory=list)
    jade_seal_flag: str | None = None  # 這個世界旗標代表玩家親手取得了這一季的玉璽碎片（設計文件九），記進跨季持久紀錄
    season_one_off: SeasonOneOff = Field(default_factory=SeasonOneOff)  # 第一季不觸發的 beta 門檻、主線、決戰、事件
    territory: TerritoryDef | None = None  # 地盤易手（出陣探索與地盤設計第四節）；不寫＝這個劇本沒有地盤
    # 江湖頁本週卡第二行（減法季整合設計 6.8）：一季前、中、後三段各一句（21 天季是三週，7 天的季是三段）；不寫就不畫那一行
    week_themes: list[str] = Field(default_factory=list, max_length=3)

    def faction(self, faction_id: str | None) -> FactionDef:
        """id 對得上的那個陣營（factions 裡的第一個）；劇本裡沒有就丟 LookupError。給一定要有這個陣營的地方用（選單上的
        id、投靠的陣營、軍令與晉升寫的陣營）：存檔裡的 id 劇本已經沒有了，就在第一個用到它的地方停下，例如叛投的第一下，
        不會等到「確定」時清了進度、改了陣營才壞。"""
        found = self.find_faction(faction_id)
        if found is None:
            raise LookupError(f"劇本裡沒有陣營 {faction_id!r}")
        return found

    def find_faction(self, faction_id: str | None) -> FactionDef | None:
        """id 對得上的那個陣營；沒有就是 None（散人、不屬於任何陣營的人物）。"""
        return next((f for f in self.factions if f.id == faction_id), None)

    def sect_owner(self, sect_id: str) -> FactionDef | None:
        """這個門派歸哪個陣營（拜入它算投靠那個陣營：rules.apply_effect、bounties.join_note 共用）；不歸任何陣營是 None。"""
        return next((f for f in self.factions if sect_id in f.sects), None)

    def faction_name(self, faction_id: str | None, default: str | None = None) -> str | None:
        """那個陣營的名字；劇本裡沒有這個陣營就是 default。"""
        faction = self.find_faction(faction_id)
        return faction.name if faction is not None else default


ExploreBranch = Literal["insight", "wild", "event"]
EXPLORE_BRANCHES: tuple[ExploreBranch, ...] = ("insight", "wild", "event")  # 探索三選一的三支：悟意境、野怪、事件


class ExploreMix(_Strict):
    """一種地點類型探索時三支的比例（探索三選一設計第三節）。

    地點有 tags 裡任何一個標籤就算這一類；Config.explore_mix 照順序比對、第一個符合的就是。
    tags 空的那一筆是「其餘」，必須放最後。weights 沒寫的那一支當 0。"""

    kind: str
    tags: list[str] = Field(default_factory=list)
    weights: dict[ExploreBranch, float]

    @field_validator("weights")
    @classmethod
    def _weights_add_up(cls, weights: dict[str, float]) -> dict[str, float]:
        if any(w < 0 for w in weights.values()):
            raise ValueError("探索比例不能是負的")
        if sum(weights.values()) <= 0:
            raise ValueError("探索比例三支加起來要大於 0")
        return weights


def _default_explore_mix() -> list[ExploreMix]:
    return [
        ExploreMix(kind="camp", tags=["營寨", "祭壇", "塢堡"], weights={"insight": 15, "wild": 35, "event": 50}),
        ExploreMix(
            kind="town", tags=["城鎮", "官署", "城池", "寺院", "書院", "莊院", "里巷", "結社"],
            weights={"insight": 15, "wild": 0, "event": 85},
        ),
        ExploreMix(kind="wild", tags=[], weights={"insight": 40, "wild": 35, "event": 25}),
    ]


# T2 之前開的季沒有蓋章，那些季都是用預設設定開的，所以長度就是這個預設值（FB-037）。
# 不是「現在載入的設定」：週末設定的 2.5 天只管有蓋章的新季。
DEFAULT_SEASON_DAYS = 14

MOVES = ("強攻", "固守", "奇襲")  # 全服決戰的三招（戰鬥系統設計 3.4）
BEATS = {"固守": "強攻", "強攻": "奇襲", "奇襲": "固守"}  # 鍵剋值：固守剋強攻、強攻剋奇襲、奇襲剋固守
Move = Literal["強攻", "固守", "奇襲"]
DEFAULT_AFFINITY: dict[str, tuple[Move, Move]] = {  # 屬性 →（擅長, 不擅長），戰鬥系統設計 3.4【預設】
    "剛": ("強攻", "奇襲"), "實": ("強攻", "奇襲"), "陽": ("強攻", "固守"),
    "柔": ("固守", "強攻"), "陰": ("固守", "強攻"), "慢": ("固守", "奇襲"),
    "快": ("奇襲", "固守"), "虛": ("奇襲", "強攻"),
}


class GeneralTuning(_Strict):
    """龍頭上陣（Joy 2026-10-17 清單第 2 條「大決戰雙方龍頭武將應該要參與且有份量」；tianxia/generals.py）：決戰開集結那一刻，每一方
    取那條戰線上在場的前 len(ranks) 位大勢人物上陣（人物表的順序就是位階）。他們不是參戰者（不佔人數、不等他、不拿軍餉），
    每回合照主將喊的那一招出手，份量＝實力（照他挑戰本人那支隊伍的難度算，同 battle_instance.strength）× ranks[i] ×
    （0.5＋0.5×此刻聲威÷開季聲威）。主將每回合喊一招，照令出招的人份量多 order_bonus。人物整場都顯眼：對面出強攻的人照集火打他，
    放手一搏寫到他的名字也打得到他；同一邊出固守的人替他擋掉一部分（guard_per、盾陣 guard_role，最多 guard_cap）。池子打光就敗走：
    戰局當下往對面推 fall_push，收場後聲威 −fall_prestige（不受一天只扣一次的限制），最後一擊的人名望 +slay_fame。
    enabled 關掉：集結時不派人物，已經在場上的照打完。"""

    enabled: bool = True
    ranks: tuple[float, ...] = (2.5, 1.5)  # 主將、副將的份量倍數（每一方最多幾位上陣＝這裡寫幾個）
    pool: tuple[float, ...] = (1500.0, 1000.0)  # 主將、副將的氣血池（聲威不影響池子）
    order_bonus: float = Field(default=0.15, ge=0)  # 照主將喊的那一招出手，份量多這麼多
    order_read: float = Field(default=0.6, ge=0, le=1)  # 主將看對面上一回合出最多的那一招、喊剋它的機會；其餘隨口喊
    guard_per: float = Field(default=0.10, ge=0, le=1)  # 同一邊每個出固守的人替人物擋掉這麼多成的傷（盾陣 guard_role）
    guard_role: float = Field(default=0.20, ge=0, le=1)
    guard_cap: float = Field(default=0.5, ge=0, le=1)  # 最多擋掉幾成；擋下來的那一份平分給出固守的人
    hit_base: float = Field(default=0.06, ge=0, le=1)  # 點名他的放手一搏成了：打掉他池子的 hit_base＋風險×hit_per_risk，最多 hit_max
    hit_per_risk: float = Field(default=0.0008, ge=0)
    hit_max: float = Field(default=0.12, ge=0, le=1)
    round_cap: float = Field(default=0.25, ge=0, le=1)  # 一回合最多被打掉池子的幾成
    fall_push: int = Field(default=6, ge=0)  # 敗走那一刻戰局往對面推幾點
    fall_prestige: int = Field(default=15, ge=0)  # 收場後聲威扣幾點
    slay_fame: int = Field(default=3, ge=0)  # 最後一擊的人名望多幾點
    # 隨主人上陣的歷史武將（歷史武將同行第五節【預設】；battle_instance.Escort）：份量＝strength(他的威力) × escort_share（不吃主人的
    # 職位、坐騎、部下），敗走時戰局往對面推 escort_fall_push（人物的三分之一）；點名、一回合上限、固守護他照上面人物那幾個數
    escort_share: float = Field(default=0.5, ge=0)
    escort_fall_push: int = Field(default=2, ge=0)


class BattleTuning(_Strict):
    """全服決戰的三招與推力（戰鬥系統設計 3.4）。全部【預設】：企劃者 2026-10-06「照預設做、測完再調」。
    放在 Config 前面：Config.battle 的預設工廠要在 Config 類別建起來時就找得到它。"""

    # 實力 ＝ power_base ＋ power_per × min(威力, power_cap)（試玩回饋 2026-10-08，Joy：「玩家越強應該越有份量，而不是一視同仁，
    # 那前面都白練了」）。舊值 40＋0.4×min(威力,150)、最多 100，新手（威力約 25）50、練上去的最多 100，只差兩倍、威力 150 以上
    # 就沒差。整季機器人（14 天）季末威力 195～397，週末設定 91～262：新值新手 32.5、威力 100 是 70、300 是 170、400 封頂 220。
    power_base: float = 20.0
    power_per: float = 0.5
    power_cap: float = 400.0
    # 放手一搏成功時的推進乘上實力 ÷ gamble_strength_ref，夾在 gamble_strength_min～max（新手打五折、練滿最多兩倍）；失敗不乘
    gamble_strength_ref: float = 100.0
    gamble_strength_min: float = 0.5
    gamble_strength_max: float = 2.0
    # 進場依屬性給職位（試玩回饋 2026-10-08，Joy：「大決戰進場時，可以根據屬性給大家職位，對戰局走向的選擇也會稍微不同」）：
    # 本人五屬性裡最高的那一項（同分照臂力、身法、根骨、悟性、博聞的順序；五項一樣高沒有職位）。
    roles: dict[str, str] = Field(default_factory=lambda: {"str": "先鋒", "agi": "斥候", "con": "盾陣", "wis": "軍師", "lore": "參謀"})
    role_move_bonus: float = Field(default=0.15, ge=0)  # 先鋒的強攻、斥候的奇襲、盾陣的固守，份量多這麼多（加入時算進份量快照）
    role_gamble_rate: int = Field(default=10, ge=0)  # 軍師放手一搏的成功率多這麼多（模型評完再加，夾在 100）
    role_counter_relief: float = Field(default=0.5, ge=0, le=1)  # 參謀被剋時，剋制係數低於 1 的那一截減掉這麼多成
    # 鼓勵自己寫放手一搏（試玩回饋 2026-10-08，Joy：「怎麼多鼓勵玩家自行創作」）：每場收場挑最有戲的那一次寫進天下大事傳聞
    # （battle_instance.more_dramatic：成了的勝過沒成的，同樣成了或同樣沒成都是成功率越低越有戲），那一次是成了的，那個人名望多這麼多
    highlight_fame: int = Field(default=1, ge=0)
    # 個人戰功（Joy 2026-10-10：「戰線推進是陣營，個人的部分有辦法做出戰績跟區別嗎」）：每一項做到一次記幾分（battle_instance.merit）。
    # 出手是自己送出、結算了的回合，逾時被系統代為固守的回合（held）照一樣算（Joy：「他進戰場已經很有心 戰功正常算」）；帶頭是自己帶頭的那一招替這一邊佔了上風；搏成是放手一搏成了；
    # 打傷是點名的放手一搏真的打掉對方氣血；撐住是這一回合被點名或被集火打掉氣血、回合結束還站著。只出手一回合就倒下的人自然只有 2 分。
    merit_points: dict[str, int] = Field(default_factory=lambda: {"acted": 2, "held": 2, "led": 3, "gamble": 4, "hit": 3, "stood": 2, "slew": 10})
    top_fame: int = Field(default=2, ge=0)  # 收場時兩軍各一位首功（戰功最高、至少 1 分）上天下大事傳聞，名望多這麼多
    affinity_base: float = 75.0  # 適性：基準，武學屬性擅長／不擅長 ±affinity_outer，內功 ±affinity_inner，夾在 50～100
    affinity_outer: float = 15.0
    affinity_inner: float = 10.0
    affinity: dict[str, tuple[Move, Move]] = Field(default_factory=lambda: dict(DEFAULT_AFFINITY))  # 屬性 →（擅長, 不擅長）
    counter: float = 0.5  # 剋制係數 ＝ 1 ＋ counter × 對面被你剋的比例 － counter × 對面剋你的比例
    # 一回合最多推多少。Joy 2026-10-10（決戰試玩回饋第 3 點）：舊值 10 時兩軍份量相當，固定招全軍一回合只推 ±1～2，放手一搏成了一次就推 8～11，
    # 「跟從預設選項的玩家現在毫無存在感」。合成重演（長社火攻 5 對 5、9 回合、每人每回合兩成想搏、成功率照那場的分佈；
    # 搏的人每幕最多一次）：push_max 20、side_trend_cap 4 時固定招佔戰局變動的 58%～60%（舊值 38%），
    # 三個人一直搏的那種場面固定招佔 67%（舊值 46%）。正式值寫在 content/config.json 的 battle.push_max（20）；這裡的預設 10 是測試內容與舊的單元測試量公式用的。
    push_max: float = 10.0
    damage: dict[Move, float] = Field(default_factory=lambda: {"強攻": 60.0, "奇襲": 35.0, "固守": 15.0})
    strong_mitigation_cap: float = 0.6  # 強攻的損耗，自己的武學威力最多抵銷這麼多（同原本的猛攻）
    # 隊伍的路數多樣（一門打不遍，2026-10-07 企劃者選甲）：這一回合出固定招的同一邊，身上武學的屬性每多一種，這一邊的力量
    # 多乘 diversity_per，最多 diversity_cap。屬性在加入戰局時快照（BattleParticipant.attribute），只有第一季開著時才快照
    diversity_per: float = Field(default=0.05, ge=0)
    diversity_cap: float = Field(default=0.15, ge=0)  # 四路以上封頂：兩軍份量相當時，一回合大約多推 1 點
    lead_crowd: int = Field(default=3, ge=2)  # 回合原因點名帶頭出固定招的人；同一招有這麼多人時寫成「結成陣勢」
    # 放手一搏點名敵方參戰者（Joy 2026-10-10：「玩家會點名敵對的玩家……顯示成功，但是其實被點名的玩家根本沒受到任何影響」）：
    # 文字裡出現對面參戰者的名號（2 字以上，取最先出現的那一個）就是指名攻擊，由引擎認、不靠模型。
    # 成了：戰局推進只剩 target_push_share，其餘化成對他的傷害：他氣血池上限的 target_hit_base＋風險 × target_hit_per_risk，
    # 最多 target_hit_max；成功率（加職位之後）≤ pin_rate 的險招成了，他下一回合被牽制、只能固守。失手照舊只傷自己。
    target_push_share: float = Field(default=0.5, ge=0, le=1)
    target_hit_base: float = Field(default=0.10, ge=0, le=1)
    target_hit_per_risk: float = Field(default=0.0015, ge=0)
    target_hit_max: float = Field(default=0.25, ge=0, le=1)
    pin_rate: int = Field(default=15, ge=0, le=100)
    # 引人注目：這一幕被點名過、或自己放手一搏成過的人是「顯眼」的，對面這一回合每一個出強攻的人，另外有 focus_per_attacker 的傷害
    # 平分到這一邊顯眼的人身上（每人最多他上限的 focus_cap）。一個人一回合被別人打掉的（點名＋集火）合起來最多他上限的 target_round_cap
    focus_per_attacker: float = Field(default=15.0, ge=0)
    focus_cap: float = Field(default=0.12, ge=0, le=1)
    target_round_cap: float = Field(default=0.30, ge=0, le=1)
    generals: GeneralTuning = Field(default_factory=GeneralTuning)  # 龍頭上陣（見 GeneralTuning）

    @field_validator("affinity", mode="before")
    @classmethod
    def _merge_with_the_default_table(cls, given: Any) -> Any:
        """config.json 的 battle.affinity 只寫幾個屬性時，沒寫的屬性照預設表：不會整張表被換掉、其他屬性悄悄變成沒有
        擅長也沒有不擅長（那樣「要當哪種兵」的取捨就不見了，也沒有任何錯誤提醒）。認不得的屬性名由 content.validate 擋。"""
        if not isinstance(given, dict):
            return given
        return {**DEFAULT_AFFINITY, **given}

    @model_validator(mode="after")
    def _numbers_that_keep_the_resolution_working(self) -> BattleTuning:
        """企劃者測完要調數字：寫壞的值在載入設定時就擋下（伺服器開不起來、改的人馬上看到），不是等第一場決戰的第一回合
        才在行動鎖裡丟 KeyError、把整場卡住。三招的損耗要寫齊、每個屬性的擅長與不擅長是兩招不同的招、威力與推力的數字要大於 0；
        適性的加減、剋制係數、強攻的抵銷可以是 0（＝不起作用），剋制係數與抵銷不超過 1。"""
        if set(self.damage) != set(MOVES):
            raise ValueError(f"damage 三招（{'、'.join(MOVES)}）都要寫，現在是 {'、'.join(self.damage) or '空的'}")
        for move, amount in self.damage.items():
            if amount <= 0:
                raise ValueError(f"damage 的 {move} 要大於 0（現在是 {amount}）")
        for attribute, (good, bad) in self.affinity.items():
            if good == bad:
                raise ValueError(f"affinity 的 {attribute}：擅長與不擅長不能是同一招（{good}）")
        for name in ("power_base", "power_per", "power_cap", "affinity_base", "push_max"):
            if getattr(self, name) <= 0:
                raise ValueError(f"{name} 要大於 0（現在是 {getattr(self, name)}）")
        for name in ("affinity_outer", "affinity_inner"):
            if getattr(self, name) < 0:
                raise ValueError(f"{name} 不能是負的（現在是 {getattr(self, name)}）")
        for name in ("counter", "strong_mitigation_cap"):
            if not 0 <= getattr(self, name) <= 1:
                raise ValueError(f"{name} 要在 0～1 之間（現在是 {getattr(self, name)}）")
        return self


class StyleRule(_Strict):
    """一門打不遍（企劃者 2026-10-07 選甲，docs/superpowers/specs/2026-10-07-武學難度與長期目標-提案.md 第三節）：大場面的對手
    （頭目、大勢人物本人、難度到 big_fight_difficulty）各有路數——最怕哪一路（soft）、最會對付哪一路（hard），照「天機｜隊伍」
    雜湊從 attributes 裡挑，每季、每個人都不一樣。上陣的人身上武學的屬性落在 soft 乘 1＋soft_bonus、落在 hard 乘 1－hard_penalty
    （跟屬性相剋的 ×1.3 疊在一起）。只在第一季開著時有（rules.season_one）。提示一律含蓄：不寫屬性、不寫倍數；
    words 是給模型看的打法描述（大場面判讀、人物對話），lines 是戰報裡的一句。"""

    soft_bonus: float = Field(default=0.25, ge=0)
    hard_penalty: float = Field(default=0.25, ge=0, lt=1)
    attributes: list[Attribute] = Field(default_factory=lambda: ["陰", "陽", "剛", "柔", "快", "慢", "虛", "實"])
    talk_affinity: int = 20  # 人物對話裡不經意露出自己的習慣：好感到這裡才會（交情不到，人家不跟你聊武藝）
    words: dict[Attribute, str] = Field(default_factory=lambda: {
        "陰": "陰寒內斂、後發制人", "陽": "熾烈外放、大開大闔", "剛": "剛猛硬打、以力壓人", "柔": "綿柔卸勁、借力打力",
        "快": "輕快迅捷、搶攻破綻", "慢": "沉穩緩重、步步為營", "虛": "虛實難測、聲東擊西", "實": "紮實穩打、一招是一招",
    })
    lines: dict[Literal["soft", "hard"], str] = Field(default_factory=lambda: {
        "soft": "你這一路正好打在對方的軟處，他接得手忙腳亂。",
        "hard": "對方似乎早料到你這一路，處處受制。",
    })

    @model_validator(mode="after")
    def _two_different_roads(self) -> StyleRule:
        if len(set(self.attributes)) < 2:
            raise ValueError("styles.attributes 至少要兩個不同的屬性（怕的與擅長對付的要是兩路）")
        missing = [a for a in self.attributes if a not in self.words]
        if missing:
            raise ValueError(f"styles.words 少了 {'、'.join(missing)} 的打法描述")
        if set(self.lines) != {"soft", "hard"}:
            raise ValueError("styles.lines 要寫 soft 與 hard 兩句")
        return self


class Spar(_Strict):
    """切磋（玩家互動第二層，企劃者 2026-10-08「互動的兩層也可以派下去做了」）：同一地點的兩個玩家，一方發邀請、對方接受才打。
    雙方各用本人的威力（不帶同伴與部下：比的是兩個人的功夫），照 encounter 的單次判定；不扣氣血、不掉銀兩、不掉素材。
    數字的依據：跟自己陣營操練一樣是零風險，操練只給對手獎勵的三成（drill_reward_share），危險度 1 一帶的散兵中位數是
    經驗 19、心得 14.5，三成是經驗約 6、心得約 4。切磋要兩個人湊在一起、雙方都花一次遊歷的體力，給得比操練略多一點：
    經驗各 exp；心得贏的 win_xinde、輸的 lose_xinde（輸了也學到東西），平手各 draw_xinde。同一對人每個遊戲日最多 per_pair_day 場，
    免得兩個人互刷。"""

    exp: int = Field(default=8, ge=0)
    win_xinde: int = Field(default=6, ge=0)
    lose_xinde: int = Field(default=3, ge=0)
    draw_xinde: int = Field(default=4, ge=0)
    per_pair_day: int = Field(default=2, ge=1)


class MingtieTuning(_Strict):
    """名帖（Joy 2026-10-19「抱拳改成互贈名帖」，設計稿 https://claude.ai/artifact/YLTXjaX77DJRsCmMX57xAi）：玩家自己畫的一張帖子，
    底下是系統照他做過的事寫的頭銜與自題的一句話。做名帖不花錢（Joy：「製作名帖要花錢好像很過分」），所以照次數擋洗版：
    定稿一天最多 made_per_day 次（每次定稿要請模型看一次那句話），一天最多主動遞 send_per_day 張，同一個人只能換一次
    （之後再遞是換新帖）。不給任何數值。一天照回體丹的現實時間換日（Game._pill_day）。"""

    enabled: bool = True
    made_per_day: int = Field(default=5, ge=1)
    send_per_day: int = Field(default=10, ge=1)
    titles: int = Field(default=3, ge=1, le=6)  # 一張名帖印幾個頭銜
    motto_max: int = Field(default=16, ge=1, le=40)  # 自題那一句最多幾個字
    taunt_max: int = Field(default=20, ge=1, le=40)  # 挑釁附的那一句最多幾個字
    report_hide: int = Field(default=3, ge=1)  # 同一張被幾個人檢舉就先對所有人藏起來，等管理者看
    box_cap: int = Field(default=300, ge=10)  # 名帖匣最多收幾張（滿了丟最舊的）
    max_strokes: int = Field(default=160, ge=1)
    max_points: int = Field(default=4000, ge=10)


class Ranger(_Strict):
    """遊俠名號（散人的成長階梯，PM 2026-10-08 派工「散人玩法對比加入陣營好像薄弱很多」）：劇本有陣營就有，每季都有（懸賞榜設計 2.2）。
    散人時攢的善名、惡名（只算加的，扣的不算）各記一本帳，俠名＝兩本取高的那一本＋懸賞的功績；走哪一條路看哪一本高
    （善名高是「俠」、惡名高是「寇」，一樣高算俠）。投靠了陣營就凍結：帳不再記、名號不顯示、好處不給，存檔照留。

    數字的依據（照整季機器人量，見 scripts/measure_sanren.py）：
    - thresholds：第 1～4 階要多少俠名。整季隨機玩的機器人善名、惡名各 10～20 上下，只靠事件大約到第 2 階；
      到第 3、4 階要再靠懸賞的功績，跟陣營的人要靠貢獻升第 3、4 階同一個量級。
    - audience_per_tier：每一階抵幾點求見門檻、對所有人物都算（陣營的人每升一階抵 audience_rank_discount 5 點，可是只對自己陣營的人物）；
      第 1 階起算。
    - exp_per_tier：第 1 階起每一階打贏的經驗多幾成（第 2 階 +20%）：陣營的人能跟自己陣營的隊伍操練（零風險拿經驗），散人碰上的都是真打；
      整季機器人量到沒有這一項時陣營的人季末等級比散人高四級（scripts/measure_sanren.py）。
    - recruit_per_tier：第 2 階起每一階招募成功率加多少（第 2 階 +5%、第 4 階 +15%）：散人沒有部下，靠同伴補。
    - qiyu_tier：到這一階，探索才遇得上散人專屬的奇遇（Condition.ranger_min）。
    - bounty_bonus_tier／bounty_bonus：到這一階，懸賞給的銀兩再乘多少。"""

    thresholds: list[int] = Field(default_factory=lambda: [5, 15, 30, 50], min_length=1)
    audience_per_tier: int = Field(default=3, ge=0)
    recruit_per_tier: float = Field(default=0.05, ge=0, le=1)
    exp_per_tier: float = Field(default=0.05, ge=0, le=1)
    qiyu_tier: int = Field(default=3, ge=1)
    bounty_bonus_tier: int = Field(default=4, ge=1)
    bounty_bonus: float = Field(default=1.25, ge=1)


class RenownTuning(_Strict):
    """名聲（docs/superpowers/specs/2026-10-15-名聲-design.md 第八節）：每一樣一個開關，預設開、測試內容關；titles 關著時其他開關都沒有作用
    （renown.on）。數字都是起始值，看試玩再調。名望的門檻在這裡，善惡的門檻沿用 Config.ranger.thresholds（設計 2.2）；兩種都在開季時
    乘季長倍數（WorldState.renown_scale，world_state.stamp_season）。"""

    titles: bool = True  # 兩個稱號本身、遊俠名號併入、狀態列／玩家卡／決戰名單、說明卡、跨段那一行、得失後面的差距、玩法說明那一節
    scale: bool = True  # 門檻乘季長倍數（設計 2.4），從下一季開季起（world_state.stamp_season）
    deed_fame: bool = True  # 立功給名望（3.1）
    discount: bool = True  # 店家折扣（4.1）
    prize_gate: bool = True  # 重賞要名動一方（4.2）
    affinity: bool = True  # 見面情誼起步與冷淡（4.3、5.2）
    duel: bool = True  # 頭目的機會與賞（4.4）
    news: bool = True  # 威震州郡那一句、天下聞名點名（4.5）
    faction_wanted: bool = True  # 敵方陣營的通緝（4.6）
    arena_reach: bool = True  # 擂台排在後面五名的人挑得到你（4.7）
    virtue_insight: bool = True  # 浩然、血煞要走對那條路（5.1）
    lessons: bool = True  # 正邪武學與綠林山寨（5.1）
    prompt: bool = True  # 對話提示帶稱號與看法（5.2）
    clinic: bool = True  # 俠的醫館折扣（5.2）
    black_market: bool = True  # 寇的收購價（5.2）
    virtue_choices: bool = True  # 俠寇選項與新事件（5.3）
    official_wanted: bool = True  # 官府通緝與掉惡名（5.4）
    explain: bool = True  # 第六節的原因字句（求見拆解、熟練、悟、共鳴、散人加成）

    fame_thresholds: list[int] = Field(default_factory=lambda: [10, 25, 50, 90], min_length=4, max_length=4)  # 名望第 1～4 段（週末季）
    # 立功給名望（3.1）：出陣攻打贏、挑戰本人打贏、決戰參戰（自己出手至少 1 回合）、自己那一邊大勝再加；寫 0 的那一項不給
    deeds: dict[str, int] = Field(default_factory=lambda: {"sortie": 1, "challenge": 2, "showdown": 2, "showdown_rout": 2})
    discounts: list[float] = Field(default_factory=lambda: [0.97, 0.94, 0.90, 0.85], min_length=4, max_length=4)  # 名望第 1～4 段的店家折扣（4.1）
    prize_tier: int = Field(default=2, ge=1, le=4)  # 重賞要名望第幾段（4.2）
    fame_affinity: int = Field(default=5, ge=0)  # 威震州郡以上見面時情誼起步（4.3）
    fame_affinity_tier: int = Field(default=3, ge=1, le=4)
    virtue_affinity: int = Field(default=3, ge=0)  # 敬俠的人遇上俠、喜狠的人遇上寇：每段 +3（5.2）
    cold_share: float = Field(default=0.8, ge=0, le=1)  # 敬俠的人遇上寇：加情誼的那幾類打八折（5.2）
    duel_chance: list[float] = Field(default_factory=lambda: [1.0, 1.1, 1.2, 1.2, 1.2], min_length=5, max_length=5)  # 頭目遇上的機會（名望第 0～4 段，4.4）
    duel_reward: float = Field(default=1.2, ge=1)  # 名動一方以上打贏頭目：經驗、銀兩、心得的倍數（4.4）
    duel_reward_tier: int = Field(default=2, ge=1, le=4)
    news_tier: int = Field(default=3, ge=1, le=4)  # 跨過這一段天下大事傳一句（4.5）
    famed_tier: int = Field(default=4, ge=1, le=4)  # 這一段起大場面打完天下大事點名（4.5）
    famed_news_per_day: int = Field(default=2, ge=0)  # 天下聞名點名一人一個遊戲日最多幾則
    wanted_tier: int = Field(default=3, ge=1, le=4)  # 敵方陣營每週掛通緝（4.6）
    wanted_silver: dict[int, int] = Field(default_factory=lambda: {3: 40, 4: 80})
    clinic_tier: int = Field(default=2, ge=1, le=4)  # 俠的醫館折扣從第幾段（5.2）
    clinic_share: float = Field(default=0.85, gt=0, le=1)
    black_market_tier: int = Field(default=1, ge=1, le=4)  # 寇的黑市從第幾段（5.2）
    # 素材的階 → 黑市收購價；三階只在素材四階開著時收（同 EconomyRules.sell_price，economy.sell_tiers）
    black_market_prices: dict[int, int] = Field(default_factory=lambda: {1: 3, 2: 8, 3: 24})
    official_tier: int = Field(default=2, ge=1, le=4)  # 江湖巨寇以上官府每週掛通緝（5.4）
    official_silver: dict[int, int] = Field(default_factory=lambda: {2: 30, 3: 50, 4: 80})
    official_hunter_tier: int = Field(default=2, ge=1, le=4)  # 俠一路第幾段揭得了官府通緝
    official_evil_loss: int = Field(default=3, ge=0)  # 被揭了官府通緝的人截殺打贏、交了這一張：惡名少幾點


class Bounties(_Strict):
    """懸賞榜（PM 2026-10-08 派工「加強散人玩法」；bounties.py）：enabled 開著、劇本有陣營就有，每季都有（懸賞榜設計 2.2），在城鎮類的地點查看（「懸賞榜」不花體力）。
    官軍、黃巾每週一各自動掛 kinds 裡的每一張（討伐兩張、打探、護送各一張）；劇本的每個陣營（官軍、黃巾、地方豪強）每週一另各掛
    give_kinds 裡的每一種（求兵，懸賞榜設計第四節；求藝企劃者 2026-10-21 拿掉）；玩家（投靠了陣營的人）可以花銀兩通緝一個敵對陣營的人。
    散人兩邊的都能接（通緝也是），陣營的人只能接自己陣營的；接了才算數，一個人同時最多接 max_taken 張。

    數字的依據：
    - silver：週末設定一天大約收 100 兩（Raid 的註解），一張討伐（要去指定的地方、打贏指定的對手）給 40 兩，比一場遊歷多一些；
      打探（去某處探索一次）最省事、給 20；護送（從一個城鎮走到另一個不相鄰的城鎮）花時間、給 30。
    - exp：完成一張給的經驗（本人與帶著的同伴，同打贏一場）。陣營的人能跟自己陣營的隊伍操練（零風險拿經驗），散人碰上的隊伍都是真打；
      整季機器人量到陣營的人季末等級比散人高三、四級（scripts/measure_sanren.py），懸賞的經驗是補這一截的主要來源。
    - deeds：散人完成一張記的俠名（遊俠名號的門檻 5／15／30／50）：一季隨機玩只靠事件到第 1、2 階，每週做兩三張就能多爬一兩階。
      陣營的人不記（名號凍結），照樣拿銀兩。
    - faction_share：陣營的人做自己陣營的懸賞，銀兩與經驗只拿幾成（他們另有軍令、貢獻、晉升與部下；懸賞榜主要是給散人的）。
    - auto_weeks：陣營的懸賞掛幾週（地點散在整張地圖上，走過去常常要大半週；只掛一週的話整季機器人揭了五十張只做成三張）。
    - quota：一張陣營懸賞前幾個完成的人有賞（照伺服器人數上限換算：100 人的量 3 張，最少 quota_min）。
    - post_min／post_max：通緝的賞金（押金）範圍；沒人完成就在 post_weeks 週後下榜、押金退回。wanted_deeds 是散人接通緝打贏記的俠名。
    - 求兵（arms）：不用揭，在城鎮的懸賞榜上直接交（交了就沒了），名額 give_quota、一張一人一次，陣營的人也拿全額
      （企劃者 2026-10-10）。give_attributes 是挑屬性的範圍（同一期三方不重複），give_list 是交出那一層最多列幾件（同拆解）。
      求藝（art：交一門合成出來的武學）企劃者 2026-10-21 拿掉（「懸賞榜直接把武學拿掉」：武學不再合成，求藝沒有來源），
      它的賞（"art" 那幾項、art_materials、art_weapon_chance……）一起拿掉。
      求兵的銀兩照交的那一把：arms_silver[品質] × arms_tier[階]（照兵器第二批的打造工錢算；三階 ×4 不是 ×3，手上多出來的三階上品
      交了才不虧工錢，懸賞榜設計 4.7 的期望值表），淬煉不加錢；經驗、心得、俠名是 exp／xinde／deeds 的 "arms"。"""

    enabled: bool = True  # 懸賞榜的開關（主機要整個關掉時用）；開著也要劇本有陣營才有（bounties.active）
    kinds: list[str] = Field(default_factory=lambda: ["strike", "strike", "scout", "escort"])
    give_kinds: list[str] = Field(default_factory=lambda: ["arms"])  # 另立一欄、不塞進 kinds：官軍、黃巾那一圈一個字都不動；每種最多一次
    give_attributes: list[str] = Field(default_factory=lambda: ["剛", "柔", "快", "慢"])
    give_quota: int = Field(default=3, ge=1)  # 不走 quota()：它在 30 人的正式設定與週末設定都算出 1
    give_list: int = Field(default=8, ge=1)
    silver: dict[str, int] = Field(default_factory=lambda: {"strike": 20, "scout": 10, "escort": 15})
    deeds: dict[str, int] = Field(default_factory=lambda: {"strike": 3, "scout": 2, "escort": 2, "wanted": 4, "arms": 2})
    exp: dict[str, int] = Field(default_factory=lambda: {"strike": 15, "scout": 10, "escort": 12, "wanted": 15, "arms": 30})
    xinde: dict[str, int] = Field(default_factory=lambda: {"arms": 10})
    arms_silver: dict[str, int] = Field(default_factory=lambda: {"下品": 20, "中品": 35, "上品": 50})
    arms_tier: dict[str, int] = Field(default_factory=lambda: {"1": 1, "2": 2, "3": 4, "4": 6})  # 四階 ×6（正式季整合 5.1）
    quota_base: int = Field(default=3, ge=1)
    quota_min: int = Field(default=1, ge=1)
    max_taken: int = Field(default=3, ge=1)
    auto_weeks: int = Field(default=2, ge=1)
    faction_share: float = Field(default=0.5, ge=0, le=1)
    post_min: int = Field(default=20, ge=1)
    post_max: int = Field(default=200, ge=1)
    post_weeks: int = Field(default=1, ge=1)


class DuelTuning(_Strict):
    """單人頭目戰（Joy 2026-10-10：「多加一些特殊事件，有種打小 boss 的感覺，也可以算是大事件的單人體驗版，可以放手一搏自訂行動」）。
    內容在 content/duels.json（DuelBoss）；規則在 tianxia/duel.py。一場 3～5 回合，每回合出決戰的三招之一（固守剋強攻、強攻剋奇襲、
    奇襲剋固守）或放手一搏；兩邊爭一條氣勢（edge，從 start 起，越高越是你佔上風），你用自己的氣血池（開打時的氣血）。

    數字的依據（全部【預設】，測完再調）：
    - 招式的推力 ＝ push_base ×（2 × 你的份量 ÷（你的＋他的）− 1）＋ counter_push × 剋（剋他 +1、被剋 −1、同招 0）＋ 運氣 ±luck。
      份量照決戰（battle_instance.move_scores：實力 × 適性 × 職位）；對手的份量是 strength(難度) × 0.75（適性的基準）。
      份量相當時一回合大約 ±8～12，四回合打完落在 70 以上（大勝）要剋中兩三次；練得比他強兩倍，不剋也推得動。
    - 每回合他打你：氣血池上限的 hit（8%），被剋 ×hit_countered、剋他 ×hit_countering，再乘 √(他的份量 ÷ 你的)（夾在 0.5～hit_scale_max）。
      最弱的新人四回合全被剋約 77%，不會一場打死；遊歷落敗是 30%。
    - 放手一搏照決戰（模型只評成功率、寫成敗兩版劇情；評不到 40；軍師 +10）：成了推 (gamble_base＋風險 × gamble_per_risk) × 實力倍數，
      扣池子 success_hp；沒成倒退 min(fail_cap, 風險 × fail_per_risk)、扣池子 fail_hp_base＋風險 × fail_hp_per_risk（同決戰）。
      單人戰裡成了的放手一搏要真的扭轉局面（大事件的單人體驗版），所以推得比決戰多（決戰一個人的推力要跟幾十個人分）。
    - 遇上：在有頭目的地點探索，先擲 explore_chance；同一隻一人一季最多 per_boss_season 次，任兩場之間隔 cooldown_seconds 世界秒。
    - 結果：打完最後一回合看氣勢，≥ big 大勝、≥ win 險勝、> draw 僵持，其餘落敗；中途到 early_win 以上提前大勝、early_lose 以下或池子見底
      提前落敗。獎勵照 reward_share 打折（落敗沒有），大勝、險勝另擲 legend_chance 撿一枚破境丹。"""

    explore_chance: float = Field(default=0.05, ge=0, le=1)
    per_boss_season: int = Field(default=2, ge=1)
    # 21 天季同一隻一人每週最多幾次（正式季整合 2.5【預設】；0＝不設，照 per_boss_season 一季算）：在 season21 設定裡打開
    per_boss_week: int = Field(default=0, ge=0)
    cooldown_seconds: float = Field(default=7200, ge=0)
    start: float = 50.0
    big: float = 70.0
    win: float = 55.0
    draw: float = 45.0
    early_win: float = 90.0
    early_lose: float = 10.0
    push_base: float = 14.0
    counter_push: float = 8.0
    luck: float = 4.0
    foe_fit: float = 0.75
    hit: float = Field(default=0.08, ge=0, le=1)
    hit_scale_max: float = Field(default=1.5, ge=0.5)
    hit_countered: float = 1.6
    hit_countering: float = 0.5
    gamble_base: float = 10.0
    gamble_per_risk: float = 0.15
    success_hp: float = Field(default=0.03, ge=0, le=1)
    fail_per_risk: float = 0.05
    fail_cap: float = 4.0
    fail_hp_base: float = 0.1
    fail_hp_per_risk: float = 0.0025
    tell_truth: float = Field(default=0.6, ge=0, le=1)  # 回合開始時寫的他的架勢有幾成是真的（其餘是虛招）
    reward_share: dict[str, float] = Field(default_factory=lambda: {"大勝": 1.0, "險勝": 0.7, "僵持": 0.3})
    legend_chance: dict[str, float] = Field(default_factory=lambda: {"大勝": 0.25, "險勝": 0.1})


class ArenaCrowdTuning(_Strict):
    """擂台的場邊事件（Joy 2026-10-17「加入一些隨機特殊的事件……讓擂台不那麼死板又加入一些玩家在世界努力過的元素，還有應用我們LLM的
    智能，但是也不要太容易觸發，會變成很膩或是主導戰場走向」；PM 定的預設；規則在 tianxia/arena_crowd.py）。全部【預設】，試玩後再調。

    - chance：這一回合有場邊事件可發生（兩邊至少一邊合條件）時擲中的機率；一場最多一件。5 回合合計約 1−(1−chance)^5。
    - outrage_chance：放手一搏被模型判成「離譜」時，觀眾發火的機率（不另擲 chance；一場最多一件照舊）。
    - patron_affinity：台下暗助的武將要跟那一邊情誼到幾。fame_tier／virtue_tier：名望、善惡稱號到第幾段才有人喝采、噓。
    - streak：連勝到幾場（或天下第一）台下才喊他的名號。veteran_hours：決戰打贏之後幾個世界小時內，台下有一起打過的弟兄。
    - edge：會推氣勢的事件推幾點（往得利的那一邊）；pool：動池子的事件動氣血上限的幾成（正的回、負的扣）。
    - weights：同一回合幾件都合條件時挑哪一件的權重（沒寫的當 1）。
    - write_budget_seconds：場邊那一句請模型重寫的預算（鎖外、背景執行緒；寫不出來照 content/arena_crowd.json 的固定句）。"""

    enabled: bool = True
    chance: float = Field(default=0.045, ge=0, le=1)
    outrage_chance: float = Field(default=0.5, ge=0, le=1)
    patron_affinity: int = Field(default=40, ge=0, le=100)
    fame_tier: int = Field(default=2, ge=1, le=4)
    virtue_tier: int = Field(default=2, ge=1, le=4)
    streak: int = Field(default=3, ge=1)
    veteran_hours: float = Field(default=24.0, ge=0)
    edge: dict[str, float] = Field(default_factory=lambda: {"patron": 4, "cheer": 3, "champion": 3, "veteran": 3})
    pool: dict[str, float] = Field(default_factory=lambda: {"boo": -0.04, "mate": 0.05, "outrage": -0.05})
    weights: dict[str, float] = Field(default_factory=dict)
    write_budget_seconds: float = Field(default=20.0, ge=0)


class ArenaTuning(_Strict):
    """擂台賽（隨時挑擂；docs/superpowers/specs/2026-10-14-擂台賽-design.md，Joy 2026-10-14 選「隨時挑擂」，同一天 PM 轉述的配套改成
    名次制）：報名的人留下一份守擂的分身，別人隨時來挑，對的是分身，只算本季。規則在 tianxia/arena.py。一場照頭目戰的純函式
    （duel.push_of、harm_of、gamble_roll），推力、挨打、放手一搏的數字都讀 DuelTuning；這裡只放擂台自己的。全部【預設】，試玩後再調。

    - reach：只能挑排在自己前面幾名以內的人（Joy「距離自己三名內」）。per_day：一個人一天挑幾次（不花體力；現實時間換日，同回體丹）。
    - pair_cooldown_seconds：同一個人挑同一個人的冷卻（世界秒，比照截殺）。defend_per_day：舊設定的「一天最多被挑幾場」，Joy 2026-10-15 拿掉（「一天挑戰6次鎖死可能要拔」），留著讓舊設定讀得進來，不再有作用。
    - rounds：一場幾回合（同奪璽單挑）。proxy_power：分身出招照三招份量的這個次方加權（同奪璽單挑的代打）。
    - streak_news：連勝到這個數的倍數上天下大事。
    - highlight_rate：一場裡最有戲的放手一搏成了、成功率不超過這個數就上天下大事，那個人名望 +highlight_fame（同決戰）。
    - board_size：擂台榜列幾名。
    - wages：每天換日那一刻照名次發的俸（銀兩, 名望），第 1 名起一名一格，格數以外沒有；要打過至少一場。
    - prizes：季末前三名的名望；prize_treasure 開著時另給一件寶物（掉落池裡你還沒有的，都有了換銀兩；寶物關著不給）。"""

    enabled: bool = True
    reach: int = Field(default=3, ge=1)
    famous_reach: int = Field(default=5, ge=1)  # 名聲 4.7：天下聞名的人守擂，排在他後面幾名以內的人都挑得到他（renown.on(content, "arena_reach")）
    per_day: int = Field(default=10, ge=1)
    pair_cooldown_seconds: float = Field(default=10800, ge=0)
    defend_per_day: int = Field(default=0, ge=0)
    rounds: int = Field(default=5, ge=1)
    proxy_power: float = Field(default=4, ge=0)
    streak_news: int = Field(default=5, ge=1)
    highlight_rate: int = Field(default=30, ge=0, le=100)
    highlight_fame: int = Field(default=1, ge=0)
    board_size: int = Field(default=10, ge=1)
    wages: list[tuple[int, int]] = Field(default_factory=lambda: [(100, 5), (60, 3), (60, 3)] + [(30, 1)] * 7)
    prizes: list[int] = Field(default_factory=lambda: [30, 20, 10])
    prize_treasure: bool = True
    crowd: ArenaCrowdTuning = Field(default_factory=ArenaCrowdTuning)  # 場邊事件（見 ArenaCrowdTuning；tianxia/arena_crowd.py）


class TavernTuning(_Strict):
    """酒肆（設計稿 https://claude.ai/artifact/3CfrzfpT1HzCxy6S985Q5W，企劃者 2026-10-18「可以，做精緻一些，包含氛圍感」）：帶「酒肆」標籤的
    城鎮有一間，進城才去得到。打聽消息、查人、交情、素材、題壁、請酒、雇殺手、問酒家，都花銀兩。規則在 tianxia/tavern.py。
    價錢以正式季（21 天）為準，季短的照季長打折（price_full_days、price_floor）。全部【預設】，試玩後再調。

    「越有名越好打聽」（企劃者 2026-10-18）：每一次打聽算打聽度＝名氣＋遠近＋近況（tavern.reach），照 reach_* 換成問不問得到、多準。"""

    enabled: bool = True
    price_full_days: float = Field(default=21.0, gt=0)  # 季長到這麼多天照原價；短的照比例打折
    price_floor: float = Field(default=0.3, ge=0, le=1)  # 最低打到幾折（週末短季）
    news_price: int = Field(default=10, ge=0)  # 聽消息
    news_days: float = Field(default=3.0, gt=0)  # 酒家說得出最近幾天（季曆天）的傳聞
    seek_price: int = Field(default=30, ge=0)  # 查人在哪
    ties_price: int = Field(default=20, ge=0)  # 打聽交情
    material_prices: dict[int, int] = Field(default_factory=lambda: {1: 5, 2: 10, 3: 25, 4: 40})  # 打聽素材：照階
    wall_price: int = Field(default=5, ge=0)  # 題壁
    wall_keep: int = Field(default=12, ge=1)  # 每間酒肆的牆留最近幾句
    wall_chars: int = Field(default=20, ge=1)  # 一句最多幾個字
    treat_price: int = Field(default=30, ge=0)  # 請全店喝酒（一天一次）
    treat_fame: int = Field(default=1, ge=0)
    treat_hours: float = Field(default=1.0, ge=0)  # 請酒之後多久（世界小時）進門的人還看得到
    hide_price: int = Field(default=50, ge=0)  # 藏行跡（一個遊戲日）
    hide_reach: int = Field(default=2, ge=0)  # 藏行跡讓別人打聽你的打聽度少幾點
    trace_price: int = Field(default=40, ge=0)  # 反查：誰打聽我、誰雇殺手找我
    refund_share: float = Field(default=0.5, ge=0, le=1)  # 問不到時退幾成
    whisper_keep: int = Field(default=10, ge=1)  # 身上留最近幾則風聲
    note_keep: int = Field(default=8, ge=1)  # 酒肆裡留最近幾則酒家的回話
    named_from: int = Field(default=2, ge=0)  # 打聽你的人名望到第幾段，風聲裡直接說名號
    offline_hours: float = Field(default=24.0, ge=0)  # 現實多久沒上線算「近來沒人見過他」
    # 買殺手（設計第六節）
    hit_prices: list[int] = Field(default_factory=lambda: [20, 40, 60], min_length=1)  # 三檔殺手
    # 殺手威力＝對方本人威力 × 這個（企劃者 2026-10-27 酒肆殺手優化：以前 0.85／1.0／1.15 幾乎殺不成，提高到真的會得手）
    hit_power: list[float] = Field(default_factory=lambda: [1.3, 1.5, 1.7], min_length=1)
    hit_hours: float = Field(default=6.0, gt=0)  # 單子有效幾個現實小時
    hit_pair_hours: float = Field(default=24.0, ge=0)  # 同一對人多久只能雇一次（現實小時）
    hit_silver_share: float = Field(default=0.10, ge=0, le=1)  # 殺手贏：對方失幾成銀兩
    hit_silver_cap: int = Field(default=60, ge=0)
    # 殺手贏：對方氣血只剩 1（企劃者 2026-10-27「上線回來時氣血只剩 1 點，強迫去醫館」），之後 hit_shield_hours 個現實小時殺手找不上他
    hit_shield_hours: float = Field(default=6.0, ge=0)
    # 下線也找得到：同步時離上一次同步超過 hit_offline_minutes 分鐘（現實），照他下線那一刻站的地方（城外、不在路上）擲一次
    hit_offline_minutes: float = Field(default=10.0, ge=0)
    # 同一個雇主找同一個人，每失手一次（被打退或不分高下），下一張單價錢 +hit_fail_price_step 成、殺手威力 +hit_fail_power_step，
    # 最多疊 hit_fail_max 次；得手歸零，換季自然歸零（單子照季存）
    hit_fail_price_step: float = Field(default=0.5, ge=0)
    hit_fail_power_step: float = Field(default=0.1, ge=0)
    hit_fail_max: int = Field(default=3, ge=0)
    hit_evil: int = Field(default=3, ge=0)  # 雇主得的惡名
    hit_bounty_share: float = Field(default=0.25, ge=0, le=1)  # 對方打贏：搜出雇金的幾成
    hit_win_fame: int = Field(default=1, ge=0)
    hit_reveal: float = Field(default=0.5, ge=0, le=1)  # 對方打贏時問出雇主的基本機會（雇主每一段名望 +0.1）
    hit_warn: float = Field(default=0.4, ge=0, le=1)  # 單子掛上那一刻對方聽到風聲的基本機會（對方每一段名望 +0.05）
    hit_find_drop: float = Field(default=0.2, ge=0, le=1)  # 打聽度每比 5 少一點，殺手找到人的機會少這麼多
    guard_price: int = Field(default=10, ge=0)  # 雇保鏢
    guard_hours: float = Field(default=6.0, ge=0)
    guard_scale: float = Field(default=0.85, ge=0)  # 保鏢在身邊時殺手的威力再乘這個
    hush_price: int = Field(default=20, ge=0)  # 雇主封口：被供出的機會減半
    # 問酒家（AI 問答，設計第八節）
    ask_price: int = Field(default=20, ge=0)
    ask_chars: int = Field(default=40, ge=1)  # 一句最多幾個字（企劃者 2026-10-27 問酒家強化：30 → 40）
    ask_budget_seconds: float = Field(default=30.0, ge=0)
    chatter_hours: float = Field(default=1.0, gt=0)  # 酒客閒談每間酒肆多久換一段（世界小時）
    # 託酒家留意（設計第三節）：查人時多付一半，之後那個人打聽得到確切地點（打聽度 3 以上）時捎信，寫進江湖紀錄
    watch_share: float = Field(default=0.5, ge=0)
    watch_hours: float = Field(default=6.0, gt=0)  # 留意多久（現實小時）
    watch_keep: int = Field(default=3, ge=0)  # 一個人同時最多託幾個


class DuelFoe(_Strict):
    """一隻頭目的一個面貌：照玩家的陣營挑（side 是他站的陣營；跟玩家同陣營的不挑，換下一個）。文字待內容方改。
    intro 是遇上時的場景；win、lose 是你打贏、打輸時的結語。moves 是他出招的偏好（三招的權重，沒寫的當 1）。"""

    side: str | None = None
    name: str
    title: str
    intro: str
    win: str
    lose: str
    moves: dict[str, float] = Field(default_factory=dict)


class DuelBoss(_Strict):
    """一隻單人頭目（content/duels.json）：在 locations 這幾個地點探索時可能遇上。difficulty 照地點的危險度定（同一帶最強的對手再高一點），
    rounds 是幾回合（3～5）。獎勵照結果打折（DuelTuning.reward_share），drops 只有大勝、險勝才給（每一樣一個）。
    foes 照玩家陣營挑面貌（DuelFoe.side）：每個陣營都要挑得到一個不是自己人的。"""

    id: str
    locations: list[str]
    difficulty: float = Field(gt=0)
    rounds: int = Field(default=4, ge=3, le=5)
    attribute: str | None = None  # 他的路數（剋不剋得到你身上武學的屬性，同遊歷的對手）
    exp: int = Field(default=0, ge=0)
    silver: int = Field(default=0, ge=0)
    xinde: int = Field(default=0, ge=0)
    fame: int = Field(default=0, ge=0)  # 打贏（大勝、險勝）的名望
    drops: list[str] = Field(default_factory=list)
    foes: list[DuelFoe] = Field(min_length=1)


class Raid(_Strict):
    """截殺（敵對陣營的玩家對打，企劃者 2026-10-08 在決策卡選「有限制地開」：「只能打敵對陣營、新手期和城裡不能打，
    輸了損失一點銀兩和氣血，同一人有冷卻」）。玩家卡上的一顆鈕，不必對方同意，對方下線、在忙也照打（他在「此地還有」的名單上就行）。
    雙方各用本人的威力（同切磋：同伴、部下不上場，比的是兩個人；也免得帶滿同伴的人變成路霸），照 encounter 的單次判定。

    數字的依據（損失要小，不能讓人被打到玩不下去）：
    - 發起的人花 stamina（10）體力：比一次遊歷（6）貴，截殺不能比遊歷更划算地刷。
    - 輸的一方失 silver_share（5%）的銀兩、最多 silver_cap（15）兩，贏的拿走其中 take_share（一半，進位）；其餘散落。
      週末設定每天大約收 100 兩，最多 15 兩約一兩場遊歷；照比例扣，身上越少扣得越少，永遠扣不光。
    - 輸的一方扣氣血上限的 hp_loss（8%），不變成內傷（自己會回，不必花錢療傷）；遊歷落敗是 30%、其中兩成變內傷。
    - 平手（僵持）誰都不失什麼，發起的人的體力照付。
    - 同一個人截殺同一個目標要隔 pair_cooldown_seconds（3 小時）；被截殺過的人 shield_seconds（1 小時）之內誰都不能再截殺他，
      不論上一場誰贏。一季（週末 60 小時）一個人最多被截殺約 60 次，每次最多 15 兩、照比例扣，加起來扣不光。
      截殺每季都有之後（懸賞榜設計 3.7）：14 天的季有 336 小時，保護時間照舊 1 小時，一季最多可能被截約 300 次；每小時的比例跟週末一樣，
      一季加起來的量多五倍多。要不要另一組數字等 sim_server_bots 量完再定（設計 14.2 第 12 條）。
    - 贏的一方記一點本季貢獻（contrib_per_push × win_contrib_push）：截殺是替陣營做事，但比推大勢一點還少，不會變成升階的捷徑。
      只在第一季規則開著時記（其他季沒有晉升；Game._raid_spoils）。
    - enabled：主機的緊急開關（懸賞榜設計 2.2 第 3 點）。截殺每季都有、劇本有陣營就有；上線之後假人截殺真人太兇時改設定就關，不必退版。
      關著時通緝一起收（通緝只能靠截殺交差）：押不了、揭不了、不算張數，已經押的照期限退押金。
    時間都是世界秒（跟邀請的逾時同一套）。"""

    enabled: bool = True
    stamina: int = Field(default=10, ge=0)
    silver_share: float = Field(default=0.05, ge=0, le=1)
    silver_cap: int = Field(default=15, ge=0)
    take_share: float = Field(default=0.5, ge=0, le=1)
    hp_loss: float = Field(default=0.08, ge=0, le=1)
    pair_cooldown_seconds: float = Field(default=3 * 3600, ge=0)
    shield_seconds: float = Field(default=3600, ge=0)
    win_contrib_push: int = Field(default=1, ge=0)


class ShowdownPay(_Strict):
    """全服決戰的軍餉（試玩回饋 2026-10-08，Joy：「參加就會有基本的軍餉獎勵，獲勝有更多」）。參戰者收場後各自補戰報時拿
    （Game._file_showdown，下線的人回來補，只發一次），這一季打的才發；沒打完收兵的不發。

    份量照個人戰功（battle_instance.merit）：戰功等於只出手 full_rounds 回合的那一份算一倍，帶頭、搏成、打傷、撐住另外加，最多 share_cap 倍；
    一回合都沒出手（掛機、全程被代選）只拿 idle_share。
    數字的依據：週末設定平衡量到每天大約收 100 兩，一場決戰的軍餉落在半天到一天的遊歷收入——滿出手的基本軍餉 40 兩、
    大勝再加一倍到 80 兩；經驗照遊歷一場 10～15 點，基本 60 點約四五場遊歷。"""

    silver: int = Field(default=40, ge=0)  # 基本軍餉（滿出手）
    exp: int = Field(default=60, ge=0)
    full_rounds: int = Field(default=6, ge=1)  # 出手幾回合算滿（黃巾決戰一場 9 回合，時刻表決戰也是 3 幕 × 3）
    idle_share: float = Field(default=0.1, ge=0, le=1)  # 一回合都沒出手的人拿幾成
    share_cap: float = Field(default=2.0, ge=1)  # 份量照戰功算（戰功 ÷ 出手 full_rounds 回合的戰功），最多拿到這麼多倍（Joy 2026-10-10 個人戰功）
    win_bonus: dict[str, float] = Field(default_factory=lambda: {"大勝": 1.0, "險勝": 0.5})  # 贏的一方另加基本軍餉的幾倍
    # 投靠了陣營的人另記本季貢獻（照推大勢的帳：contrib_per_push × 這幾點 × 份量）；臨時投效的散人、第三方不記
    contrib_push: int = Field(default=2, ge=0)  # 參戰就記的
    win_contrib_push: dict[str, int] = Field(default_factory=lambda: {"大勝": 5, "險勝": 3})  # 贏的一方另記的


class SmithQuality(_Strict):
    """打造的品質機率（兵器設計 4.3；跟 FuseQuality 同一套推法，fusion.odds_from_points）：這一爐的組成加成造化分，
    從 odds（下品 50／中品 30／上品 20）往上或往下推，上品夾在 up_range、下品夾在 low_range。數字都是【預設】。
    天時地利（企劃者 2026-10-10 第二批附帶決定 b：沿用合成那一套）預設 0（測試內容不開），正式值在 config.json：
    地利同合成（此地探索悟得到同屬性的意境，fusion.terrain_here），戰場、心靜也同合成；兵器沒有正邪，所以沒有晝夜。"""

    odds: dict[str, float] = Field(default_factory=lambda: {"下品": 50, "中品": 30, "上品": 20})
    up_per_point: float = Field(default=0.5, ge=0)
    low_per_point: float = Field(default=1.0, ge=0)
    up_range: tuple[float, float] = (5, 45)
    low_range: tuple[float, float] = (15, 80)
    # 輔料比主料高幾階 → 分數（「-1」是輔料低一階）：同階或更高加分、低階扣分（4.3）
    # 差三階（正式季整合 5.1：主料四階配一階輔料 −24、主料一階配四階輔料 +16）
    aux_tier: dict[str, float] = Field(default_factory=lambda: {"-3": -24, "-2": -16, "-1": -8, "0": 4, "1": 8, "2": 12, "3": 16})
    wis_weight: float = Field(default=0.5, ge=0)  # 悟性：stat_factor 多出來的百分點 × 這個（同 FuseQuality.wis_weight）
    practice_point: float = Field(default=2, ge=0)  # 熟手：這個配方這一季你打過一次加幾分
    practice_cap: float = Field(default=10, ge=0)  # 熟手最多加幾分
    terrain: float = 0  # 地利：此地探索悟得到跟打出來的兵器同屬性的意境（fusion.terrain_here，同合成）
    battlefield: float = 0  # 戰場：打出剛的兵器、人在營寨或（第一季）亂局的大區（fusion.battlefield_here）
    calm: float = 0  # 心靜：出關之後 calm_hours 遊戲小時之內（fusion.calm_now）
    calm_hours: float = Field(default=2, ge=0)
    setting_max: int = Field(default=2, ge=0)  # 一爐最多算幾條天時地利（照分數的絕對值挑）
    setting_good: str = ""  # 天時地利合起來加分時，結果多一句
    setting_bad: str = ""  # 合起來扣分時，結果多一句
    shown_from: float = Field(default=3, ge=0)  # 說明那一句只寫分數絕對值到這麼多的因素，最多兩個
    # 說明那一句：因素 → [加分時, 扣分時]（待 joy 潤）
    lines: dict[str, list[str]] = Field(default_factory=lambda: {
        "aux": ["輔料壓得住主料", "輔料壓不住主料"],
        "wis": ["你心思靈透", "你心思還不夠靈透"],
        "practice": ["這個配方你打得順手", ""],
        "terrain": ["此地水土與這股料性相合", ""],
        "battlefield": ["殺伐之氣未散", ""],
        "calm": ["出關未久，心如止水", ""],
    })


class WeaponRules(_Strict):
    """兵器（docs/superpowers/specs/2026-10-09-兵器-design.md）。數字都是【預設】，量表（scripts/measure_weapons.py）校準後可以改。
    加成＝（階＋品質＋淬煉＋屬性搭配）×（edge_floor＋（1－edge_floor）×鋒利度／100），乘在本人的 Boost.factor；
    參考內外同屬性 +20%、正邪共鳴最多 +20%，最好的兵器約抵其中一項。"""

    enabled: bool = True
    # 四階 17%（正式季整合 5.1：四階名器上品 17＋2＋4＝23%，剛好追平仿品）
    tier_bonus: dict[str, float] = Field(default_factory=lambda: {"1": 0.05, "2": 0.10, "3": 0.15, "4": 0.17})
    quality_bonus: dict[str, float] = Field(default_factory=lambda: {"下品": 0.0, "中品": 0.02, "上品": 0.04})
    temper_step: float = Field(default=0.01, ge=0)  # 淬煉一次加多少（第二批才淬得了）
    match: float = Field(default=0.05, ge=0)  # 跟身上武學同屬性加、相剋扣
    edge_floor: float = Field(default=0.5, ge=0, le=1)  # 全鈍時剩幾成加成
    wear: dict[str, int] = Field(default_factory=lambda: {"大勝": 2, "險勝": 2, "僵持": 3, "落敗": 5})  # 一場扣多少鋒利度
    style_soft: float = Field(default=0.1, ge=0)  # 兵器屬性落在大場面對手怕的那一路：威力 ×(1＋這個)
    style_hard: float = Field(default=0.1, ge=0)  # 落在他最會對付的那一路：×(1－這個)
    shop_price: int = Field(default=40, ge=0)  # 鐵匠鋪架上一階下品的價錢（開局 50 兩買得起一把）
    repair_silver: int = Field(default=5, ge=0)  # 修一次的工錢（另加一個一階素材）
    drop_chance: float = Field(default=0.03, ge=0, le=1)  # 打贏遊歷或野怪掉一把一階下品的機會
    rack_cap: int = Field(default=100, ge=1)  # 裝備庫幾格（企劃者 2026-10-10：原來的 6 格改 100；程式裡的 rack 就是玩家看到的「裝備庫」）
    edge_warn: int = Field(default=30, ge=0, le=100)  # 鈍到這裡以下時江湖紀錄提醒一次
    forge_silver: dict[str, int] = Field(default_factory=lambda: {"1": 20, "2": 60, "3": 150, "4": 300})  # 打造的工錢（4.2）：照主料的階；素材另算、不花體力心得（四階 300，正式季整合 5.1）
    quality: SmithQuality = Field(default_factory=SmithQuality)  # 打造的品質機率（見 SmithQuality）
    temper_max: int = Field(default=5, ge=0)  # 淬煉最多幾次（4.7）；每次 +temper_step
    temper_silver: dict[str, int] = Field(default_factory=lambda: {"1": 0, "2": 30, "3": 80, "4": 150})  # 淬煉一次的工錢，照用的那個素材的階（4.7；四階料 150，正式季整合 5.3）
    named_bonus: float = Field(default=0.02, ge=0)  # 名器（照隱藏配方打出來的）的加成多這麼多（打造隱藏配方設計 4.2）
    copy_base: float = Field(default=0.19, ge=0)  # 神器仿品的基本加成，取代階那一格（打造隱藏配方設計 4.3；品質一律上品再 +4%，合計 23%）
    original_base: float = Field(default=0.22, ge=0)  # 神器原品的基本加成（同上；合計 26%）；不另加名器的 named_bonus
    # 名將本命兵器（兵器設計 4.10；打造第三批）。跟頂層的 Config.signature_affinity（70，本命武學）不是同一個數
    signature_affinity: int = Field(default=80, ge=0, le=100)  # 情誼到這裡，名將把本命兵器送你
    signature_wins: int = Field(default=3, ge=1)  # 這一季打贏他本人幾次（大勝、險勝），他讓你奪走（只有內容寫了 figure 的那幾位）


class ArmorRules(_Strict):
    """防具（docs/superpowers/specs/2026-10-10-裝備四欄-design.md 第四節）。數字都是【預設】（企劃者 2026-10-10「全部照預設」），
    量表（scripts/measure_gear.py）校準後可以改。減損＝（階＋品質＋淬煉＋對上內功）夾在 0 以上
    ×（edge_floor＋（1－edge_floor）×耐久度／100）；本人一場仗扣的氣血乘（1－min(total_cap, 化勁＋減損)），截殺輸的一方只乘防具。
    不掛第一季開關（2.6，同兵器）。打造與淬煉（四欄設計 4.7；打造隱藏配方設計第九節）的數字照兵器，各欄自己一組（2.6、3.4），
    天時地利正式值在 config.json。"""

    enabled: bool = True
    tier_cut: dict[str, float] = Field(default_factory=lambda: {"1": 0.06, "2": 0.12, "3": 0.18, "4": 0.20})  # 查表用 str(tier)，同 WeaponRules.tier_bonus（四階 20%，正式季整合 5.1）
    quality_cut: dict[str, float] = Field(default_factory=lambda: {"下品": 0.0, "中品": 0.02, "上品": 0.04})
    temper_step: float = Field(default=0.01, ge=0)  # 淬煉一次加多少（4.1）
    match: float = Field(default=0.03, ge=0)  # 跟身上內功同屬性加、相剋扣（4.2）
    edge_floor: float = Field(default=0.5, ge=0, le=1)  # 全壞時剩幾成減損（4.5：不會壞掉消失）
    total_cap: float = Field(default=0.6, ge=0, le=1)  # 跟化勁合計最多減幾成（4.3）
    wear: dict[str, int] = Field(default_factory=lambda: {"大勝": 1, "險勝": 2, "僵持": 3, "落敗": 5})  # 一場扣多少耐久度（4.5）
    shop_price: int = Field(default=40, ge=0)  # 鐵匠鋪架上一階下品的價錢（4.6，同武器）
    repair_silver: int = Field(default=5, ge=0)  # 修一次的工錢，另加一個一階素材（4.5）
    edge_warn: int = Field(default=30, ge=0, le=100)  # 耐久低到這裡以下時江湖紀錄提醒一次
    forge_silver: dict[str, int] = Field(default_factory=lambda: {"1": 20, "2": 60, "3": 150, "4": 300})  # 打造的工錢（同兵器 4.2）：照主料的階
    quality: SmithQuality = Field(default_factory=SmithQuality)  # 打造的品質機率（同兵器 4.3；天時地利預設 0，正式值在 config.json）
    temper_max: int = Field(default=5, ge=0)  # 淬煉最多幾次（4.1）；每次 +temper_step
    temper_silver: dict[str, int] = Field(default_factory=lambda: {"1": 0, "2": 30, "3": 80, "4": 150})  # 淬煉一次的工錢，照用的那個素材的階（同兵器 4.7）
    named_cut: float = Field(default=0.02, ge=0)  # 名器的減損多這麼多（同上）
    copy_cut: float = Field(default=0.22, ge=0)  # 神器仿品的基本減損，取代階那一格（打造隱藏配方設計 4.3、5.6；上品再 +4%，合計 26%）
    original_cut: float = Field(default=0.25, ge=0)  # 神器原品的基本減損（合計 29%）；不另加名器的 named_cut


class MountRules(_Strict):
    """坐騎（docs/superpowers/specs/2026-10-10-裝備四欄-design.md 第五節；裝備二）。數字都是【預設】（企劃者 2026-10-10「全部照預設」），
    量表（scripts/measure_mounts.py）校準後可以改。省體力（趕路、疾行）與路上快（步行、趕路）照階查表、再加品質；騎兵、脫身只照階；
    全部乘飽足係數（edge_floor＋（1－edge_floor）×飽足度／100）。腳力＝省體力（含品質）×飽足係數，截殺追逃比的是兩邊的腳力。
    階：1 駑馬、2 良駒、3 名駒；查表用 str(tier)（同 WeaponRules.tier_bonus）。不掛第一季開關（2.6，同兵器、防具）。"""

    enabled: bool = True
    stamina_save: dict[str, float] = Field(default_factory=lambda: {"1": 0.25, "2": 0.40, "3": 0.55})  # 疾行的體力省幾成（5.1）
    speed: dict[str, float] = Field(default_factory=lambda: {"1": 0.30, "2": 0.45, "3": 0.60})  # 步行的時間快幾成（5.1）
    quality_bonus: dict[str, float] = Field(default_factory=lambda: {"下品": 0.0, "中品": 0.03, "上品": 0.05})  # 只加在上面兩列
    cavalry: dict[str, float] = Field(default_factory=lambda: {"1": 0.05, "2": 0.10, "3": 0.15})  # 決戰強攻、奇襲的份量多幾成（5.9）
    escape: dict[str, float] = Field(default_factory=lambda: {"1": 0.30, "2": 0.50, "3": 0.70})  # 落敗策馬脫身、保住銀兩的機會（5.11）
    raid_escape_cap: float = Field(default=0.4, ge=0, le=1)  # 截殺追逃：守方腳力－攻方腳力最多算幾成（5.10）
    edge_floor: float = Field(default=0.5, ge=0, le=1)  # 飽足係數：餓到底剩幾成（5.4：不會餓死、不會跑掉）
    hunger: dict[str, int] = Field(default_factory=lambda: {"walk": 5, "hurry": 5, "dash": 10})  # 每抵達新的一站扣的飽足度（5.4）
    shop_price: int = Field(default=100, ge=0)  # 馬市一匹駑馬下品的價錢（5.5）
    edge_warn: int = Field(default=30, ge=0, le=100)  # 飽足低到這裡以下時江湖紀錄提醒一次（5.4）


# 寶物的八種效果（裝備四欄 6.2）：win_material、legend 是企劃者 2026-10-11 換掉招募、氣血回復的兩種
TREASURE_EFFECTS = ("cultivate", "insight", "win_xinde_pct", "win_exp_pct", "seclusion", "audience", "win_material", "legend")
TreasureEffect = Literal["cultivate", "insight", "win_xinde_pct", "win_exp_pct", "seclusion", "audience", "win_material", "legend"]
GOOD_HORSE = "good_horse"  # Effect.gear 寫這個是給一匹良駒（裝備四欄 5.7）；寶物表與名駒的 id 不能叫這個


class TreasureRules(_Strict):
    """寶物與好馬的來源（docs/superpowers/specs/2026-10-10-裝備四欄-design.md 第六節、5.7；裝備三）。數字都是【預設】（企劃者 2026-10-10
    「全部照預設」），量表（scripts/measure_treasures.py）校準後可以改。效果的數字放這裡，內容（content/gear.json）只寫名字與效果種類；
    同一種效果的寶物數字一樣（名將的贈禮也不另外強）。乘的效果（cultivate、insight、legend）寫倍數，加的寫加多少：win_xinde_pct、
    win_exp_pct、seclusion 是比例，audience 是點數，win_material 是機率。不掛第一季開關（2.6，同兵器、防具、坐騎）；良駒、名駒的數字照 Config.mounts。"""

    enabled: bool = True
    effects: dict[str, float] = Field(default_factory=lambda: {
        "cultivate": 1.2, "insight": 1.5, "win_xinde_pct": 0.2, "win_exp_pct": 0.15,
        "seclusion": 0.25, "audience": 3, "win_material": 0.25, "legend": 2.0,
    })
    bounty_treasure_chance: float = Field(default=0.15, ge=0, le=1)  # 每週一掛單時每一邊擲一次：掛一件寶物（6.4）
    bounty_horse_chance: float = Field(default=0.10, ge=0, le=1)  # 同上、分開擲：掛一匹良駒（5.7、6.4）
    horse_quality: dict[str, float] = Field(default_factory=lambda: {"下品": 0.5, "中品": 0.3, "上品": 0.2})  # 懸賞與奇遇給的良駒品質的權重（5.7）
    challenge_chance: float = Field(default=0.20, ge=0, le=1)  # 打贏大勢人物本人掉一件掉落池的寶物（6.4）
    gift_affinity: int = Field(default=60, ge=0, le=100)  # 名將贈禮的情誼門檻（6.4；在本命武學 signature_affinity 70 之前）
    dup_silver: int = Field(default=50, ge=0)  # 掉落池都有了、奇遇給的那一件已經有了，改給這麼多銀兩（6.5）


# 引將、頒詔、承露、傳檄、收心（第 2 批）；鎮地、補缺（第 3 批，建在翻地與爭搶上）
SealActKind = Literal["yinjiang", "banzhao", "chenglu", "chuanxi", "shouxin", "zhendi", "bujue"]


class ShardDef(_Strict):
    """一片傳國玉璽的碎片（content/seal.json，玉璽碎片設計 7.1）：名字與一句說明交 joy 潤，數字在 Config.seal.effects。"""

    id: str
    name: str
    part: str  # 取自玉璽的哪一部分
    effect: str  # Config.seal.effects 的鍵（改版關著時的那一個效果）
    note: str = ""
    # 改版（Config.seal.revamp 開著）的常駐成長或生活效果：Config.seal.revamp.effects 的鍵，一片可以好幾個（玄紐、歸心）；
    # 戰力 ×revamp.power 每片都有、不寫在這裡（docs/superpowers/specs/2026-10-21-玉璽碎片改版-design.md 第三章）
    effects: list[str] = Field(default_factory=list)
    # 改版第 2、3 批：這一片的獨門行動（tianxia/seal_acts.py；設計第三章）；載入時一種只給一片
    act: SealActKind | None = None


class MandateTuning(_Strict):
    """天命之季與天命之爭（玉璽碎片設計第八節；玉璽二）。全部是【預設】。"""

    start_shift: int = Field(default=3, ge=0)  # 天命之爭的起點：每片往握著它的那一軍偏幾點（8.3）
    start_shift_cap: int = Field(default=12, ge=0)  # 偏移合計最多幾點
    holder_weight: float = Field(default=1.2, ge=1)  # 手上有碎片的人到場，份量的倍數（只在天命之爭；碎片本身不加威力）
    fame: int = Field(default=10, ge=0)  # 得天命那一方的參戰者名望
    pay_scale: int = Field(default=2, ge=1)  # 得天命那一方的軍餉（銀兩、經驗）倍數：只寫在這裡，Game._showdown_pay 讀
    decisive_from_week: int = Field(default=13, ge=1)  # 天命之季從第幾週起才提前收季（13：等於不提前收，8.2）
    recall_battles: int = Field(default=2, ge=0)  # 天命之季，時刻表上標了 seal 的前幾場收場時各喚回一片（8.2）


class SealCacheTuning(_Strict):
    """領地爭奪的季，碎片從哪裡來（領地爭奪設計 3.9、4.8；計畫 Task 14、15）：開季先擲 hide_chance，擲中就把一片未現世的碎片藏在
    一塊開季中立的區塊（核心照 core_weight 加權），之後在那一塊探索（四種都算）每一下擲 find_chance，那一塊此刻歸你的陣營 ×own_scale。
    一季最多現世一片；季末沒人撿到就清掉、下一季重擲。藏在哪一塊不公開。全部是【預設】，機率照 scripts/measure_seal.py 的
    --mandate-mc 對到「湊滿七片平均約 16～20 季」（企劃者 2026-10-20），見 docs/guide/玉璽碎片.md 的量表。"""

    # 開季這一季有沒有一片藏在中立地（PM 先定 40%，沒動）。它是速度的上限：探索再多也快不過 7 ÷ 0.4 ＝ 17.5 季
    hide_chance: float = Field(default=0.4, ge=0, le=1)
    # 在藏碎片的那一塊每探索一下撿到的機率（非常低）。PM 先定 0.5%，量表（--mandate-mc，藏處一季被探索 300 次）量到平均 20.5 季、
    # 比企劃者要的 16～20 季長一點，調成 1%：藏處一季被探索 200～1000 次都落在 17.4～18.9 季，150 次約 20.5 季、100 次約 24 季
    find_chance: float = Field(default=0.01, ge=0, le=1)
    own_scale: float = Field(default=1.5, ge=1)  # 那一塊此刻歸你的陣營時的倍數（設計 3.9「機率再高一點」；PM 先定 ×1.5）
    # 核心加權（輿圖簡化設計 3.1，企劃者定「所有開季中立的區塊都可能藏，核心的機率最高」）：地點落在 core_regions 這些大區 id 裡的，
    # 藏的權重是 core_weight，其餘是 1。新地理的核心自成一區、id 是 "core"（dev/map-1b 的 map.json）；今天的地圖沒有這一區，所以全是 1。
    # 權重 3＝核心三處合起來約佔四成多（中原十二處＋核心三處），每一處的機率是中原每一處的三倍【暫，待企劃者看過量表】
    core_regions: list[str] = Field(default_factory=lambda: ["core"])
    core_weight: float = Field(default=3.0, ge=1)


class SealActsTuning(_Strict):
    """玉璽碎片改版第 2 批：獨門行動（設計第三章最右欄、五之一；計畫 docs/superpowers/plans/2026-10-21-玉璽碎片改版-2.md）。
    全部是【預設】，等 21 天的季試玩再調。「天」在有季曆的季（第一季的章：週末、7 天、21 天）是季曆天，14 天的季是世界天（seal_acts.day_seconds）。
    - uses、gap_days：每一片一季幾次、兩次之間隔幾天（次數記在全服的碎片上，換手跟著碎片走）；days：每個行動生效幾天。
    - sense_points、cultivate：頒詔——靜心感悟擲中的機會多幾個百分點（夾在 sense_rate_range 的上限）、衝絕學的機會倍數
      （契機與服丹都乘，cultivation.peak_scale；企劃者 2026-10-21：武學重構之後修練不再擲升品）。
    - stamina：承露——那一區體力回復的倍數（醫館療傷不收錢，沒有數字）。
    - push：傳檄——那一軍在那條線上推的量的倍數（盡頭阻力與每人每日上限照舊）。
    - affinity：收心——跟他說話、宴客敬酒的情誼漲幅倍數（求見不看門檻，沒有數字）。
    - hold_hours：鎮地（第 3 批）——那一塊誰都推不動幾個季曆小時（「一日」的 hold_hours/24；設計第三章 12 個季曆小時）。
    - mend_days：補缺（第 3 批）——幾日之內被翻走的地補得回來（PM 五之一 5「1 個季曆天」；冷卻比它長的季照冷卻算）。"""

    uses: int = Field(default=2, ge=0)
    gap_days: float = Field(default=3, ge=0)
    days: float = Field(default=1, gt=0)
    sense_points: int = Field(default=10, ge=0)
    cultivate: float = Field(default=1.2, ge=1)
    stamina: float = Field(default=1.5, ge=1)
    push: float = Field(default=1.25, ge=1)
    affinity: float = Field(default=2.0, ge=1)
    hold_hours: float = Field(default=12, gt=0)
    mend_days: float = Field(default=1, gt=0)


class SealRevampTuning(_Strict):
    """玉璽碎片改版（docs/superpowers/specs/2026-10-21-玉璽碎片改版-design.md；計畫 docs/superpowers/plans/2026-10-21-玉璽碎片改版-1.md）
    第 1 批：常駐效果與持有者平時藏起來。子開關（PM 五之一 6：預設開、部署在休季換程式，不蓋章）；關著時舊的七個效果
    （SealTuning.effects）、江湖史七格與璽動點名、酒肆名氣一個字都不變。判斷一律走 seal.revamp_on（treasures.revamp_on 同一條）。
    - power：持有者本人的 Boost.factor 倍數（team.player_boost；企劃者「中：約 +10%」）。奪璽單挑的快照與江湖水漲的浮動難度照不含
      它的那一份算（企劃者第 7 條、PM 五之一 2）；同伴、部下不吃。
    - effects：content/seal.json 每片 effects 清單的鍵 → 數字（設計第三章；全部【預設】，等 21 天的季試玩再調）。乘的效果
      （treasures.MULTIPLY）寫倍數、加的寫加多少：injury 螭首每場仗變成內傷的倍數、talk_turns 玄紐每位人物每日多談幾輪、
      audience 玄紐求見門檻抵幾點、practice 雲篆練成的心得倍數（熔煉照原價退）、keep_silver 金角落敗不失銀兩（1＝有，只管
      Game._lose_silver，PM 五之一 3）、stamina_regen 承露體力回復倍數、fuse_points 赤璋自創的意分（create.seal_points；
      武學重構之後合成不擲品質，PM 2026-10-21 合 develop 時改成自創的意分 +10）、mate_exp 歸心同伴經驗倍數、
      chuangong 歸心傳功的心得倍數。"""

    enabled: bool = True
    power: float = Field(default=1.10, ge=1)
    effects: dict[str, float] = Field(default_factory=lambda: {
        "injury": 0.5, "talk_turns": 2, "audience": 5, "practice": 0.75, "keep_silver": 1,
        "stamina_regen": 1.25, "fuse_points": 10, "mate_exp": 1.25, "chuangong": 0.9,
    })
    acts: SealActsTuning = Field(default_factory=SealActsTuning)  # 第 2 批：獨門行動（同一個子開關）


class SealTuning(_Strict):
    """玉璽碎片（docs/superpowers/specs/2026-10-11-玉璽碎片-design.md；玉璽一）。數字照設計與 19.1「PM 2026-10-11 的決定」：
    - 現世 emerge_chance（3.2，PM 甲綁標 emerge 的那一場）；璽動每場、每片各擲 stir_chance（4.1，PM 乙），全服一季最多 season_stir_cap 次。
    - 易手機率＝cap ×局勢係數（side_factor，大勝不打單挑）×護璽（guard，持有者自己出手滿門檻）×單挑係數（take_share，照挑戰者的結果）；
      四個都不超過 1（載入時檢查），一場最多 cap（5.8）。PM 乙採 9.4 甲＋乙：局勢全 1.0、單挑 1.0／1.0／0.6；一場每一邊最多搏 gamble_cap 次。
    - 單挑節奏（5.4、5.5）：下戰書 muster_seconds、rounds 回合、在場的人每回合最多等 round_seconds、每回合最早 pace_seconds 後結算、
      最近 presence_window 秒推過這場才算在場、last_seen 每 seen_write_seconds 秒最多寫一次；代打的招照份量的 proxy_power 次方加權（5.6）。
    - 名望（5.9；near 是 PM 丁）、隱沒（7.6；PM 庚：連續 sink_seasons 季沒上線、而且滿 sink_days 天）、持碎片的退隱假人每季回來的機率（7.6）。
    - 小伺服器（PM 癸）：決戰參戰名單不到 small_battle 人時出手門檻放寬到 1 回合，旁觀的散人也能被挑上陣前。
    - emerge_skill：現世的得主同一季補送時學會的武學（11.2 第 4 條；舊鏈看守者給的混元一氣改給這裡）。
    - qa_tools：管理者「不必有決戰」的強制開單挑（第十二節），正式伺服器關著。
    內容沒有 content/seal.json 時整個碎片系統等於關著（seal.on）。
    - mandate：天命之季與天命之爭（玉璽二，見 MandateTuning）。"""

    enabled: bool = True
    emerge_chance: float = Field(default=0.35, ge=0, le=1)
    stir_chance: float = Field(default=0.07, ge=0, le=1)
    season_stir_cap: int = Field(default=2, ge=0)
    cap: float = Field(default=0.25, ge=0, le=1)
    side_factor: dict[str, float] = Field(default_factory=lambda: {"險勝": 1.0, "險敗": 1.0, "大敗": 1.0, "旁觀": 1.0})
    guard: float = Field(default=0.7, ge=0, le=1)
    take_share: dict[str, float] = Field(default_factory=lambda: {"提前大勝": 1.0, "大勝": 1.0, "險勝": 0.6})
    gamble_cap: int = Field(default=2, ge=0)
    challenger_pool: int = Field(default=3, ge=1)
    small_battle: int = Field(default=10, ge=0)
    muster_seconds: float = Field(default=180, ge=0)
    rounds: int = Field(default=5, ge=1)
    round_seconds: float = Field(default=120, ge=0)
    pace_seconds: float = Field(default=20, ge=0)
    presence_window: float = Field(default=45, ge=0)
    seen_write_seconds: float = Field(default=15, ge=0)
    proxy_power: float = Field(default=4, ge=0)
    fame: dict[str, int] = Field(default_factory=lambda: {"keep": 3, "lose": 5, "near": 1})
    sink_seasons: int = Field(default=3, ge=1)
    sink_days: float = Field(default=28, ge=0)
    bot_return_chance: float = Field(default=0.7, ge=0, le=1)
    emerge_skill: str | None = "hunyuan"
    effects: dict[str, float] = Field(default_factory=lambda: {
        "hp_cap": 1.06, "talk_turns": 1, "practice": 0.9, "dodge": 0.03, "stamina_regen": 1.1, "fuse_points": 5, "mate_exp": 1.1,
    })
    qa_tools: bool = False
    mandate: MandateTuning = Field(default_factory=MandateTuning)
    cache: SealCacheTuning = Field(default_factory=SealCacheTuning)  # 領地爭奪的季，碎片藏在中立地、探索撿到（Task 14）
    revamp: SealRevampTuning = Field(default_factory=SealRevampTuning)  # 改版第 1 批：常駐效果與持有者藏起來（子開關）


class TreasureDef(_Strict):
    """寶物表的一件（content/gear.json，裝備四欄 6.3）。名字原創、暫名交 joy 潤；效果是八種之一，數字在 Config.treasures.effects。
    pool：掉落池（懸賞的重賞、挑戰本人、奇遇）；False 是名將的贈禮（只從 gifts 送出，事件不准給）。"""

    id: str
    name: str
    effect: TreasureEffect
    pool: bool = True


class SteedDef(_Strict):
    """名駒（content/gear.json，5.7）：三階、專名，只從名將贈禮來（事件與懸賞不給）。"""

    id: str
    name: str
    quality: Literal["下品", "中品", "上品"] = "上品"


class GiftDef(_Strict):
    """名將贈禮（6.3、6.4）：情誼到 Config.treasures.gift_affinity 時送；每位名將每季全服只送一人。"""

    character: str  # 人物 id（content/characters.json）
    gear: str  # treasures（pool 為 false）或 steeds 的 id
    line: str = ""  # 送禮那一句（{general}、{gift} 換成人物與贈禮的名字）；空的照 treasures.GIFT_LINE（待 joy 潤）


class SignatureArmDef(_Strict):
    """名將本命兵器（兵器設計 4.10；打造第三批）：content/gear.json 的 signature_arms，一位名將一把。名字原創、暫名待 joy 潤（換名只改
    內容檔：手上的那一把讀檔時照這裡重寫，signature_arms.refresh_names）。種類・屬性照他的本命武學寫（載入不比對，正式內容的測試鎖）。
    情誼到 Config.weapons.signature_affinity 他送你；figure 有寫的，這一季打贏那位大勢人物本人 signature_wins 次他讓你奪走（現在只有孫堅）。
    每位名將每季全服一人（WorldState.signature_arms）。拿到的那一把算神器原品的加成（signature_arms.new_arm）。"""

    character: str  # 人物 id（content/characters.json）
    name: str
    kind: str  # models.WEAPON_KINDS
    attribute: str  # martial_arts.ATTRIBUTES
    figure: str | None = None  # 大勢人物 id（content/figures.json），他的 character 要是同一位；沒寫就只有情誼那條路
    gift_line: str = ""  # 情誼那條路送你的那一句（{general}、{arm}）；空的照 signature_arms.GIFT_LINE（待 joy 潤）
    seize_line: str = ""  # 打贏那條路讓你奪走的那一句（{general}、{arm}）；空的照 signature_arms.SEIZE_LINE（待 joy 潤）
    tactic: TacticDef | None = None  # 誰拿都有的特技（第三批）
    bond: TacticBond | None = None  # 人器合一：身上也練著這位名將的本命時，他的戰法改強


class GearBook(_Strict):
    """content/gear.json：寶物表、名駒、名將贈禮、名將本命兵器（裝備四欄 6.3；兵器設計 4.10）。沒有這個檔就是空的（測試內容）：寶物沒有來源、
    名將不送禮。防具架上的名字（armor.SHOP_NAMES）與馬的毛色（mounts.COATS）照舊是程式常數（計畫「要 PM 定的」第 2 條）。"""

    treasures: dict[str, TreasureDef] = Field(default_factory=dict)
    steeds: dict[str, SteedDef] = Field(default_factory=dict)
    gifts: list[GiftDef] = Field(default_factory=list)
    signature_arms: list[SignatureArmDef] = Field(default_factory=list)  # 名將本命兵器（打造第三批）


class Secrets(_Strict):
    """口訣與秘方（tianxia/secrets.py；PM 2026-10-10 派工，企劃者選「甲乙都做」的甲）。預設全關（測試內容沒有秘方池），
    正式值在 config.json。"""

    # 每季照天機挑幾條：種類 → 條數（池子不夠就全上）
    per_season: dict[str, int] = Field(default_factory=lambda: {"fuse": 2, "merge": 2})
    quality_points: float = 0  # 合中秘方的那一爐，造化分加這麼多（+20：普通搭配的上品從兩成拉到三成，還是夾在上限之內）
    insight_points: float = 0  # 拿秘方合出來的意境去融，那一爐的「意境來歷」再加這麼多
    tale_events: list[str] = Field(default_factory=list)  # 這些事件了結之後，有 tale_chance 的機會多一句說書版的口訣
    tale_chance: float = Field(default=0, ge=0, le=1)
    scrap_chance: float = Field(default=0, ge=0, le=1)  # 探索最後擲一次，撿到一頁殘譜（殘譜版的口訣）
    talk_affinity: int = Field(default=20, ge=0)  # 跟人物的情誼到這麼多，他才會不經意引一句（人物順口版）
    # 寫給玩家看的框（{clue} 換成口訣）
    tale_frame: str = "說書先生收場前搖頭晃腦念了兩句：「{clue}」——茶客們聽得一頭霧水。"
    scrap_frame: str = "你在亂石堆裡翻出一頁殘譜，字跡斑駁，只認得出一句：「{clue}」"
    overheard: str = "（這句話你記進了武學譜。）"
    hit_line: str = "爐中忽地一變——這一爐竟暗合了江湖上流傳的一句口訣。"
    # 這一季第一次參透一條（玩家回報 2026-10-25「武學譜很空」）：結果多一句進度，另寫一則標題「武學譜」的江湖紀錄、跳一個視窗。
    # {n} 這一季參透了幾條、{total} 這一季全服共有幾條。待 joy 潤
    solved_note: str = "武學譜上多了一方朱印——這一季的秘方，你已參透 {n}／{total}。"
    solved_title: str = "參透口訣・{n}／{total}"
    rumor: str = "江湖上傳開了：{who}參透了一句口訣，合出了{thing}。"
    chronicle: str = "{who}參透口訣，首創{thing}。"


class ForgeSecretRules(_Strict):
    """打造的隱藏配方與鑄器的口訣（打造隱藏配方設計第三、六、七節；tianxia/forge_secrets.py）。預設全關（測試內容沒有配方池），
    正式值在 config.json。"""

    # 每季照天機挑幾條：「欄位:組」→ 條數；組是主料的階（1、2、3）或 divine（神器配方，打造第二批起照挑）
    per_season: dict[str, int] = Field(default_factory=dict)
    tale_chance: float = Field(default=0, ge=0, le=1)  # 說書事件（Config.secrets.tale_events）了結時，另擲一次多一句說書版鑄器口訣
    smith_chance: float = Field(default=0, ge=0, le=1)  # 在鐵匠鋪花了銀兩或素材之後，鐵匠順口說出這家知道的那一句（鐵匠版）
    scrap_chance: float = Field(default=0, ge=0, le=1)  # 探索最後撿到半張鑄譜（殘譜版）
    # 寫給玩家看的字（待 joy 潤；{clue} 換成口訣、{who} 換成名號、{name} 換成名器的名字）
    tale_frame: str = "說書先生又扯到一段兵器的掌故：「{clue}」"
    smith_frame: str = "鐵匠一邊收錢一邊嘀咕：「{clue}」"
    smith_frame_free: str = "鐵匠一邊收拾一邊嘀咕：「{clue}」"  # 這一下沒收銀兩（一階淬煉只收素材，FB-142）
    scrap_frame: str = "你在灰堆裡扒出半張燒焦的鑄譜，只認得出一句：「{clue}」"
    first_line: str = "這是失傳的鑄法，江湖上你是第一個摸出來的。"
    mine_line: str = "照你摸出來的鑄法，又打了一件。"
    follow_line: str = "這門鑄法由{who}先摸出來，你也打成了。"
    rumor: str = "{who}在鐵匠鋪摸出了一門失傳的鑄法，打出了【{name}】。"
    # 神器（打造第二批；待 joy 潤；{who} 換成名號）
    divine_line: str = "這是一{unit}神器，這門鑄法這一季只出這一{unit}原品——到修練頁的裝備庫替它定名。"  # {unit} 照欄位（防具一件，FB-146）
    copy_line: str = "這門鑄法的原品在{who}手上，你打出的是仿品。"
    copy_mine_line: str = "原品已經在你手上，這一爐打出的是仿品。"
    divine_rumor: str = "{who}在鐵匠鋪打出了一{unit}神器。"
    named_rumor: str = "{who}替手上的神器定了名，叫【{name}】。"  # 定名時的傳聞（7.2：帶名字的那一句）
    named_chronicle: str = "{who}打出一{unit}神器（{what}），為之定名【{name}】。"  # 江湖史那一行（5.2；{what} 是種類或「防具」，{unit} 照欄位）
    # 三階素材的新來源（兵器設計 4.9；打造第二批，PM 決定第 7 條）：預設全關，正式值在 config.json。擲骰都用自己的亂數（Game._tier3）
    challenge_tier3: float = Field(default=0, ge=0, le=1)  # 挑戰大勢人物本人打贏，掉一個三階素材（屬性照他的隊伍）的機會；正式 1
    tier3_per_figure: int = Field(default=0, ge=0)  # 同一位人物對同一個人每季最多掉幾次（0＝不設限；正式 2：閉門不見只有 2 小時，不設會被刷）
    big_tier3: float = Field(default=0, ge=0, le=1)  # 大場面對手（不是本人那支隊伍）打贏，另擲一次三階素材；正式 0.25
    # 素材與經濟（docs/superpowers/specs/2026-10-15-素材與經濟-design.md，企劃者 2026-10-15）：預設開、測試內容關，關掉一個字都不變。
    # 前兩個從下一季開季起照 WorldState 的章（world_state.stamp_season）：正在跑的季中途改會讓已經聽到的線索對不上
    divine_per_kind: bool = True  # 神器配方每一季每種兵器最多一條；第一季的章六種兵器各一條（forge_secrets.active）
    split_clues: bool = True  # 神器配方的線索拆三片（種類／主料／輔料），散在鐵匠鋪、說書、殘譜（forge_secrets.hear、hear_smith）
    scrap_every_mode: bool = True  # 殘譜（武學口訣與半張鑄譜）三種探索都擲；上線就生效，關著只在找事件擲（Game._explore_mode）
    # 神器輪替與收集（正式季整合 5.6～5.8；第 10 批，tianxia/divine.py）：主機的緊急開關，模型預設關、config.json 開、測試內容關。
    # 開著時開季、換季照全服登記（SharedWorldState.divine）挑這一季的神器、蓋進 WorldState.divine_lineup；從下一個開季起生效
    rotation: bool = False
    rotation_min: int = Field(default=2, ge=1)  # 第二季起每季開幾件神器（照天機，5.6【定】2～4 件）
    rotation_max: int = Field(default=4, ge=1)
    wear_level: int = Field(default=15, ge=1)  # 神器（原品、仿品）本人幾級才穿得上（5.8【定】）


class FirstEcho(_Strict):
    """首創名望回饋（企劃者 2026-10-07 選甲時一起要的「乙的首創回饋」）：別人照著你首創的配方合出同一門（武學或意境），
    每多一個不同的人，你下一次上線時名望 +fame_per；一門最多算 cap 個人（擋灌名望）。湊滿 cap 那一下江湖上傳一句。
    只在第一季開著時有。"""

    fame_per: int = Field(default=1, ge=0)
    cap: int = Field(default=5, ge=1)


class Biography(_Strict):
    """玩家傳（企劃者 2026-10-12：「記錄玩家在大戰的行動還有一些值得紀錄的日常活動尤其跟每個歷史人物的對話互動，然後最後賽季結束時
    凝結成一個某某傳」）。第一批只記行狀（tianxia/annals.py，PlayerState.annals）；每季都有，不掛第一季開關。"""

    enabled: bool = True
    # 行狀一季最多留幾則：超過就先丟份量最輕的、同份量丟最早的（annals.trim）。一季一百多個小時，決戰三場、人物十來位、
    # 日常的大事幾十件；150 則夠一篇一兩千字的傳挑，存檔也只多十幾 KB
    cap: int = Field(default=150, ge=10)
    level_every: int = Field(default=5, ge=1)  # 等級每到這個倍數記一筆（第 5、10、15……級）
    affinity_marks: list[int] = Field(default_factory=lambda: [20, 40, 60, 80])  # 跟人物的情誼往上跨過這幾格各記一筆
    affinity_drop: int = Field(default=10, ge=1)  # 一個動作裡情誼掉這麼多就記一筆（交惡）
    talk_swing: int = Field(default=5, ge=1)  # 對話一輪情誼動這麼多才記那一句（自己說的話不看這個，一律記）
    # 第二批（季末寫成傳）：寫一篇最多等模型幾秒（鎖外、背景做，網頁每幾秒問一次寫好了沒，不受 trycloudflare 一個請求約 100 秒的限制）；
    # 一篇一千多字，gemma4:26b 約一兩分鐘
    budget_seconds: int = Field(default=240, ge=0)
    rewrites: int = Field(default=1, ge=0)  # 寫成之後還能請史官重寫幾次（模型版、規則版都算）
    # 分享網址的開頭（「https://tianxia.example.com」，不含結尾的斜線）。空字串＝照這次請求的網址組（trycloudflare 每次重開都換，
    # 要長期分享得換具名 Tunnel 的固定網域，再把它寫在這裡；換網域不必改程式）
    public_url: str = ""


class FollowerTuning(_Strict):
    """部下（PM 2026-10-12 派工：企劃者問「部下現在是不是沒有作用」）：武學成數跟著本人的等級長、全服決戰的份量。"""

    # 部下的武學成數＝max(模板寫的成數, 本人等級 ÷ levels_per_cheng)，最多十成。跟著等級、不跟著晉升階：階只有 2～4 三格，
    # 第 4 階還是每週輪替的席次（掉下來就回第 3 階），部下會忽強忽弱；等級一季從 1 長到二三十，跟玩家花的時間一起走。
    # 3：開局第 1～8 級是模板的三成（拿到部下時大多已經在這一帶），第 9 級起每 3 級一成，第 30 級十成
    levels_per_cheng: int = Field(default=3, ge=1)
    # 全服決戰：每帶一名部下，強攻、奇襲的份量多幾成（加入時快照，跟職位、騎兵疊乘；固守不加——部下衝殺不守）。
    # 0.05：兩名（第 2 階）+10%，跟一匹駑馬的騎兵（5%～15%）同一個量級；四名（第 4 階）+20%
    battle_per: float = Field(default=0.05, ge=0)


class ChuangongTuning(_Strict):
    """傳功門下（企劃者 2026-10-14「心得大量溢出，需要想個可以大量消耗的地方」，在決策卡選「傳功門下」）：用心得替同伴、部下
    練武學、加屬性，隊伍變強，本人的威力一點都不動。價錢越後越貴：心得多的人有地方一直花，少的人先花在自己身上划算。
    量到的（週末設定、一直在線打仗的機器人，2026-10-14）：一季攢 1.2 萬～1.8 萬心得，練滿自己兩門只要 180，其餘全部堆著。"""

    enabled: bool = True  # 主機的緊急開關：關掉時修練頁不畫傳功、按了也只回一句
    # 同伴的武學、內功從第 N 成練到 N+1 成要 mate_art_xinde × N 心得（練滿一門 45 倍＝900）。本人自己的是 2 × N（練滿 90）：
    # 同伴的本命武學都是絕學（第一成 50、第十成 120，本人開局的基礎武學是下品 8～24），練一成長的威力是本人的好幾倍，所以貴十倍
    mate_art_xinde: int = Field(default=20, ge=1)
    # 同伴的臂力、身法、根骨：傳給他的第 k 點要 mate_stat_xinde × k 心得（k 算他身上三項合計已經傳了幾點，不分哪一項）。
    # 三項各傳滿 mate_stat_max 點（45 點）合計 15 ×（1＋…＋45）＝15525——一個同伴就吃得下最拚的人大半季的心得
    mate_stat_xinde: int = Field(default=15, ge=1)
    # 每一項最多傳幾點。照 stat_cap（15）：同伴自己每級會長屬性、高等時本來就超過 15，上限只能算在「傳了幾點」，不然高等的同伴傳不進去
    mate_stat_max: int = Field(default=15, ge=0)
    # 部下的武學：在照等級長的那條線（team.follower_level）之上再多練一成，第 k 成要 follower_cheng_xinde × k；線＋多練的最多十成。
    # 線在第 30 級就到十成，所以多練的成數只在前半季有用（之後線追上來、多練的那幾成就沒有空間了）——便宜一點
    follower_cheng_xinde: int = Field(default=25, ge=1)
    # 部下的臂力：第 k 點要 follower_str_xinde × k，臂力最高 stat_cap。模板 4～7，一名最多傳 8～11 點（約 1300～2600）
    follower_str_xinde: int = Field(default=20, ge=1)


class ArtsTuning(_Strict):
    """武學重構（Joy 2026-10-20；tianxia/arts.py）：品級只管威力上限（martial_arts.QUALITY_TOP_POWER）與意境槽數（slots）；
    意境就是技能，裝進槽生效。戰力＝威力 ×（1 ＋ Σ 權重）：一般功效每級 general_weight、高階 high_weight、特別功效 special_weight、
    本命戰法 signature_weight（只用來排清單與寫卡，不進戰鬥）。自創：create_xinde 起、一季每多一門 ×create_step、最多 create_per_season 門；
    自創的一律是 create_grade（Joy 2026-10-21「自創武學應該保底都是上品」；多付心得加分、擲品級都拿掉了）。數字是佔位，量表定。"""

    # 槽（招式與絕學稿案第二輪，Joy 2026-10-21 按建議）：學來的（下品）2、自創與合成的 3、絕學 3（另加絕招那一環，arts.ULTIMATE_SLOT）
    slots: dict[str, int] = Field(default_factory=lambda: {"下品": 2, "中品": 3, "上品": 3, "絕學": 3})
    general_weight: float = Field(default=0.05, ge=0)
    # 同一個功效好幾份（Joy 2026-10-22 決策卡選「第二份算半」，traits.stack_value）：只有一份、或加起來沒超過上限照舊；
    # 超過時第一份照算，第二份起每份算 stack_share，合起來最多上限的 stack_ceiling 倍。打仗、戰力、評分同一條。
    # 同一個真意第二份：發動率 ×(1＋stack_share)；本來就每次發動的（鎮岳、金身）多撐一回合；第三份起不再加
    stack_share: float = Field(default=0.5, ge=0, le=1)
    stack_ceiling: float = Field(default=1.5, ge=1)
    high_weight: float = Field(default=0.12, ge=0)
    special_weight: float = Field(default=0.10, ge=0)
    signature_weight: float = Field(default=0.15, ge=0)
    # 自創不限門數、價錢固定（招式與絕學稿案第二輪）：create_per_season 0＝不限；create_step 1＝不漲價
    create_xinde: int = Field(default=500, ge=0)
    # 這一季第一門自創的價錢（Joy 2026-10-21「第一次自創武學，降低到只需要100心得，之後一樣500，擔心初始門檻太高玩家玩不到那邊就放棄」）；
    # 0＝跟後面一樣（測試內容）。角色每季重來，所以每一季的第一門都是這個價
    create_first_xinde: int = Field(default=0, ge=0)
    # 重悟帖（萬寶閣）一門自創最多重骰幾次（Joy 2026-10-21「一次創造武學的時候可能最多重骰3或是5，總共要買幾張都可以」）
    create_reroll_cap: int = Field(default=5, ge=0)
    create_step: float = Field(default=1.0, ge=1)
    create_per_season: int = Field(default=0, ge=0)
    create_grade: Literal["下品", "中品", "上品"] = "上品"
    # 成形（create.roll_colors）：每一路屬性的權重＝底 create_base_weight ＋ 兵器或行功之法的偏向（content/create_forms.json）
    # ＋ 姿勢讀出的偏向（第一路 create_pose_weights[0]、第二路 [1]）＋ 意讀出的偏向（create_intent_weights）。
    # 第一格一定是權重最高的那一路單色（定向）；其餘每一格先照 create_slot_odds 擲單色、雙色、全色，再照權重抽顏色（格與格之間可以重複）。
    # 意讀不出偏向（不偏）時全色的機率 ×create_neutral_any_scale。create_redo：一張單子能免費重來幾次
    create_base_weight: float = Field(default=0.5, ge=0)
    create_pose_weights: list[float] = Field(default_factory=lambda: [1.5, 0.75])
    create_intent_weights: list[float] = Field(default_factory=lambda: [2.5, 1.25])
    create_slot_odds: dict[str, float] = Field(default_factory=lambda: {"單": 55, "雙": 35, "全": 10})
    create_neutral_any_scale: float = Field(default=2.0, ge=1)
    create_redo: int = Field(default=1, ge=0)
    create_slots: int = Field(default=3, ge=1)  # 成形擲幾格（品級開幾格就用前幾格；第一格也照 create_slot_odds 擲，單色雙色都以權重最高那一路打頭）
    # 以意成招（tianxia/moves.py）：意分 ≤ move_fire_cuts[0] 生、≤ [1] 熟、其餘透；生熟透照 move_fire 打折表上會長的數；
    # 稀有路數擲中的機會 move_rare_odds；一到 move_raw_levels 成招還生，再乘 move_raw_scale
    move_fire_cuts: list[int] = Field(default_factory=lambda: [40, 70], min_length=2, max_length=2)
    move_fire: dict[str, float] = Field(default_factory=lambda: {"生": 0.6, "熟": 0.8, "透": 1.0})
    move_rare_odds: float = Field(default=0.1, ge=0, le=1)
    move_raw_levels: int = Field(default=3, ge=0)
    move_raw_scale: float = Field(default=0.5, ge=0, le=1)
    # 撞出來的稀有（招式與絕學稿案「強不強、稀有不稀有」）：三格全單色「純」、三格全任色「渾」，槽裡意境的一般功效打架時再乘 1＋這個數
    pure_bonus: float = Field(default=0.10, ge=0)
    whole_bonus: float = Field(default=0.15, ge=0)
    # 破境（招式與絕學稿案第三節）：自創的練成絕學，自己的招升為絕招——會長的數再乘 ascend_scale。
    # 發動率（Joy 2026-10-23 決策卡「甲 加一半」，方案頁 https://claude.ai/artifact/1bVYzrqyMjsqEdaEKaxEvz）：每回合會發的招（rounds 0）
    # 乘 ascend_scale、最多 ascend_rate_cap（本來就超過的照舊）；起手的招（前幾回合）照原本的發動率。以前一律升到必定，最會配的玩家打本命剩 1%
    ascend_scale: float = Field(default=1.5, ge=1)
    ascend_rate_cap: float = Field(default=0.5, ge=0, le=1)
    # 基本威力（Joy 2026-10-21「基本威力你先自己用一版」）：同一品級的威力區間再乘一個倍數，夾在 power_scale_range。
    # 自創照「意」分＋加分＋赤璋（夾 0～100）從下限線性推到上限；武學＋武學合出來的照兩門來源的倍數平均再加 blend_power_step。
    # 以前是名字雜湊的 ±10%；已經登記的武學照舊、不重算
    power_scale_range: list[float] = Field(default_factory=lambda: [0.9, 1.1], min_length=2, max_length=2)
    blend_power_step: float = Field(default=0.02, ge=0)
    # 意境效果池（第二批，tianxia/insight_fx.py）：悟到一份意境先擲品質（insight_quality_odds；在那一路最濃的地方升一品；
    # 悟性每高過 5 一點多 insight_quality_per_wis 的機會再升一品、最多 insight_quality_wis_cap），再擲效果：第一個是那一路兩個一般功效挑一個（一重），
    # 照品質有 insight_second 的機會出第二個，第二個有 insight_grand 的機會是大獎（那一路的高階技能）、不然是另一個一般功效。
    # 兩個不同的意境合出來的照兩份裡較好的品質擲，第二個效果多 compound_second_bonus、大獎機會 ×compound_grand_scale。
    # 揣摩（同一種意境兩份）：同一個一般功效的層數相加（最多三重），都沒有大獎時照品質擲 insight_grand × deepen_grand_scale；
    # 一份意境最多 insight_max_effects 個效果，多的拿掉層數最少的一般功效。同一種意境手上最多 insight_piece_cap 份，再悟到化成心得
    insight_quality_odds: dict[str, float] = Field(default_factory=lambda: {"下品": 60, "中品": 30, "上品": 10})
    insight_quality_per_wis: float = Field(default=0.03, ge=0)
    insight_quality_wis_cap: float = Field(default=0.4, ge=0, le=1)
    insight_second: dict[str, float] = Field(default_factory=lambda: {"下品": 0.2, "中品": 0.5, "上品": 0.8})
    # 大獎（招式與絕學稿案第五輪：先量再改）：上品 .35、合出來 ×2.0 時，週末季整季機器人三十季合出來的有 47% 是珍品、季末手上珍品 19%，
    # 珍不稀罕了；改 .25 × 1.5 後合出來的珍品 22%、季末手上 12%（量法：每一份悟到、合出來、揣摩出來的照 insight_fx.look 數）
    insight_grand: dict[str, float] = Field(default_factory=lambda: {"下品": 0.05, "中品": 0.15, "上品": 0.25})
    compound_second_bonus: float = Field(default=0.3, ge=0)
    compound_grand_scale: float = Field(default=1.5, ge=0)
    deepen_grand_scale: float = Field(default=1.0, ge=0)
    insight_max_effects: int = Field(default=2, ge=1)
    insight_piece_cap: int = Field(default=4, ge=1)
    # 評分（武學重構第三批；Joy 2026-10-20「武學的總評分就是看各意境效果疊加分數……可能滿一百是絕學」，選法 B）：
    # 槽裡每一份意境的效果加總——一般功效每重 score_per_layer、大獎 score_grand、特別功效 score_special，單色格裡的 ×score_single_color；
    # 評分不是衝絕學的門檻（Joy 2026-10-20「評分可以超過100呀……武學衝絕品跟評分無關」）：只寫在卡上、排武學榜與內功榜。
    # 寫死的武學照它的功效算。master_score 沒有地方讀了（留著讓舊設定讀得進來）。
    score_per_layer: float = Field(default=8, ge=0)
    score_grand: float = Field(default=28, ge=0)
    score_special: float = Field(default=20, ge=0)
    score_single_color: float = Field(default=1.1, ge=0)
    master_score: int = Field(default=100, ge=0)


class SignatureArtTuning(_Strict):
    """本命武學（企劃者 2026-10-15「現在的本命絕學很爛，甚至比玩家自己合成的還差，也沒什麼特色效果」；PM 定的做法）：
    以前本命武學照絕學的固定區間（第一成 50、第十成 120），合成擲到的絕學帶 ±10% 微調、最高 132，還可以帶 3 個一般功效與特別功效；
    本命武學只有自己屬性一個功效、學到時第一成（威力 50，比練滿的上品 72 還低）。現在：玩家自己那一份威力 × power_scale
    （絕學第十成 138，高頂級合成一截；同伴自己練的照舊，不然全隊又往上竄）、內容寫 3 個一般功效與一個本命戰法（SkillDef.tactic）、
    學到時直接第 start_level 成（讀檔時情誼送過的舊角色補到這一成，signature.lift_levels，Game._drop_stale_references 叫）。"""

    power_scale: float = Field(default=1.15, gt=0)
    start_level: int = Field(default=7, ge=1, le=10)


class TacticTuning(_Strict):
    """一般的仗的回合與本命戰法（tianxia/tactics.py；Joy 2026-10-15 選「全部改回合制」）的數字。
    一般的仗照舊先用單次判定擲出差距（encounter.resolve_encounter，同一顆 Game.rng），再把差距攤成一回合一回合的氣勢（span：差距
    一個對手強度 ＝ 氣勢 span 點；50 起，到 50 ± stop 提前收場）。沒有戰法時每一回合加起來剛好回到那個差距，結果一個字都不變；
    戰法在回合裡改氣勢（讓對手打空、出不了手、被剋、連環……），收場的氣勢換回差距再照門檻判結果。
    strike 是對手一回合打過來的氣勢、counter 是一回合剋中的那一下，戰法的效果都照這兩個數換算（量法見 scripts/measure_tactics.py）。"""

    span: float = Field(default=40.0, gt=0)  # 差距一個對手強度換成幾點氣勢
    stop: float = Field(default=40.0, gt=0)  # 氣勢離 50 這麼遠就提前收場（90／10）
    strike: float = Field(default=0.8, ge=0)  # 對手一回合打過來的氣勢（定身、打空、借力、壓低他的推力都照它算）
    counter: float = Field(default=0.6, ge=0)  # 一回合剋中的那一下
    wobble: float = Field(default=3.0, ge=0)  # 回合之間的起伏（只是演出，加起來照舊回到差距）
    dot: float = Field(default=0.08, ge=0)  # 對手每掉一成氣血池的百分之一，氣勢多幾點（焚身、風沙、血創、落雷）
    self_hit: float = Field(default=0.3, ge=0, le=1)  # 失神的那一回合打到自己的機會
    prefer_guard: float = Field(default=0.5, ge=0, le=1)  # 帶著固守才發動的戰法時，自動出招改出固守的機會
    band: float = Field(default=12.0, ge=0)  # 沒有戰法時中途的氣勢不越過 50 ± (stop − band)（不然還沒打完就提前收場，結果會變）
    # 對手那一方也帶本命戰法（挑戰大勢人物本人：他自己的兩門；team.foe_tactics）。主機的開關
    foe_tactics: bool = True
    # 頭目戰、擂台、奪璽單挑（自己挑招的仗，tactics.step）：一擊是幾點氣勢（那邊一回合的推力約 ±8～12、剋中 counter_push 8）。
    # 2 是量出來的（scripts/measure_tactics.py --bouts，2026-10-15）：頭目戰十八位平均贏面 +4.0（5 是 +10.0、3 是 +5.7），
    # 跟一般的仗第一批的 +3.6 差不多
    bout_strike: float = Field(default=2.0, ge=0)
    # 決戰（tactics.war_round）：一個人的份量加成乘多少（連環是 +1 擊）。0.5：發動多的人一回合份量平均 ×1.17（孫堅），
    # 跟職位的 +15% 差不多（1.0 是 ×1.34）
    war_scale: float = Field(default=0.5, ge=0)
    # 第三批（玩家自己的武學功效、神器與名將本命兵器的特技）：
    copy_rate: float = Field(default=0.7, ge=0, le=1)  # 神器的仿品：特技的發動率乘這個（心法那一種每回合照它擲）
    mist_fast_share: float = Field(default=0.5, ge=0, le=1)  # 險的霧：身法高的那一方打空的機會乘這個
    momentum_cap: float = Field(default=0.3, ge=0)  # 乘勝：一場裡疊起來的推力加成最多這麼多
    # 頭目戰、擂台、奪璽單挑裡重控場（tactics.BOUT_CONTROL）的發動率乘這個：那幾種仗一回合的勝負幾乎全看剋不剋，
    # 經緯（看穿）與長坂一喝（定身）照原本的發動率，擂台同樣身手對上自組上品贏 73%（scripts/measure_tactics.py --kits）
    bout_control_share: float = Field(default=0.6, ge=0, le=1)
    # 鑄器配招（玩家武學追上本命）：身上的名器屬性跟一門絕學相同時，那一門絕招的發動率多這麼多（小一截的人器合一）
    named_bond_rate: float = Field(default=0.08, ge=0, le=1)


class CompanionsTuning(_Strict):
    """歷史武將同行（docs/superpowers/specs/2026-10-18-歷史武將同行-design.md；tianxia/roster.py、tianxia/escorts.py）：
    十五位標了 recruitable 的歷史武將照陣營招進名下（全服唯一），名下最多 max_owned 位；大決戰挑一位上陣（battle_instance.Escort），
    打完那一場他回江湖、原主人的情誼乘 parted_keep（無條件捨去）。enabled 關著：招募、隊伍上限、決戰、叛投一個字都不變
    （上限照 state.MAX_TEAM_COMPANIONS）。正式開、測試內容關。"""

    enabled: bool = False
    max_owned: int = Field(default=3, ge=1)  # 名下最多幾位（照 CompanionProgress.owner 算，名號比對不分大小寫）
    parted_keep: float = Field(default=0.5, ge=0, le=1)  # 決戰打完回江湖、叛投帶不走時，原主人的情誼留幾成（無條件捨去）


class FigureLifeTuning(_Strict):
    """人物活起來（大勢人物擴充第一批，Joy 2026-10-17「歷史武將人數新增多一些，更智能化，像是真的活在這個亂世」；
    設計稿 https://claude.ai/code/artifact/03df3760-b4bd-417c-935f-96dda0f500c2；tianxia/figure_life.py）。
    每 every_cal_days 個季曆天，每位人物照規則做一件事（移動、募兵、襲擾、養傷）；心事照事實算（figures.mood_of）；
    玩家做了份量夠的事，跟這件事有關係的人物記一句風聞、情誼照表動。數字全在這裡，模型不碰。"""

    enabled: bool = True  # 主機的緊急開關：關掉時人物站著不動、沒有心事、不記風聞（跟這一批之前一模一樣）
    # 多久做一件事（季曆天）：週末一季 84 個季曆天、約 1.4 個現實小時一次；14 天的季約 8 小時一次。一季每人約 42 件事
    every_cal_days: float = Field(default=2.0, gt=0)
    recruit: int = Field(default=2, ge=0)  # 募兵回幾點聲威（回到開季值為止）
    # 一位人物一個遊戲日在戰場外最多回幾點聲威：募兵、自然回復、（大勢人物參戰與護衛那一份的）犒軍共用這一個上限，不各自疊
    daily_gain_cap: int = Field(default=10, ge=0)
    raid_push: int = Field(default=1, ge=0)  # 襲擾推幾點：規則關著的季推黃巾聲勢、乘季長倍數、照盡頭阻力；第一季只是傳聞（figures.tick 已經在推）
    mood_cal_days: float = Field(default=2.0, gt=0)  # 負傷、悲憤撐幾個季曆天（同一個行事週期）
    hurt_scale: float = Field(default=0.9, gt=0)  # 負傷：挑戰難度（也是決戰份量）乘多少
    grief_scale: float = Field(default=1.1, gt=0)  # 悲憤：同上
    lean: int = Field(default=15, ge=0)  # 戰線偏向自己這一方多少算得意、偏向對方多少算焦慮
    healer_share: float = Field(default=0.5, gt=0, le=1)  # 華佗坐診的醫館，療傷價錢乘多少
    # 風聞：一位人物對一個人最多記幾條（舊的先丟）、對話提示最多帶幾條
    hearsay_keep: int = Field(default=5, ge=1)
    hearsay_prompt: int = Field(default=3, ge=0)
    # 情誼照表動：打退他的盟友、打退他的仇敵、替他的陣營在決戰立功、截殺他陣營的人（一件事一位人物只算一次）
    ally_beaten: int = -5
    foe_beaten: int = 3
    side_merit: int = 3
    side_raided: int = -3
    # 第二批（人與人）：關係表與倒下時的反應、復仇懸賞、書信與委託
    reactions: bool = True  # 一位人物倒下時，盟友悲憤、往那一區趕、掛復仇懸賞，仇敵得意（figure_life.on_fall）
    revenge_silver_scale: float = Field(default=2.0, gt=0)  # 復仇懸賞的賞銀是一般討伐的幾倍（設計稿：秦頡「放話加倍懸賞」）
    revenge_cal_days: float = Field(default=7.0, gt=0)  # 復仇懸賞掛幾個季曆天（同一般懸賞的一週）
    revenge_affinity: int = Field(default=3, ge=0)  # 交了復仇懸賞，掛單的人物情誼加多少
    # 書信：情誼到 letter_affinity 的人物在規則觸發時派人送信（求援：心事焦慮或悲憤；道賀：你剛做了他欣賞的事），一人一個遊戲日最多一封
    letters: bool = True
    letter_affinity: int = Field(default=40, ge=0)
    letters_keep: int = Field(default=5, ge=1)  # 身上留幾封（舊的先丟）
    # 求援附的委託（討伐、打探、護送，跟懸賞同一套）：完成了情誼 +commission_affinity、銀兩 commission_silver；commission_days 個遊戲日內要辦完
    # （遊戲日＝世界秒 // DAY，跟「一天最多一封」同一把尺：週末是現實一天、14 天的季也是現實一天；照季曆天的話週末只撐三個鐘頭）
    commission_affinity: int = Field(default=5, ge=0)
    commission_silver: int = Field(default=30, ge=0)
    commission_days: float = Field(default=1.0, gt=0)
    letter_write_budget_seconds: float = Field(default=60.0, gt=0)  # 書信請模型照他的口氣重寫的預算（鎖外、背景執行緒；寫不出來照固定句）
    # 第三批（大家一起）：宴客、月旦評、求援委託
    # 宴客：每一輪每位人物擲 feast_chance 設宴（心事是得意或沒有心事、此刻在場），全服同時最多 feast_max_open 場、上一場開席之後
    # feast_gap_hours 個世界小時內不再開；一場擺 feast_hours 個世界小時（週末＝現實小時）。赴宴不花體力，一人一場敬一句：
    # 情誼 +1～+feast_affinity_max（照分數）；散席時分數最高那一句上天下大事、名望 +feast_fame
    feasts: bool = True
    feast_chance: float = Field(default=0.03, ge=0, le=1)
    feast_max_open: int = Field(default=1, ge=0)
    feast_gap_hours: float = Field(default=6.0, ge=0)
    feast_hours: float = Field(default=2.0, gt=0)
    feast_affinity_max: int = Field(default=5, ge=1)
    feast_fame: int = Field(default=1, ge=0)
    feast_score_budget_seconds: float = Field(default=30.0, gt=0)  # 自己寫的敬酒詞請模型評分的預算（評不到照 feasts.DEFAULT_SCORE）
    # 月旦評：許劭每週一評 yuedan_count 個人（名人、善人、惡人榜輪流挑），第 yuedan_from_week 週起；模型寫評語的預算，
    # 等過 yuedan_wait_seconds 個世界秒還沒寫好就照固定句發
    yuedan: bool = True
    yuedan_count: int = Field(default=6, ge=1)
    yuedan_from_week: int = Field(default=2, ge=1)
    yuedan_wait_seconds: float = Field(default=900.0, ge=0)
    yuedan_budget_seconds: float = Field(default=90.0, gt=0)
    # 求援委託：心事焦慮的大勢人物每一輪擲 rally_chance 對自己陣營全部人發一件（同一位一次一件），前 rally_quota 個辦成的
    # 拿銀兩 rally_silver、他的情誼 +rally_affinity，他寫信道謝；掛 rally_cal_days 個季曆天。護衛、犒軍他也算辦成
    rallies: bool = True
    rally_chance: float = Field(default=0.3, ge=0, le=1)
    rally_quota: int = Field(default=3, ge=1)
    rally_silver: int = Field(default=30, ge=0)
    rally_affinity: int = Field(default=5, ge=0)
    rally_cal_days: float = Field(default=3.0, gt=0)


class PlanTuning(_Strict):
    """世界活起來（Joy 2026-10-29「讓整個世界活起來」，選了「世界會自己變」加「你做的事被世界記住」；設計稿
    https://claude.ai/artifact/LFooPvhRw5NHosh3wDUKRV；tianxia/plans.py、tianxia/deeds.py）。有名的人物照 content/itineraries.json
    的行程自己動身、自己做事；有些站是「盤算」：提前公告，全服的人都能去那裡助他一臂或壞他的事，到點由引擎照兩邊各幾人擲骰。
    數字全在這裡，模型不碰。"""

    enabled: bool = False  # 關著時人物照舊在常去的地方之間晃，沒有行程、沒有盤算、不記世界記事（一個字都不變）
    lead_days7: float = Field(default=1.0, ge=0)  # 盤算提前多久公告（7 天季的天數；別的季長照比例：21 天季是 3 天）
    max_open: int = Field(default=2, ge=1)  # 全服同時最多開幾件盤算（Joy 2026-10-29「會不會一大堆盤算玩家看都看不完」）
    stamina: int = Field(default=10, ge=0)  # 助一臂、壞他的事花幾點體力（一人一件一次）
    # 成算：base（內容寫，預設 0.6）＋ swing ×（助的人－壞的人）÷（助＋壞＋soft），夾在 [floor, cap]
    swing: float = Field(default=0.35, ge=0, le=1)
    soft: int = Field(default=3, ge=1)
    floor: float = Field(default=0.1, ge=0, le=1)
    cap: float = Field(default=0.9, ge=0, le=1)
    affinity: int = Field(default=3, ge=0)  # 站對了邊：替他辦成的人跟他的情誼加多少（壞事得逞的人不加情誼）
    deeds_keep: int = Field(default=300, ge=10)  # 世界記事全服留幾筆（舊的先丟）
    deeds_prompt: int = Field(default=3, ge=0)  # 人物對話提示最多帶幾筆跟玩家有關的記事
    deeds_place: int = Field(default=3, ge=0)  # 此地舊事最多列幾筆


class ParleyTuning(_Strict):
    """NPC 智能 2.0（Joy 2026-10-23「先做看看」；設計稿 https://claude.ai/artifact/KtRz62jWShogpaXEzv2sbt；tianxia/parley.py）：
    對話裡「自己說」那一句也可以是求他做事。模型當談判者，從引擎列的清單挑一件、評一個意願、要不要開條件；引擎照情誼與份量夾住意願、
    自己擲骰、做事。第一批：當場做、先付後做、婉拒；帶路、並肩出陣、指點、給情報、贈物五件事。數字全在這裡，模型不碰。"""

    enabled: bool = False  # 關著時「自己說」一個字都不變（20 字、不列清單、不擲骰）
    say_max: int = Field(default=40, ge=1)  # 開著時「自己說」最多幾個字（NPC 智能 2.0要講得清楚一點）
    asks_per_day: int = Field(default=2, ge=1)  # 同一位人物一個遊戲日最多被求幾件事（算在一天三輪對話裡）
    # 意願的天花板：情誼到第幾檔（[門檻, 上限]，由低到高）；份量 1、2、3 各減多少；敵對陣營再減；最低 floor
    bands: list[list[int]] = Field(default_factory=lambda: [[0, 50], [20, 65], [40, 80], [60, 90]])
    band_words: list[str] = Field(default_factory=lambda: ["生疏", "認得", "信得過", "託付"])
    weight_cut: list[int] = Field(default_factory=lambda: [0, 10, 25])
    enemy_cut: int = Field(default=30, ge=0)
    floor: int = Field(default=5, ge=0, le=100)
    # 五件事的份量與給多少
    escort_places: int = Field(default=6, ge=1)  # 帶路最多列幾個目的地（近的先）
    backing_share: float = Field(default=0.3, ge=0)  # 並肩出陣：今天在他那一區出陣一次，這一仗本人的威力多幾成
    spar_xinde: int = Field(default=15, ge=0)  # 指點一招：心得（同一位一天一次）
    gift_silver: int = Field(default=20, ge=0)  # 贈物：他手頭沒有素材時給的銀兩
    intel_count: int = Field(default=3, ge=1)  # 給情報：講幾件事
    # 條件：交銀的價錢照份量；交素材是三份一階；打探、討伐是委託（同書信的委託，辦成了下次見面他兌現）
    silver_terms: list[int] = Field(default_factory=lambda: [20, 50, 100])
    material_terms: int = Field(default=3, ge=1)
    # 第二批：先做後付與食言、人物主動開口、同行中的自由文字
    broken_cut: int = Field(default=10, ge=0)  # 每一筆還沒抵掉的食言（自己的、聽說的）讓意願天花板減多少
    owe_limit: int = Field(default=3, ge=1)  # 同時最多欠幾位人物（欠滿了他不再先做後付，改成先付後做）
    owe_broken: int = Field(default=15, ge=0)  # 先做後付的食言：情誼減多少（你白拿了東西）
    plea_broken: int = Field(default=8, ge=0)  # 接了他的請託沒做到：情誼減多少
    heard_broken: int = Field(default=3, ge=0)  # 他的盟友聽說你食言：情誼減多少
    heavy_days: int = Field(default=1, ge=0)  # 份量 3 的條件期限多幾個遊戲日
    plea_moods: list[str] = Field(default_factory=lambda: ["焦慮", "悲憤"])  # 心事是這幾種時，你求見他，他會先開口求你
    plea_wants: int = Field(default=3, ge=1)  # 他想請你做的事列幾件給模型挑
    plan_floor: int = Field(default=5, ge=0, le=100)  # 跟他商量打法：成功率夾在這兩個數之間（放手一搏同一個上限）
    plan_cap: int = Field(default=85, ge=0, le=100)
    escort_pace: float = Field(default=0.5, gt=0)  # 他帶路：步行的時間乘這個數（他熟路、腳程快），一分體力不花


class RiseTuning(_Strict):
    """江湖水漲（企劃者 2026-10-14「玩家變強後好像也沒有更高的挑戰，10 幾級都能把所有歷史武將跟所有事件打敗，根本不會輸」；
    tianxia/rise.py）。量到的原因（scripts/measure_difficulty.py，週末、2026-10-14）：大勢人物本人最難 160、劇情戰的大場面最難 150，
    可是招到兩位同伴的隊伍第 10 級全隊威力就 300 多（同伴第一級就 135～146），單次判定威力過難度的 1.45 倍就必勝——
    第 10 級起打誰都 100%；沒有同伴的人第 30 級本人威力 150～220，第 40 級 300 多，也一樣全贏。事件檢定難度 3～8、屬性最高 15，
    第 30 級起平均成功率 88～94%、九成以上的檢定 ≥90%。

    - 大場面（挑戰大勢人物本人、劇情戰裡難度到 big_fight_difficulty 的對手）：難度取「內容寫的」與「你此刻對他的全隊威力 × 倍數」
      的大者。倍數 big_scale 起、你這一季每打贏他一次多 per_win、最多 max_scale——強的隊伍頭一場有把握、越打越難；
      沒那麼強的照舊打內容寫的難度（新手第一場不會因為這條變難）。獎勵照舊照內容寫的那一份（挑戰本人照聲威打折），浮上去的難度不多給。
    - 頭目戰：他的難度取「內容寫的」與「你的武學威力 × duel_scale」的大者（頭目戰只算本人；同一隻這一季第二次遇上再多 duel_per_meet）。
    - 事件檢定：本人第 event_from_level 級起，每 event_per_levels 級檢定難度 +1、最多 +event_cap（rules.check_outlook，
      選項的心裡話、擲骰都照它）。內容寫的難度不動（DIFFICULTY_BANDS 照鎖），加深的是執行期的那一格。"""

    enabled: bool = True  # 主機的緊急開關：關掉時三樣都照內容寫的
    # 威力過難度多少倍才贏（單次判定：贏的那一線是難度的 1.15 倍，運氣 ±0.3 倍）：倍數 0.75 → 威力是難度的 1.33 倍，贏面約八成（有把握）；
    # 0.85 → 約五成五（五五波）；0.95 → 約三成五（凶險）；1.05 → 約一成五
    big_scale: float = Field(default=0.75, gt=0)
    per_win: float = Field(default=0.15, ge=0)  # 這一季每打贏同一位人物一次，倍數再加多少（只算大勢人物本人：figure_wins）
    max_scale: float = Field(default=1.10, gt=0)
    # 挑戰大勢人物本人的僵持下緣（encounter.Mods.draw_floor）：差距 ≥ −難度×這麼多才算僵持（一般的仗 0.5）。企劃者 2026-10-16
    # 「名將挑戰難度提高很容易一直平手」：一般的僵持帶（−50%～+15%，寬 65%）比運氣的範圍（±30%，寬 60%）還寬，倍數走到 1 附近
    # 不論怎麼調都幾乎全是僵持（打贏三次之後 81%）；收窄到 −10%～+15%，僵持最多四成多，倍數往上是真的會輸（per_win、max_scale 一起調）
    figure_draw: float = Field(default=0.10, ge=0)
    # 頭目戰（推氣勢，不是單次判定）：他的份量照「難度」換算（duel.foe_strength），1.0 是跟你同一個難度。量出來（measure_difficulty.py，
    # 招一半看架勢一半亂出、不放手一搏）：見 CLAUDE.md「江湖水漲」
    duel_scale: float = Field(default=1.0, gt=0)
    duel_per_meet: float = Field(default=0.15, ge=0)  # 同一隻這一季第二次遇上（per_boss_season 2）再多這麼多
    event_from_level: int = Field(default=15, ge=1)
    event_per_levels: int = Field(default=6, ge=1)
    event_cap: int = Field(default=4, ge=0)


class SortieRules(_Strict):
    """出陣（docs/superpowers/specs/2026-10-14-出陣探索與地盤-design.md 第二節；遊歷改版）。地盤（＝領地爭奪，territory.on）開著就有
    （sortie.on），沒有開關；沒有地盤的季（沒有第一季規則、劇本沒寫區塊）是舊的遊歷與操練（2026-10-27 舊出陣的推線與攪局拿掉）。"""

    per_day: int = Field(default=5, ge=1)  # 每人每天幾次（攻、守、攪局共用；照 pill_day_utc_offset_hours 的 00:00 換日，同回體丹）
    hold_share: float = Field(default=0.5, gt=0, le=1)  # 守、攪局推的量是攻的幾成
    # ── 出陣更誘人（正式季整合 2.6、第 4 批；一類一顆 precise_actions 開著才有，關著照舊三成）──
    reward_scale: float = Field(default=2.0, ge=0)  # 攻打贏的經驗、心得是對手的幾倍（同一個對手練功打贏的兩倍【PM】）
    merit_silver_per_level: int = Field(default=3, ge=0)  # 攻打贏另加軍功賞：本人等級 × 這麼多兩【暫】
    rare_legend: float = Field(default=0.05, ge=0, le=1)  # 攻打贏另擲：破境丹【暫】
    rare_treasure: float = Field(default=0.02, ge=0, le=1)  # 寶物（挑戰本人的掉落池，另記一本帳 PlayerState.sortie_treasures）
    rare_horse: float = Field(default=0.02, ge=0, le=1)  # 良駒
    treasure_cap: int = Field(default=2, ge=0)  # 出陣掉的寶物一人一季最多幾件（不讀 figure_treasure_cap；season21 寫 3【PM】）
    horse_cap: int = Field(default=1, ge=0)  # 出陣掉的良駒一人一季最多幾匹
    # ── 批 3b：減法季的出陣約戰（整合設計 4.3；計畫第四節，tianxia/sortie_duel.py）──
    # 只在 rules.jianfa(content, world, "sortie_duel") 開著的季讀；關著的季沒有任何地方讀這一段。時間都是現實分鐘（Game.now）。全部【預設】
    jianfa_per_day: int = Field(default=2, ge=1)  # 一天貼幾次約戰（取代 per_day；同 pill_day 的換日）
    jianfa_stamina: int = Field(default=12, ge=0)  # 貼一次約戰的體力（取代 action_cost["train"]）
    cooldown_minutes: float = Field(default=60.0, ge=0)  # 兩次約戰之間（從貼的那一刻起算）
    window_minutes: float = Field(default=10.0, gt=0)  # 貼出去之後幾分鐘內可以應戰；窗滿才結算
    answer_per_day: int = Field(default=3, ge=0)  # 一天應戰幾次（跟出陣分開算，企劃者 2026-10-24）；應戰沒有冷卻
    answer_stamina: int = Field(default=12, ge=0)  # 應戰一次的體力
    lose_injury: float = Field(default=10.0, ge=0)  # 輸的一方另加的內傷（三回合扣的氣血照留；不碰銀兩）
    lose_cooldown_minutes: float = Field(default=30.0, ge=0)  # 輸的一方下一次出陣或應戰的冷卻多這麼久（sortie_duel.cooldown_after）
    # 推多少：名目量 × 這一場的結果倍率（攻方贏推攻方那一條；守方贏照守方的結果拉攻方那一條，企劃者 2026-10-24 第 1 件）
    result_scale: dict[str, float] = Field(default_factory=lambda: {"big": 1.5, "win": 1.0, "draw": 0.4, "lose": 0.0})
    # 封三招能挑的招：現有的三招（tactics.counter 的相剋照用；設計寫的「以巧破力」就是奇襲）加撤退；不放「放手一搏」（企劃者 2026-10-24）
    moves: list[str] = Field(default_factory=lambda: ["強攻", "固守", "奇襲", "撤退"])
    counter_swing: float = Field(default=0.3, ge=0, lt=1)  # 一回合剋中，攻方威力 ×(1＋這個)；被剋 ×(1−這個)
    retreat_toll: float = Field(default=0.3, ge=0, le=1)  # 撤退的那一回合算輸，扣的氣血打這個折（兩邊都撤退算僵持，各打這個折）
    # 一回合扣氣血上限的幾成（照那一邊這一回合贏、僵持、輸）：三回合全輸 30%＝遊歷落敗（encounter_neili_loss 的落敗）
    round_toll: dict[str, float] = Field(default_factory=lambda: {"win": 0.03, "draw": 0.06, "lose": 0.10})
    keep_hours: float = Field(default=24.0, ge=0)  # 結算完（或作廢）的約戰留多久（卡上看得到、各自同步時補送）
    # 約戰推（拉）進度的倍數（取代 Config.conquest.progress_scale；None＝照 progress_scale）：量表 scripts/measure_conquest.py 照「20 人一季易手 7～8 次」
    # 調（計畫第四節 4.0 之四：week7 27、season21 10，寫在兩份設定覆寫檔的 sortie 那一塊）。另開一個數、不改 progress_scale：約戰關著的季
    # （舊出陣）一個字都不變
    duel_progress_scale: float | None = Field(default=None, ge=0)
    duty_contribution: int = Field(default=1, ge=0)  # 巡哨、傳道、保境安民收進此地：不推線、不佔出陣次數，記這麼多貢獻（企劃者 2026-10-24 第 2 件）
    duty_per_day: int = Field(default=1, ge=0)  # 上面那一點貢獻一天記幾次
    # ── 出陣回報的小籤寫字不寫數字（企劃者 2026-10-26「出陣寫字」；sortie.amount_words、order_words）──
    chip_mine_steps: tuple[float, float] = (5.0, 15.0)  # 【PM】今天自己推的量：到第一個「推了不少」、到第二個「推了一大截」，不到「推了一點」
    chip_all_steps: tuple[float, float] = (15.0, 50.0)  # 【PM】全軍今天推的量，同上（全軍是很多人加起來，門檻高一些）

    @model_validator(mode="after")
    def _duel_tables(self) -> SortieRules:
        if set(self.result_scale) != {"big", "win", "draw", "lose"}:
            raise ValueError("sortie.result_scale 要寫 big、win、draw、lose 四種結果的倍率")
        if set(self.round_toll) != {"win", "draw", "lose"}:
            raise ValueError("sortie.round_toll 要寫 win、draw、lose 三種回合的損耗")
        if not self.moves or not set(self.moves) <= {*MOVES, "撤退"}:
            raise ValueError(f"sortie.moves 只能挑 {'、'.join(MOVES)}、撤退")
        return self


class ExploreModes(_Strict):
    """探索三選一（設計第三節）：找素材、找事件、靜心感悟。enabled 關掉回到照地點比例自動抽的探索（Config.explore_mix），
    事件推戰線也不再打折。"""

    enabled: bool = True
    encounter_chance: float = Field(default=0.35, ge=0, le=1)  # 找素材撞上怪（城鎮不撞）
    second_tier: dict[int, float] = Field(default_factory=lambda: {1: 0.0, 2: 0.25, 3: 0.5})  # 照危險度：再一個二階的機會
    town_chance: float = Field(default=0.5, ge=0, le=1)  # 城鎮找素材撿到一個一階的機會
    event_trend_share: float = Field(default=0.5, ge=0, le=1)  # 可重複的事件推戰線的量（設計 3.2、5.3；一次性的事照全額）
    sense_treasure_points: int = Field(default=15, ge=0)  # 寶物「探索悟意境」：靜心感悟擲中機率多幾個百分點（夾在 sense_rate_range 的上限）


class Training(_Strict):
    """城裡操練與城外練功分級（新手引導重做，Joy 2026-10-22 同意設計稿 https://claude.ai/artifact/Eb25MwPveJMYSf5Ge4mDyx）。
    一類一顆（precise.on）開著才有：城鎮裡行動列那一格是「操練」（act:drill），零風險、一天 drill_per_day 次（同回體丹的現實
    00:00 換日）、主要給心得；城外那一格是「練功」（explore:practice），照這裡最弱的對手分一、二、三級（tier_bounds），心得與銀兩
    乘 tier_loot（經驗不加成：50 級的升級速度是量好的）。enabled 關掉回到練功收在探索裡、沒有操練。"""

    enabled: bool = True
    drill_per_day: int = Field(default=5, ge=1)
    drill_xinde_base: int = Field(default=4, ge=0)  # 操練一次的心得：drill_xinde_base ＋ 等級 × drill_xinde_per_level
    drill_xinde_per_level: float = Field(default=1.0, ge=0)
    drill_exp_base: int = Field(default=1, ge=0)  # 操練一次的經驗：drill_exp_base ＋ 等級 // drill_exp_level_div
    drill_exp_level_div: int = Field(default=5, ge=1)
    tier_bounds: list[int] = Field(default_factory=lambda: [10, 30])  # 最弱的對手難度 ≤ 第一個是一級、≤ 第二個是二級，再上去三級
    tier_loot: list[float] = Field(default_factory=lambda: [1.0, 1.25, 1.5])  # 一、二、三級練功打贏的心得與銀兩倍數
    # 新手目標（tianxia/newbie.py）：引導走完、新手期裡任務卡上的那一塊；做到一條給 goal_pill 顆回體丹或 goal_silver 兩
    goals: bool = True
    goal_pill: int = Field(default=1, ge=0)
    goal_silver: int = Field(default=20, ge=0)

    @model_validator(mode="after")
    def _shape(self) -> Training:
        if len(self.tier_bounds) != 2 or self.tier_bounds[0] >= self.tier_bounds[1]:
            raise ValueError("training.tier_bounds 要寫兩個由小到大的難度")
        if len(self.tier_loot) != 3:
            raise ValueError("training.tier_loot 要寫一、二、三級三個倍數")
        return self


class GatherBranch(_Strict):
    """找素材的一條分支（第 32 項，企劃者 10/18「往深山可能探索到的就是山或者風之類的意境」「素材可能就能分狩獵、挖礦」；
    content/gather_branches.json）：地點帶 tags 其中一個、危險度到 min_danger 就有這條。給 attributes 這幾種屬性的素材
    （數量照找素材一定給的那一套，explore_modes.gather_finds），deep（深入）照地點的 Location.materials、另外擲一次悟意境。
    line 是紀錄的第一句（{place} 換地點名）；名字與句子待 joy 潤。"""

    id: str
    name: str
    tags: list[str]
    attributes: list[str] = Field(default_factory=list)
    line: str
    min_danger: int = Field(default=1, ge=1, le=3)
    deep: bool = False


class GatherBranches(_Strict):
    """找素材分支（第 32 項；tianxia/explore_modes.py 的 branches_*）：按「找素材」先展開這裡的幾條路，每條一定給素材、差在屬性；
    最後一顆「自己說…」寫 20 字的找法，模型評成算、引擎擲骰。另要探索三選一與一類一顆（precise.on）都開著、內容有
    content/gather_branches.json 才生效；不蓋章（只影響給哪種屬性，正在跑的季中途打開沒有壞處，PM）。測試內容關著。"""

    enabled: bool = True
    deep_insight_chance: float = Field(default=0.10, ge=0, le=1)  # 【預設】「深入」另擲一次悟意境：附帶的小驚喜（同殘譜、破境丹），不取代素材
    say_enabled: bool = True  # 「自己說」單獨的緊急開關（模型壞了只關它）
    say_bonus_second: bool = True  # 【預設】「自己說」寫得好：多一個同屬性一階之外，再照危險度擲一次二階（企劃者 2026-10-19 照 PM 先定的做）


class InsightStrong(_Strict):
    """意境提示（意境提示設計第二節）：每個地點最濃的意境（Location.insight_strong）。enabled 關掉一個字都不變：輿圖沒有意境濾鏡、
    感悟擲中的門檻與心得照舊、悟到時不多那一句、validate 不要求每處都寫；抽屜的「此地能悟」是補漏，不看這個開關。"""

    enabled: bool = True
    sense_points: int = Field(default=15, ge=0)  # 選對最濃那一種的做法：感悟擲中機率多幾個百分點（夾在 sense_rate_range 的上限）
    duplicate_xinde: int = Field(default=15, ge=0)  # 在最濃的地方又悟到一次已經會的那一種，化成的心得（平常 duplicate_insight_xinde）


class TerrainArts(_Strict):
    """武學隨地理環境（地利；企劃者 10/17 清單第 36 項，計畫 2026-10-18-武學隨地理環境）：一般的仗（遊歷、出陣、探索撞上的野怪、
    練功、劇情戰、挑戰大勢人物本人）裡，本人與出戰同伴身上的武學、內功一門一門比這一地最濃的意境（insights.strong_of）：
    同一路 ×match、被它剋 ×clash，其餘不動（tianxia/terrain.py）。部下不吃；決戰、擂台、頭目戰、奪璽單挑、護衛、切磋、截殺、
    設伏不算；江湖水漲浮難度不算。enabled 關掉（或 insight_strong 關著）一個字都不變：倍數 1、戰報沒有那一句、輿圖沒有那一行、
    玩法說明沒有那一句。"""

    enabled: bool = True
    match: float = Field(default=1.10, gt=0)  # 【預設】那一門跟最濃的意境同一路（PM 2026-10-19：企劃者說可以派下去，照 PM 先定的）
    clash: float = Field(default=0.95, gt=0)  # 【預設】那一門被最濃的意境剋（水地裡的剛、山地裡的快）
    # 戰報那一句（一場最多一句，同一路先於相剋、本人先於同伴；不寫倍數）：鍵 match:<意境 id>、clash:<意境 id>、mate_match（{name}）。
    # 全部待 joy 潤
    lines: dict[str, str] = Field(default_factory=lambda: {
        "match:huo": "此地火氣正旺，你的剛猛之勁越打越烈。",
        "clash:huo": "火氣燥烈，你的柔勁被逼得散了。",
        "match:shui": "水氣漫過陣前，你的柔勁如魚得水。",
        "clash:shui": "水氣沉沉，你的剛猛之勁施展不開。",
        "match:shan": "山勢壓著陣腳，你的沉穩功夫在這裡更穩。",
        "clash:shan": "山路崎嶇，你的快招總慢了半步。",
        "match:feng": "風從背後推來，你的快招如虎添翼。",
        "clash:feng": "風急勢亂，你的慢功夫跟不上。",
        "mate_match": "{name}的功夫與此地的氣象相合。",
    })
    # 輿圖地利那一行的屬性字（terrain.place_line：「此地水氣最濃：柔勁的功夫在這裡得勢，剛猛的施展不開。」；待 joy 潤）
    words: dict[str, str] = Field(default_factory=lambda: {"柔": "柔勁", "剛": "剛猛", "快": "快招", "慢": "沉穩"})


class TerritoryRules(_Strict):
    """地盤易手（設計第四節；tianxia/territory.py）。沒有開關：territory.on 照內容與第一季規則；沒有地盤的季沒有控制方，隊伍照 Location.enemies，價錢照原價。"""

    own_price: float = Field(default=0.9, gt=0)  # 在自己陣營控制的地方療傷、打造工錢、買馬
    enemy_price: float = Field(default=1.2, gt=0)  # 在別的陣營控制的地方


# ── 三陣營四勝利（減法季整合設計第三章；計畫第五節，批 3c）：數字掛在 JianfaRules.tiers、lean_default_by_join（wins.rules_of）──

# 豪強開季的「此刻幫誰」照投靠點預設（企劃者 2026-10-24，計畫第十一節第 6 件）：鄉里結社、曹氏莊院幫官軍，豪族塢堡幫黃巾
LEAN_DEFAULT_BY_JOIN = {"zhuo_militia_hall": "guan", "cao_manor": "guan", "haozu_fort": "huang"}
# 四階的稱號（設計 3.3；鍵是「階:陣營 id」，wins.title_of 照它找、找不到再看只寫階的鍵）：第一階分官軍、黃巾，第三、四階分兩軍與豪強。
# 字待 joy 潤（企劃者 2026-10-24 第 4 件：先用這組）
TIER_TITLES = {
    "1:guan": "漢室忠良", "1:huang": "黃天功臣",
    "2:haoqiang": "一方之雄",
    "3:guan": "有功之臣", "3:huang": "有功之臣", "3:haoqiang": "鄉里之望",
    "4:guan": "隨軍", "4:huang": "隨軍", "4:haoqiang": "附從",
}


class TierRules(_Strict):
    """季末四階（設計 3.3；wins.settle）。名次只在過了門檻的人裡排，人數照比例無條件捨去；第一、二階至少 1 人，
    第三階的「前 40%」是累計的（含第一、二階），扣掉第一、二階那一池還有人時第三階也至少 1 人（PM 2026-10-25 第 1 件）；
    同分同階（計畫 5.0 第 13 條）。20 人與 2,000 人同一條規則。"""

    tier1_share: float = Field(default=0.10, ge=0, le=1)  # 第一階：贏的那一軍裡前 10%（至少 1 人）【定】
    tier2_share: float = Field(default=0.10, ge=0, le=1)  # 第二階：豪強「替贏的那一軍」那一本前 10%（至少 1 人）；兩軍拿不到【定】
    tier3_share: float = Field(default=0.40, ge=0, le=1)  # 第三階：各自前 40% 的其餘人（贏的、輸的、豪強都有）【定】
    min_contribution: int = Field(default=40, ge=0)  # 每一階都要先過的門檻（絕對數，約「一季認真玩三天」）【定】企劃者 2026-10-26 定 40（原本 60【待量】）
    start_shares: dict[int, float] = Field(default_factory=lambda: {1: 1.0, 2: 0.8, 3: 0.5, 4: 0.3})  # 下一季起手資源的成數【預設】
    start_silver: int = Field(default=300, ge=0)  # 起手資源滿額：銀兩【預設】
    start_xinde: int = Field(default=200, ge=0)  # 起手資源滿額：心得【預設】
    titles: dict[str, str] = Field(default_factory=lambda: dict(TIER_TITLES))  # 「階:陣營 id」→ 稱號（待 joy 潤）

    @model_validator(mode="after")
    def _shares_in_order(self) -> "TierRules":
        if self.tier1_share > self.tier3_share or self.tier2_share > self.tier3_share:
            raise ValueError("第一、二階的比例不能大於第三階（第三階是累計的前幾成）")
        if set(self.start_shares) - {1, 2, 3, 4}:
            raise ValueError("start_shares 只有第 1～4 階")
        return self


class EpiphanyRules(_Strict):
    """特殊頓悟（tianxia/epiphany.py；企劃者 2026-10-26 設計稿 https://claude.ai/artifact/EBUqqzK3dPMpjwYTdRzLs3）：有所感選對做法、擲中進感悟狀態的那一刻
    再擲一次，中了不畫那一筆，改走一條「頓悟」的線（storyline，kind「頓悟」）：心靈拷問 → 心境小試 → 心魔，過了從四十個神品意境模板
    （TraitBook.god）挑一個、取名、收進自己的意境。另要一條線的底座開著（Config.jianfa.storylines）；序章不擲。
    失敗可以重複挑戰（Joy 10/26「留住玩家很重要」）：沒有期限，心魔打輸過 retry_days 再打，次數不限。"""

    enabled: bool = False
    chances: list[float] = Field(default_factory=lambda: [0.03, 0.015, 0.0075])  # 這一季第幾次頓悟的機率；列完就是一季的上限
    wis_from: int = 5  # 悟性高過這個數，每一點機率乘 (1 + wis_step)，最多乘 wis_cap
    wis_step: float = Field(default=0.05, ge=0)
    wis_cap: float = Field(default=1.5, ge=1)
    pity: int = Field(default=40, ge=0)  # 只管第一次：這一季擲中感悟這麼多次都沒頓悟，下一次必中；0 是不保底
    demon_scale: float = Field(default=0.95, gt=0)  # 心魔的難度＝你此刻的全隊威力 × 這個倍數（你自己的影子）
    retry_days: float = Field(default=1.0, ge=0)  # 心魔打輸了，過幾個遊戲日能再打（照季長，rules.day_seconds）
    # 心境小試抽到「靜候」那一種時要等幾個遊戲日（FB-902）：預設 1.0 是設計稿的「靜候一日」，
    # 但 7 天的季裡那是真實 24 小時、一關吃掉整季的 1/7，所以 week7／season21 寫 1/12（一個時辰），
    # 跟心魔重試的 retry_days 對齊。每次檢定都照此刻的設定讀，所以改了對正在走的線也立刻生效。
    trial_wait_days: float = Field(default=1.0, ge=0)
    # 重複挑戰時削弱他（企劃者 2026-10-28「心魔重複打的時候削弱他好了」；「僵持也算過關」被否了：太簡單）：
    # 每輸一次（含僵持）難度的倍數降這麼多，降到 demon_floor 為止。0.95 滿血勝率約三成，每次 −0.05：
    # 第三次過半、第六次九成五、第七次起照 floor 幾乎篤定過，所以不會卡死，但也不是白給。
    demon_weaken: float = Field(default=0.05, ge=0)
    demon_floor: float = Field(default=0.65, gt=0)


class JianfaRules(JianfaNumbers):
    """減法季（減法季整合設計，企劃者 2026-10-24；設計稿第十章）：把遊戲從「打怪、練等、拚戰力」拉回「文字互動改變世界」。
    規則的改動全掛在這裡加上開季時蓋的章（WorldState.jianfa_on，world_state.stamp_season；讀的時候一律走 rules.jianfa）：
    正在跑的季照它開季時的章，換了設定也不變。季只分 7 天與 21 天兩種，兩種都開（content/profiles 的 season21、week7 打開）；
    週末設定不再維護、不打開，關著一個字都不變。畫面的改動不掛這個開關。欄位名是兩邊（畫面與引擎）共用的，各批的數字之後加在這一節。
    批 2（探索一顆、三道閘、屬性五段）的數字繼承自 jianfa_numbers.JianfaNumbers（explore_stamina、explore_tables、drill_*、
    milestone_levels、stat_rates、event_bump_scale…；純規則 explore_one、growth 吃同一份）；那邊不 import 這裡，免得循環。"""

    enabled: bool = False  # 預設關（測試內容與不帶設定的正式內容照它）；season21.json、week7.json 打開
    # 子開關（整合設計第十二章）：總開關開著、這一季有章時，各批的規則再看自己的那一個（rules.jianfa(content, world, "explore_one")）；
    # 預設全開，哪一批出了事主機可以單獨關掉那一批。總開關關著時子開關一律不算。
    explore_one: bool = True  # 4.1 探索一顆照地點抽（批 2）
    outing: bool = True  # 走一趟：探索一次走一、三、五段（tianxia/outing.py；要 explore_one 也開著）
    drill_gates: bool = True  # 4.2 三道閘、45 級後只收仗的經驗（批 2）
    sortie_duel: bool = True  # 4.3 出陣改約戰（批 3b）
    free_text_outcomes: bool = True  # 第五章 隨口應對分岔（批 4）
    marks_visible: bool = True  # 第五章 痕跡看得見（批 4）
    stances: bool = True  # 第五章 人物心意（批 6）
    errands: bool = True  # 第五章 託付與來信（批 6）
    week_unlock: bool = True  # 6.6 功能照週解鎖（批 5）
    rewrite_narration: bool = True  # 第十章 事件旁白每週改寫（批 10）
    rewrite_round_seconds: float = Field(default=20, gt=0)  # 伺服器的背景執行緒幾秒改寫一則（一週約兩百六十則，一個多小時寫完）
    rewrite_budget_seconds: float = Field(default=40, gt=0)  # 一則最多等模型幾秒（含排隊）
    rewrite_tries: int = Field(default=2, ge=1)  # 同一則同一週寫壞幾次就這一週照原文
    morning_mail: bool = True  # 第十章 回來的理由：人物的信每天 mail_hour 點送到（批 9；letters.mail_day）
    opening: bool = True  # 6.7 開局第一分鐘（批 7 前半，tianxia/opening.py）：不進草廬，旁白→三選一→人物開口託付→本週卡；關著照舊走草廬序章
    mail_hour: int = Field(default=9, ge=0, le=23)  # 當地幾點送信（時區照 pill_day_utc_offset_hours）
    # 一條線（特殊事件與特殊頓悟的底座，tianxia/storyline.py；企劃者 2026-10-26 設計稿）：關著時內容寫的線一條都不開、程式也開不了
    storylines: bool = True
    # 同時開著幾條（照 StoryDef.kind）；沒列的種類不限。【預設】設計稿：奇事兩條、頓悟一條
    story_caps: dict[str, int] = Field(default_factory=lambda: {"奇事": 2, "頓悟": 1})
    # 章回主線（企劃者 2026-10-29 選丙、2026-10-29「四個都同意」；tianxia/chapters.py）：每一方照時刻表大事各幾回，做完改那一件大事。
    # 要 storylines 也開著（章回是一條線，kind「章回」，不佔 story_caps）
    chapters: bool = True
    chapter_roll_cap: float = Field(default=0.15, ge=0, le=0.2)  # 【定：企劃者 10-29】全陣營做成這一回最多讓那一骰動多少（跟伏筆合計仍夾 ±0.20）
    chapter_half_at: float = Field(default=9, gt=0)  # 【預設】做成的人（照份量）到幾個，那一方推到上限的一半（開根號：√n ÷（√n＋√half_at））
    chapter_edge_cap: int = Field(default=5, ge=0, le=20)  # 【預設】決戰那幾回：開打時起點最多挪幾點（大場面判讀的量級）
    chapter_contribution: int = Field(default=8, ge=0)  # 【預設】做成一回記幾點貢獻
    # 事件分級（企劃者 2026-10-26，事件分級設計稿；tianxia/tiers.py）：第二、三階事件照門開，抽的時候照開到第幾階的比例先挑階
    event_tiers: bool = True
    # 五道門：[第二階的門檻, 第三階的門檻]。武事是等級、名流是名望第幾段、俠義與綠林是善名、惡名第幾段（要走那一條路）、
    # 擂主是擂台名次至少到第幾名（擂台十傑、天下第一）。【預設】設計稿
    tier_doors: dict[str, list[int]] = Field(default_factory=lambda: {
        "武事": [20, 40], "名流": [2, 3], "俠義": [2, 3], "綠林": [2, 3], "擂主": [10, 1],
    })
    # 開到第幾階的人抽事件時各階的比重（第一階、第二階、第三階）；這裡沒有合格事件的階不算。【預設】設計稿：開到二是六比四、開到三是 4:3.5:2.5
    tier_mix: dict[int, list[float]] = Field(default_factory=lambda: {1: [1.0], 2: [6.0, 4.0], 3: [4.0, 3.5, 2.5]})
    # ── 批 2（探索一顆、三道閘、屬性五段；數字在 JianfaNumbers）──
    stat_milestones: bool = True  # 4.5 屬性五段加點、每點加倍、境界卡（批 2；數字是 milestone_levels、stat_points_per_milestone、stat_rates）
    # ── 批 4：隨口應對分岔與痕跡（主機側計畫第六節；子開關 free_text_outcomes、marks_visible）──
    # 【預設】一天（季曆日，同推線的 daily_push_cap）從分岔的後果（之後連心意、託付）記進陣營帳的貢獻上限；同出陣推線的量級（整合設計 5.3）
    deed_contribution_cap: int = Field(default=12, ge=0)
    # ── 批 6：人物心意與託付（主機側計畫第七節；整合設計 5.3～5.5、5.9；子開關 stances、errands）──
    stance_threshold: int = Field(default=30, ge=1)  # 【預設】全服這一週記到幾筆，人物照那個心意改做事（StanceDef.threshold 沒寫照這個）
    stance_contribution: int = Field(default=1, ge=0)  # 【預設】記一筆心意記幾點貢獻（整合設計 5.3；跟分岔同一本每日上限 deed_contribution_cap）
    bot_stance_chance: float = Field(default=0.3, ge=0, le=1)  # 【預設】假人每天直接記一筆心意的機會（企劃者 2026-10-24 第 5 件；不說話、不寫字）
    errand_lapse_affinity: int = Field(default=2, ge=0)  # 【預設】託付過了期限作罷，他的情誼扣幾點（婉拒不扣）
    # 【預設】情誼到幾點人物才託你事（PM 2026-10-26：40 的話新手第一週幾乎拿不到；另開一個數，不動 figure_life.letter_affinity——
    # 道賀、邀宴、求援的信與勸降的情誼加成照舊讀那一個）
    errand_affinity: int = Field(default=20, ge=0, le=100)
    errand_stamina: int = Field(default=10, ge=0)  # 【預設】探營、勸降各花幾點體力（交信不花：走到就是那一趟）
    errands_keep: int = Field(default=12, ge=1)  # 身上留幾件託付的帳（辦完、作罷的照留到滿了才丟舊的；一季三位人物各三週）
    # 勸降的成功率（整合設計 5.9「照情誼、名望、說的話；引擎再夾」）：模型只評那一句（0～100），引擎加情誼與名望的修正、夾在 floor～cap
    persuade_floor: int = Field(default=5, ge=0, le=100)  # 【預設】同隨口應對的 5～85
    persuade_cap: int = Field(default=85, ge=0, le=100)  # 【預設】
    persuade_affinity_step: int = Field(default=4, ge=1)  # 【預設】情誼比 figure_life.letter_affinity 每多幾點加 1 個百分點
    persuade_fame_step: int = Field(default=10, ge=1)  # 【預設】名望每幾點加 1 個百分點
    persuade_bonus_cap: int = Field(default=10, ge=0)  # 【預設】情誼、名望兩樣各最多加幾個百分點
    # ── 批 3c 三陣營四勝利（整合設計第三章；wins.py 讀，wins.rules_of）──
    tiers: TierRules = Field(default_factory=TierRules)  # 季末四階的切法、門檻、起手資源與稱號（wins.settle）
    # 豪強的投靠點 → 投靠那一下預設幫哪一軍（wins.lean_default；content.validate 叫 wins.check 驗每個投靠點都有、都是它能幫的那一軍）
    lean_default_by_join: dict[str, str] = Field(default_factory=lambda: dict(LEAN_DEFAULT_BY_JOIN))
    # ── 批 7b：列傳為終點（整合設計第九章；主機側計畫第八節；tianxia/zhuan_end.py）──
    zhuan_end: bool = True  # 第九章 列傳為終點：行狀補齊（季末論功、〈天下形勢〉）、人物評曰、列傳的三件商品（批 7b；深交上限企劃者 2026-10-28 拿掉）
    verdict_chars: int = Field(default=40, ge=1)  # 人物評曰一句最多幾個字【預設】
    verdict_affinity_max: int = Field(default=3, ge=0)  # 情誼 70 以上替你寫評曰的最多幾位（情誼高的在前；PM 2026-10-28，深交不限人數之後）【預設】
    verdict_budget_seconds: float = Field(default=40, gt=0)  # 一條評曰最多等模型幾秒（含排隊，排在真人後面）【預設】


class WebPushRules(_Strict):
    """網頁推送（減法季整合設計第十章「回來的理由」，批 9）：分頁關著、手機鎖著也跳一則通知，五種事——來信、約戰、決戰集結、
    被截殺、被〈天下形勢〉提到（tianxia/notices.py 認，server.py 的看守送）。玩家在設定頁自己打開（預設關、第一次來信時問一次）；
    enabled 是主機的開關，關著設定頁不畫那一顆、看守不開。畫面的改動，不掛 Config.jianfa。"""

    enabled: bool = False  # 測試內容照它關著；content/config.json 打開
    watch_seconds: float = Field(default=30, gt=0)  # 看守每幾秒看一次開了推播的人有沒有新的事
    quiet_seconds: float = Field(default=120, ge=0)  # 這麼久之內同步過（分頁開著、正在玩）就不跳通知：畫面上已經看得到
    per_round: int = Field(default=3, ge=1)  # 同一個人一輪最多跳幾則（離線一陣子回來不會被一串通知淹掉）
    max_devices: int = Field(default=5, ge=1)  # 一個帳號最多記幾台裝置


class ConquestRules(_Strict):
    """領地爭奪（第 38 項改版，docs/superpowers/specs/2026-10-20-領地爭奪-design.md；計畫 docs/superpowers/plans/2026-10-20-領地爭奪.md；
    tianxia/conquest.py）。地盤開著（territory.on：第一季規則開著、劇本有官軍與黃巾、寫了 territory.blocks、豪強分屬兩軍）就是領地爭奪，
    沒有開關（2026-10-27 舊的拔河與割據連 enabled、開季的章一起拿掉，企劃者選「拿掉舊玩法和它的測試」）。控制方只照佔領（不拔河、不割據），三條戰線的值＝佔領的基準＋其他
    來源的偏移，出陣推那一塊的進度、不推線，人站在自家領地吃加成，散人在開季中立的區塊也吃。翻地與爭搶（輿圖簡化設計第四章）：每一塊對
    每個攻方一條進度，推滿當場易手、冷卻一小時；兩邊推到同一塊撞上就打（混戰）；一起推有集火；攻下與守住都分紅；第 4 階的人進度過門檻
    可以下戰書，時間到了開攻城戰（siege.py，決戰的縮小版，跟決戰同時打），攻方贏了就易手。數字全是【預設】，等 21 天的季試玩再調。"""

    share: float = Field(default=35.0, ge=0)  # 【預設】佔領的份量：中立地全被一方拿下，基準偏到 50±share（分母只算中立時，設計 4.7）
    neutral_weight: float = Field(default=1.0, ge=0)  # 【預設】中立區塊的權重（設計 4.7）
    faction_weight: float = Field(default=2.0, ge=0)  # 【預設】陣營區塊的權重：打進敵方陣營影響比較大（設計 4.7、3.2）
    # 【預設】基準的分母：neutral＝那條線開季中立的權重和（裁決 5：中立全被拿下剛好走到 50±share）；total＝那條線所有可奪區塊的權重和
    # （設計 4.7 原文；潁川汝南被後方的陣營區塊稀釋到只偏幾點）。兩種都留，數字等試玩調
    weigh_by: Literal["total", "neutral"] = "neutral"
    gather_bonus_chance: float = Field(default=0.25, ge=0, le=1)  # 【預設】人站在自家領地找素材，多一個同屬性一階的機會（設計 4.5）
    sense_bonus_points: int = Field(default=5, ge=0)  # 【預設】人站在自家領地靜心感悟，擲中多幾個百分點（夾在 sense_rate_range 的上限，設計 4.5）
    progress_scale: float = Field(default=2.0, ge=0)  # 【預設】出陣推進度：max(1, 地點寫的推量合計) × 這個 ×（攻 1、守 hold_share）÷ √人數（計畫 2.3）
    event_progress: float = Field(default=1.0, ge=0)  # 【預設】在區塊做完一則事件，往自己那一邊推進度一次的量（計畫 2.3；散人不推）
    start_shift_per_10: int = Field(default=2, ge=0)  # 【預設】攻城戰起點：進度偏 50 每 10 點偏幾點（設計 4.4；第二批才用）
    start_shift_cap: int = Field(default=10, ge=0)  # 【預設】最多偏幾點（設計 4.4；第二批才用）
    # ── 每天的鐘與攻城時段（tianxia/conquest_day.py；設計 4.3，裁決 6；投票與 22:00 公告結算照輿圖簡化設計 4.4 拿掉了，PM 2026-10-20）──
    # 時刻一律是當地時間（照 pill_day_utc_offset_hours，跟回體丹同一個換日的算法）從 00:00 起算的分鐘
    settle_hour: int = Field(default=22, ge=0, le=23)  # 【預設】每天幾點換天（Game._conquest_tick 的掛鉤：前一天沒開成的攻城作罷、〈天下形勢〉一篇）；要晚過 slot_last
    slot_first: int = Field(default=12 * 60, ge=0, lt=24 * 60)  # 【預設】戰書的攻城最早幾點開打（設計 4.3：12:00～21:00 的整點或半點）
    slot_last: int = Field(default=21 * 60, ge=0, lt=24 * 60)  # 【預設】最晚幾點開打
    slot_step_minutes: int = Field(default=30, ge=1)  # 【預設】開打時段的間隔（整點與半點）
    showdown_gap_before: int = Field(default=30, ge=0)  # 【預設】時刻表決戰排定時刻之前幾分鐘不排攻城（裁決 6）
    showdown_gap_after: int = Field(default=45, ge=0)  # 【預設】之後幾分鐘不排攻城（裁決 6）
    muster_minutes: int = Field(default=30, ge=1)  # 【預設】開打前幾分鐘開集結（設計 4.3）；戰書挑的時段要晚過「現在＋這麼久」
    pay_share: float = Field(default=0.5, ge=0)  # 【預設】攻城戰的軍餉與貢獻是決戰的幾成（設計 4.4）
    # ── 翻地與爭搶（輿圖簡化設計第四章、第九章；計畫 docs/superpowers/plans/2026-10-20-翻地與爭搶.md）──
    # 進度：一塊地對每一個攻方各一條 0～100，攻推自己那一條、守（此刻佔著的那一方）把每一條都拉下，任一條到 100 當場易手（conquest.push）。
    # 全部【預設，等 21 天的季試玩】
    cooldown_minutes: float = Field(default=60.0, ge=0)  # 【預設】剛翻的地幾分鐘（現實）內兩邊都推不動、那一塊的加成暫停（設計 4.1【企劃者】）
    decay_per_day: float = Field(default=10.0, ge=0)  # 【預設】前一整個季曆日沒人推過的塊，每一條往守方回幾點（設計 4.1、第九章第 1 條）
    focus_minutes: float = Field(default=60.0, ge=0)  # 【預設】集火：這麼多分鐘內同一邊推過同一塊的其他人才算（設計 4.2）
    focus_step: float = Field(default=0.1, ge=0)  # 【預設】集火：每多一個人，每一下多幾成
    focus_cap: float = Field(default=0.5, ge=0)  # 【預設】集火最多多幾成
    clash_minutes: float = Field(default=10.0, ge=0)  # 【預設】混戰：對面這麼多分鐘內在這一塊出陣過、人還在這裡，撞上就打（設計 4.3【企劃者選 b】）
    clash_scale: float = Field(default=1.5, ge=0)  # 【預設】混戰打贏那一下的推力倍數（輸的那一下白跑）
    letter_at: float = Field(default=60.0, ge=0, le=100)  # 【預設】自己那一邊的條到這裡，第 4 階的人可以下戰書（設計 4.4）
    alarm_at: float = Field(default=50.0, ge=0, le=100)  # 【預設】守城功：哪一條到過這裡、守方再把全部拉回零才算（設計 4.5「從五成以上拉回零」）
    take_silver: int = Field(default=200, ge=0)  # 【預設】攻下一塊開季中立的地，推過的人照貢獻分的銀兩總額（設計 4.5）
    take_exp: int = Field(default=300, ge=0)  # 【預設】同上，經驗總額
    take_fame: int = Field(default=20, ge=0)  # 【預設】同上，名望總額
    faction_pool_share: float = Field(default=0.5, ge=0)  # 【預設】開季是陣營領地的塊，總額打幾成（設計 4.5「陣營區塊減半」）
    guard_pool_share: float = Field(default=0.5, ge=0)  # 【預設】守城功的總額是攻下的幾成（設計 4.5）
    # 【預設】兩軍同時攻同一塊中立地（三方混戰，裁決 22）：守將的池子＝這個 × 集結結束時兩軍到場的人數（至少算 2 人，siege.size_melee_guard）。
    # 一個人五回合都強攻、戰線在中線打得掉 15×5＝75：兩軍平均四成的回合出強攻，守將撐不過五回合（一回合最多打掉四分之一，最快第 4 回合倒）
    melee_pool_per_head: float = Field(default=30.0, gt=0)


class XingshiTuning(_Strict):
    """〈天下形勢〉（領地爭奪第三批 A；設計 3.10，計畫第五章 Task 16、17；tianxia/xingshi.py）：每天 22:00 換天那一刻開一張單，伺服器鎖外
    請模型照那一天的事實寫一篇旁白（三段式，server.write_xingshi），寫不出來照固定段。只在領地爭奪開著（conquest.on）而且這裡開著時有；
    模型只寫文章，不給任何數字、不定任何勝負。enabled 是主機的開關（關掉時不開單、不碰季的形勢欄位）。"""

    enabled: bool = True  # 【預設】正式開；領地爭奪本身還關著（ConquestRules.enabled），開了領地爭奪就有
    grace_seconds: float = Field(default=900, ge=0)  # 【預設】單開了這麼久（現實秒）還沒交回，下一個同步的人照固定段收（伺服器關著、模型壞了照樣每天一篇）
    budget_seconds: int = Field(default=120, ge=0)  # 【預設】鎖外那一趟模型呼叫的總預算（同決戰劇情 battle_tale_budget_seconds）
    # 【預設】佇列裡假人的名額被佔（或排不到）、這一趟沒叫成模型：單子放回去，隔這麼久（現實秒）再試；寬限（grace_seconds）到了才照固定段
    # （PM，第三批 A 回報之後）。不隔的話每一次輪詢都撞一次佇列
    retry_seconds: float = Field(default=30, ge=0)
    facts_max: int = Field(default=30, ge=1)  # 【預設】一張單最多幾條事實（攻城的在前、三條線、再補天下大事，新的在前）
    keep: int = Field(default=30, ge=1)  # 【預設】這一季最多留幾篇（21 天的季約 20 篇，留得下一整季）


class AmbushRules(_Strict):
    """設伏劫道（後期體力玩法第一批，Joy 2026-10-16；tianxia/ambush.py）：花一大筆體力守在一段路上，敵對的人走過那一段（步行、疾行都算）
    就跟你打一場；贏的搶走輸的一點銀兩與素材，輸的扣氣血——雙向的，伏兵輸了賠的是自己的東西。設伏的人守在路段的這一頭，期間不能移動
    （沒有分身）；下線也照守。保護照截殺：敵對陣營（或你揭了通緝他）、雙方過了新手期、城鎮旁邊的路不能設、同一對人的冷卻、剛被截過的護身。
    enabled 關掉：沒有設伏鈕，已經設下的照時刻作廢（_arrivals 不比）。時間都是世界秒（time_scale 1 就是現實秒）。"""

    enabled: bool = True
    stamina: int = Field(default=80, ge=0)  # 設一次花的體力（Joy：大約 80）
    hours: float = Field(default=3.0, gt=0)  # 守多久（世界小時）；期間可以自己收
    keep_hours: float = Field(default=24.0, ge=0)  # 收了、過了時刻的埋伏紀錄再留多久：下線的人回來補算路程時照「當時」有沒有埋伏判
    silver_share: float = Field(default=0.1, ge=0, le=1)  # 輸的一方失身上銀兩的幾成
    silver_cap: int = Field(default=40, ge=0)  # 最多失幾兩
    take_share: float = Field(default=1.0, ge=0, le=1)  # 贏的拿走其中幾成（Joy：輸的東西被搶走）
    materials: int = Field(default=2, ge=0)  # 輸的一方被搶走幾個素材（挑手上最多的那幾種，一階先）
    hp_loss: float = Field(default=0.1, ge=0, le=1)  # 輸的一方扣氣血上限的幾成（乘 1−防具減損，不變成內傷，同截殺）
    pair_cooldown_seconds: float = Field(default=3 * 3600, ge=0)  # 同一個伏兵劫同一個人的冷卻（跟截殺共用一本帳 WorldState.raids）
    win_contrib_push: int = Field(default=1, ge=0)  # 贏的記幾點推力的貢獻（只在第一季規則開著時，同截殺）


class FigureAidRules(_Strict):
    """同陣營的人護著大勢人物（Joy 2026-10-17 清單第 6 條「同陣營玩家能不能幫他回復，或是護衛他讓他不要太容易退場」；tianxia/figure_aid.py）。
    三樣都在人物所在的地點（探望在自己陣營的大本營），只有投靠了同一陣營的人有。兩種季都有。
    護衛：花 guard_stamina 站一班崗 guard_hours 個世界小時，把此刻的身手抄成分身；一位人物同時最多 guard_slots 班。敵方挑戰他時先跟班上最強的
    分身過一招（本人對本人，同截殺），輸了這一次挑戰不成；贏了那一班提前結束、接著打人物。一班最多擋 guard_blocks 次。人物離開那個地點，
    班就結束。擋下一次：護衛名望 +guard_fame、心得 +guard_xinde（下次同步補）。
    犒軍：花 rally_stamina 體力加 rally_silver 兩，聲威 +rally_points，補到開季值；一個人對同一位人物一天最多 rally_per_day 次。
    人物一天在戰場外回的聲威（自然回復、犒軍、人物自己募兵）合起來最多 daily_restore_cap 點（跟大勢人物擴充對好的）。
    探望：人物被打到退場或重創、還在等回來時，在自己陣營的大本營花 visit_stamina，讓他早 visit_hours 個季曆小時回來；每人每天一次，最多提前一半。
    enabled 關掉：三顆鈕都不畫，站著的班照時刻作廢、挑戰不再先打護衛。"""

    enabled: bool = True
    guard_stamina: int = Field(default=20, ge=0)
    guard_hours: float = Field(default=2.0, gt=0)
    guard_slots: int = Field(default=3, ge=1)
    guard_blocks: int = Field(default=3, ge=1)
    guard_fame: int = Field(default=1, ge=0)
    guard_xinde: int = Field(default=5, ge=0)
    rally_stamina: int = Field(default=30, ge=0)
    rally_silver: int = Field(default=20, ge=0)
    rally_points: int = Field(default=1, ge=1)
    rally_per_day: int = Field(default=2, ge=1)
    daily_restore_cap: int = Field(default=10, ge=0)
    visit_stamina: int = Field(default=20, ge=0)
    visit_hours: float = Field(default=2.0, gt=0)
    visit_max_share: float = Field(default=0.5, ge=0, le=1)
    contrib_push: int = Field(default=1, ge=0)  # 第一季規則開著時，每一下記幾點推力的貢獻


class StockpileRules(_Strict):
    """屯糧練兵（後期體力玩法第一批；tianxia/works.py）：在自家控制的地方花體力替自己那一軍屯糧，下一場時刻表決戰開集結那一刻，
    兩軍屯的量換成起點往屯得多的那一軍偏，最多 cap 點（照天命之爭的偏法夾住），屯的量隨即用掉。只有交戰兩軍（含依附那一軍的豪強）。"""

    enabled: bool = True
    stamina: int = Field(default=50, ge=0)  # 屯一下花的體力
    cap: int = Field(default=6, ge=0)  # 起點最多偏幾點
    soft: int = Field(default=20, ge=0)  # 偏移＝cap×(甲−乙)÷(甲＋乙＋soft)：兩邊都沒什麼人屯時偏得少


class PushResistance(_Strict):
    """盡頭阻力與季長縮放（設計第五節）。enabled 關掉：推力不打盡頭的折、每人每曆日上限與出陣推的量不乘季長倍數。"""

    enabled: bool = True
    full_within: int = Field(default=15, ge=0, le=50)  # 推之前離 50 在這以內（35～65，亂局帶）全額
    half_within: int = Field(default=35, ge=0, le=50)  # 在這以內（15～35、65～85）打 mid_share
    mid_share: float = Field(default=0.5, gt=0, le=1)
    far_share: float = Field(default=0.2, gt=0, le=1)  # 再外面（0～15、85～100）


class QuietHours(_Strict):
    """時刻表決戰避開半夜（企劃者 2026-10-15，經 PM）：照季曆自動排的決戰（開季、換季、天命之季蓋章）的集結開始換成現實時間，
    集結加打一幕（timetable.showdown_span）碰到 start～end 點（時區照 pill_day_utc_offset_hours）的，挪到最近的可開時間
    （timetable.avoid_quiet_hours）。管理者自己排的時間不動。enabled 關掉一個字都不變。"""

    enabled: bool = True
    start: float = Field(default=0, ge=0, lt=24)  # 幾點起不開（當地時間）
    end: float = Field(default=8, gt=0, le=24)  # 幾點以後才開


class Season21Daily(_Strict):
    """21 天季的每天一批與推線（正式季整合設計第七章、6.1；只在 calendar.season21_on 的季讀，週末與 14 天一個字都不變）。
    數字都是【預設】（12.3 第 39 條：先照預設做），量完（第 5～8 批做完的 20 人假人三週）再調。
    - 軍令（7.1）：每天 00:00 每個陣營 orders_per_day 道；湊滿套效果時效果量乘 order_effect_share（0.43＝以前一週三道的總量攤到七天）。
    - 懸賞（7.2、6.1）：每天 00:00 一批，期限 bounty_days 天；經驗＝這一級升下一級的經驗 × exp_ratio，銀兩＝等級 × silver_per_level
      （求兵照那一把再加這一份）；滿級時經驗換成心得（第 8 批起是通用的 Config.maxed_exp_per_xinde）；討伐另擲 strike_tier3_chance 一個三階；
      重賞每天每邊擲 prize_treasure_chance、prize_horse_chance。
    - 推線（7.4）：出陣、捐軍備、事件乘 push_speed（取代季長倍數；事件再乘事件五折），每人每天每條線上限 push_daily_cap，
      盡頭阻力的兩檔 push_mid_share／push_far_share（離 50 的兩個邊界照 PushResistance）。"""

    orders_per_day: int = Field(default=1, ge=0)
    order_effect_share: float = Field(default=0.43, ge=0)
    bounty_days: float = Field(default=2, gt=0)
    # 求藝（"art"）企劃者 2026-10-21 跟懸賞榜的求藝一起拿掉
    exp_ratio: dict[str, float] = Field(
        default_factory=lambda: {"strike": 0.15, "escort": 0.12, "scout": 0.08, "arms": 0.10},
    )
    silver_per_level: dict[str, int] = Field(
        default_factory=lambda: {"strike": 6, "escort": 5, "scout": 3, "arms": 5},
    )
    strike_tier3_chance: float = Field(default=0.10, ge=0, le=1)
    prize_treasure_chance: float = Field(default=0.10, ge=0, le=1)
    prize_horse_chance: float = Field(default=0.07, ge=0, le=1)
    push_speed: float = Field(default=1.0, ge=0)
    push_daily_cap: float = Field(default=10, gt=0)
    push_mid_share: float = Field(default=0.5, gt=0, le=1)
    push_far_share: float = Field(default=0.2, gt=0, le=1)


class EconomyRules(_Strict):
    """素材與經濟（docs/superpowers/specs/2026-10-15-素材與經濟-design.md；tianxia/economy.py）：每一樣一個開關，預設開、
    測試內容關，關掉一個字都不變（亂數序列也一樣）。都上線就生效，不看季的章。"""

    gather_cut: bool = True  # 找素材的一階從一定給改成 gather_first_chance（第七節；城鎮的 town_chance 照舊）
    gather_first_chance: float = Field(default=0.7, ge=0, le=1)
    sortie_silver: bool = True  # 出陣攻打贏加給對手銀兩的 sortie_silver_share（第八節；守、攪局不給）
    sortie_silver_share: float = Field(default=0.3, ge=0, le=1)
    sell: bool = True  # 鐵匠鋪收購（第五節）：階 → 一個幾兩；不在表上的階不收（三階要留著做神器）；收購價不分地盤
    # 三階 18 兩只在素材四階開著時收（正式季整合 4.2、6.6；Config.four_tiers，關著照舊不收三階）；四階不在表上，一律不收
    sell_price: dict[int, int] = Field(default_factory=lambda: {1: 2, 2: 6, 3: 18})
    upgrade: bool = True  # 鐵匠鋪升階（第四節）：換到幾階 → 要幾個同屬性低一階的、工錢（套地盤福利 territory.price_factor）
    upgrade_need: dict[int, int] = Field(default_factory=lambda: {2: 3, 3: 10})
    upgrade_silver: dict[int, int] = Field(default_factory=lambda: {2: 5, 3: 50})
    # 一天最多換幾個（回體丹的換日，台灣 00:00）；不在表上的不限。素材四階開著時不設每日上限（正式季整合 4.2：拿掉二換三一天一個），
    # 三換四另有一季的上限（Config.four_tiers.season_cap）
    upgrade_per_day: dict[int, int] = Field(default_factory=lambda: {3: 1})
    # 升階出來的是哪一種（企劃者 2026-10-15 選「屬性隨機、偏向投入的」）：這個機會是投入的那個屬性，其餘平均落到同一階的其他屬性
    # （正式內容剛柔快慢，各 1/6）；1 是一定照投入的屬性、不擲骰。擲骰用自己的亂數（economy.upgrade_rng），不碰 Game.rng
    upgrade_same_share: float = Field(default=0.5, ge=0, le=1)
    donate: bool = True  # 自家陣營的大本營捐軍備（第六節）
    donate_points: dict[int, int] = Field(default_factory=lambda: {1: 1, 2: 3, 3: 9})  # 階 → 貢獻（糧草的份量）
    donate_daily_cap: int = Field(default=100, ge=0)  # 每人每天捐的貢獻最多幾點（回體丹的換日）
    # 每一點貢獻推大勢多少（PM 2026-10-15 同意專職開發的定法）：再打事件五折（Config.explore_modes.event_trend_share）、
    # 季長倍數、盡頭阻力，跟出陣共用每人每日推力上限，不另記推力的貢獻（貢獻照捐的份量記）
    donate_push_per_point: float = Field(default=0.05, ge=0)
    armaments: dict[str, str] = Field(  # 素材屬性 → 陣營軍備的名字（第六節第 3 點；存量照份量累積）
        default_factory=lambda: {"慢": "糧秣", "快": "箭矢", "剛": "甲冑", "柔": "戰馬"}
    )


class FourTiers(_Strict):
    """素材四階（docs/superpowers/specs/2026-10-17-正式季整合-design.md 第四、五章；tianxia/four_tiers.py）：主機的緊急開關，
    預設開、測試內容關。內容（四階料、九件神器的配方與口訣、四階名器名字表）收不回（10.1），這裡關得掉的是規則：三階收購與黑市、
    拿掉二換三一天一個（關著回到 economy.upgrade_per_day）、三換四、四階名器的機率、鐵匠講神器的規矩。數字都是 PM 提案或暫定。"""

    enabled: bool = True
    upgrade_need: int = Field(default=5, ge=1)  # 三換四：幾個同屬性的三階（4.5）
    upgrade_silver: int = Field(default=150, ge=0)  # 三換四的工錢（乘地盤福利與名望折扣，同升階老規矩）
    season_cap: int = Field(default=2, ge=0)  # 三換四一季最多幾個（PlayerState.tier4_upgrades）
    named_main: float = Field(default=0.5, ge=0, le=1)  # 主料四階、沒打中神器配方：出名器的機會（5.2）
    named_both: float = Field(default=0.8, ge=0, le=1)  # 主輔都是四階（也沒打中神器配方）
    # 四階的來源（4.5，第 4 批）：挑戰本人這一季第一次打贏某位人物另擲一個；時刻表決戰得勝那一方出手夠的人各一個
    challenge_chance: float = Field(default=0.15, ge=0, le=1)
    challenge_cap: int = Field(default=2, ge=0)  # 挑戰本人掉的四階一人一季最多幾個（另一本帳 PlayerState.tier4_challenge_drops）
    showdown: bool = True  # 時刻表決戰得勝給四階（天命之爭、保底收場不給）


class SilverOutlets(_Strict):
    """銀兩出口（docs/superpowers/specs/2026-10-17-正式季整合-design.md 6.5；tianxia/silver.py）：21 天季才有（enabled 預設關，
    只有 content/profiles/season21.json 打開，另照開季的章）。數字都是【預設】【待量】（12.3 第 39 條）。「一天」照回體丹的換日。"""

    enabled: bool = False
    donate_per_point: int = Field(default=10, ge=1)  # 捐銀兩：每幾兩記 1 點貢獻、捐成糧秣；跟捐素材共用 Config.economy.donate_daily_cap
    donate_step: int = Field(default=100, ge=1)  # 按一下捐幾兩（收不下時照收得下的捐）
    donate_daily_silver: int = Field(default=1000, ge=0)  # 一天最多捐幾兩
    mentor_silver: int = Field(default=50, ge=0)  # 名師指點：有醫館的城鎮，下一次修練升品的機率加 mentor_bonus（在上限之內），一天一次
    mentor_bonus: int = Field(default=10, ge=0)
    furnace_silver: int = Field(default=50, ge=0)  # 看火候：有鐵匠鋪的城鎮，下一次合成或打造的品質基準換成 furnace_odds，一天一次、序章不能用
    furnace_odds: dict[str, float] = Field(default_factory=lambda: {"下品": 35, "中品": 40, "上品": 25})
    legend_silver: int = Field(default=300, ge=0)  # 醫館買破境丹：一枚幾兩，一個角色一季最多 legend_season_cap 枚（撿到的不算）
    legend_season_cap: int = Field(default=2, ge=0)
    bribe_silver: int = Field(default=30, ge=0)  # 打點門路（塞門房）：大勢人物所在的地點，情誼 +bribe_affinity，一位一天一次，只加到 bribe_max
    bribe_affinity: int = Field(default=5, ge=0)
    bribe_max: int = Field(default=40, ge=0, le=100)


class CheckIn(_Strict):
    """每日簽到與回體丹（docs/superpowers/specs/2026-10-17-正式季整合-design.md 6.2～6.4；tianxia/checkin.py）：21 天季才有（enabled 預設關，
    只有 content/profiles/season21.json 打開，另照開季的章）。第 N 天照開季那一天（台灣日）起算（12.3 第 43 條）。
    表照 6.2 與 12.3 第 27 條：丹的日子只給丹、四階的日子只給四階（第 6 天兩樣都給），其餘的日子照先後輪流銀兩、一階素材【預設】。"""

    enabled: bool = False
    pills: int = Field(default=2, ge=0)  # 丹的日子給幾顆回體丹
    pill_days: list[int] = Field(default_factory=lambda: [3, 6, 9, 12, 15, 18, 21])
    tier4_days: list[int] = Field(default_factory=lambda: [6, 13, 20])  # 自己挑屬性的四階一個（素材四階關著時第 13、20 天改給銀兩）
    silver: int = Field(default=30, ge=0)  # 一般日子（照先後的第 0、2、4…個）給幾兩
    material_tier: int = Field(default=1, ge=1, le=3)  # 一般日子（第 1、3、5…個）給一個這一階的素材（照種子挑）
    pill_drop: float = Field(default=0.02, ge=0, le=1)  # 找素材、練功各擲一次掉一顆回體丹（6.4）


class MallTuning(_Strict):
    """商城（docs/superpowers/specs/2026-10-20-商城架構-design.md；tianxia/mall.py、tianxia/wallet.py）。enabled 預設關、測試內容明寫關、
    正式內容與 week7 開；關著時不發元寶、不讀不寫商城的三張表（月卡不加上限）、商城的 API 都 404，其餘一個字都不變（4.10）。
    設定覆寫檔是淺合併：覆寫檔寫 mall 就要整個寫（例 week7 寫 {"enabled": true, "beta_grant": 5000}），不然 enabled 會回到預設的關。"""

    enabled: bool = False
    # 封閉測試的元寶（4.2）：每個錢包第一次進來（本人那一輪，Game.own_turn_checks）時發一次，寫一列「封測發放」；0 是不發。
    # 正式內容 0、week7 5000【預設】；之後再開新的一季不再發（編號 grant:beta:<主人> 只記一次）
    beta_grant: int = Field(default=0, ge=0)
    card_pill_bonus: int = Field(default=1, ge=0)  # 月卡：每天能服的回體丹多幾顆（企劃者 10/17「月卡每天多 1 顆」；平常 2→3、新手期 5→6）
    # 月卡每日領（Joy 2026-10-21 定案甲・每日領，/mnt/project-files/plan/萬寶閣販賣清單定案.md）：卡的期間裡每天（台灣 00:00 換日）上線
    # 按一下領這麼多元寶與回體丹，沒上線那天不補（Joy「沒上線不補」）。0 是沒有這一份（舊規則）；正式內容與 week7 寫 60／1
    card_daily_ingots: int = Field(default=0, ge=0)
    card_daily_pills: int = Field(default=0, ge=0)
    records_shown: int = Field(default=50, ge=1)  # 購買紀錄與帳的畫面、管理者查帳最多列幾筆【預設】


class MallLimit(_Strict):
    """一件商品的限購（4.3）：每天（台灣 00:00 換日，同回體丹）、每季、每個帳號各幾次；不寫是不限。數的是沒退的購買。"""

    day: int | None = Field(default=None, ge=1)
    season: int | None = Field(default=None, ge=1)
    account: int | None = Field(default=None, ge=1)


class MallWindow(_Strict):
    """一件商品的上架期間（4.3）：哪幾季（空的是每一季）、哪一段日子（台灣日期 YYYY-MM-DD，含頭尾；不寫是不限）。
    減法季批 7b（列傳為終點的四件商品，整合設計第九章）多三樣，都不寫就跟以前一樣：rule 是 Config.jianfa 的子開關名，這一季
    （開季的章）開著才上架；phases 是賣在季中（season：籌備中與開打的季）還是休季（resting），空的是都賣；from_week 是季中從季曆
    第幾週起賣（休季不看）。"""

    seasons: list[int] = Field(default_factory=list)
    start: str | None = None
    end: str | None = None
    rule: str | None = None
    phases: list[Literal["season", "resting"]] = Field(default_factory=list)
    from_week: int | None = Field(default=None, ge=1)


class MallItem(_Strict):
    """商城的一件商品（content/mall.json，joy 寫；4.3）。效果只能從 mall.EFFECTS（允許的效果表）挑、種類要對得上，載入時
    content.check_mall 擋表外的。外觀（look）、通行證（pass）的種類留著，這一版允許表裡沒有它們的效果，所以寫不出來（4.3）。"""

    id: str
    name: str  # 過 naming.name_problem
    note: str = ""  # 一句說明（joy 寫）
    price: int = Field(gt=0)  # 元寶
    kind: Literal["look", "consumable", "card", "pass"]
    effects: dict[str, int] = Field(default_factory=dict)  # 效果 → 數量（例 {"pills": 5}、{"card_days": 30}）
    limit: MallLimit = Field(default_factory=MallLimit)
    on_sale: MallWindow = Field(default_factory=MallWindow)
    draft: str = ""  # 作者的備註（例「PM 佔位：名字、說明、價錢待 joy」）；不給玩家看


class Config(_Strict):
    stamina_max: int = 150
    stamina_regen_seconds: float = 180  # 自然回復：每幾秒（遊戲時間）回 1 點體力（地圖擴充設計第二節：每 3 分鐘 1 點）
    rest_regen_multiplier: float = Field(default=2, ge=1)  # 打坐 2026-10-12 拿掉了（企劃者），沒有地方讀它；留著是舊設定檔讀得進來
    # 地方痕跡的門檻倍數（Condition.marks_min/max 的數字乘上它、無條件進位）：開發期 1，正式伺服器依人數調大
    mark_threshold_scale: float = Field(default=1.0, gt=0)
    # 熟練加成（Check.practice）：名聲 → 每幾點加 1、最多加幾。惡名的估算見 CLAUDE.md「惡名的熟練加成」。
    practice_bonus: dict[str, PracticeBonus] = Field(default_factory=lambda: {
        "evil": PracticeBonus(per=10, cap=3, line="這種事{who}幹得多了。"),
    })
    # 地圖座標 1 單位＝步行幾分鐘：現行內容（40 個地點的地圖）取 0.04，也就是 25 個單位約 1 分鐘；這裡的預設值只是沒寫時的退路
    travel_minutes_per_unit: float = Field(default=0.0375, gt=0)
    road_factor: dict[RoadKind, float] = Field(
        default_factory=lambda: {"官道": 0.8, "路": 1.0, "山路": 1.5}
    )  # 路程＝距離 × 路的種類係數 × travel_minutes_per_unit（地圖擴充設計 3.1）
    hurry_stamina_per_minute: float = Field(default=1, ge=0)  # 趕路：每分鐘路程扣幾點體力（時間減半）
    dash_stamina_per_minute: float = Field(default=2, ge=0)  # 疾行：每分鐘路程扣幾點體力（立刻到）
    # 路上小事（路上設計第四節）：收入要明顯低於在站上做事，不然一直趕路會變成最賺的玩法
    road_think_xinde: int = Field(default=3, ge=0)  # 邊走邊想：心得（一次遊歷大約 12～20）
    road_rumor_pool: int = Field(default=5, ge=1)  # 沿途打聽：從這一帶最近幾則傳聞裡挑一則
    # 傳聞分層（傳聞分層設計第三、八節；第一季的規則開著時才用，計畫 2026-10-06 傳聞分層一）
    # 大區的傳聞板留最近幾天（季曆天，跟著 weekend 設定縮）；輿圖 ✦ 與詳情欄的「最近幾天」也用這一個（atlas.news_days）
    rumor_board_days: float = Field(default=3, gt=0)
    away_hours: float = Field(default=1, gt=0)  # 「你不在的時候」：離線超過幾個「現實」小時，再上線先看一份摘要（PM 2026-10-06）
    # 那一份摘要最多幾行（含放不下時最後那一行「另有 N 則」；天下大事、陣營軍情的要點、所在大區，照這個順序）。
    # 8：第一屏放得下（最終審查 I1：週末一晚離開 15～17 行幾乎都是過期的軍令）
    away_max: int = Field(default=8, ge=1)
    road_gather_chance: float = Field(default=0.4, ge=0, le=1)  # 路邊採集：撿到一樣一階素材的機率
    road_sight_chance: float = Field(default=0.3, ge=0, le=1)  # 路上見聞：每抵達一站有幾成機會看見一則（路上設計第五節）
    road_sight_recent: int = Field(default=5, ge=0)  # 路上見聞：最近看過的幾則先排除，池子不夠才重複
    road_reward_daily_cap: int = Field(default=6, ge=0)  # 路上小事、見聞的收穫每個遊戲日各前幾次才有（遊戲日跟著季長縮：rules.day_seconds）
    ollama_url: str = "http://localhost:11434"  # companion_agent.py 深度對話用；連不上時那輪對話取消
    ollama_model: str = "qwen2.5:14b"
    ollama_timeout: int = 120
    # 行動鎖內的模型呼叫（大事與決戰回合的潤色、決戰自訂行動的評分、鎖內才備料的對話與記憶整理、
    # 鎖內才取名的開爐）最多等幾秒：鎖拿著的時候全服玩家與假人都在等，模型慢或冷的時候照 ollama_timeout 的 120 秒會讓整台
    # 伺服器凍結好幾分鐘，試玩走的 trycloudflare 也會在約 100 秒切斷請求。Game._quick_client 給鎖內呼叫端這個逾時的複本
    # （引擎不讀時鐘，靠 HTTP 的逾時，跟 naming.propose 同一個做法）；逾時或失敗都退回固定的文字。這是硬上限：鎖內的呼叫
    # 不重問（chat_structured 只送一趟）、記憶整理／性情漂移／取名只試一次，而且一次拿鎖期間有一次呼叫失敗之後，後面的鎖內
    # 呼叫都不再叫模型。鎖外的路徑（對話備料、開爐取名、隨口應對的評分與潤色）有自己的逾時與重問，不受這個管。
    # 第二階段的模型佇列上線後，鎖內就不該再有模型呼叫了
    in_lock_model_timeout: int = Field(default=15, ge=1)
    # 開爐首次取名（鎖外的 B 段）整段最多花幾秒（最終審查 Critical 1）：server.py 讀它、扣掉 A 段等鎖的時間，傳給
    # naming.generate 的 budget；用完就走退路字表。試玩走 trycloudflare，一個請求約 100 秒就被切斷，60 秒留下 A、C 兩段
    # 等行動鎖的餘裕（控制者 2026-10-05 從 75 改成 60）
    naming_budget_seconds: int = Field(default=60, ge=0)
    # 大場面（武學與成長設計 8.3、計畫三 Task 2）：挑戰大勢人物本人、打頭目（Squad.boss）或難度到這裡的對手，先在行動鎖外
    # 請模型判讀，優勢最多把勝算推這麼多個百分點；鎖外那一段（含 A 段等鎖）最多花 big_fight_budget_seconds 秒
    # （server.prepare_fight 扣掉等鎖的時間傳給 fight_llm.judge，跟開爐取名同一個理由：trycloudflare 約 100 秒切斷請求）
    big_fight_difficulty: float = 100  # 難度到這裡就算大場面【預設】
    big_fight_swing: int = Field(default=15, ge=0)  # 模型判讀最多把勝算推多少個百分點【預設】
    styles: StyleRule = Field(default_factory=StyleRule)  # 大場面對手的路數（一門打不遍，見 StyleRule）
    first_echo: FirstEcho = Field(default_factory=FirstEcho)  # 首創名望回饋（見 FirstEcho）
    secrets: Secrets = Field(default_factory=Secrets)  # 口訣與秘方（見 Secrets）
    forge_secrets: ForgeSecretRules = Field(default_factory=ForgeSecretRules)  # 打造的隱藏配方（見 ForgeSecretRules）
    seal: SealTuning = Field(default_factory=SealTuning)  # 玉璽碎片（見 SealTuning；內容在 content/seal.json）
    showdown_pay: ShowdownPay = Field(default_factory=ShowdownPay)  # 全服決戰的軍餉與獲勝加給（見 ShowdownPay）
    duel: DuelTuning = Field(default_factory=DuelTuning)  # 單人頭目戰（見 DuelTuning；內容在 content/duels.json）
    arena: ArenaTuning = Field(default_factory=ArenaTuning)  # 擂台賽（見 ArenaTuning；tianxia/arena.py）
    tavern: TavernTuning = Field(default_factory=TavernTuning)  # 酒肆（見 TavernTuning；tianxia/tavern.py）
    mall: MallTuning = Field(default_factory=MallTuning)  # 商城：元寶錢包、商品、月卡、封測發放（見 MallTuning；商品在 content/mall.json）
    raid: Raid = Field(default_factory=Raid)  # 截殺敵對陣營的人（見 Raid）
    bounties: Bounties = Field(default_factory=Bounties)  # 懸賞榜（見 Bounties）
    sortie: SortieRules = Field(default_factory=SortieRules)  # 出陣（見 SortieRules）
    explore_modes: ExploreModes = Field(default_factory=ExploreModes)  # 探索三選一（見 ExploreModes）
    gather_branches: GatherBranches = Field(default_factory=GatherBranches)  # 找素材分支（見 GatherBranches；內容在 content/gather_branches.json）
    training: Training = Field(default_factory=Training)  # 城裡操練、城外練功分級（見 Training）
    # 一類一顆（正式季整合第二章；tianxia/precise.py）：每一顆鈕只給一類、按了一定拿到那一類。預設開、測試內容關；照開季蓋章
    # （WorldState.precise_actions，12.3 第 13 條：正在跑的季不變、下一個開季起生效）；探索三選一也開著時才生效
    precise_actions: bool = True
    # 借進找事件的戰後事件（內容寫 train 的九則）在一處池子裡合起來最多佔幾成（PM 2026-10-19：QA 量到潁川郊野佔七成）；
    # 當地自己的事件都抽不到時照舊補上，池子裡只有這幾則時不受上限（events.pick_event）
    precise_aftermath_share: float = Field(default=0.3, ge=0, le=1)
    insight_strong: InsightStrong = Field(default_factory=InsightStrong)  # 意境提示：每個地點最濃的意境（見 InsightStrong）
    terrain_arts: TerrainArts = Field(default_factory=TerrainArts)  # 地利：武學跟此地最濃的意境同一路或被剋（見 TerrainArts）
    territory: TerritoryRules = Field(default_factory=TerritoryRules)  # 地盤易手（見 TerritoryRules）
    conquest: ConquestRules = Field(default_factory=ConquestRules)  # 領地爭奪（見 ConquestRules）
    jianfa: JianfaRules = Field(default_factory=JianfaRules)  # 減法季（見 JianfaRules；暫名）
    epiphany: EpiphanyRules = Field(default_factory=EpiphanyRules)  # 特殊頓悟（見 EpiphanyRules）
    xingshi: XingshiTuning = Field(default_factory=XingshiTuning)  # 〈天下形勢〉：領地爭奪每天一篇的旁白（見 XingshiTuning）
    ambush: AmbushRules = Field(default_factory=AmbushRules)  # 設伏劫道（見 AmbushRules）
    figure_aid: FigureAidRules = Field(default_factory=FigureAidRules)  # 護衛、犒軍、探望大勢人物（見 FigureAidRules）
    stockpile: StockpileRules = Field(default_factory=StockpileRules)  # 屯糧練兵（見 StockpileRules）
    push_resistance: PushResistance = Field(default_factory=PushResistance)  # 盡頭阻力與季長縮放（見 PushResistance）
    battle_quiet_hours: QuietHours = Field(default_factory=QuietHours)  # 時刻表決戰避開半夜（見 QuietHours）
    economy: EconomyRules = Field(default_factory=EconomyRules)  # 素材與經濟：收購、升階、捐軍備、找素材減量、出陣銀兩（見 EconomyRules）
    four_tiers: FourTiers = Field(default_factory=FourTiers)  # 素材四階的規則（見 FourTiers）
    silver_outlets: SilverOutlets = Field(default_factory=SilverOutlets)  # 21 天季的銀兩出口（見 SilverOutlets）
    checkin: CheckIn = Field(default_factory=CheckIn)  # 21 天季的每日簽到與掉回體丹（見 CheckIn）
    weapons: WeaponRules = Field(default_factory=WeaponRules)  # 兵器（見 WeaponRules）
    armor: ArmorRules = Field(default_factory=ArmorRules)  # 防具（見 ArmorRules；裝備四欄設計第四節）
    mounts: MountRules = Field(default_factory=MountRules)  # 坐騎（見 MountRules；裝備四欄設計第五節）
    follower: FollowerTuning = Field(default_factory=FollowerTuning)  # 部下的成長與決戰份量（見 FollowerTuning）
    chuangong: ChuangongTuning = Field(default_factory=ChuangongTuning)  # 傳功門下：心得花在同伴、部下身上（見 ChuangongTuning）
    arts: ArtsTuning = Field(default_factory=ArtsTuning)  # 武學重構：品級的槽數、戰力的權重、自創的價錢（見 ArtsTuning）
    signature_arts: SignatureArtTuning = Field(default_factory=SignatureArtTuning)  # 本命武學的威力與學到時的成數（見 SignatureArtTuning）
    tactics: TacticTuning = Field(default_factory=TacticTuning)  # 一般的仗的回合與本命戰法（見 TacticTuning）
    figure_life: FigureLifeTuning = Field(default_factory=FigureLifeTuning)  # 人物活起來：每日行事、心事、風聞（見 FigureLifeTuning）
    plans: PlanTuning = Field(default_factory=PlanTuning)  # 世界活起來：人物的行程與盤算、世界記事（見 PlanTuning）
    parley: ParleyTuning = Field(default_factory=ParleyTuning)  # NPC 智能 2.0：模型談判、引擎做事（見 ParleyTuning）
    companions: CompanionsTuning = Field(default_factory=CompanionsTuning)  # 歷史武將同行：招募、名下三位、決戰助陣（見 CompanionsTuning）
    # 情誼放慢（歷史武將同行第三節、9.4）：每一筆加的情誼乘這個倍數（renown.warmed：四捨五入，原本加 1 以上的至少加 1；扣的不乘）。
    # 1 是不放慢；正式 0.7、週末設定 0.85。對話、事件、名聲起步、風聞都走它；名將贈禮、本命、招募的門檻不動，所以跟著晚一點拿到
    affinity_gain_scale: float = Field(default=1.0, gt=0, le=1)
    rise: RiseTuning = Field(default_factory=RiseTuning)  # 江湖水漲：大場面、頭目、事件檢定跟得上變強的人（見 RiseTuning）
    treasures: TreasureRules = Field(default_factory=TreasureRules)  # 寶物與好馬的來源（見 TreasureRules；裝備四欄設計第六節）
    ranger: Ranger = Field(default_factory=Ranger)  # 遊俠名號（散人的成長階梯，見 Ranger）
    renown: RenownTuning = Field(default_factory=RenownTuning)  # 名聲（兩個稱號與各段的效果，見 RenownTuning）
    biography: Biography = Field(default_factory=Biography)  # 玩家傳：行狀與季末的傳（見 Biography）
    mingtie: MingtieTuning = Field(default_factory=MingtieTuning)  # 名帖與挑釁附一句話（見 MingtieTuning）
    spar: Spar = Field(default_factory=Spar)  # 切磋（見 Spar）；雙方各花 action_cost["train"] 的體力
    # 玩家之間的邀請（invites.py）放多久沒回就作廢（世界秒）：10 分鐘夠對方看到、想一下、按下去；週末設定也不縮——
    # 兩個人都在線上才有切磋，等的是現實的人
    invite_ttl_seconds: int = Field(default=600, ge=30)
    big_fight_budget_seconds: int = Field(default=60, ge=0)
    # 人物對話的生成（鎖外的 B 段）與隨口應對的評分、潤色也各有一份總預算（PM 2026-10-06，跟開爐取名、大場面同一套；評分與潤色
    # 共用 free_text_budget_seconds，潤色用評分剩下的，控制者 2026-10-06）：server.py 從 A 段開始量、扣掉等行動鎖與排模型佇列的
    # 時間，剩下的一半當那一趟模型呼叫的逾時（chat_structured 一次最多送兩趟）；用完就走原本的退路（對話取消、評分 40、潤色不插句子）。
    # 以前這幾件只有 ollama_timeout（120 秒），重問一次最壞要 240 秒
    dialogue_budget_seconds: int = Field(default=60, ge=0)
    free_text_budget_seconds: int = Field(default=60, ge=0)
    # 決戰放手一搏的劇情（Joy 2026-10-13「應該要做到能承受」）：評分只回成功率，劇情等回合結算後一整回合批給模型寫一次
    # （server.narrate_battle，背景執行緒、在佇列裡排在真人的評分後面）；這是那一趟的總預算，用完就照固定句
    battle_tale_budget_seconds: int = Field(default=120, ge=0)
    # LLM 佇列（線上架構設計 5.2，第 2 期）：行動鎖外的模型呼叫先排隊（server.model_call）。llm_queue_slots＝顯卡同時處理幾件，
    # 0＝不建佇列（預設；照舊直接叫）；假人在排加在跑最多 llm_queue_bot_cap 件（滿了拿退路）；排超過 llm_queue_wait_seconds 秒
    # 還沒輪到的那一件不叫模型、被擋下來、不拿退路（PM 2026-10-06，跟第二件一樣）：評分、開爐、大場面、對話回一句話、什麼都不套用
    # （對話是 FB-077），潤色不插句子（每個人同時最多一件，第二件被擋下來、不拿退路，處理一樣）。
    # 排隊等掉的時間算在上面四份總預算裡，而且排隊最久只等「那一件預算還剩的秒數」（server.model_call）。上限 120 秒：請求在
    # trycloudflare 約 100 秒就被切斷；太大的數字還會讓 Condition.wait 丟 OverflowError（threading.TIMEOUT_MAX）
    llm_queue_slots: int = Field(default=0, ge=0)
    llm_queue_bot_cap: int = Field(default=1, ge=0)
    llm_queue_wait_seconds: float = Field(default=20, ge=0, le=120)
    # 2026-10-03 實測（gemma4:26b）：有思考模式的模型要關掉思考，不然每輪多等好幾秒；None 表示不送這個欄位
    ollama_think: bool | None = None
    ollama_keep_alive: str = "30m"  # 模型閒置多久後卸載；大模型重新載入要十幾秒
    # 重複懲罰：太重時模型會改用英文字避開已經用過的中文字（gemma4 實測），換模型時一起調
    ollama_repeat_penalty: float = 1.18
    ollama_presence_penalty: float = 0.3
    ollama_frequency_penalty: float = 0.3
    action_cost: dict[str, int] = Field(
        default_factory=lambda: {"explore": 10, "train": 10, "socialize": 5}
    )
    drill_reward_share: float = Field(default=0.3, ge=0, le=1)  # 跟自己人操練只給對手獎勵的幾成（戰鬥系統第八節：沒風險就拿得少）
    # 操練推大勢的基準季長（遊戲日；FB-165，企劃者 2026-10-12「操練給的聲勢要隨著賽季長度而調整」）：每次操練推
    # train_trend × min(1, 這個 ÷ 這一季蓋章的季長)。取週末設定的季長 2.5 天——操練的推力是照那一季調的，週末設定的倍數
    # 是 1、一個字都不變；14 天的季約 0.18（不然那種季沒有推力緩衝與上限，黃巾的人在自己營寨點三十下操練就收掉一整季）。
    drill_push_base_days: float = Field(default=2.5, gt=0)
    # 季長倍數小於 1（季比基準長）時，操練推的量再乘這個（PM 2026-10-12：企劃者「操練給的聲勢就不該那麼大佔比」）：14 天的季
    # 只照季長縮放時操練仍佔黃巾聲勢漲幅的六到十成，再打五折是 2.5／14 × 0.5 ≈ 0.09。週末設定倍數是 1、不乘。
    # 事件的大勢效果只照季長縮放、不乘這個（Game.season_scale）。
    drill_long_season_share: float = Field(default=0.5, gt=0, le=1)
    time_scale: float = 1.0
    # 伺服器自己的排程（線上架構設計第四節）：每幾秒推一次全服的事（世界時間、時刻表、開決戰、決戰逾時、季末）；
    # 0＝關（預設），世界照舊等有人連線才推。設計的預設是 10；由設定檔或 content/profiles 打開（打開哪一份由 PM 驗收後決定）
    world_tick_seconds: float = Field(default=0, ge=0)

    @field_validator("world_tick_seconds")
    @classmethod
    def _tick_off_or_at_least_a_second(cls, seconds: float) -> float:
        """0 是關；開著至少 1 秒：每一下是一筆寫入交易（含 fsync），0.1 秒就是每秒十筆（最終審查 M5）。"""
        if 0 < seconds < 1:
            raise ValueError("world_tick_seconds 是 0（關）或至少 1 秒")
        return seconds

    # 伺服器主動推送（線上架構設計 5.3；用 SSE，server_push.py）：push_events 開著時，分頁開一條 /api/events，有變化才刷新、
    # 平常 60 秒才問一次；關著（預設）/api/events 是 404，分頁照舊每 10 秒輪詢。看守每 push_watch_seconds 秒比一次「公開的
    # 世界指紋」，兩次「世界變了」的通知至少隔 push_world_min_seconds 秒（也是各分頁收到之後重抓畫面要攤開的秒數）
    push_events: bool = False
    push_watch_seconds: float = Field(default=5, gt=0)
    push_world_min_seconds: float = Field(default=10, ge=0)
    web_push: WebPushRules = Field(default_factory=WebPushRules)  # 手機跳通知（減法季第十章，批 9；server_push.WebPush）

    season_days: float = DEFAULT_SEASON_DAYS
    # 第一季濃縮版的規則（預設關，beta 那一季照舊）：季曆、時刻表、三條戰線都掛在這個開關後面。
    # 做到一半的 main 也會換上試玩伺服器，開關關著才不會把正在跑的那一季弄壞；
    # 全部做完、開測前由 PM 跟季長（season_days 改 2.5）一起打開（計畫 2026-10-04-第一季濃縮版）
    season_one: bool = False
    # 三條戰線與豪強割據（計畫 2026-10-04-T1；開關關著時沒人讀它們）
    geju_chaos_per_day: float = Field(default=1.0, ge=0)  # 每有一條戰線在亂局，豪強割據每曆日漲幾點
    # 割據漲速依人數等比例調整（企劃者 2026-10-05，測試階段）：漲速再乘 min(1, 這一季投靠名冊人數 ÷ geju_full_players)。
    # 湊滿這個人數就是設計的速度；人少的季（週末只有兩個人、沒人玩）割據照人數比例慢下來，不會第 5 週就衝到 100 提早收季。只管漲，不管回落
    geju_full_players: int = Field(default=15, gt=0)
    geju_calm_per_day: float = Field(default=1.0, ge=0)  # 三條戰線都穩下來時，豪強割據每曆日回落幾點（不能是負的，否則「回落」變成漲）
    chaos_low: int = 35  # 亂局：戰況在 chaos_low～chaos_high 之間（含兩端，第一季設計 4.2；low 不能大於 high，content.validate 檢查）
    chaos_high: int = 65
    # 第一季豪強分屬兩軍（企劃者 2026-10-15：「一樣可以選豪強～只是豪強中也區分黃巾～以及官軍」「純官軍或者純黃巾才有辦法升到最高
    # 軍階，豪強版的只能升到三階」）：開季時蓋章（WorldState.haoqiang_allied），只在蓋了第一季章的季生效（allied.on）。
    # 預設關、週末設定開；14 天的季就算打開也照舊有第三方豪強
    haoqiang_allied: bool = False
    # 21 天季的骨架（正式季整合設計第一章；12.3 第 41 條：預設關，只有 content/profiles/season21.json 打開，週末與 14 天一個字都不變）：
    # 季曆就是現實的三週（season_weeks 3、season_days 21，cal_scale 1），錨在開季那一週的台灣週一 00:00（WorldState.cal_offset）；
    # 21 天季自己的時刻表（TimetableEvent.real）、官軍將領與伏筆照天數、不提前收季、「今天」是現實的一天（台灣 00:00 換日）。
    # 開季時蓋章（WorldState.season21），正在跑的季照它開季時的章。
    # 名字是歷史的：現在是「照現實天的季」的骨架，7 天濃縮季（content/profiles/week7.json，企劃者 2026-10-20）也打開，另寫 season_segments
    season21: bool = False
    season_weeks: int = Field(default=12, ge=1)  # 季曆：一季壓成幾週（計畫第六節：季曆秒＝世界秒 × 週數 × 7 ÷ season_days）
    # 7 天濃縮季（企劃者 2026-10-20；計畫 docs/superpowers/plans/2026-10-20-七天濃縮季.md）：照現實天的季把季曆的「週」換成幾段、每段幾天
    # （week7 寫 [2, 2, 3]：第 1～2、3～4、5～7 天）。照週算的東西（第四階輪替、月旦評、寶物每週上限、頭目每週次數、貢獻的週帳、版圖變化）
    # 一律照段；錨點是開季那一天的台灣 00:00（開季那天是第 1 天），畫面寫「第 N 天 HH:MM」（calendar.week7_on）。
    # 空的是一週 7 天（21 天季與其他季，一個字都不變）。載入時驗：要 season21、段數＝season_weeks、段的和＝season_days＝7
    season_segments: list[int] = Field(default_factory=list)
    # 決定性勝利（黃巾聲勢 ≥85、≤15）季曆第幾週起才提前收季；之前到了門檻也不收，季末照常比（企劃者 2026-10-05，計畫 T9）。
    # 割據 ≥85 不提前收季、季末才判群雄並起（FB-254，企劃者 2026-10-15「提前收季只看戰線」；rules.ends_early）
    decisive_from_week: int = Field(default=10, ge=1)
    # 企劃者 2026-10-13「季中，第 5 週起才開」（FB-168）：規則關著的季，開決戰的大勢門檻（starts_battle，例 huangjin_60）季曆第幾週起才開
    # 集結；之前推過了也不開、不記成觸發過，到了那一週還在門檻上就開（world.battle_held，寫法同 decisive_from_week）。第一季照時刻表，
    # 不受影響。測試內容寫 1（舊測試第 1 週就開）
    battle_from_week: int = Field(default=5, ge=1)
    # 時刻表的人物結局扣多少聲威（時刻表結算文件第一節）：只有這三種用詞會扣；退場、重創是聲威歸零，下獄、到任不動聲威
    fate_prestige: dict[Literal["重挫", "聲威大減", "受挫"], int] = Field(
        default_factory=lambda: {"重挫": -30, "聲威大減": -30, "受挫": -15}
    )
    # 大勢人物（計畫 T4、總計畫第五節）：挑戰本人每季都有（figures.challenge_on）；推戰線、反應規則只在第一季
    figure_reaction_lean: int = Field(default=15, ge=0)  # 戰線偏向對方這麼多時，人物推得更勤（反應規則，第一季設計 8.2）
    figure_reaction_mult: float = Field(default=2.0, ge=1)  # 推得更勤的倍數
    figure_defeat_prestige: int = Field(default=5, ge=0)  # 挑戰本人打贏一次扣幾點聲威（照陣營人數緩衝）
    figure_defeat_affinity: int = Field(default=5, ge=0)  # 打贏的人跟他的情誼扣多少（軍令文件 4.5）
    snub_hours: float = Field(default=2, ge=0)  # 打贏之後幾個「現實」小時內他不見你、也不跟你交手（軍令文件 4.5）
    figure_difficulty_floor: float = Field(default=0.5, ge=0, le=1)  # 挑戰本人的難度：聲威 0 時是隊伍難度的幾成（100 時原值，中間線性）
    # 挑戰大勢人物每季都有（挑戰每季都有設計 3.1）：第一季以外的季也有挑戰本人；關掉就回到「只有第一季」（主機的退路，第一季不看它）
    figure_challenge_every_season: bool = True
    # 甲 (b)＋(d)，企劃者 2026-10-13：沒有時刻表的季，被打下來的聲威每個季曆天回幾點（14 天的季一個季曆天是現實 4 小時；0＝不回）、
    # 每位人物每個遊戲日最多被打掉幾點（0＝不設）。目標「十來個人合力連打好幾天才打得退，一季頂多一兩位」
    figure_prestige_regen: float = Field(default=1, ge=0)
    figure_daily_loss_cap: int = Field(default=15, ge=0)
    # 二十人試玩（PM 2026-10-16，週末第一季一季打退官軍五位）：兩種季都算。
    # figure_dent_once_per_day：同一個人對同一位人物，一個遊戲日（世界秒 // DAY）只有第一場打贏扣聲威，之後照拿獎勵、聲威不動。
    # figure_return_days：被挑戰打到退場、重創的人物，過這麼多季曆天以 figure_return_share × 開季聲威回到原本的戰線與所在
    # （0＝不回來）；時刻表寫死的退場、重創、病逝不回來。
    figure_dent_once_per_day: bool = True
    # 挑戰大勢人物本人打成僵持（企劃者 2026-10-16）：給險勝那一份心得、經驗的這麼多（engine._challenge_draw），另算一次頓悟的契機；
    # 銀兩、素材、三階、寶物、碎片、聲威、情誼、閉門不見都沒有。0 是舊規則（僵持什麼都不給，也不擲頓悟）
    figure_draw_share: float = Field(default=0.5, ge=0, le=1)
    figure_return_days: float = Field(default=3, ge=0)
    figure_return_share: float = Field(default=0.5, gt=0, le=1)
    # 丁 (c)，企劃者 2026-10-13：挑戰本人掉的三階一人一季最多幾個、寶物最多幾件（照總數算，擋豪強兩邊打與叛投；0＝不設）。兩種季都算
    figure_rare_cap: int = Field(default=6, ge=0)
    figure_treasure_cap: int = Field(default=2, ge=0)
    # 挑戰本人掉的寶物一人每週最多幾件（季曆的週；0＝不設）。只有 21 天季的設定檔打開（正式季整合 3.8：每週 1 件、一季 3 件）
    figure_treasure_weekly: int = Field(default=0, ge=0)
    # 推力規則（第一季設計第七節、計畫 T3；掛在 season_one 後面，開關關著時推大勢跟以前一樣）
    daily_push_cap: float = Field(default=10, gt=0)  # 每人每曆日、每條線推得動多少（人數緩衝之後的量）
    over_cap_contrib_ratio: float = Field(default=0.2, ge=0, le=1)  # 超過每日上限的部分，貢獻只記幾成
    contrib_per_push: int = Field(default=10, ge=0)  # 推 1 點大勢記幾點貢獻（不打人數緩衝的折）
    active_window_days: float = Field(default=1, gt=0)  # 陣營人數緩衝的「活躍」時窗：幾個曆日內推過大勢的成員才算
    # 糧草（計畫 T6；這一版沒有軍備物資，糧草＝背包裡的慢屬性素材，濃縮版內容表 4.0）：凡、靈、天一個各算幾份
    grain_values: list[int] = Field(default_factory=lambda: [1, 3, 9])
    # ── 軍令（計畫 T6、軍令文件第二節、濃縮版內容表第三節；掛在 season_one 後面）──
    # 21 天季的每天一批與推線（正式季第 5 批，見 Season21Daily）：只在蓋了 21 天季章的季讀
    season21_daily: Season21Daily = Field(default_factory=Season21Daily)
    orders_per_week: int = Field(default=3, ge=0)  # 每個陣營每週同時有幾道（豪強這一版只有打擊一種，最多一道）
    order_quota_min: int = Field(default=4, ge=1)  # 陣營總額度最少幾次（軍令文件寫 5；週末兩人時太滿，總計畫待決 3 先用 4）
    convoy_ambush_chance: float = Field(default=0.2, ge=0, le=1)  # 糧車送到終點前先撞上敵方截糧隊的機率
    convoy_grain: int = Field(default=4, ge=1)  # 接一車糧要交出幾份糧草（軍令文件 3.4：份量 ≥ 4）
    duty_stamina: int = Field(default=10, ge=0)  # 第 1 階守勢行動（巡哨、傳道、保境安民）的體力
    rank2_contrib: int = Field(default=300, ge=0)  # 升第 2 階的貢獻門檻（計畫 T5、第五節：推 30 點大勢）
    # 升第 3、4 階的貢獻門檻（正式版丙一；【預設】企劃者 2026-10-06 同意，用整季模擬調）：到了還要完成過那一階的一種機緣才發召見
    rank3_contrib: int = Field(default=900, ge=0)
    rank4_contrib: int = Field(default=1800, ge=0)
    # ── 機緣與第 2 階行動（正式版乙一；全部【預設】，企劃者 2026-10-06 同意）──
    rank2_stamina: int = Field(default=15, ge=0)  # 第 2 階行動（招降黃巾散兵、施符水收人心）的體力
    rank2_daily: int = Field(default=3, ge=0)  # 每曆日最多做幾次（不論成敗都算一次）
    rank2_push: int = Field(default=3, ge=0)  # 成功往己方推所在戰線幾點（走 Game.push_trend：緩衝、上限、貢獻）
    opp_showdown_days: float = Field(default=1.0, gt=0)  # 「戰後的地」：決戰結算之後幾個曆日內
    opp_wild_tags: list[str] = Field(default_factory=lambda: ["野外", "河畔", "山林", "渡口", "官道"])  # 「戰後的地」算野外的地點標籤
    # 機緣的時間窗口（天時地利型的夜裡、黎明、戰後的地，與乙二集體密謀的期限 plot_days）每個至少開幾個「現實」分鐘（企劃者 2026-10-06「照比例調整」）。
    # 季壓得越緊，同樣的曆時占的現實時間越短（週末設定 cal_scale 33.6：一個黎明只有 3.6 分鐘），所以窗口不夠長的才放寬，
    # 放寬後的窗口＝這個分鐘數 × cal_scale 個曆分，也就是跟壓縮成正比；本來就夠長的（整季 14 天：黎明現實 20 分鐘）一個字不動。
    # 0＝不放寬。只管機緣的窗口，calendar.is_night（伏筆、事件條件）不受影響。算法見 opportunities.windows
    opp_window_min_minutes: float = Field(default=10, ge=0)
    # ── 集體密謀（正式版乙二；【預設】，企劃者 2026-10-06 同意）──
    plot_days: float = Field(default=1.0, gt=0)  # 發起之後幾個曆日內要湊齊，過了作罷（預設 1 曆日＝24 曆時）
    plot_contrib: int = Field(default=30, ge=0)  # 密謀成了，沒有第 3 階資格（或這種機緣已經完成）的參與者記幾點貢獻
    # ── 伏筆（計畫 T7、伏筆文件 2.8）──
    # 需求量照 server_max_players 換算：人數上限「未滿」第一個數時用第二個數當係數，照順序找第一個符合的；
    # 都不符合（1000 人以上）就是 1。片段的機率反過來除以它（foreshadow.scale、foreshadow.need）
    foreshadow_tiers: list[tuple[int, float]] = Field(default_factory=lambda: [(10, 0.2), (100, 0.3), (1000, 0.6)])
    foreshadow_contrib: int = Field(default=50, ge=0)  # 最後一步答對記多少貢獻（五點推力的量；先完成、搶輸、同陣營後到都照記）
    guanyin_chance: float = Field(default=0.3, ge=0, le=1)  # 黃巾遊歷打贏官軍的隊伍時拿到一錠官銀的機率（濃縮版內容表 4.0）
    train_event_chance: float = 0.3
    qiyu_weight_multiplier: float = 1.5
    starter_skills: list[str] = Field(default_factory=list)
    start_stats: dict[str, int] = Field(
        default_factory=lambda: {
            "str": 5, "agi": 5, "con": 5, "wis": 5, "lore": 5,
            "silver": 50, "good": 0, "evil": 0, "fame": 0, "xinde": 0,
        }
    )
    # 顯示名只寫在這裡（博聞是暫名，武學與成長設計 6.3；改名只動這一處）
    stat_names: dict[str, str] = Field(
        default_factory=lambda: {
            "str": "臂力", "agi": "身法", "con": "根骨", "wis": "悟性", "lore": "博聞",
            "silver": "銀兩", "good": "善名", "evil": "惡名", "fame": "名望", "xinde": "心得",
        }
    )
    max_log: int = 200
    neili_base: float = 300
    neili_per_level: float = 20
    neili_regen_hours: float = 2  # 氣血從零回滿所需時間
    # 新手期（第一季設計第十四節；體力平衡提案第〇節，企劃者 2026-10-07）：從自己加入那一刻起的季曆天（roster.since_join），
    # 照季長自動縮放：18 季曆天＝14 天的季 3 個現實天、週末 2.5 天的季約 13 小時。beta 那一季照同一個比例從季初算（14 天的季也是 3 天）
    newbie_days: float = 18  # 這段期間氣血回復加倍
    newbie_stamina_days: float = 18  # 這段期間體力回復乘 newbie_stamina_multiplier（跟打坐的倍數疊乘）
    newbie_stamina_multiplier: float = Field(default=1, ge=1)  # 1 是不加快（Joy 2026-10-17「回體速率先調成一樣，不要分新手期」）
    # 新手期照現實時間算（Joy 2026-10-17「新手期 48 小時」）：大於 0 時 roster.newbie 與 raid_newbie 一律從自己加入這一季那一刻（joined_at）
    # 照現實的這麼多小時算，不看 newbie_days、newbie_stamina_days 的季曆天；0 是舊規則。正式值在 content/config.json（48）
    newbie_real_hours: float = Field(default=0, ge=0)
    newbie_hp_double: bool = True  # 新手期氣血回復加倍；Joy 2026-10-17「氣血不用加倍」，正式內容關掉
    # 新手期一天能服幾顆回體丹（Joy 2026-10-17「回體丹可以吃到五顆，平常兩顆」）：0 是跟 stamina_pills_per_day 一樣
    newbie_pills_per_day: int = Field(default=0, ge=0)
    # 事件失敗另扣的體力（檢定失敗、隨口應對失敗的 fail_effect.stamina）乘這個倍數、四捨五入（15 → 8、5 → 3）；
    # 選項上照乘過的數字寫「（失手多耗體力 N）」（events.choice_label）。正式值 0.5（企劃者 2026-10-07），測試內容照舊 1
    event_fail_stamina_scale: float = Field(default=1, ge=0, le=1)
    seclusion_xinde_per_hour: int = 15
    # 狀態列 💡 心得提示的下限（skillview.practice_hint）：心得至少這麼多、而且真的付得起又做得了一件事（練成下一成、或一次合成）才提示。
    # explain-2（FB-100「心得到 34 也不知道要拿去哪裡用」）從 50 改成 0：只看「付得起、做得了」——最便宜那一件做得了的事就是門檻
    xinde_hint_threshold: int = Field(default=0, ge=0)
    # ── 探索三選一（探索三選一設計）──
    # 這裡有還能遇上的奇遇（一次性或奇遇事件）時，探索先滾這個機率，中了就是奇遇、不走三選一。
    # 照整季模擬換算（設計第二節，企劃者 2026-10-03 改）：一個玩家一季在奇遇池非空的地點探索 E 次，
    # 隨機機器人 120 季（p＝0.025 時）的中位數 E＝26.5，p ≤ 1 − 0.5^(1/26.5) ≈ 0.0258，取 0.025。
    # 設好之後量到：每人每季碰到奇遇那一步 0.58 次，至少一次的約四成六。正式內容的值寫在 content/config.json。
    rare_explore_chance: float = Field(default=0.025, ge=0, le=1)
    explore_mix: list[ExploreMix] = Field(default_factory=_default_explore_mix)  # 地點類型 -> 悟意境／野怪／事件的比例
    wild_neili_loss_factor: float = Field(default=0.5, ge=0, le=1)  # 探索撞上的野怪扣氣血是遊歷的幾倍（內傷照同一個比例）
    level_exp: int = 10  # 第 n 級升 n+1 級需要 level_exp × n
    # 原本是 100，但實測一季打 19~26 場只升到第 2~3 級（升到第 10 級要 4500 經驗），
    # 而氣血設計 §1.4 的平衡量測點在第 5／10／15 級——連第 5 級都到不了。降到 10 之後
    # 一季大約升到第 10 級，等級的兩條線（氣血上限、屬性點）才有量級可談。
    max_level: int = 50
    # 滿級之後的經驗換成心得（正式季整合 3.5【暫】，第 8 批做成通用的）：本人滿 max_level 之後拿到的經驗每這麼多換 1 心得
    # （team.maxed_xinde；打仗、出陣、守與操練、決戰軍餉、頭目戰、切磋、懸賞都一樣），同伴照拿經驗
    maxed_exp_per_xinde: int = Field(default=5, ge=1)
    # 企劃者 2026-10-14「50 級加陡」：二十人試玩有人四小時練到 30 級，上限從 30 調到 50。升到第 30 級之前一個字都不變；
    # 第 late_level_from 級起每升一級要 level_exp × n ×（1＋late_exp_step ×（n − late_level_from ＋ 1））（team.level_cost），
    # 屬性點與同伴的每級成長改成每 late_stat_every 級一點（team.growth_steps：50 級一共 29＋10 點）。
    # 量法（2026-10-14）：一個只挑「穩勝」裡經驗最多的地點遊歷、體力一有就打、照真人一天服滿五顆丹的機器人，一天在線 16 小時
    # （最拚）或 6 小時（認真玩），3 個種子。不設上限時一季拿到的經驗：週末 2.5 天約 2.3～2.4 萬；14 天 9.2～10.6 萬、頭兩天約 2.2～2.4 萬
    # ——兩種季一天能拿的差不多，所以一條曲線顧不了兩種季：預設（14 天）0.5，30 → 50 要 52700；週末設定蓋成 0.12，30 → 50 要 18650。
    # 量到的：週末 16 小時 52～58 小時到 50 級、6 小時季末 40／45／46 級；14 天 16 小時第 5 天（約 122 小時）到 50、兩天時 41 級，
    # 6 小時第 10 天到 50。週末改 0.2 時 16 小時季末 46、6 小時 38／42／44。伺服器假人與整季機器人一季到不了 30 級，碰不到這一段。
    # 21 天季（content/profiles/season21.json）蓋成 0.1【預設】（正式季整合 3.3 甲，第 8 批；PM：試玩後再調）：scripts/measure_exp_pace.py
    # 的「最認真、不吃丹」（練功＋出陣，不合成不修練，威力停在 35 上下）0 是第 8.5～8.75 天滿級、0.05 第 11.2～11.8 天、0.1 第 12 天 46～47 級；
    # 會合成、威力過 90 的人練功點一點體力約換 6 經驗（量表的兩倍），照這個估 0.1 約第 7～8 天滿級，落在設計估的 0.09～0.18 裡。
    late_level_from: int = Field(default=30, ge=1)
    late_exp_step: float = Field(default=0.5, ge=0)
    late_stat_every: int = Field(default=2, ge=1)
    # ── 練功（sanguo-companions 合併重寫，見設計文件六.2）──
    practice_injury_chance: float = 0.15  # 每次練功累積受傷（內傷）的機率
    # 遭遇戰按結果扣氣血，扣掉的量是上限的幾成（氣血設計 §1.3：打完要付代價，不是免費收入）
    encounter_neili_loss: dict[str, float] = Field(
        default_factory=lambda: {"大勝": 0.05, "險勝": 0.15, "僵持": 0.20, "落敗": 0.30}
    )
    injury_share: float = 0.2  # 損失的氣血有幾成變成內傷（其餘是輕傷，自己會回）
    practice_injury_amount: float = 15.0  # 受傷時扣的氣血（累積為內傷，需療傷才能回到滿上限）
    heal_neili_per_silver: float = 2.0  # 療傷：每幾點內傷算一兩銀子（氣血設計 §二：預設每 2 點 1 兩，無條件進位）
    # 療傷只在醫館（帶「醫館」標籤的地點，tianxia/clinic.py；企劃者 2026-10-12「不能隨地療傷」）。關著時哪裡都能療傷（測試內容關著）
    heal_at_clinic: bool = True
    # 《符水與湯藥》湯藥那條路的「仲景欠你一次」（旗標 zhongjing_owes，這一季有效）：醫館療傷照這個倍數收（tianxia/clinic.py）
    zhongjing_clinic_share: float = Field(default=0.7, gt=0, le=1)
    # 鐵匠鋪、馬市、懸賞榜的獨立介面（店面獨立介面設計 6.4；第一批：鐵匠鋪）：關著時 main_view 不給 shop，網頁照現在把店裡的選項
    # 畫成一串按鈕（現在的選單本來就留著，所以不用退版）。主機在 config.json 寫 false、兩個程式重開
    shop_screens: bool = True
    # ── 武學與成長（設計第四節；全部【預設】，整季模擬校準見計畫一 Task 14）──
    practice_xinde_per_level: int = 2  # 練成：第 N 成升 N+1 成花 N × 這個數的心得（企劃者 2026-10-07 方案 A：1 → 2，練滿 45 → 90）
    fuse_xinde: int = 5  # 舊的武學＋意境合成一次（Joy 2026-10-21 起煉製只合意境，沒有地方讀了；設定還在）
    merge_xinde: int = 5  # 合併（意境＋意境）一次
    # 企劃者 2026-10-05：合併要花體力（跟修練一次一樣；那時合成不花，設計 12.1 起三種合成一樣花，見 fuse_stamina）。合併→熔掉（melt_insight_xinde）→再合併
    # 每一圈淨賺心得，決定不擋重合、也不動熔的價，而是讓每一圈都付一次體力：「意境合併要花體力，這樣的話她要拿心得就給他拿」。
    # FB-067（企劃者 2026-10-05）：從 10（跟修練一次一樣）降到 5；修練（含衝絕學）維持 10。一圈淨賺 5 心得＝每點體力 1 心得，
    # 跟「同一個地點探索又悟到同一個意境」（10 體力換 10 心得）一樣划算
    merge_stamina: int = 5
    # 武學與成長設計 12.1：三種合成同一套價錢；Joy 2026-10-21 起煉製只合意境，fuse_xinde／fuse_stamina 沒有地方讀了（設定還在）
    fuse_stamina: int = Field(default=5, ge=0)
    # 合成出新武學（武學＋意境、武學＋武學）時，每個人自己那一份的品質機率，「普通搭配」的平均（企劃者 2026-10-06：
    # 「不要直接顯示合成出來確定的品級，用機率，下品50%，中品30%，上品20%」）；權重，不必加起來是 100。
    # 序章那一爐照劇本固定下品。擲到的品質算「登記時就有」，熔的時候不給加給（library.melt_value）
    fuse_quality_odds: dict[str, float] = Field(default_factory=lambda: {"下品": 50, "中品": 30, "上品": 20})
    # 上面那組是「普通搭配」的平均；每一爐照它的組成往上或往下推（企劃者 2026-10-06，fusion.quality_odds）
    fuse_quality: FuseQuality = Field(default_factory=FuseQuality)
    cultivate_stamina: int = 10  # 修練一次的體力
    # 武學重構：衝品拿掉了，cultivate_odds／sure_by／cap／fit 跟著拿掉（舊設定檔寫了照讀不進來，所以內容檔一起刪）
    # 企劃者 2026-10-07（PR #28 方案 A）：衝哪一品之前要先練到第幾成（「火候不到，練不出那一品」）。沒寫的那一品不擋。
    # 序章安排好一定升品的那一步不看這個（劇本只練到第三成）
    cultivate_min_level: dict[str, int] = Field(default_factory=lambda: {"中品": 4, "上品": 7, "絕學": 10})
    breakthrough: Breakthrough = Field(default_factory=Breakthrough)  # 方案 C：絕學要契機
    legend_item_name: str = "破境丹"
    legend_item_note: str = "衝擊絕學時可以服下，那一次的機會多幾分。"
    legend_item_bonus: int = 15
    # 服丹衝關失敗會累積（Joy 2026-10-22「破境丹同一門武學成功率應該逐次上升」；PM 佔位）：同一門每沒衝開一次，下一次多
    # legend_fail_step 個百分點，記在那一門上（PlayerState.legend_fails）；這份可以越過 breakthrough.max_chance，最多到 legend_fail_cap。
    # 衝開或那一門熔掉就清掉；仗裡的契機（seize）不吃這份
    legend_fail_step: int = Field(default=10, ge=0)
    legend_fail_cap: int = Field(default=100, ge=1, le=100)
    # 回體丹（企劃者 2026-10-07「新增物品回體丹可以回體力100點，新手進來都送20顆，現在是內測期間，讓大家初期可以盡情遊玩體驗」）：
    # 狀態列體力條旁邊按「服丹」吃一顆，回 stamina_pill_restore 點體力，夾在體力上限（不溢出；體力是滿的不讓吃）
    stamina_pill_name: str = "回體丹"
    stamina_pill_note: str = "服下立刻回復體力。"
    stamina_pill_restore: int = Field(default=100, ge=1)
    # 內測贈送：建立新角色時送 beta_gift_stamina_pills 顆（真人、假人、整季機器人都一樣）；關掉之後新角色不再送，手上的照樣能吃。
    # 舊角色不補送，換季不再送（剩下的跟著帶到下一季）
    beta_gift: bool = True
    beta_gift_stamina_pills: int = Field(default=20, ge=0)
    # 一天最多服幾顆（企劃者 2026-10-12「體力丹一天最多吃兩顆每天00:00重新計算」，2026-10-13 改五顆）：0 是不限（測試內容）。「一天」看現實時間
    # （Game.pill_now），照 pill_day_utc_offset_hours 的時區 00:00 換日（台灣 UTC+8）；真人、假人、整季機器人一樣
    stamina_pills_per_day: int = Field(default=0, ge=0)
    pill_day_utc_offset_hours: float = Field(default=8, ge=-12, le=14)
    # 測試期間一鍵補滿體力（企劃者 2026-10-07，緊急）：「體力在這個遊戲是很重要的資源，現在的回復以及消耗完全不成正比，探索偶爾
    # 還順便扣一堆體力，新人玩家體驗不到樂趣。另外現在還在測試版，請直接讓玩家能直接補滿體力。」打開時，狀態列體力條上 joy 的
    # 「丹」鈕（同一個入口 Game.take_stamina_pill、同一條路由 pill）變成「補滿」：按一下直接補到 stamina_max，不花丹、不花銀兩、
    # 不限次數；關著時回體丹一個字不變。只在測試期間開（content/profiles/weekend.json），content/config.json 不寫；測試期過了就關掉。
    # 伺服器假人與整季機器人不吃這個，照舊吃丹（bot.take_pill 傳 pill_only=True），平衡量表不受影響
    beta_free_refill: bool = False
    # 開關打開時狀態列那顆鈕上的字（取代「丹 N」）；新寫，待 joy 潤。不能是空字串：網頁見空字串會退回畫「丹 N」，引擎卻照樣補滿
    beta_free_refill_label: str = Field(default="補滿", min_length=1)
    explore_legend_chance: float = Field(default=0.02, ge=0, le=1)  # 每按一次探索（不論走哪一支）撿到一枚的機率
    melt_refund_ratio: float = Field(default=0.8, ge=0, le=1)  # 熔一門武學退回練成花的心得的幾成
    # FB-068（企劃者 2026-10-05）：熔掉全服登記的武學（合成出來的）時，「練成花的八成」那一份至少退這麼多——合成也花了東西。
    # 不超過合成的價（fuse_xinde 5）：合成→熔掉一圈淨虧 1，不成迴圈。內容裡的武學（基礎武學有的免費教、學藝不花體力）
    # 不給基本值，否則「學、熔、再學」就是無本的心得迴圈（library.melt_value）
    melt_min_refund: int = Field(default=4, ge=0)
    # 熔煉的品質加給，只算玩家自己修練上去的那幾階（企劃者 2026-10-05）：領的是「現在的品質」減去「登記時的品質」的差
    # （library.melt_refund）。合成的武學登記在下品，修練到上品領 15；內容直接給的絕學（本命武學）登記就是絕學，沒有加給
    melt_quality_bonus: dict[str, int] = Field(
        default_factory=lambda: {"下品": 0, "中品": 5, "上品": 15, "絕學": 40}
    )
    melt_insight_xinde: int = 10  # 熔一個意境換的心得
    duplicate_insight_xinde: int = 10  # 已經會的意境又悟到一次換的心得
    # ── 悟意境（悟意境設計第零、四、五節；企劃者 2026-10-06 定）──
    sense_rate: int = 70  # 有所感選對做法之後，進入感悟狀態的成功率（%）
    sense_rate_per_wis: int = 3  # 悟性比基準 5 每多一點 +3%（少一點 −3%）
    sense_rate_range: tuple[int, int] = (40, 95)  # 夾在這之間（痕跡的加成另外加在上面，見 sense_marks_bonus）
    sense_miss_xinde: int = 3  # 選對了但沒擲中：「差一點就抓到了」給的心得
    sense_marks_bonus: int = 3  # 這一處悟成過的人每多一檔模糊人數（一兩個人、幾個人、十來個人），成功率 +3%……
    sense_marks_cap: int = 9  # ……最多 +9%
    sense_budget_seconds: float = 45.0  # 畫完之後等模型看圖取名的預算（秒，扣掉等鎖的時間；看圖熱機約 4 秒，冷啟動 19～28 秒）
    holding_cap_base: int = 50  # 武學與意境合計最多幾個
    holding_cap_levels: int = 5  # 每升幾級……
    holding_cap_step: int = 3  # ……多幾格（企劃者 2026-10-05 從 5 改成 3，另加博聞，設計 6.3）
    holding_per_lore_point: int = 2  # 博聞比基準每多一點，多幾格（設計 6.3）
    # ── 五屬性（武學與成長設計第六節；【預設】）──
    stat_points_per_level: int = 1  # 每升一級給幾點屬性，自己分配（取代每級自動 +0.3 與打贏隨機 +1）
    stat_cap: int = 15  # 臂力、身法、根骨、悟性、博聞每項最高
    stat_bonus_per_point: float = 0.03  # 比基準 5 每多一點的加成（計畫二 Task 2 起用）
    # 人物資質設計 14.4：本人的身法比 5 每多一點，落敗時閃成僵持的機會加這麼多（身法 15 是 20%）
    dodge_per_point: float = Field(default=0.02, ge=0, le=1)
    pairing_bonus: float = 0.2  # 內功與武學同屬性，整個人威力 +幾成（武學與成長設計 5.1）
    pairing_penalty: float = 0.2  # 內功與武學是相剋的一對，整個人威力 −幾成（再大也只到 encounter.BOOST_FLOOR）
    resonance_per_point: float = 0.005  # 正派武學每一點善名（邪派每一點惡名）+幾成（設計 7.4：名聲 ÷ 2 %）
    resonance_cap: float = 0.2  # 共鳴最多 +幾成
    # ── 武學的功效（武學與成長設計第十三節；【預設】，校準只改內容與這兩項）──
    trait_quality_multiplier: dict[str, float] = Field(  # 功效的強度跟著品質（13.1）
        default_factory=lambda: {"下品": 1.0, "中品": 1.5, "上品": 2.0, "絕學": 3.0}
    )
    # ── 同伴招募（sanguo-companions 合併重寫，取代舊的收徒/招賢，見設計文件四.4）──
    recruit_stamina: int = 15  # 嘗試招募一次的體力
    recruit_base_chance: float = 0.35  # 基礎成功率，情誼會再往上加（見 roster.py）
    recruit_affinity_bonus: float = 0.5  # 情誼每 100 點，成功率加多少（乘上目前好感度/100）
    # 情誼到這裡才招得了他（Joy 2026-10-21「現在怎麼很隨便的就能邀請武將加入隊伍」，決策卡選「情誼門檻」）：沒到的招募鈕不畫、
    # 「此地還有人可招」也不說；舊的 recruit_at 那一條與歷史武將同行一樣（roster.affinity_ok）。0 是舊規則
    recruit_min_affinity: int = 40
    duel_chance_on_fail: float = 0.4  # 招募失敗時，額外觸發對方要求決鬥的機率
    duel_fail_silver_loss: int = 15  # 決鬥吃虧：賠的銀兩（原本只有「你惹上了一場決鬥」的文字，沒有任何實際代價）
    recruit_consolation_xinde: int = 30  # 劇情事件想結識的人已經被別人招走時，改給的心得
    # 新立門戶福緣的兩個天數：第一季是從自己加入那一刻起算的季曆天（roster.since_join），beta 那一季是季的第幾天
    fortune_day_min: int = 2  # 新立門戶福緣：第幾天起交友必定先觸發
    fortune_day_max: int = 7  # 新立門戶福緣：第幾天結束還沒發生就直接送上門
    # ── 賽季生命週期（第一季設計第十四節）──
    admins: list[str] = Field(default_factory=list)  # 管理者的名號；暫時用名號認人，線上架構會換成帳號權限
    auto_open_first_season: bool = False  # True＝全服第一次開局就直接開季（測試內容用）；正式內容由管理者開季
    affinity_carry_ratio: float = 0.1  # 換季重來時，每位人物的好感度乘上這個數、無條件捨去後帶進下一季（第一季設計第十四節：最多從 10 起步）
    # ── 伺服器規模（伺服器假人設計第八節第 5 項；第一季設計 5.4、十二）──
    server_max_players: int = 30  # 伺服器人數上限；第四階席次、之後的軍令陣營額度照它等比例換算
    rank4_seat_ratio: float = 0.008  # 每陣營第四階席次＝上限 × 這個比例（四捨五入，最少 1 席）
    talk_stamina: int = 2  # 跟大勢人物對話，每一輪扣的體力
    talk_turns_per_day: int = 3  # 同一位大勢人物，每個遊戲日最多聊幾輪（只算玩家選的 talk:N；遊戲日跟著季長縮：rules.day_seconds）
    # 情誼到這裡，人物把本命武學傳給你（設計文件七.1，companion_agent._maybe_grant_signature_skill）。explain-1 從 companion_agent 的常數搬來：
    # 碰到才說的 h_bond 與玩法說明寫的數字讀它，不在句子裡寫死
    signature_affinity: int = Field(default=70, ge=0, le=100)
    audience_rank_discount: int = 5  # 投靠了名將的陣營，每升一階抵掉幾點求見門檻（武學與成長設計 9.1）【預設】
    # ── 玩家之間的互動（企劃者 2026-10-08）──
    # 「此地還有誰」只列這麼多現實秒數之內同步過的人：網頁開著每 10 秒同步一次，假人在線時 1～3 分鐘做一個動作，
    # 十分鐘夠把在線的都列進來；關了網頁、下了線的人十分鐘後就不在名單上（真人假人同一條規則）
    presence_seconds: float = 600
    # 專有名詞禁用名單（content/banned_names.json）擋不擋（Joy 2026-10-31：「關閉禁用名單，上面的內容可以留著，但是現階段不卡」）：
    # 關著時取名、潤色、題壁都不看這份名單（Content.banned_name_list 回空的），名單照樣載入、照樣驗；髒話字表照舊擋
    banned_names_on: bool = False
    # 答應結伴之後，帶頭的人這麼多現實秒數之內沒動身，就各走各的
    party_wait_seconds: float = 600
    # 同一對人（不分誰送誰）每個遊戲日最多贈物幾次（FB-116，PM 2026-10-14）：贈物不必對方同意，沒有上限時連送三十次 1 兩就把
    # 對方的江湖紀錄洗光（紀錄只留 30 則）。五次夠真的送東西（銀兩、丹、幾種素材各一趟）；帳照切磋記在 WorldState.gift_tally
    gift_per_pair_day: int = Field(default=5, ge=1)
    # 贈物只剩素材（Joy 2026-10-19：拿掉互贈銀兩；PM 建議拿掉贈回體丹〔小號送丹繞過一天五顆〕，Joy「照建議」）：只能送到 gift_max_tier 階，
    # 一個人一天（現實時間，同回體丹換日）總共只能送 gift_per_day 次、不分送給誰，小號搬不了三階、也搬不了大量的料
    gift_max_tier: int = Field(default=2, ge=1, le=3)
    gift_per_day: int = Field(default=5, ge=1)
    # 同一對人每個遊戲日最多論武幾回（FB-116，PM 2026-10-14；照切磋 Spar.per_pair_day 的兩場）：論武各付一半的價錢，沒有上限時
    # 兩個人可以一直合、熔掉淨賺；帳記在 WorldState.discuss_tally
    discuss_per_pair_day: int = Field(default=2, ge=1)
    # ── 伺服器假人（伺服器假人設計第四、六節）──
    bots_min_per_faction: int = 5  # 每個陣營（真人＋假人）至少幾人，不足由假人程式補
    bot_strength: float = 0.6  # 假人挑最高分選項的機率（0＝全隨機，1＝永遠挑最高分）；積極 +0.2、懶散 -0.2
    bot_tick_seconds: float = 20  # 假人程式多久巡一輪（現實秒數）
    bot_fill_seconds: float = 3600  # 同一個陣營兩次補人至少隔幾秒（現實時間），看起來像玩家陸續湧入
    bot_naming: bool = True  # 假人首創的配方與絕學定名也請模型取名（企劃者 2026-10-05、10-06）；關掉時假人不開要取名的爐、也不定名
    bot_naming_gap_seconds: float = 120  # 假人兩次請模型取名至少隔幾秒（現實時間；PM 10/5：一次一件，不搶真人的顯卡）
    # 假人一次取名最多花幾秒；取不到：首創的那一爐不開（不用字表名字搶首創），絕學定名改用字表另組。
    # 正式內容 60（2026-10-19 從 30 提高）：naming.propose 把預算切成兩趟，而省電模式下模型可能是卸掉的，
    # 冷啟動在這台實測 11.4 秒——30 秒的話一趟只有 15 秒，光載入就吃掉大半，線上實際逾時過兩次。
    bot_naming_budget_seconds: float = 30
    # ── 全服決戰的三招與推力（戰鬥系統設計 3.4；全部【預設】）──
    battle: BattleTuning = Field(default_factory=BattleTuning)

    @field_validator("explore_mix")
    @classmethod
    def _rest_comes_last(cls, mixes: list[ExploreMix]) -> list[ExploreMix]:
        """照順序比對、tags 空的是「其餘」：它必須是最後一筆，而且只能有一筆（放前面會蓋掉後面的類型）。"""
        if not mixes or mixes[-1].tags:
            raise ValueError("explore_mix 最後一筆必須是 tags 空的「其餘」")
        if any(not mix.tags for mix in mixes[:-1]):
            raise ValueError("explore_mix 裡 tags 空的「其餘」只能放最後")
        return mixes

    def explore_mix_of(self, tags: list[str]) -> ExploreMix:
        """這組地點標籤算哪一類：照 explore_mix 的順序，第一個有共同標籤的；都沒有就是最後那筆「其餘」。"""
        have = set(tags)
        for mix in self.explore_mix:
            if have & set(mix.tags):
                return mix
        return self.explore_mix[-1]


class BattleFaction(_Strict):
    id: str
    name: str


class BattleActionEffect(_Strict):
    """舊的行動分類（tag）查表的一列：決戰改版一之後固定招走三招（Config.battle），結算不再讀它；
    留著只是讓還帶 action_tags 的舊內容檔照樣讀得進來（內容裡寫 {}）。"""

    trend_delta: int = 0  # 推動戰局 trend 的量（正負方向看 BattleDef 怎麼定義雙方）
    neili_damage: float = 0  # 這個行動的基礎氣血損耗
    mitigated_by_power: bool = False  # True 時依選擇者自身武學威力算一個抵銷比例（有實力的人魯莽也扛得住一些）


class BattleOption(_Strict):
    text: str  # free_text=True 時這是提示語（顯示在輸入框旁），不是按鈕文字
    tag: str  # 這個選項在這一幕、這一邊的名字：出招、逾時代選、假人打分數都用它找選項（內容檢查要求同一邊同一幕不重複）。
    # 玩家自己打的字不會改變任何數值（不信任 LLM 自己算數字），只會被餵給 LLM 當敘事潤色的素材
    # （見 battle_instance.py::resolve_round）；放手一搏的推動與損耗走 FreeTextGamble 的公式。
    faction: str | None = None  # 限定某一方才能選；None＝雙方都能選（固定的三招一定要寫自己這一邊）
    free_text: bool = False  # True 時這個「選項」不是按鈕，是一個最多 20 字的自訂行動輸入框
    # （設計討論：「魯莽」這類選項本來就該是玩家自己想出的招，不是從固定清單挑一個）
    move: Move | None = None  # 固定招是三招的哪一招（戰鬥系統設計 3.4）；放手一搏（free_text）不填


class BattleAct(_Strict):
    """決戰的一幕。換幕照回合數走（BattleDef.rounds_per_act），不看戰局，所以幕本身沒有換幕條件
    （戰鬥系統設計 3.2；劇情線的幕 Act.advance_when 是另一回事）。"""

    id: str
    title: str
    text: str
    goal: str
    options: list[BattleOption] = Field(min_length=1)
    text_by_lead: dict[str, str] = Field(default_factory=dict)  # 陣營 id → 那一邊佔上風時的幕文字（3.2）；戰局剛好 50 或沒寫用 text


class BattleOutcome(_Strict):
    faction: str
    trend_min: int | None = None
    trend_max: int | None = None
    title: str
    text: str
    world_flags_add: list[str] = Field(default_factory=list)  # 結果套用到共用賽季的世界旗標
    trend_delta: dict[str, int] = Field(default_factory=dict)  # 結果套用到共用賽季的大勢推動（trend id -> 增減量）


class FreeTextGamble(_Strict):
    """自訂行動（放手一搏）的機制（設計討論：「我就是希望看到玩家的奇葩操作對戰局產生
    影響」）：LLM 評估這個行動聽起來有多可能成功（success_rate，0~100），系統拿這個
    機率真的擲骰——賭贏了吃大戰果，賭輸了付大代價，幅度都跟著 LLM 評出的風險程度
    （100 - success_rate）走，不是固定一個數字，所以同樣是「放手一搏」，打「直取敵將
    首級」（成功率低）贏了戰果驚人、輸了代價慘重；打相對保守的描述（成功率高）輸贏
    幅度都小很多。LLM 只負責評機率這一件事（已實測 qwen2.5:14b 對這種單純的機率評估
    排序穩定、同一行動重複問也不會亂跳），擲骰跟換算成數值完全是系統做的，不信任 LLM
    自己決定「這次到底成不成功」或「成功了該加多少」。"""

    # 試玩回饋 2026-10-08（Joy：「個別玩家如果失敗除了稍微影響大局比較嚴重的懲罰是扣自己的氣血，自己的扣到0就自己先出局」）：
    # 舊值（成功 5＋風險×0.3、失敗倒退風險×0.1）讓五個人亂寫就把全官軍推輸（50→5）。現在一個人對戰局只有小影響、
    # 一邊一回合放手一搏合起來也有上限（固定招一回合最多推 BattleTuning.push_max 10），主要的代價是自己的氣血池。
    success_trend_base: int = 2  # 成功時，戰局推動的基礎量
    success_trend_per_risk: float = 0.06  # 成功時，風險每 1 點再加多少戰局推動（成功率 0 成了是 +8，再受 side_trend_cap 夾）
    success_neili_share: float = 0.05  # 成功時扣氣血池上限的幾成（賭贏了代價不高）
    failure_trend_per_risk: float = 0.02  # 失敗時，戰局往對方倒退的量（乘上風險、四捨五入，取負）
    failure_trend_cap: int = 1  # 失敗時一個人最多讓戰局倒退多少（風險 25 以上才會倒退這 1）
    failure_neili_share_base: float = 0.1  # 失敗時扣氣血池上限的基礎比例
    failure_neili_share_per_risk: float = 0.0025  # 失敗時風險每 1 點再加多少比例（成功率 0 失手扣 35%，亂寫的人第三次失手才倒下）
    side_trend_cap: int = 5  # 同一回合同一邊失手的放手一搏合起來最多倒退多少（正式內容 content/battles.json 2026-10-10 從 5 調成 4，見 BattleTuning.push_max；
    # 擋 10/8 那種五個人亂寫就把全軍拖垮。2026-10-15 以前成了的也一起算在這個上限裡）
    success_trend_cap: int | None = None  # 同一回合同一邊成了的放手一搏合起來最多推進多少；None＝跟 side_trend_cap 一樣。
    # Joy 2026-10-15 決策卡選「成功另算」：長社火攻成了的搏一回合常常不只一個，合起來被 4 夾掉，寫得好的人推不動戰局；
    # 正式內容寫 10：一回合幾個人都成了，最多抵得過固定招 push_max 20 的一半，固定招還是大宗
    # 放手一搏不再「誰手快誰刷」（Joy 2026-10-10 決戰試玩回饋第 3 點：「跟從預設選項的玩家現在毫無存在感」）：
    # 一個人每一幕最多放手一搏 per_act 次；**0 ＝ 不限，每回合都能搏**（joy 2026-10-13「放手一搏取消冷卻」，
    # 推翻 2026-10-10 的一幕一次；留著這個欄位是為了之後想再上限制時不用改程式）
    per_act: int = Field(default=0, ge=0)


class BattleDef(_Strict):
    """全服共用的即時多人戰鬥骨架（例如「黃巾決戰」）：集結選陣營→逐幕逐回合（框架給
    選項是每邊每幕強攻／固守／奇襲三招，照 Config.battle 的算法推動戰局/扣氣血；每幕固定幾回合）→打完最後一回合、
    或戰局一面倒時，看戰局數值判定最終勝負。不是自由發展的 LLM 劇情，
    是固定骨架裡的有限變因（設計討論：「有一個基本框架，玩家可以根據自身影響一些要素，
    但是大框架還是會進行下去」）。

    factions 的第一個是戰局 trend 的正向方（trend 越高對他們越有利，越低對第二個陣營
    越有利）——三招的推力與 free_text 的賭局型行動（見 FreeTextGamble）都照這個順序決定方向。"""

    id: str
    name: str
    region: str | None = None  # 決戰所在的大區（MapRegion.id）：人要在這個大區、不在路上才能加入（地圖擴充設計第六節）；
    # None＝不限地點，只有測試用的戰鬥這樣寫——地圖有大區時內容檢查要求一定要寫
    factions: list[BattleFaction] = Field(min_length=2)
    trend_name: str = "戰局"
    trend_start: int = 50
    acts: list[BattleAct] = Field(min_length=1)
    rounds_per_act: int = Field(default=3, ge=1)  # 每幕打幾回合（戰鬥系統設計 3.2）：第 rounds_per_act 回合結算完換下一幕，
    # 整場 rounds_per_act × 幕數 回合，最後一回合結算完看戰局定結果
    decisive_margin: int = Field(default=40, ge=1)  # 戰局偏離中線 50 到這麼多（|trend − 50| ≥ 這個值，battle_instance.CENTER）
    # 就當回合收場、不再換幕（壓倒性提前收場：40 時是 90／10；看中線、不看這一場的起點，戰鬥系統 5.3）
    action_tags: dict[str, BattleActionEffect] = Field(default_factory=dict)  # 已退役的舊固定招查表（穩守／猛攻）：
    # 三招之後固定招看 BattleOption.move 與 Config.battle，結算不再讀這張表；內容寫 {}，留著只是讓舊的內容檔讀得進來
    free_text_gamble: FreeTextGamble | None = None  # 有 free_text 選項時必填
    outcomes: list[BattleOutcome] = Field(min_length=1)  # 時刻表決戰只留一筆保底：實際的結果與效果走時刻表
    muster_seconds: float = 600  # 集結期：開放選陣營的時間，逾時系統自動分配
    round_seconds: float = 120  # 每回合等待所有參戰者選擇的時間，逾時系統代選保守行動
    # ── 時刻表決戰（第一季三場大戲，計畫 T8）：時間到了照 WorldState.schedule 開集結，收場用 battle_instance.decide_result
    # 判誰贏、大勝或險勝，交給 timetable.resolve 結算；beta 那場（黃巾決戰）這四欄都是 None ──
    timetable_event: str | None = None  # 時刻表上的哪一件決戰（TimetableEvent.id）
    version: str | None = None  # 那件大事分版本時（宛城甲、乙）這一筆是哪一版；到時間照 version_from 的結果開對的那一筆
    defender: Literal["guan", "huang"] | None = None  # 守方：戰局剛好停在 50 算守方守住（戰鬥系統 4.2）
    front: str | None = None  # 起點讀哪條戰線（戰線 id）：集結開始時讀一次戰況 v，起點＝50 ＋（50 − v）÷ 2（戰鬥系統 5.3）
    # 領地爭奪第二批：攻城戰的範本（每個有區塊的大區一筆 siege_<大區>，tianxia/siege.py）：不是時刻表決戰、不從門檻開、不在「立刻開戰」的
    # 選單上；每一場打哪一塊、誰攻記在 BattleInstance.siege，名字照 siege.title。範本的幕文字待 joy 潤
    siege: bool = False
    # 沒有第三方（Joy 2026-10-13「豪強在大決戰還是要加入某一陣營，主軸還是官兵跟黃巾」）：不是交戰兩軍的人臨時投效其中一軍


FigureFate = Literal["退場", "重創", "重挫", "聲威大減", "受挫", "下獄", "到任"]  # 用詞照時刻表結算文件第一節
TimetableKind = Literal["fixed", "roll", "showdown", "finale"]  # 固定發生／照戰況擲骰／全服決戰／季末


class FigureChange(_Strict):
    """時刻表結果對一位大勢人物的效果（計畫 T2 先定義，T4 補完接手規則）。"""

    fate: FigureFate | None = None
    prestige: int = 0  # fate 之外另加減的聲威
    front: str | None = None  # 重挫轉往、到任接手的戰線（大區 id）；重挫時 None＝退出戰線
    location: str | None = None  # 轉往、到任的地點
    only_if: dict[str, str] = Field(default_factory=dict)  # 人物 id → 那位人物當下必須在的戰線；條件不合整筆略過
    note: str = ""  # 這筆真的套用時接在公告後面的一句（例：朱儁到任南陽）


class StanceAction(_Strict):
    """心意過了門檻，這位人物改做什麼（減法季整合設計 5.4、5.9；tianxia/stances.py 讀）。三樣可以一起寫。"""

    push: float = Field(default=1.0, ge=0)  # 他每天推線（figures.tick）乘幾倍：2＝加倍（速戰），0＝不推（持重、恤民）
    # 每天 00:00（world.DAY_HOOKS）把他那一條線上自家佔著的塊、每個攻方的進度各拉下幾點（持重的「守勢」；領地爭奪開著才有）
    guard: float = Field(default=0.0, ge=0)
    marks: dict[str, int] = Field(default_factory=dict)  # 「地點 id:痕跡名」→ 倍數：這幾條痕跡記一筆算幾筆（恤民的「算雙倍」）
    # 這個心意生效時開的人物事件（content/events 的事件 id；地點照那一則事件自己寫的）：只有這時候抽得到、每人每天一則
    # （stances.closed_events；速戰的「盧植急攻」、恤民的「收容流民」，PM 2026-10-26）。沒寫是 None
    event_daily: str | None = None


class StanceDef(_Strict):
    """大勢人物的一個心意（減法季整合設計 5.4、5.9；FigureDef.stances）：跟他說話時模型除了照舊回話，多歸一次「玩家在勸他哪一種」，
    一人一天一筆、全服計數（WorldState.stance_counts）；這一週到門檻的照最多的那一個改做事、發天下大事、記江湖史，每週一歸零。
    字待 joy 潤。"""

    id: str
    name: str  # 心意的名字（速戰、持重、恤民）：心意條、傳聞、紀錄那一句
    hint: str  # 給模型：玩家說什麼會歸進來
    threshold: int | None = Field(default=None, ge=1)  # 全服這一週幾筆到門檻；None 照 Config.jianfa.stance_threshold
    action: StanceAction = Field(default_factory=StanceAction)
    rumor: str  # 到門檻那一刻的天下大事（不列名字）
    chronicle: str = ""  # 江湖史那一句；空的照 rumor


class PersuadeDef(_Strict):
    """勸降那一種託付的細節（整合設計 5.5、5.9）：勸誰（只是字）、成了留的痕跡與推的線（同 Effect.marks、Effect.trend；
    trend 的 "front" 是那個地點的戰線）、敗了打的那一路。"""

    who: str  # 「黃巾的小頭目」：信、選單、勸的那一句的情境
    foe: str  # 勸不成打一場遭遇的隊伍（squads 的 id）
    marks: dict[str, int] = Field(default_factory=dict)
    trend: dict[str, int] = Field(default_factory=dict)


ErrandKind = Literal["letter", "scout", "persuade"]


class ErrandDef(_Strict):
    """一位大勢人物託你的一件事（減法季整合設計 5.5、5.9；FigureDef.errands 是他的池子，每週從裡面挑一件）：
    送信（走到 target 按「交信」）、探營（走到 target 按「探營」，一次不打仗的探查，回一張卡）、勸降（走到 target 寫一句，
    模型評成功率、引擎夾、成了立痕跡推線、敗了打一場）。task、text 的 {place} 是 target 的名字、{hero} 是對玩家的稱呼。字待 joy 潤。"""

    id: str
    kind: ErrandKind
    target: str  # 地點 id
    task: str  # 一句話：做什麼（「把一封信送到{place}，交給皇甫嵩」）；託付清單、本週卡、信的單子
    text: str  # 信的固定句（模型照他的口氣重寫，寫不出來照這一句）
    to: str = ""  # 送信：交給誰（只是字）
    deadline_days: float = Field(default=2.0, gt=0)  # 幾個遊戲日內要辦完（21 天季是現實的天）
    affinity: int = Field(default=5, ge=0, le=20)  # 辦成了他的情誼 +幾
    contribution: int = Field(default=4, ge=0, le=12)  # 辦成了記幾點陣營貢獻（跟分岔、心意同一本每日上限）
    stance: str | None = None  # 辦成了替他的這個心意記一筆（心意 +1）；沒寫不記
    persuade: PersuadeDef | None = None  # 勸降才寫


class FigureDef(_Strict):
    """一位大勢人物（content/figures.json，計畫 T4、濃縮版內容表 1.1）：開季時照這裡種進 WorldState.figures。"""

    id: str
    character: str | None = None  # 對話用的人物（characters.json）；輕量接位者（彭脫、韓忠）是 None，不開放對話
    name: str
    faction: str  # 陣營 id（Scenario.factions）
    front: str | None = None  # 開季時推哪條戰線（戰線 id）；None＝在地圖上、能見能打，只是不推（何進、趙弘、董卓）
    location: str  # 開季時在哪個地點
    destiny: bool = False  # 天命人物：聲威歸零是重創，不是退場
    start_prestige: int = Field(default=60, ge=0, le=100)
    actions_per_day: float = Field(default=1.0, ge=0)  # 每曆日推幾次（季曆）
    push: int = Field(default=1, ge=0)  # 每次推幾點
    successor: str | None = None  # 空出戰線時由誰接（人物表的 id）
    squad: str  # 挑戰本人時的對手（squads.json）；難度是聲威 100 時的值
    active_from_week: int = Field(default=1, ge=1)  # 第幾週起才推（官軍三將與孫堅是第 2 週「朝廷出兵」之後）
    # 21 天季（Config.season21，正式季整合設計 1.2 給開發 5）照天數：第 1 週週一 00:00 起幾天才推（1.5＝週二 12:00，跟朝廷出兵同時）；
    # 21 天季只看它（沒寫是 0）、不看 active_from_week。active_from_week 大於 1 的人物在 21 天季的內容裡要寫（content.validate）
    active_from_day: float | None = Field(default=None, ge=0)
    # 7 天濃縮季（Config.season_segments）照天數另寫：開季那天 00:00 起幾天才推（0.5＝第 1 天 12:00，跟朝廷出兵同時）；
    # 7 天濃縮季只看它，active_from_week 大於 1 的人物在 7 天的內容裡要寫（content.validate）
    active_from_day7: float | None = Field(default=None, ge=0)
    start_status: Literal["active", "away"] = "active"  # 輕量接位者開季時還沒出場，接手時才出現
    challenge_off_front: bool = False  # 沒有戰線也能挑戰（何進）；其他人戰線空著時不受挑戰（PM 2026-10-05 定）
    # 丙 (c)，企劃者 2026-10-13：沒有時刻表的季這位人物被打到退場時記下的世界旗標（波才寫 bocai_defeated：等於「擊敗波才」）；第一季不記
    out_flag: str | None = None
    # 減法季批 6（整合設計 5.4、5.5、5.9）：心意（最多 3 個）與託付的池子。只在 Config.jianfa 的 stances、errands 開著的季讀；
    # 空的時候不寫進序列化（內容的鍵一個都不多）
    stances: list[StanceDef] = Field(default_factory=list)
    errands: list[ErrandDef] = Field(default_factory=list)

    @model_serializer(mode="wrap")
    def _drop_new_defaults(self, handler):
        return _drop_unset(handler(self), ("stances", "errands"))


class TimetableOutcome(_Strict):
    """一件大事的一種結果：結算文件第五節一列的「公告」「江湖史」「效果」。"""

    text: str  # 沒人鎖定時的公告（接在 TimetableEvent.preface 後面）
    locked_text: dict[str, str] = Field(default_factory=dict)  # 鎖定方 → 具名公告（整句，含開頭；{name} 是鎖定者，伏筆文件）
    loser_text: dict[str, str] = Field(default_factory=dict)  # 鎖定方 → 搶輸那一方的一句（{loser} 是搶輸的人）
    note: str = ""  # 不論有沒有人鎖定都接在公告後面的一句（例：長社黃巾大勝的「波才北上」）
    chronicle: str = ""  # 江湖史一行
    trends: dict[str, int] = Field(default_factory=dict)  # 戰況移動，往黃巾為正
    figures: dict[str, FigureChange] = Field(default_factory=dict)  # 人物 id、「@commander:<戰線>:<guan|huang>」或「@人物:<人物 id>」
    chance_mods: dict[str, float] = Field(default_factory=dict)  # 之後那件大事的成功率修正（寫進 event_bonus，不佔 ±0.20 上限）
    world_flags_add: list[str] = Field(default_factory=list)
    third_party_text: str | None = None  # 這個結果專用的豪強那一句，蓋過 TimetableEvent.third_party_text（盧植下獄分兩版）
    control: dict[str, str] = Field(default_factory=dict)  # 這個結果讓哪幾處易手：地點 → 陣營（設計 4.2 第 3 點；只能是可易手或 fixed 的地點）


class RealSlot(_Strict):
    """21 天季（Config.season21）這一件大事排在哪：現實的第幾週、星期幾（0 是週一）、幾點（正式季整合設計 1.2：一般大事 12:00、
    決戰週六 20:00、天命之爭最後一個週日 20:00）。載入時（content.load_content，驗證之前）換掉 week、day、weekday、hour。"""

    week: int = Field(ge=1)
    weekday: int = Field(default=0, ge=0, le=6)
    hour: int = Field(default=0, ge=0, le=23)


class RealDay(_Strict):
    """7 天濃縮季（Config.season_segments，企劃者 2026-10-20）這一件大事排在第幾天（開季那天是第 1 天）、幾點：大決戰在第 2、4、7 天，
    鐘點沿用 21 天季那一場。載入時（content.season21_timetable）照段換成 week（第幾段）、weekday（段裡第幾天）、hour。"""

    day: int = Field(ge=1, le=7)
    hour: int = Field(default=0, ge=0, le=23)


class TimetableEvent(_Strict):
    """時刻表上的一件大事（content/timetable.json，照時刻表結算文件第五節逐件轉）。

    outcomes 的鍵：固定的是 "fixed"；擲骰的是 "成"／"不成"；決戰的是 "guan:大勝" 這類；有版本時前面加 "甲:"。"""

    id: str
    week: int = Field(ge=1)
    day: float = Field(default=0, ge=0, lt=7)  # 那一週的第幾曆日發生；0＝週一凌晨
    front: str | None = None  # 戰線（大區 id）；None＝不在戰線上（例：洛陽的盧植下獄）
    title: str
    kind: TimetableKind
    roll_side: Literal["guan", "huang"] | None = None  # 擲骰的「成」對哪一方有利；成功率就是這一方的機率
    base_chance: float | None = Field(default=None, ge=0, le=1)  # 沒有戰線時的基礎成功率
    preface: str = ""  # 沒人鎖定時公告共用的開頭（例：長社的「史書上，……」）
    version_from: str | None = None  # 看哪一件大事的結果決定版本（例：宛城看第 3 週）
    versions: dict[str, str] = Field(default_factory=dict)  # 那件的結果鍵 → 版本（例：{"成": "甲", "不成": "乙"}）
    skip_if_out: str | None = None  # 這位人物已經退場（或重創）就跳過，不公告
    outcomes: dict[str, TimetableOutcome] = Field(default_factory=dict)
    lock_result: dict[str, str] = Field(default_factory=dict)  # 鎖定方 → 結果鍵（不含版本）；決戰不寫，由 T8 給鍵
    third_party_text: str | None = None  # 豪強做完伏筆時接在公告後面的一句（{name} 是豪強那邊的人）
    third_party_trends: dict[str, int] = Field(default_factory=dict)  # 豪強每個名字各套一次的效果
    # 江湖史具名（計畫 T7、伏筆文件 2.4）：有人鎖定、結果是他那一方的具名公告時，江湖史用這一方的這一行（{name} 是鎖定者）；
    # 這一方沒寫就在原本那一行後面接「（{name}改寫）」
    locked_chronicle: dict[str, str] = Field(default_factory=dict)
    # 豪強做完伏筆時另外記的一行江湖史（例：「{name} 取得新野」；多人用「、」接），不論誰贏都記
    third_party_chronicle: str | None = None
    # ── 季末大事（kind＝finale，計畫 T9；別的種類不能寫）──
    early_preface: str = ""  # 季中就收季（決定性勝利、管理者提早收季）時取代 preface 的開頭
    out_lines: dict[str, str] = Field(default_factory=dict)  # 人物 id → 那位人物退場或重創時接在最後的一句（董卓兵敗）
    ending_chronicle: str = ""  # 江湖史那一行，{結局} 換成結局標題
    # 玉璽碎片（玉璽碎片設計 8.5）：這一件決戰開集結時擲不擲碎片。emerge＝現世那一場（也算璽動）、stir＝只璽動；
    # 不寫死黃巾之亂的 id，每個劇本自己標。只能標在 kind 是 showdown 的那幾件（載入時檢查）
    seal: Literal["emerge", "stir"] | None = None
    # ── 天命之爭（玉璽二；玉璽碎片設計 8.3、8.5）：只能標在 kind 是 showdown 的那一件、最多一件；載入時分到 Content.mandate_timetable，
    # 只有蓋了天命之季章的季看得到（timetable.events）。不寫死黃巾之亂的 id，每個劇本自己標 ──
    mandate_only: bool = False
    mandate_endings: dict[str, str] = Field(default_factory=dict)  # 得天命的那一軍 → 結局 id（劇本裡標 mandate 的第一季結局）
    weekday: int | None = Field(default=None, ge=0, le=6)  # 決戰的預設時刻：週幾（0 是週一）；None 照 timetable.SHOWDOWN_WEEKDAY
    hour: int | None = Field(default=None, ge=0, le=23)  # 同上，幾點；None 照 timetable.SHOWDOWN_HOUR
    real: RealSlot | None = None  # 21 天季的時刻（RealSlot）；21 天季的內容每一件都要寫（content.validate），其他季不看
    real7: RealDay | None = None  # 7 天濃縮季的時刻（第幾天、幾點）；7 天濃縮季的內容每一件都要寫（content.validate），其他季不看


FsKind = Literal["天時地利", "推理", "反直覺抉擇", "拼圖", "累積", "情誼", "集體密謀"]  # 第一季設計 11.3 的類型（只是標記）
FsSource = Literal["action", "event", "talk"]  # 片段從哪裡聽到：在那個大區花體力的行動／那則事件／跟那位人物對話


class FsItem(_Strict):
    """伏筆專用物品（伏筆文件第八節）：名字固定，不進煉製、不進軍備；存在 PlayerState.clue_items，換季清空。"""

    id: str
    name: str


class FsFragment(_Strict):
    """一則線索片段（伏筆文件 2.2）。只發給做得了這條鏈的陣營成員；同一個人每則只聽一次。

    text 可以寫 {風向}、{偽裝}（天機，foreshadow.tianji_answer）；versions 是有版本的大事（宛城甲、乙）的分版文字，
    鍵是版本（timetable 的 versions 的值），那件大事還沒定版本時用史書那一版（第一個）。"""

    region: str  # 大區 id（map.json 的 regions）；action 照它抽，talk 在這個大區的行動裡讓求見不到那位人物的人偷聽，event 只是標記
    source: FsSource
    text: str
    versions: dict[str, str] = Field(default_factory=dict)
    event: str | None = None  # source=event：哪一則事件（事件觸發時給，foreshadow.hear_from_event）
    character: str | None = None  # source=talk：人物 id；在不在那裡照對話（_deep_interaction_target／talk_at）
    stand_in: str | None = None  # source=talk：主角色退場、重創或下獄時改由他出面（例：盧植下獄後董卓）
    topic: str = ""  # source=talk：對話選單上的標籤（例：「問起破敵之策」）
    affinity_min: int = Field(default=0, ge=0)  # source=talk：跟出面那位人物的情誼門檻（基準量，照 foreshadow.need 換算）


class FsCheck(_Strict):
    """最後一步的屬性檢定（只看本人，伏筆是個人做的）：答完題、要交出東西之前擲。"""

    stat: Literal["str", "agi", "con", "wis", "lore"]
    dc: int


class FsRequires(_Strict):
    """最後一步的條件積木（伏筆文件 2.2：片段是知識不是門票，只檢查這些）。數字是 1000 人以上那一檔的基準量，
    檢查時照 foreshadow.need 換算（無條件進位、最少 1；寫 0 就是不要）。"""

    clue_items: dict[str, int] = Field(default_factory=dict)  # 物品 id → 數量；答對時交出（扣掉換算後的量）
    grain: int = 0  # 糧草份量（materials.grain_of）；答對時交出
    donations: dict[str, int] = Field(default_factory=dict)  # 「據點 id:糧草」→ 至少捐過多少（PlayerState.donations）；不扣
    affinity: dict[str, int] = Field(default_factory=dict)  # 人物 id → 情誼至少多少；不扣
    counters: dict[str, int] = Field(default_factory=dict)  # 隱藏計數（PlayerState.fs_counters）→ 至少多少；不扣
    check: FsCheck | None = None  # 檢定（不是門檻：照樣顯示可以做，答完題才擲；失敗照 wrong 處理）
    any_of: list[FsRequires] = Field(default_factory=list)  # 非空時至少一組成立（例：乾葦證物，或波才情誼 30）；答對時交出第一組成立的


FsRequires.model_rebuild()


class FsWrong(_Strict):
    """答錯（或檢定失敗）的懲罰；之後可以再來。全部空的就是「沒有損失」。"""

    text: str = ""
    lose_items: list[str] = Field(default_factory=list)  # 這幾樣物品全部收走
    lose_all: bool = False  # 這一步條件裡寫到的物品全部作廢（含 any_of 的每一組）
    lose_grain: bool = False  # 這一步要交的糧草沒收（份量照條件換算）
    affinity: dict[str, int] = Field(default_factory=dict)  # 人物 id → 情誼增減（例：波才 -5）
    cooldown_days: float = Field(default=0, ge=0)  # 幾個曆日之內不能再做這條鏈


class FsOption(_Strict):
    id: str  # 答案用 tianji:<key> 時要是那個天機的候選（例：東、南、西、北）
    text: str
    wrong: FsWrong | None = None  # 選了這個（而且答錯）時用它，蓋過那一步的 wrong


class FsAsk(_Strict):
    """一道題：question 是場景上的問句，options 是選單；answer 是正解的選項 id，或 tianji:<key>（天機決定，伏筆文件 2.9）。"""

    question: str
    options: list[FsOption] = Field(min_length=1)
    answer: str


class FsStep(_Strict):
    """最後一步的一趟（在一個地點做完的事）。單趟的鏈把這些欄位直接寫在 final 上；兩頭賣糧要兩趟，寫成 final.steps。

    question 沒寫：按下選單上的 label 就直接做（例：交糧、點糧）。question 寫了：先問題，答對再接 then 的追問
    （例：孫堅的第二問），全對才擲檢定、交東西、完成。"""

    location: str | None = None  # 在哪個地點做（steps 的每一趟、或單趟的 final 都要寫）
    label: str = ""  # 選單上的字（例：「束苣乘城」「交糧」）
    requires: FsRequires = Field(default_factory=FsRequires)
    unready: str = ""  # 條件不夠時選單上按不下去寫的那句（例：「官軍縮在城裡，我還怕他放火？」）；沒寫就是「東西還沒備齊」
    question: str = ""
    options: list[FsOption] = Field(default_factory=list)
    answer: str | None = None
    then: list[FsAsk] = Field(default_factory=list)
    wrong: FsWrong = Field(default_factory=FsWrong)  # 答錯（選項沒有自己的 wrong 時）與檢定失敗
    success_text: str = ""  # 多趟時：這一趟做完的那句；整條還沒完成就只有這句，最後完成的這一趟則接在 final.success_text 前面（單趟的看 final.success_text）


class FsFinal(FsStep):
    """最後一步（伏筆文件 2.3）：時間窗、夜裡、戰況，加上一趟（直接寫在這裡）或好幾趟（steps）。"""

    window_days: float = Field(default=7, gt=0)  # 時間窗：大事前幾個曆日內（timetable.when 往前算）
    window: Literal["before_event", "during_muster"] = "before_event"  # during_muster：決戰排定的時間到了、還沒收場（新野）
    night: bool = False  # 要在季曆的夜裡（子時到寅時，calendar.is_night）
    front_rule: Literal["side"] = "side"  # 戰況：官軍 ≤ 60、黃巾 ≥ 40、其他（豪強）35～65
    steps: list[FsStep] = Field(default_factory=list)  # 兩趟以上時寫這裡，final 自己的 location 留空；final.requires 每一趟都要
    success_text: str = ""  # 整條完成時看到的敘事（不論先完成還是搶輸都一樣）；可以寫 {風向}、{偽裝}、{人物}
    success_versions: dict[str, str] = Field(default_factory=dict)  # 有版本的大事：版本 → 完成的敘事
    figure: str | None = None  # {人物}：這位人物在那條戰線上（figures.on_front）時寫他的名字，否則寫 stand_in
    stand_in: str | None = None


class FsInvalidIf(_Strict):
    figure_out: str | None = None  # 這位人物退場或重創（figures.is_out）後，整條鏈失效：片段、選項都不再出現


class FsChain(_Strict):
    """一條關鍵伏筆鏈（伏筆文件第二～六節，濃縮版內容表第四節）。"""

    id: str
    event: str  # 時刻表大事 id（content/timetable.json）
    side: str  # 誰能做：劇本的陣營 id（guan、huang 會鎖定那件大事；其他陣營是第三方，寫進 third_party）
    kind: FsKind
    front: str | None = None  # 戰況看哪條線；沒寫就看那件大事的戰線（盧植下獄、張角病逝要寫 jizhou）
    fragments: list[FsFragment] = Field(default_factory=list)
    final: FsFinal
    invalid_if: FsInvalidIf = Field(default_factory=FsInvalidIf)


class FsGuanyin(_Strict):
    """官銀（濃縮版內容表 4.0）：side 的人在 regions 的大區遊歷打贏 squad_faction 的隊伍時，有 Config.guanyin_chance
    的機率 fs_counters["guanyin"] +1，寫 text 這一句。只在某條鏈的條件讀 guanyin 時才擲。"""

    side: str = "huang"
    squad_faction: str = "guan"
    regions: list[str] = Field(default_factory=list)
    text: str


class Foreshadows(_Strict):
    """content/foreshadows.json（計畫 T7）。檔案不存在或是空的就是這個空的預設值：什麼都不發生。"""

    items: list[FsItem] = Field(default_factory=list)
    chains: list[FsChain] = Field(default_factory=list)
    guanyin: FsGuanyin | None = None


OrderKind = Literal["siege", "defend", "intercept", "escort", "strike"]  # 攻城、守城、截糧、護糧、打擊大勢人物
PersonalKind = Literal["win", "duty", "convoy", "challenge"]  # 遊歷打贏、守勢行動、糧車送到、挑戰打贏


class OrderWhen(_Strict):
    """什麼時候發（濃縮版內容表 3.1）；寫了的每一項都要成立（or_enemy_siege 只放寬 losing_by；opening_fronts 在第 1 週是例外，
    見下，不看其他條件）。
    front_min／front_max：那條戰線的戰況在這個區間（含兩端）；打擊是看目標人物所在戰線。
    losing_by：戰線偏向對方超過多少（官軍：戰況 ≥ 50＋n；黃巾：≤ 50－n）。
    or_enemy_siege：或者敵方上週在這條戰線達成了攻城（守城）。
    event_within_weeks：這條戰線的下一件時刻表大事在幾週內（季曆）。
    opening_fronts：第 1 週（開局週）這幾條戰線不看局勢也發，其他條件（front_min／front_max、losing_by、event_within_weeks）
    一概略過：開局的戰況官軍都不吃緊，守城發不出來，新手第一週就沒有一道走得到的軍令（FB-054）；黃巾的守城也寫上，
    不靠 100－40 剛好踩在 60 的邊界。只在第 1 週有效，之後照舊看局勢。
    always：每週固定一道（豪強的打擊）。"""

    front_min: int | None = None
    front_max: int | None = None
    losing_by: int | None = None
    or_enemy_siege: bool = False
    event_within_weeks: float | None = None
    opening_fronts: list[str] = Field(default_factory=list)
    always: bool = False


class OrderEffect(_Strict):
    """達成時的效果（濃縮版內容表 3.1）。trend：戰況往己方偏幾點；守城的 trend 只在敵方這週還沒達成攻城時才給，
    已經達成就改成把對方攻城的效果收回一半（halve_enemy_siege）。event_mod：那條戰線下一件時刻表大事己方 +多少。
    figure_prestige：打擊的人物聲威再扣多少（負數）。"""

    trend: int = 0
    event_mod: float = 0.0
    figure_prestige: int = 0
    halve_enemy_siege: bool = False


class OrderTemplate(_Strict):
    """一種軍令對一個陣營（濃縮版內容表 3.1 的一列）。文字的插槽：{戰線}{地點}{起點}{終點}{主將}{人物}{號令}。"""

    kind: OrderKind
    side: str  # 陣營 id
    priority: int  # 數字小的先發
    when: OrderWhen = Field(default_factory=OrderWhen)
    text: str  # 發布文字
    personal: PersonalKind  # 個人部分怎樣算一次（跟 kind 是固定的對應，content.validate 檢查）
    quota_base: int = Field(ge=1)  # 陣營總額度（3000 人的量）
    effect: OrderEffect = Field(default_factory=OrderEffect)
    faction_rumor: str  # 達成時的陣營軍情（後面接「出力最多：…」）
    leak_rumor: str  # 達成時在那一帶外洩的地方傳聞（不寫名字）


class OrderSlots(_Strict):
    """一條戰線、一個陣營的地點插槽（濃縮版內容表 3.2）。"""

    intercept: str  # 截糧的 {地點}：在這裡與相鄰站遊歷可能遇上敵方糧隊
    escort: tuple[str, str]  # 護糧的 {起點}、{終點}（終點是己方據點）


class Duty(_Strict):
    """第 1 階守勢行動（濃縮版內容表 2.6）：選單上的名字與一句敘事（{地點} 換成所在地點）。"""

    name: str
    text: str


class Rank2Action(_Strict):
    """第 2 階行動（第一季設計 5.5；正式版乙一）：官軍「招降黃巾散兵」、黃巾「施符水收人心」。在有戰線的地方做，
    每曆日限次（Config.rank2_daily），過檢定才算成功；成功往己方推所在戰線 Config.rank2_push 點。
    content/orders.json 的 rank2 兩筆是新寫的初稿，待 joy 潤（JSON 沒有註解，標記記在這裡；內容改動走 joy 的 PR）。"""

    name: str
    check: Check
    ok: str  # 成功的敘事（{地點}）
    fail: str  # 失敗的敘事（{地點}）


class RankAction(_Strict):
    """第 3、4 階的行動（第一季設計 5.5；正式版戊一）。id 也是選項（act:rank:<id>）與軍令記功的 kind。
    tags：只能在帶其中一個標籤的地點做（空＝有戰線的地方都行）；chaos_only：那條戰線要在亂局。
    push：檢定過了（沒有 check 就是一定過）推幾點——官軍、黃巾推所在戰線往己方，豪強推割據。
    content/orders.json 的 rank_actions 三筆是新寫的初稿，待 joy 潤（JSON 沒有註解，標記記在這裡）。"""

    id: str
    faction: str
    rank: Literal[3, 4]
    name: str
    stamina: int = Field(ge=1)  # 每個行動都花體力（至少 1）：選項上寫「體力 N」，沒有花費的行動等於免費的推力
    weekly: int = Field(gt=0)  # 每週（季曆）最多幾次，不論成敗都算
    tags: list[str] = Field(default_factory=list)
    chaos_only: bool = False
    check: Check | None = None
    push: int = Field(gt=0)
    ok: str  # 成功的敘事（{地點}）
    fail: str = ""  # 失敗的敘事（{地點}）；有 check 就一定要寫（content.validate 擋）


class OrderCaller(_Strict):
    """黃巾發令的人（{號令}）：照順序第一個沒退場的（figure 是 None 的那一筆是最後的退路）。"""

    figure: str | None = None
    text: str


class OrdersContent(_Strict):
    """content/orders.json（計畫 T6）。不存在時是空的：沒有軍令、沒有守勢行動。"""

    templates: list[OrderTemplate] = Field(default_factory=list)
    slots: dict[str, dict[str, OrderSlots]] = Field(default_factory=dict)  # 戰線 id → 陣營 id → 插槽
    duties: dict[str, Duty] = Field(default_factory=dict)  # 陣營 id → 守勢行動
    rank2: dict[str, Rank2Action] = Field(default_factory=dict)  # 陣營 id → 第 2 階行動（正式版乙一）
    rank_actions: list[RankAction] = Field(default_factory=list)  # 第 3、4 階的行動（正式版戊一）
    commander_fallback: dict[str, str] = Field(default_factory=dict)  # 陣營 id → 沒有主將時 {主將} 寫的泛稱
    callers: list[OrderCaller] = Field(default_factory=list)  # {號令}
    convoy_squads: dict[str, str] = Field(default_factory=dict)  # 陣營 id → 自己的運糧隊（截糧打的是對方的）
    petition: dict[str, Petition] = Field(default_factory=dict)  # 陣營 id → 請命的說法（正式版乙二；計畫己再加機密軍令）


class PromotionCast(_Strict):
    """一段奇遇的一個版本（晉升奇遇文件第一節「人物不在」與「時局」）：照順序第一個成立的演。
    figure 寫了：那位人物要在場（active）；at 也寫了就要在 at，沒寫 at 就是他此刻的所在。
    before_event：那件時刻表大事還沒結算才成立（何進的索賄在盧植下獄之前、之後各一版）。
    flags_none：這些世界旗標都不在才成立。after：上一段演的是這一則才成立（董卓版的第二段接董卓版的第一段）。"""

    event: str
    figure: str | None = None
    at: str | None = None
    before_event: str | None = None
    flags_none: list[str] = Field(default_factory=list)
    after: str | None = None
    summons_text: str  # 召見的話（{據點}＝地點名）


class PromotionLeg(_Strict):
    """晉升奇遇的一段（一個地點的戲）。location 是 cast 沒寫 at、也沒有 figure 時的地點（可寫 "nearest_base"）。"""

    location: str | None = None
    casts: list[PromotionCast]


class PatronLine(_Strict):
    """豪強升第 4 階時，看靠山多一句話（晉升奇遇文件 4.3）。"""

    text: str
    affinity: dict[str, int] = Field(default_factory=dict)


class PromotionDef(_Strict):
    """一階的晉升（濃縮版內容表 2.1、2.2；計畫 T5）。figure 是出面的大勢人物（豪強的馬商不是人物，空著），不在時由
    successor 出面、演 event_handoff。location 是地點 id，或 "nearest_base"（豪強：離自己最近的投靠點）。
    召見文字放這裡（{據點} 換成地點名）；結尾那一句（closing）接在選項的反應後面。
    第 2 階照舊寫上面那幾個欄位（location、event_main、summons_text 空著會被 content.validate 擋下）；
    第 3、4 階（正式版丙一）改寫 legs：一段一個地點、每段幾個版本（PromotionCast），patron_lines 是豪強第 4 階看靠山的那一句。"""

    faction: str
    rank: int = Field(ge=2, le=4)
    figure: str | None = None
    successor: str | None = None
    location: str = ""
    event_main: str = ""
    event_handoff: str | None = None
    summons_text: str = ""
    summons_handoff: str | None = None
    closing: str
    legs: list[PromotionLeg] = Field(default_factory=list)
    patron_lines: dict[str, PatronLine] = Field(default_factory=dict)  # 靠山（yuan、cao、self）→ 那一句


class OppBond(_Strict):
    """情誼型：跟 character 的情誼到 affinity（基準量，照 foreshadow.need 換算），對話選單多一個話題 topic，問了就完成。"""

    character: str
    affinity: int = Field(ge=0)
    topic: str
    text: str  # 他說的話（含一句敘事）


class OppHost(_Strict):
    """天時地利型的主持人：figure 此刻在 at、在場（figures.present_at）才算數。"""

    figure: str
    at: str


class OppAccumulate(_Strict):
    """累積型：source 的行動成功時（流民是守勢行動之後擲 chance）記一次，湊滿 count（基準量）拿到 item，
    交到 deliver（那條戰線己方主將所在，或己方據點）就完成；完成時推 trend 點（戰線往己方，豪強推割據）。"""

    source: Literal["rank2", "duty"]
    count: int = Field(gt=0)
    chance: float = Field(default=1.0, gt=0, le=1)
    tick: str = ""  # 每記一次寫的一句（{地點}）；rank2 的成功句已經在 Rank2Action，這裡留空
    milestone: str  # 湊滿那一刻（{n}＝換算後的次數、{渠帥}＝那條戰線黃巾的主將或「黃巾渠帥」）
    item: str  # 拿到、要交的東西
    deliver: Literal["front_commander", "nearest_base"]
    label: str  # 交付選項（{主將}）
    done: str  # 交付那一刻的敘事（{主將}）
    trend: int = 1


class OppTiming(_Strict):
    """天時地利型：when 的時段、在對的地點，花 stamina、過 check。ok 之後有 item 的要再送給 deliver_front 那條戰線
    己方主將；沒有 item 的 ok 就是完成。失敗：夜裡、黎明要等下一回；決戰之後在時限內可以再試。"""

    when: Literal["night", "dawn", "after_showdown"]
    at: list[str] = Field(default_factory=list)  # night 的地點
    hosts: list[OppHost] = Field(default_factory=list)  # dawn：照順序第一位在場的主持
    clue: str
    clue_regions: list[str] = Field(default_factory=list)  # 空＝哪個大區都聽得到
    label: str  # 選項（{人物}＝主持人）
    stamina: int = Field(default=10, ge=0)
    check: Check
    ok: str  # （{人物}）
    fail: str  # （{人物}）
    item: str | None = None
    deliver_front: str | None = None
    deliver_label: str = ""  # （{主將}）
    done: str = ""  # 送到那一刻（{主將}）


class OppPiece(_Strict):
    """拼圖型的一樣東西（機緣文件 2.2 D、4.2 D）。拿法三選一：
    ask：跟 front 那條戰線己方的將領聊話題 topic（情誼到 affinity，基準量）；原本要問的是 figure，他不在那條戰線就問
         那時的主將；lines 是各人給的那一句（人物 id → 句子；"*" 是沒列到的人）。
    silver：在 at 付 silver 兩。check：在 at 花 stamina、過 check。"""

    key: str
    name: str
    how: Literal["ask", "silver", "check"]
    front: str | None = None
    figure: str | None = None
    affinity: int = Field(default=0, ge=0)
    topic: str = ""
    lines: dict[str, str] = Field(default_factory=dict)
    at: str | None = None
    silver: int = Field(default=0, ge=0)
    stamina: int = Field(default=10, ge=0)
    check: Check | None = None
    label: str = ""  # silver／check 的選項
    ok: str = ""
    fail: str = ""


class OppPatron(_Strict):
    """豪強的靠山（晉升奇遇 4.2）：誰、在哪裡收、收下時說什麼。"""

    character: str
    at: str
    done: str


class OppPresent(_Strict):
    """湊齊之後交給誰。官軍：固定地點 at，figure 在場就是他，不在寫 stand_in；豪強：patrons（靠山 → 收的人）。"""

    at: str | None = None
    figure: str | None = None
    stand_in: str = ""
    patrons: dict[str, OppPatron] = Field(default_factory=dict)
    label: str  # （{人物}）
    done: str = ""  # 官軍用（{人物}）；豪強用各靠山的 done


class OppPuzzle(_Strict):
    pieces: list[OppPiece]
    present: OppPresent


class OppSuspect(_Strict):
    id: str
    name: str
    traits: list[str]


class OppTrait(_Strict):
    key: str
    region: str
    text: str


class OppDeduce(_Strict):
    """推理型（機緣文件 3.2 D）：嫌疑人由本季天機決定（foreshadow.tianji_answer(天機, tianji)）；片段只透露那個人的特徵，
    在各自的大區、以伏筆片段的機率聽到。最後一步在 askers 第一位在場的人物那裡指認；指錯了他的情誼 wrong_affinity、
    當天不能再指。"""

    tianji: str
    suspects: list[OppSuspect]
    traits: list[OppTrait]
    askers: list[OppHost]
    label: str  # （{人物}、{嫌疑人}）
    right: str  # （{人物}）
    wrong: str  # （{人物}、{嫌疑人}）
    wrong_affinity: int = -10
    trend: dict[str, int] = Field(default_factory=dict)  # 指對了推的大勢線（戰線或割據；衍生線不行）（例：{"jizhou": 1}）


class OppPart(_Strict):
    """集體密謀的一處：front（打贏一場對敵方的遊歷）或 at（在那個地點過檢定）。name 給陣營軍情的「還缺……」用。"""

    key: str
    name: str
    front: str | None = None
    at: str | None = None


class OppPlot(_Strict):
    """集體密謀型（機緣文件 1.1）：how＝win（各處是打贏）或 check（各處是在地點過檢定）。need_parts 沒寫＝每一處都要。"""

    how: Literal["win", "check"]
    parts: list[OppPart]
    need_parts: int | None = None
    headcount: int = Field(default=3, gt=0)  # 基準量
    check: Check | None = None
    stamina: int = Field(default=10, ge=0)
    part_label: str = ""  # check 類的選項（{地點}）
    part_ok: str = ""  # （{地點}）
    part_fail: str = ""  # （{地點}）
    start_text: str  # 陣營軍情（{name}、{缺}）
    done_text: str  # 第 3 階以上的成員收到的那一句
    helper_text: str  # 其他參與者收到的那一句（接著記貢獻）
    fail_text: str  # 期限到了


class Petition(_Strict):
    """「請命」的說法（機緣文件 1.1、軍令文件 5.1）：label 是畫面上的動作名；characters 給沒有大勢人物的陣營（豪強）。"""

    label: str
    characters: list[str] = Field(default_factory=list)


class OppDef(_Strict):
    """一種機緣（機緣文件；正式版乙一有 bond、accumulate、timing 三類，乙二加 puzzle、deduce、plot 三類，都是第 4 階）。
    content/opportunities.json 裡機緣文件寫好的句子照原文，新寫的句子（乙一、乙二計畫內容表標「新寫」的）是初稿，
    待 joy 潤（JSON 沒有註解，標記記在這裡；內容改動走 joy 的 PR）。"""

    id: str
    name: str
    faction: str
    rank: Literal[3, 4]
    kind: Literal["bond", "accumulate", "timing", "puzzle", "deduce", "plot"]
    bond: OppBond | None = None
    accumulate: OppAccumulate | None = None
    timing: OppTiming | None = None
    puzzle: OppPuzzle | None = None
    deduce: OppDeduce | None = None
    plot: OppPlot | None = None


class FollowerDef(_Strict):
    """部下的模板（濃縮版內容表 2.4）：原創的無名稱呼；不能對話、不能散功，只算威力（計畫 T5）。"""

    id: str
    faction: str
    name: str
    stats: dict[str, int] = Field(default_factory=dict)
    wugong: str  # skills.json 的武學
    wugong_level: int = Field(ge=1, le=10)


class CheckVoiceBand(_Strict):
    """一檔心聲：本人的屬性（含熟練加成）減難度 ≥ min_gap 就用這一檔（由高到低找第一個符合的；差值跟擲骰同一個，
    rules.check_gap）。"""

    min_gap: float
    lines: dict[str, str]  # 屬性（str/agi/con/wis）→ 句子，{who} 換成「你」；"default" 是其他屬性的退路


class CheckVoice(_Strict):
    """有檢定的事件選項括號裡的那一句心裡話（content/check_voice.json，joy 寫的）：「去拉那張老弓（臂力 5：以你現在的
    臂力，恐怕力有未逮。）」，讓玩家選之前就知道這件事對自己難不難（企劃者 2026-10-05 定案；取代 S1 的 check_lines.json）。
    檢定是屬性每高於難度 1 點成功率 +10%（rules.check_chance），所以差 +2 約七成、0 是五成、−2 約三成。"""

    bands: list[CheckVoiceBand] = Field(default_factory=list)


class MingtieArt(_Strict):
    """名帖的一張現成的畫：一筆一筆的筆劃（mingtie.Stroke 的寫法：[墨色, 筆粗, x0, y0, x1, y1, …]，畫布 300×400）。
    真人與假人都能挑，所以「用現成的畫」看不出是假人。"""

    id: str
    name: str
    strokes: list[list[int]]


class MingtieContent(_Strict):
    arts: list[MingtieArt] = Field(default_factory=list)
    mottos: list[str] = Field(default_factory=list)  # 假人自題的那一句從這裡挑（真人自己寫）


class CreateForm(_Strict):
    """自創武學的執器那一步（content/create_forms.json 的 forms）：一種兵器或一種行功之法，偏向哪幾路屬性。"""

    kind: str  # 武學／內功
    key: str  # 武學是兵器種類（WEAPON_KINDS）；內功是行功之法的名字
    blurb: str = ""  # 鈕底下那一句
    bias: dict[str, float] = Field(default_factory=dict)  # 屬性 → 權重（主偏向 3、次 2、再次 1）


class PosePreset(_Strict):
    """擺式那一步的起點架式（點一下套上再拖）。angles 是 create.POSE_KEYS 九個角度（度）。"""

    name: str
    angles: dict[str, float]


class CreateMove(TacticDef):
    """以意成招（招式與絕學稿案第二節，Joy 2026-10-21）：自創武學的招從表裡出——主屬性（attribute）配擺式讀出的勢（timing：
    攻勢出招、守勢應招、變勢乘勢、起勢起手；內功除了起勢都是心法）。數字寫的是「透」（十成火候，約人物本命的八成）；
    火候生、熟照 Config.arts.move_fire 打折，grow 列的那幾個數（rate 是發動率、其餘是 params 的鍵）跟著打折。
    rare 的那一格是同一路同一勢的稀有路數（成形時照 Config.arts.move_rare_odds 擲到才換成它）。name 是預設的招名（立名時玩家可改）。"""

    attribute: str
    rare: bool = False
    grow: list[str] = Field(default_factory=lambda: ["rate"])


class CreateForms(_Strict):
    """自創武學的內容（content/create_forms.json；Joy 2026-10-20）：執器的兵器與行功之法、擺式的起點架式、
    模型讀不出意時的關鍵字表（屬性 → 字；正邪 → 字）、以意成招的招表（moves）。沒有這個檔：沒有偏向、沒有起點架式、讀不出就是不偏、沒有招。"""

    forms: list[CreateForm] = Field(default_factory=list)
    presets: list[PosePreset] = Field(default_factory=list)
    keywords: dict[str, list[str]] = Field(default_factory=dict)
    lean_words: dict[str, list[str]] = Field(default_factory=dict)
    moves: list[CreateMove] = Field(default_factory=list)


class ArtBook(_Strict):
    """圖的分類表（content/art.json，減法季批 8 圖像版；第一批圖提示單）：events 是事件插圖的 20 類，類型鍵 → 名字
    （圖檔 web/img/events/<鍵>.webp）。事件的 image 只能寫這裡有的鍵，分類表在內容檔、不寫死在程式。"""

    events: dict[str, str] = Field(default_factory=dict)


class Content(_Strict):
    config: Config
    scenario: Scenario
    locations: dict[str, Location]
    events: dict[str, Event]
    skills: dict[str, SkillDef]
    insights: dict[str, InsightDef] = Field(default_factory=dict)  # 意境（content/insights.json，武學與成長設計附錄 A）
    insight_scenes: dict[str, InsightScene] = Field(default_factory=dict)  # 有所感的場景（content/insight_scenes.json）；沒有這個檔就是空的，探索悟意境照舊直接悟

    traits: TraitBook = Field(default_factory=TraitBook)  # 功效（content/traits.json，13.2、13.4）；沒有這個檔就是沒有功效
    trait_lines: dict[str, list[str]] = Field(default_factory=dict)  # 功效的演出句（content/trait_lines.json，S1）：功效名 → 句子
    materials: dict[str, Material]
    craft_names: CraftNames
    combat_lines: CombatLines  # 回合演出的句型（content/combat_lines.json，武學與成長設計 8.2）
    front_lines: FrontLines  # 戰況變化的說法（content/front_lines.json，FB-064）
    banned_names: list[str]  # 合成、合併命名的禁用詞（原創原則：不用金庸等作品的專有名詞）
    sects: dict[str, Sect]
    characters: dict[str, CharacterDef]
    squads: dict[str, Squad]
    battles: dict[str, BattleDef] = Field(default_factory=dict)  # 內容尚未撰寫，先留介面（見設計討論，骨架做完再回頭寫黃巾決戰）
    road_sights: dict[str, RoadSight] = Field(default_factory=dict)  # 路上見聞（content/road_sights.json，路上設計第五節）
    timetable: list[TimetableEvent] = Field(default_factory=list)  # 第一季的時刻表（content/timetable.json，計畫 T2）
    mandate_timetable: list[TimetableEvent] = Field(default_factory=list)  # 天命之爭（timetable.json 裡標 mandate_only 的；玉璽二）：只准 timetable.events／find、seal、content 讀
    duels: dict[str, DuelBoss] = Field(default_factory=dict)  # 單人頭目戰（content/duels.json）；沒有這個檔就是空的
    gear: GearBook = Field(default_factory=GearBook)  # 寶物表、名駒、名將贈禮（content/gear.json，裝備三）；沒有這個檔就是空的
    figures: dict[str, FigureDef] = Field(default_factory=dict)  # 大勢人物（content/figures.json，計畫 T4）；沒有這個檔就是空的
    foreshadows: Foreshadows = Field(default_factory=Foreshadows)  # 關鍵伏筆（content/foreshadows.json，計畫 T7）
    orders: OrdersContent = Field(default_factory=OrdersContent)  # 陣營軍令（content/orders.json，計畫 T6）
    promotions: list[PromotionDef] = Field(default_factory=list)  # 晉升（content/promotions.json，計畫 T5）
    opportunities: list[OppDef] = Field(default_factory=list)  # 機緣（content/opportunities.json，正式版乙一）
    followers: dict[str, FollowerDef] = Field(default_factory=dict)  # 部下模板（content/followers.json，計畫 T5）
    preset_recipes: list[PresetRecipe] = Field(default_factory=list)  # 師門配方（新手引導計畫一）；沒有這個檔就是空的
    secret_recipes: list[SecretRecipe] = Field(default_factory=list)  # 秘方池（content/secret_recipes.json）；沒有這個檔就是空的
    forge_secrets: dict[str, ForgeSecret] = Field(default_factory=dict)  # 隱藏配方池（content/forge_secrets.json，照 id）；沒有這個檔就是空的
    tier4_named: dict[str, Tier4Named] = Field(default_factory=dict)  # 四階名器名字表（content/tier4_named.json，照 id）；沒有這個檔就是空的（測試內容）
    arena_crowd: dict[str, list[str]] = Field(default_factory=dict)  # 擂台的場邊事件的固定句（content/arena_crowd.json）：種類 → 句子；沒有這個檔就沒有場邊事件
    # 〈天下形勢〉的句型（content/xingshi_lines.json，領地爭奪第三批 A；tianxia/xingshi.py 讀、content.check_xingshi_lines 驗）；沒有這個檔就沒有〈天下形勢〉
    xingshi_lines: dict = Field(default_factory=dict)
    banned_words: list[str] = Field(default_factory=list)  # 玩家寫給別人看的話（挑釁那一句、名帖自題）的髒話與辱罵字表（content/banned_words.json）；沒有這個檔就是空的
    mingtie: MingtieContent = Field(default_factory=lambda: MingtieContent())  # 名帖的現成的畫與假人的自題句庫（content/mingtie.json）；沒有這個檔就是空的
    shop_lines: dict[str, dict[str, list[str]]] = Field(default_factory=dict)  # 店面上掌櫃的話（content/shop_lines.json，店面獨立介面設計 1.4）：店 → 情況 → 句子；沒有這個檔就是空的
    seal: dict[str, ShardDef] = Field(default_factory=dict)  # 玉璽碎片（content/seal.json，照 id）；沒有這個檔就是空的（碎片關著）
    mall: dict[str, MallItem] = Field(default_factory=dict)  # 商城的商品（content/mall.json，照 id、照檔案的順序）；沒有這個檔就是空的
    itineraries: list[Itinerary] = Field(default_factory=list)  # 人物的行程（content/itineraries.json，世界活起來）；沒有這個檔就是沒有
    relations: list[RelationDef] = Field(default_factory=list)  # 人物之間的關係（content/relations.json，大勢人物擴充第二批）；沒有這個檔就是沒有
    gather_branches: dict[str, GatherBranch] = Field(default_factory=dict)  # 找素材分支（content/gather_branches.json，照內容的順序）；沒有這個檔就是空的（分支關著）
    mark_rules: list[MarkRule] = Field(default_factory=list)  # 地方痕跡過門檻（content/mark_rules.json，減法季批 4）；沒有這個檔就是空的
    # 探索一顆出門一趟的段落句子（content/outing_lines.json，減法季批 2；explore_one.paragraph 讀、content.check_outing_lines 驗）：
    # 拍的類 → 結果 → 句子；沒有這個檔就是空的（照 explore_one.FALLBACK 寫）
    outing_lines: dict[str, dict[str, list[str]]] = Field(default_factory=dict)
    # 人物評曰的固定句（content/verdicts.json，減法季批 7b-2；模型叫不動時照它，待 joy 潤）：寫的理由（affinity／tier／bought）→ 句子，
    # {name} 換成名號；沒有這個檔就是空的（照 zhuan_end.DEFAULT_VERDICTS）
    verdicts: dict[str, list[str]] = Field(default_factory=dict)
    # 一條線（content/storylines.json，特殊事件設計稿；tianxia/storyline.py）：照 id、照檔案的順序；沒有這個檔就是空的
    storylines: dict[str, StoryDef] = Field(default_factory=dict)
    map: MapLayout
    tutorial: Tutorial
    art: ArtBook = Field(default_factory=ArtBook)  # 圖的分類表（content/art.json，減法季批 8）；沒有這個檔就是空的（事件不准寫 image）
    opening: Opening | None = None  # 開局第一分鐘（content/opening.json，減法季批 7）；沒有這個檔就沒有（測試內容、舊內容照走草廬）
    hints: Hints = Field(default_factory=Hints)  # 碰到才說（content/hints.json，新手引導計畫三）；沒有這個檔就是沒有提示
    check_voice: CheckVoice = Field(default_factory=CheckVoice)  # 檢定選項括號裡的那一句（content/check_voice.json，載入時必備）
    create_forms: CreateForms = Field(default_factory=CreateForms)  # 自創武學的兵器偏向、起點架式、關鍵字表（content/create_forms.json）

    def banned_name_list(self) -> list[str]:
        """取名、潤色、題壁要擋的專有名詞：開關（Config.banned_names_on）關著時是空的，名單本身照樣留在 banned_names。"""
        return self.banned_names if self.config.banned_names_on else []

    @model_serializer(mode="wrap")
    def _drop_new_defaults(self, handler):
        return _drop_unset(handler(self), ("mark_rules", "outing_lines", "verdicts", "storylines"))  # 沒有痕跡規則、段落句子、評曰固定句的內容（測試內容）序列化一個鍵都不多
