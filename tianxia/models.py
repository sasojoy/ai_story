"""內容資料模型：content/ 底下所有 JSON 設定的結構定義。"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, GetCoreSchemaHandler, field_validator, model_validator
from pydantic_core import core_schema

STATS = ("str", "agi", "con", "wis", "lore", "silver", "good", "evil", "fame", "xinde")
ActionKind = Literal["explore", "train", "socialize"]
TravelMode = Literal["walk", "hurry", "dash"]  # 步行／趕路／疾行（地圖擴充設計 3.2）
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
)
SPECIAL_HOOKS = (  # 特別功效的掛點（13.4）：一個掛點只能有一個特別功效（身上的特別功效照掛點記，validate 擋共用）。
    # 這 7 個掛點現在都被初版的 7 個特別功效佔了，所以新的特別功效要嘛換掉掛同一點的那一個、要嘛加新的掛點（要寫程式）
    "double_luck", "no_injury", "no_loss", "win_xinde", "power_from_difficulty", "heal_after", "train_stamina",
)


class _Strict(BaseModel):
    """內容檔的欄位拼錯時直接報錯，而不是被默默忽略。"""
    model_config = ConfigDict(extra="forbid")


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
    # 遊俠名號（ranger.py）：散人、第一季開著、名號到這一階才成立（投靠了陣營一律不成立）；ranger_path 是「俠」或「寇」（不寫＝不限）
    ranger_min: int | None = None
    ranger_path: Literal["俠", "寇"] | None = None
    # 季曆（calendar）的時刻：第一季開關關著（或這一季開季時沒開）時，寫了這三個的條件一律不成立——beta 季沒有季曆
    night: bool | None = None  # calendar.is_night 要等於它（True＝只在夜裡，False＝只在白天）
    week_min: int | None = None  # calendar.point(...).week 至少／至多第幾週
    week_max: int | None = None
    clue_items: dict[str, int] = Field(default_factory=dict)  # 伏筆專用物品至少幾個（原數字，不照伺服器規模換算）
    grain_min: int = Field(default=0, ge=0)  # 糧草至少幾份（基準量，照 foreshadow.need 換算；0＝不檢查；正式版丙二的帶糧選項）
    # 戰後事件用：這次行動打的那一場（戰鬥卡片 state.battle_card 指著的那筆）的結果（大勝／險勝／僵持／落敗）在清單裡才成立；
    # 這次行動沒打架（卡片已清掉）一律不成立。文字假設打贏了的戰後事件寫 ["大勝", "險勝"]。載入時只准寫在 actions 剛好是 ["train"] 的事件的條件上
    fight_tiers: list[str] = Field(default_factory=list)
    any_of: list[Condition] = Field(default_factory=list)  # 非空時，至少一個子條件成立


Condition.model_rebuild()


FRONT_KEY = "front"  # Effect.trend／Location.train_trend 的特殊鍵：效果發生地所在大區的戰線（rules.resolve_trend）


class EventMod(_Strict):
    """一般伏筆（伏筆文件 4.4）：event 那件大事 side 那一方的成功率 +amount；那件大事還沒結算才算，全服合計夾在 ±0.20
    （timetable.add_mod）。只有擲骰的大事（有 roll_side）才有意義，content.validate 擋別的。"""

    event: str
    side: Literal["guan", "huang"]
    amount: float


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


class Material(_Strict):
    """素材：一個屬性 × 一個階（見 docs/superpowers/specs/2026-10-01-無限煉製-design.md §三）。
    不再拿去煉製（Task 8），現在是糧草（慢屬性的算糧）與伏筆用的。
    """

    id: str
    name: str
    attribute: Attribute
    tier: int = Field(ge=1, le=3)  # 1 凡品、2 靈品、3 天品
    description: str = ""


class CraftNames(_Strict):
    """合成、合併時模型不可用（或產出的名字過不了過濾）的決定性組名字表，見無限煉製設計 §5.6、武學與成長設計 3.6。

    用配方鍵的雜湊挑 prefix × suffix，所以同一個配方永遠組出同一個名字——離線也能玩，
    而且 `tests/test_real_content.py` 整季模擬（LLM 被 mock）走的就是這條路。
    """

    prefixes: list[str]
    wugong: list[str]  # 武學的字尾
    neigong: list[str]  # 內功的字尾
    insight: list[str] = Field(default_factory=lambda: ["意", "勢", "韻", "境"])  # 意境的退路字尾（武學與成長設計 3.2）


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


class Check(_Strict):
    stat: str
    difficulty: int
    # 讀得進來、不再有作用（企劃者 2026-10-05「探索應該沒有本人跟夥伴之分了」）：以前 team 派隊伍中這項屬性最高的人、
    # self 只看本人；現在每一個事件檢定都看本人的屬性（rules.check_outlook）。留著這個欄位，舊內容與 joy 寫好的事件照樣載入。
    by: Literal["team", "self"] = "team"
    # 熟練（企劃者 2026-10-05「你常常做壞事，因為很熟練所以也增加成功率」）：寫了 "evil" 時，
    # 本人的檢定值再加上由惡名換算的加成（Config.practice_bonus）。
    practice: str | None = None


class PracticeBonus(_Strict):
    """熟練加成：這項名聲每 per 點，本人的檢定值 +1，最多 +cap（rules.practice_bonus）。"""

    per: int = Field(gt=0)
    cap: int = Field(ge=0)
    line: str = ""  # 吃到加成時併進選項括號裡的那一句（events.choice_label），{who} 換成「你」


class FuseQuality(_Strict):
    """合成品質的機率怎麼跟著這一爐的搭配走（企劃者 2026-10-06：「每個武學搭配不同的意境或是其他的東西都應該要有
    不同的機率吧，這是一整套系統，不要套死固數值」）。fusion.quality_odds 把這一爐的組成加成一個「造化分」，
    從 Config.fuse_quality_odds（普通搭配的平均）往上或往下推：上品每分 +up_per_point、下品每分 −low_per_point，
    中品是剩下的。上品夾在 up_range、下品夾在 low_range，所以沒有必出、也沒有必不出的組合。"""

    up_per_point: float = Field(default=0.5, ge=0)
    low_per_point: float = Field(default=1.0, ge=0)
    up_range: tuple[float, float] = (5, 45)  # 上品最少、最多幾 %
    low_range: tuple[float, float] = (15, 80)  # 下品最少、最多幾 %
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


class CultivateFit(_Strict):
    """修練的機率看這一回的搭配（企劃者 2026-10-07 選 PR #28 方案 B；原則同 FuseQuality：「不要套死固數值」）。
    cultivation.fit 把三樣乘起來：練到第幾成（×（level_base＋成×level_step））、用的是不是原本融進去的那個意境（代用
    ×substitute）、在不在對味的地方修（所在地點探索悟得到同屬性的意境 ×home_ground）。寫了必成的那一階（Config.cultivate_sure_by，
    W8 剛放寬的第一階）不看搭配。全設成 level_base 1、其他 0 或 1 就是不乘（以前的樣子）。
    lines 是修練頁與修練結果裡那一句話（含蓄，不寫倍數）：因素 → 句子，空字串就不說。"""

    level_base: float = Field(default=0.5, ge=0)
    level_step: float = Field(default=0.05, ge=0)
    substitute: float = Field(default=0.7, ge=0)
    home_ground: float = Field(default=1.5, ge=0)
    lines: dict[str, str] = Field(default_factory=lambda: {
        "home_ground": "此地的氣象跟這路功夫相投，練起來格外順手。",
        "substitute": "拿別的意境代替，總是隔了一層。",
        "raw": "招式還不夠熟，心思有一半花在招上。",
    })
    raw_below: float = Field(default=0.8, ge=0)  # 成數那一項低於這個倍數才說 raw 那一句


class Breakthrough(_Strict):
    """絕學要契機（企劃者 2026-10-07 選 PR #28 方案 C）：上品往絕學不再擲骰。在上品反覆修練只累積火候（Player.art_mastery，
    一次 +1），火候滿 heat、成數也到了，剩下那一步要等契機——拿身上這一門打贏一場不輕鬆的仗（對手難度 ÷ 我方威力 ≥ min_ratio），
    或在全服決戰裡出手滿 showdown_rounds 回合（當成難度比 showdown_ratio 的一仗）。每個契機擲一次頓悟：
    chance ×（難度比 ÷ par_ratio）× 修練的搭配（CultivateFit）× 悟性，夾在 1～max_chance。破境丹不等契機：火候滿了勾著丹修練，
    就是服丹強行衝關（legend_item_bonus × 搭配 × 悟性，cultivation.force_odds）。
    heat 是 0 就是關著：上品往絕學照以前的機率擲（Config.cultivate_odds 的「絕學」）。"""

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


class Choice(_Strict):
    text: str
    condition: Condition = Field(default_factory=Condition)
    check: Check | None = None
    combat: str | None = None  # 敵方隊伍 id：選了就自動開打
    effect: Effect = Field(default_factory=Effect)  # 檢定成功／戰鬥勝利（或無檢定時）
    fail_effect: Effect = Field(default_factory=Effect)  # 檢定失敗／戰鬥落敗


FREE_TEXT_MAX = 20  # 隨口應對最多幾個字（跟決戰的放手一搏一樣）


class FreeTextChoice(_Strict):
    """隨口應對（探索的多人與LLM玩法 §8.1）：事件多一個自己寫一句話的選項。LLM 只評估成功率，
    引擎再按 stat 修正、夾在 5%～85% 之後擲骰：成功套 effect，失敗套 fail_effect。"""

    prompt: str  # 選單上的標籤，例如「自己想辦法……」
    stat: Literal["str", "agi", "con", "wis", "lore"]
    by: Literal["team", "self"] = "team"  # 跟 Check.by 一樣：讀得進來、不再有作用，隨口應對也只看本人的屬性
    effect: Effect = Field(default_factory=Effect)
    fail_effect: Effect = Field(default_factory=Effect)


class Event(_Strict):
    id: str
    title: str
    text: str
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
    enemies: list[str] = Field(default_factory=list)
    train_trend: dict[str, int] = Field(default_factory=dict)  # 遊歷打贏／操練推大勢的量；正負是散人的方向，有陣營目標的人照自己的目標推（Game._train_push）
    materials: list[str] = Field(default_factory=list)  # 路邊採集（兩頭的地點）出什麼屬性的素材：採到的是那些屬性的一階；探索不再撿素材（探索改悟意境，見 insights）
    insights: list[str] = Field(default_factory=list)  # 探索「悟意境」那一支悟得到的意境 id（武學與成長設計附錄 C）
    unlock_flag: str | None = None  # 設定後，需該世界旗標成立才能前往
    # 序章（新手引導計畫一）的草廬：只有站在這裡的人看得到、到得了（atlas.is_unlocked）；序章走完離開後誰都回不去。
    # 一份內容最多一個，而且就是 Tutorial.location（content.validate）
    prologue_only: bool = False

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
    陣營營地只教投靠了那個陣營的人；門派只教那個門派的弟子。"""

    at: str  # 地點 id
    fame: int = 0
    silver: int = 0
    faction: str | None = None
    sect: str | None = None


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


class GeneralTrait(_Strict):
    """一般功效（content/traits.json，13.2）：一個屬性一個。每層 per_layer、疊加到 cap 為止；desc 的 {value} 換成數字。"""

    attribute: Attribute
    name: str
    hook: Literal[TRAIT_HOOKS]
    per_layer: float = Field(ge=0)
    cap: float = Field(ge=0)
    desc: str


class SpecialTrait(_Strict):
    """特別功效（13.4、13.5）：不分品質、強度固定（amount）。pool 是 false 的只屬於一門內容武學（名將本命絕學），
    合成擲不到。"""

    id: str
    name: str
    hook: Literal[SPECIAL_HOOKS]
    amount: float = Field(ge=0)
    pool: bool = True
    desc: str


class TraitBook(_Strict):
    general: list[GeneralTrait] = Field(default_factory=list)
    special: list[SpecialTrait] = Field(default_factory=list)


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
    starting_wugong: str | None = None  # 本命武學 id（指向 SkillDef，kind 必須是「武學」）
    starting_neigong: str | None = None  # 本命內功 id（指向 SkillDef，kind 必須是「內功」）
    deep_interaction: bool = False  # 是否走 companion_agent.py 的即時 LLM 對話（見設計文件四.3）
    recruit_at: str | None = None  # 可招募的同伴在哪個地點找得到他（龍頭人物不填，用 talk_at）
    talk_at: str | None = None  # kind=locked 的龍頭人物在哪個地點可以深度對話（不可招募，見上一輪「還要改進」5）
    affinity_tag_deltas: dict[str, int] | None = None  # 覆寫 companion_agent.AFFINITY_TAG_DELTAS 的個別項目；None／缺的 tag 用預設值
    audience_fame: int = 0  # 求見門檻：名望要到多少才見得到他（透過他的「結識」劇情事件認識的人不受限制）
    brush_off: list[str] = Field(default_factory=list)  # 名望不夠時打發人的話（他自己的口吻，最多三句，武學與成長設計 9.1）


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
    condition: Condition = Field(default_factory=Condition)
    # ── 第一季濃縮版（計畫 T9）：只在 rules.season_one 成立時算；beta 季只看沒標的那幾筆。同一季清單的最後一筆是保底 ──
    season_one: bool = False
    stance_min: dict[StanceSide, int] = Field(default_factory=dict)  # 態勢至少（決定性勝利：季中一到就收季）
    stance_max: dict[StanceSide, int] = Field(default_factory=dict)  # 態勢至多（同上）
    stance_top: StanceSide | None = None  # 季末比態勢：這一方最高（平手時照清單順序，排前面的先成立）


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
    ] | None = None
    locations: list[str] = Field(default_factory=list)
    condition: Condition = Field(default_factory=Condition)
    has_wugong: bool = False  # 身上要有一門武學才算（沒有武學威力是 0，出城只有挨打的份）
    # 序章：有一門合成出來的武學（fused）、它至少第幾成（fused_level）、至少什麼品質（fused_quality，看自己那一份）
    fused: bool = False
    fused_level: int = 0
    fused_quality: Quality | None = None


# 序章每一步 reveal 可以寫的畫面元件（網頁照它藏／亮，見 web/app.js 的 pro()）；content.validate 擋拼錯的
REVEAL_KEYS = frozenset({
    "all",  # 全部亮齊（出師那一步）
    "stamina", "hp", "silver", "xinde", "stats",  # 狀態列：體力、氣血、銀兩、心得、點名號展開屬性與配點
    "tab:jianghu", "tab:practice", "tab:craft", "tab:map", "tab:news",  # 底下的分頁
    "act:explore", "act:train", "act:rest", "act:social", "act:move",  # 江湖頁行動列的五格
    "board", "quest", "fronts", "orders", "minimap",  # 江湖頁的公告卡、主線與目標、戰況、軍令卡、小地圖
    "stances",  # 江湖頁最上面那一排小標裡的「態勢」（第一季才有）；跟公告卡（board）一起亮，見 Task 6 的 shown("stances")
})
# 序章每一步 glow 可以寫的鍵（網頁的 data-glow，見 web/app.js 的 applyGlow）：亮得起來的元件加上修練頁、煉製頁裡的幾顆鈕。
# 「all」是全部亮齊的意思，沒有東西可發光，不收。寫錯的鍵悄悄什麼都不亮，帶引號或括號的還會讓 applyGlow 的選擇器丟例外
# pick:art、pick:insight 是煉製頁挑選清單裡這一步要放進爐子的那門武學與意境（Game.art_rows／insight_rows 的 glow 標出來）
GLOW_KEYS = (REVEAL_KEYS - {"all"}) | frozenset({"forge", "practice", "switch", "cultivate", "melt", "allocate", "pick:art", "pick:insight"})


# 序章每一步 allow 可以寫的選單 id（TutorialStep.allow 是前綴比對，見 prologue.allowed）：照 Game._everyday_options 與它叫的
# 幾個函式真的做得出來的 id 列。固定的整串寫在 ALLOW_FIXED；帶參數的（尾巴是地點、人物、武學的 id）只列到冒號，在 ALLOW_FAMILIES，
# allow 可以寫到整個家族（"move:"）或家族加上 id（"move:town"）。兩道檢查，都不是萬全的：
#   tests/test_prologue.py::test_the_allow_lists_only_name_ids_the_code_really_makes 只查「這裡列的每一筆都真的出現在原始碼」（不憑空多寫）；
#   tests/test_real_content.py::test_every_idle_menu_id_is_one_the_prologue_allow_list_knows 整季隨機玩、對照每個閒著的選單，
#   查「引擎做得出來的有沒有漏列」，但只看得到那一季玩到的 id。引擎多了閒著選單的行動，記得手動補進這兩個。
ALLOW_FIXED = frozenset({
    "act:explore", "act:train", "act:socialize", "act:rest", "act:summons", "act:call", "act:recruit", "act:duty", "act:convoy",
    "act:rank2",  # 第 2 階守勢行動（正式版乙一）
    "act:bounties",  # 懸賞榜（第一季、城鎮類的地點）
    "act:smith",  # 鐵匠鋪（兵器設計，城鎮類的地點）
})
# opp: 是機緣的交東西與天時地利（opp:deliver:<id>、opp:try:<id>，正式版乙一）；對話選單的 talk:opp: 不是閒著的選單，不列
# act:rank: 是第 3、4 階的行動（act:rank:<行動 id>，正式版戊一）
ALLOW_FAMILIES = ("act:challenge:", "act:rank:", "call:", "move:", "learn:", "faction:", "defect:", "opp:", "fs:")


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
    allow: list[str] = Field(default_factory=list)  # 在草廬閒著時選單只留這些（前綴比對，例："act:explore"、"move:"）
    explore_event: str | None = None  # 在草廬探索時一定端出這則事件（四景四選一）
    explore_scene: str | None = None  # 在草廬探索時一定端出這段有所感（InsightScene，prologue 要是 true；跟 explore_event 二選一）
    enemies: list[str] = Field(default_factory=list)  # 這一步草廬的對手（遊歷才出現）
    force_tier: str | None = None  # 這一步的遊歷結果照寫好的（雪恥：險勝）
    sure_cultivate: bool = False  # 這一步的修練一定升品
    instant_rest: str = ""  # 非空：這一步的打坐一坐就回滿，說這一句
    fuse_base: str | None = None  # 這一步的合成只准拿這一門當底
    melt_only: str | None = None  # 這一步只准熔這一門
    give_art: GiveArt | None = None  # 完成這一步時給的武學
    # 師父的話太長、一次放不下時分頁（T7 審查 I1）：網頁照 \n\n 切成幾頁、一頁一頁按「下一段 ▸」，最後一頁是要做的事；話整段都在、不切。
    # 只有 reveal 之後這一步的行動列落到分頁列底下才用得到（量測見 Task 7 報告）；至少要有兩段
    paged: bool = False
    # 這一步的動作做成之後，結果那一句（設計 10.3 的「…之後（場景）」）：草廬裡合成、修練、熔煉成功時用它取代引擎的一般那句。
    # {意境}、{武學}、{心得} 換成這一次真的合出來的／修練的／退回的（prologue.after_line）
    after: str = ""
    # 這一步真的做完（走出草廬的出師那一步）時，把這些地點記成摸清了（PlayerState.surveyed）：師父的話講到的地方，輿圖上就有名字、點得開，
    # 不用先自己走過去。寫在內容裡、載入時檢查地點 id；略過序章的人不做這一步，什麼都沒有（guide.note_action）
    survey: list[str] = Field(default_factory=list)


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
    fuse：art＋insight；merge：left、right 兩格分左右；blend：arts 兩門不分先後。"""

    id: str
    kind: Literal["fuse", "merge", "blend"]
    art: ArtPattern | None = None
    insight: InsightPattern | None = None
    left: InsightPattern | None = None
    right: InsightPattern | None = None
    arts: list[ArtPattern] = Field(default_factory=list)
    name: str
    note: str = ""
    special: str | None = None  # 特別功效 id（traits.json 的 special）；沒寫照天機挑一條。合出意境的秘方不用
    clues: list[str] = Field(min_length=3, max_length=3)


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


class Recruiter(_Strict):
    """入伍段（新手引導計畫二，設計第四節）一個陣營的引薦人：框上的名字與他說的話。"""

    name: str  # 老石、青禾、季伯平
    intro: str  # 入營（r1）：投靠的當下，排在第一步的話前面
    briefing: str  # 看戰局（r2）
    order_hint: str  # 第一道軍令（r3）還沒做時，框裡那一句
    done: str  # 第一道軍令做完，引薦人的結尾（按「知道了」收起）
    lines: list[str] = Field(default_factory=list)  # 每一步收起後那一行，照 Enlist.steps 的順序；不帶名字（框上的名字另外寫）
    rejoin: str = ""  # 第二季起再投靠時打的招呼（新手引導計畫三用）


class EnlistStep(_Strict):
    id: str
    done_when: TutorialGoal


class Enlist(_Strict):
    steps: list[EnlistStep] = Field(default_factory=list)
    recruiters: dict[str, Recruiter] = Field(default_factory=dict)  # 陣營 id → 引薦人
    drifter_line: str = ""  # 「主線與目標」裡散人那一行：三邊各在哪裡收人（設計 6.3）


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


class Hints(_Strict):
    """碰到才說（content/hints.json，新手引導計畫三）：沒有這個檔就是沒有提示。"""

    head: str = "想起師父說過"  # 師父那幾條框上寫的字
    hints: list[HintDef] = Field(default_factory=list)
    season_return: str = ""  # 第二季起開季時師父的一句（設計 7.1）；空的就沒有


class FactionDef(_Strict):
    """一季的玩家陣營（第一季設計第五節）：在 join_at 的地點可以投靠；拜入 sects 裡的門派也算投靠這個陣營。
    goals 是這個陣營想把各條大勢線往哪推（伺服器假人照它打分數）。"""

    id: str
    name: str
    join_at: list[str] = Field(default_factory=list)
    sects: list[str] = Field(default_factory=list)
    goals: dict[str, int] = Field(default_factory=dict)  # 大勢線 id → 1 推高／-1 壓低；伺服器假人照這個行動
    defect_text: str = ""  # 叛投到這個陣營那一刻的一句敘事（計畫甲；content/scenario.json 的三句是初稿，待 joy 潤，joy 會走自己的 PR）


class SeasonOneOff(_Strict):
    """第一季不觸發的 beta 內容（控制者與地圖擴充 T4 說好的格式，2026-10-04）：只在 rules.season_one 成立時生效
    （開關開著、這一季開季時也蓋了「開」的章）；開關關著時 beta 那一季照舊。四種各自是那一種內容的 id。
    - thresholds：大勢門檻不觸發（管理者也觸發不了）；
    - storylines：主線不推進，「主線與目標」不顯示那條主線；
    - battles：大勢門檻的 starts_battle 不開，管理者「立刻開戰」的選單不列；
    - events：探索的事件抽選跳過（T4 做；這裡只定欄位，id 一樣在載入時檢查）；
    - milestones：「主線與目標」的個人目標不列（做不到的 beta 目標，例如擊敗波才、平定黃巾）。"""

    thresholds: list[str] = Field(default_factory=list)
    storylines: list[str] = Field(default_factory=list)
    battles: list[str] = Field(default_factory=list)
    events: list[str] = Field(default_factory=list)
    milestones: list[str] = Field(default_factory=list)


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
    merit_points: dict[str, int] = Field(default_factory=lambda: {"acted": 2, "held": 2, "led": 3, "gamble": 4, "hit": 3, "stood": 2})
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
    third_grab_damage: float = 35.0  # 第三方「趁亂搶地盤」扣的氣血（同奇襲的損耗，戰鬥系統第六節；獨立的欄位：調奇襲不連動）
    third_keep_damage: float = 10.0  # 第三方「保存實力」扣的氣血
    third_keep_share: float = 0.5  # 「保存實力」的份量與收穫算幾成（固守的份量乘它）
    third_cap: int = 10  # 一場最多推第三方的大勢線幾點
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
        適性的加減、剋制係數、強攻的抵銷可以是 0（＝不起作用），剋制係數與抵銷不超過 1。
        第三方（決戰改版 5）：兩種扣血大於 0，保存實力的折數在 0～1，一場的上限不能是負的（0 是豪強不推）。"""
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
        for name in ("counter", "strong_mitigation_cap", "third_keep_share"):
            if not 0 <= getattr(self, name) <= 1:
                raise ValueError(f"{name} 要在 0～1 之間（現在是 {getattr(self, name)}）")
        for name in ("third_grab_damage", "third_keep_damage"):  # 第三方的扣血：寫成 0 或負的，豪強就扣不了血、永遠倒不下
            if getattr(self, name) <= 0:
                raise ValueError(f"{name} 要大於 0（現在是 {getattr(self, name)}）")
        if self.third_cap < 0:  # 負的上限會把割據往下推；0 是合法的（豪強不推）
            raise ValueError(f"third_cap 不能是負的（現在是 {self.third_cap}）")
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


class Ranger(_Strict):
    """遊俠名號（散人的成長階梯，PM 2026-10-08 派工「散人玩法對比加入陣營好像薄弱很多」）：只有第一季開著時有。
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


class Bounties(_Strict):
    """懸賞榜（PM 2026-10-08 派工「加強散人玩法」；bounties.py）：只有第一季開著時有，在城鎮類的地點查看（「懸賞榜」不花體力）。
    官軍、黃巾每週一各自動掛 kinds 裡的每一張（討伐兩張、打探、護送各一張）；玩家（投靠了陣營的人）可以花銀兩通緝一個敵對陣營的人。
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
    - post_min／post_max：通緝的賞金（押金）範圍；沒人完成就在 post_weeks 週後下榜、押金退回。wanted_deeds 是散人接通緝打贏記的俠名。"""

    kinds: list[str] = Field(default_factory=lambda: ["strike", "strike", "scout", "escort"])
    silver: dict[str, int] = Field(default_factory=lambda: {"strike": 20, "scout": 10, "escort": 15})
    deeds: dict[str, int] = Field(default_factory=lambda: {"strike": 3, "scout": 2, "escort": 2, "wanted": 4})
    exp: dict[str, int] = Field(default_factory=lambda: {"strike": 15, "scout": 10, "escort": 12, "wanted": 15})
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
    - 贏的一方記一點本季貢獻（contrib_per_push × win_contrib_push）：截殺是替陣營做事，但比推大勢一點還少，不會變成升階的捷徑。
    時間都是世界秒（跟邀請的逾時同一套）。"""

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


class WeaponRules(_Strict):
    """兵器（docs/superpowers/specs/2026-10-09-兵器-design.md）。數字都是【預設】，量表（scripts/measure_weapons.py）校準後可以改。
    加成＝（階＋品質＋淬煉＋屬性搭配）×（edge_floor＋（1－edge_floor）×鋒利度／100），乘在本人的 Boost.factor；
    參考內外同屬性 +20%、正邪共鳴最多 +20%，最好的兵器約抵其中一項。"""

    enabled: bool = True
    tier_bonus: dict[str, float] = Field(default_factory=lambda: {"1": 0.05, "2": 0.10, "3": 0.15})
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


class Secrets(_Strict):
    """口訣與秘方（tianxia/secrets.py；PM 2026-10-10 派工，企劃者選「甲乙都做」的甲）。預設全關（測試內容沒有秘方池），
    正式值在 config.json。"""

    # 每季照天機挑幾條：種類 → 條數（池子不夠就全上）
    per_season: dict[str, int] = Field(default_factory=lambda: {"fuse": 2, "merge": 2, "blend": 2})
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
    rumor: str = "江湖上傳開了：{who}參透了一句口訣，合出了{thing}。"
    chronicle: str = "{who}參透口訣，首創{thing}。"


class FirstEcho(_Strict):
    """首創名望回饋（企劃者 2026-10-07 選甲時一起要的「乙的首創回饋」）：別人照著你首創的配方合出同一門（武學或意境），
    每多一個不同的人，你下一次上線時名望 +fame_per；一門最多算 cap 個人（擋灌名望）。湊滿 cap 那一下江湖上傳一句。
    只在第一季開著時有。"""

    fame_per: int = Field(default=1, ge=0)
    cap: int = Field(default=5, ge=1)


class Config(_Strict):
    stamina_max: int = 150
    stamina_regen_seconds: float = 180  # 自然回復：每幾秒（遊戲時間）回 1 點體力（地圖擴充設計第二節：每 3 分鐘 1 點）
    rest_regen_multiplier: float = Field(default=2, ge=1)  # 打坐中體力回復是平常的幾倍
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
    # 行動鎖內的模型呼叫（大事與決戰回合的潤色、重複事件與重遊的點綴句、決戰自訂行動的評分、鎖內才備料的對話與記憶整理、
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
    showdown_pay: ShowdownPay = Field(default_factory=ShowdownPay)  # 全服決戰的軍餉與獲勝加給（見 ShowdownPay）
    duel: DuelTuning = Field(default_factory=DuelTuning)  # 單人頭目戰（見 DuelTuning；內容在 content/duels.json）
    raid: Raid = Field(default_factory=Raid)  # 截殺敵對陣營的人（見 Raid）
    bounties: Bounties = Field(default_factory=Bounties)  # 懸賞榜（見 Bounties）
    weapons: WeaponRules = Field(default_factory=WeaponRules)  # 兵器（見 WeaponRules）
    ranger: Ranger = Field(default_factory=Ranger)  # 遊俠名號（散人的成長階梯，見 Ranger）
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
    season_weeks: int = Field(default=12, ge=1)  # 季曆：一季壓成幾週（計畫第六節：季曆秒＝世界秒 × 週數 × 7 ÷ season_days）
    # 決定性勝利（黃巾聲勢 ≥85、≤15，割據 ≥85）季曆第幾週起才提前收季；之前到了門檻也不收，季末照常比（企劃者 2026-10-05，計畫 T9）
    decisive_from_week: int = Field(default=10, ge=1)
    # 時刻表的人物結局扣多少聲威（時刻表結算文件第一節）：只有這三種用詞會扣；退場、重創是聲威歸零，下獄、到任不動聲威
    fate_prestige: dict[Literal["重挫", "聲威大減", "受挫"], int] = Field(
        default_factory=lambda: {"重挫": -30, "聲威大減": -30, "受挫": -15}
    )
    # 大勢人物（計畫 T4、總計畫第五節；掛在 season_one 後面，開關關著時沒人讀）
    figure_reaction_lean: int = Field(default=15, ge=0)  # 戰線偏向對方這麼多時，人物推得更勤（反應規則，第一季設計 8.2）
    figure_reaction_mult: float = Field(default=2.0, ge=1)  # 推得更勤的倍數
    figure_defeat_prestige: int = Field(default=5, ge=0)  # 挑戰本人打贏一次扣幾點聲威（照陣營人數緩衝）
    figure_defeat_affinity: int = Field(default=5, ge=0)  # 打贏的人跟他的情誼扣多少（軍令文件 4.5）
    snub_hours: float = Field(default=2, ge=0)  # 打贏之後幾個「現實」小時內他不見你、也不跟你交手（軍令文件 4.5）
    figure_difficulty_floor: float = Field(default=0.5, ge=0, le=1)  # 挑戰本人的難度：聲威 0 時是隊伍難度的幾成（100 時原值，中間線性）
    # 推力規則（第一季設計第七節、計畫 T3；掛在 season_one 後面，開關關著時推大勢跟以前一樣）
    daily_push_cap: float = Field(default=10, gt=0)  # 每人每曆日、每條線推得動多少（人數緩衝之後的量）
    over_cap_contrib_ratio: float = Field(default=0.2, ge=0, le=1)  # 超過每日上限的部分，貢獻只記幾成
    contrib_per_push: int = Field(default=10, ge=0)  # 推 1 點大勢記幾點貢獻（不打人數緩衝的折）
    active_window_days: float = Field(default=1, gt=0)  # 陣營人數緩衝的「活躍」時窗：幾個曆日內推過大勢的成員才算
    # 糧草（計畫 T6；這一版沒有軍備物資，糧草＝背包裡的慢屬性素材，濃縮版內容表 4.0）：凡、靈、天一個各算幾份
    grain_values: list[int] = Field(default_factory=lambda: [1, 3, 9])
    # ── 軍令（計畫 T6、軍令文件第二節、濃縮版內容表第三節；掛在 season_one 後面）──
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
    vision_base: int = 2  # 從所在地沿道路看得見幾步
    vision_fame: int = 10  # 名望達到這個值，視野 +1
    max_log: int = 200
    neili_base: float = 300
    neili_per_level: float = 20
    neili_regen_hours: float = 2  # 氣血從零回滿所需時間
    # 新手期（第一季設計第十四節；體力平衡提案第〇節，企劃者 2026-10-07）：從自己加入那一刻起的季曆天（roster.since_join），
    # 照季長自動縮放：18 季曆天＝14 天的季 3 個現實天、週末 2.5 天的季約 13 小時。beta 那一季照同一個比例從季初算（14 天的季也是 3 天）
    newbie_days: float = 18  # 這段期間氣血回復加倍
    newbie_stamina_days: float = 18  # 這段期間體力回復乘 newbie_stamina_multiplier（跟打坐的倍數疊乘）
    newbie_stamina_multiplier: float = Field(default=1, ge=1)  # 正式值在 content/config.json（3）；測試內容照舊 1
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
    max_level: int = 30
    # ── 練功（sanguo-companions 合併重寫，見設計文件六.2）──
    practice_injury_chance: float = 0.15  # 每次練功累積受傷（內傷）的機率
    # 遭遇戰按結果扣氣血，扣掉的量是上限的幾成（氣血設計 §1.3：打完要付代價，不是免費收入）
    encounter_neili_loss: dict[str, float] = Field(
        default_factory=lambda: {"大勝": 0.05, "險勝": 0.15, "僵持": 0.20, "落敗": 0.30}
    )
    injury_share: float = 0.2  # 損失的氣血有幾成變成內傷（其餘是輕傷，自己會回）
    practice_injury_amount: float = 15.0  # 受傷時扣的氣血（累積為內傷，需療傷才能回到滿上限）
    heal_neili_per_silver: float = 2.0  # 療傷：每幾點內傷算一兩銀子（氣血設計 §二：預設每 2 點 1 兩，無條件進位）
    # ── 武學與成長（設計第四節；全部【預設】，整季模擬校準見計畫一 Task 14）──
    practice_xinde_per_level: int = 2  # 練成：第 N 成升 N+1 成花 N × 這個數的心得（企劃者 2026-10-07 方案 A：1 → 2，練滿 45 → 90）
    fuse_xinde: int = 5  # 合成（武學＋意境）一次
    merge_xinde: int = 5  # 合併（意境＋意境）一次
    # 企劃者 2026-10-05：合併要花體力（跟修練一次一樣；那時合成不花，設計 12.1 起三種合成一樣花，見 fuse_stamina）。合併→熔掉（melt_insight_xinde）→再合併
    # 每一圈淨賺心得，決定不擋重合、也不動熔的價，而是讓每一圈都付一次體力：「意境合併要花體力，這樣的話她要拿心得就給他拿」。
    # FB-067（企劃者 2026-10-05）：從 10（跟修練一次一樣）降到 5；修練（含衝絕學）維持 10。一圈淨賺 5 心得＝每點體力 1 心得，
    # 跟「同一個地點探索又悟到同一個意境」（10 體力換 10 心得）一樣划算
    merge_stamina: int = 5
    # 武學與成長設計 12.1：三種合成同一套價錢——武學＋意境、武學＋武學也收體力
    fuse_stamina: int = Field(default=5, ge=0)
    # 合成出新武學（武學＋意境、武學＋武學）時，每個人自己那一份的品質機率，「普通搭配」的平均（企劃者 2026-10-06：
    # 「不要直接顯示合成出來確定的品級，用機率，下品50%，中品30%，上品20%」）；權重，不必加起來是 100。
    # 序章那一爐照劇本固定下品。擲到的品質算「登記時就有」，熔的時候不給加給（library.melt_value）
    fuse_quality_odds: dict[str, float] = Field(default_factory=lambda: {"下品": 50, "中品": 30, "上品": 20})
    # 上面那組是「普通搭配」的平均；每一爐照它的組成往上或往下推（企劃者 2026-10-06，fusion.quality_odds）
    fuse_quality: FuseQuality = Field(default_factory=FuseQuality)
    # 12.2 合到舊的：一個組合第一次被合時，候選每有一個，機會加這麼多，最多到 land_chance_cap（企劃者定九成）；0 就永遠長新的
    land_chance_per_candidate: float = Field(default=0.05, ge=0, le=1)
    land_chance_cap: float = Field(default=0.9, ge=0, le=1)
    cultivate_stamina: int = 10  # 修練一次的體力
    # 修練升到這一品：第一次的機率、每失敗一次加多少（%）（設計 3.5）。中品、上品加到 100 就必成；
    # 絕學沒有保底：累積的機率最多到 cultivate_cap（企劃者 2026-10-05），剩下靠破境丹
    # 企劃者 2026-10-06（W8）：第一階（下品→中品）放寬成 40% 起、每失敗一次 +20%、第三次必成（見 cultivate_sure_by）。理由：試玩
    # 走一遍，連續四次（40 體力）還是下品，第一次玩一個 session 可能什麼都沒得到；第一階是新手第一次感覺到「修練有用」的地方，
    # 要夠快。中品→上品（10%、+6）、上品→絕學（4%、+3）一個數字都沒動
    # 企劃者 2026-10-07（PR #28 方案 B）：中品→上品改成 6%、+3，再乘這一回的搭配（cultivate_fit）。上品→絕學在方案 C（breakthrough）
    # 開著時不擲骰（火候＋契機），「絕學」那一組只在 breakthrough.heat 是 0 時用得到
    cultivate_odds: dict[str, tuple[int, int]] = Field(
        default_factory=lambda: {"中品": (40, 20), "上品": (6, 3), "絕學": (4, 3)}
    )
    # 第幾次修練必成（W8）：寫了的那一階，第 N 次（失敗 N−1 次之後）機會直接是 100%——蓋過悟性的乘數與 cultivate_cap。
    # 沒寫的那一階照舊：機會加到 100% 才必成（上品第 16 次），絕學沒有保底。預設只有第一階寫了，第三次必成
    cultivate_sure_by: dict[str, int] = Field(default_factory=lambda: {"中品": 3})
    # 企劃者 2026-10-05：絕學沒有保底，靠破境丹提升。累積機率的上限（%）：沒寫的那一階上限是 100（照舊必成）；
    # 破境丹是探索偶爾撿到的傳奇道具，玩家在修練頁勾了、而且這一次衝的是絕學，才服下一枚：那一次多 legend_item_bonus%，
    # 成不成都用掉（不勾就不服；被拒絕的修練不擲骰、丹也不動）
    cultivate_cap: dict[str, int] = Field(default_factory=lambda: {"絕學": 50})
    # 企劃者 2026-10-07（PR #28 方案 A）：衝哪一品之前要先練到第幾成（「火候不到，練不出那一品」）。沒寫的那一品不擋。
    # 序章安排好一定升品的那一步不看這個（劇本只練到第三成）
    cultivate_min_level: dict[str, int] = Field(default_factory=lambda: {"中品": 4, "上品": 7, "絕學": 10})
    cultivate_fit: CultivateFit = Field(default_factory=CultivateFit)  # 方案 B：修練的機率看搭配
    breakthrough: Breakthrough = Field(default_factory=Breakthrough)  # 方案 C：絕學要契機
    legend_item_name: str = "破境丹"
    legend_item_note: str = "衝擊絕學時可以服下，那一次的機會多幾分。"
    legend_item_bonus: int = 15
    # 回體丹（企劃者 2026-10-07「新增物品回體丹可以回體力100點，新手進來都送20顆，現在是內測期間，讓大家初期可以盡情遊玩體驗」）：
    # 狀態列體力條旁邊按「服丹」吃一顆，回 stamina_pill_restore 點體力，夾在體力上限（不溢出；體力是滿的不讓吃）
    stamina_pill_name: str = "回體丹"
    stamina_pill_note: str = "服下立刻回復體力。"
    stamina_pill_restore: int = Field(default=100, ge=1)
    # 內測贈送：建立新角色時送 beta_gift_stamina_pills 顆（真人、假人、整季機器人都一樣）；關掉之後新角色不再送，手上的照樣能吃。
    # 舊角色不補送，換季不再送（剩下的跟著帶到下一季）
    beta_gift: bool = True
    beta_gift_stamina_pills: int = Field(default=20, ge=0)
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
    special_trait_chance: float = Field(default=0.05, ge=0, le=1)  # 新武學帶特別功效的機會（13.4）
    # ── 同伴招募（sanguo-companions 合併重寫，取代舊的收徒/招賢，見設計文件四.4）──
    recruit_stamina: int = 15  # 嘗試招募一次的體力
    recruit_base_chance: float = 0.35  # 基礎成功率，情誼會再往上加（見 roster.py）
    recruit_affinity_bonus: float = 0.5  # 情誼每 100 點，成功率加多少（乘上目前好感度/100）
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
    # 答應結伴之後，帶頭的人這麼多現實秒數之內沒動身，就各走各的
    party_wait_seconds: float = 600
    # ── 伺服器假人（伺服器假人設計第四、六節）──
    bots_min_per_faction: int = 5  # 每個陣營（真人＋假人）至少幾人，不足由假人程式補
    bot_strength: float = 0.6  # 假人挑最高分選項的機率（0＝全隨機，1＝永遠挑最高分）；積極 +0.2、懶散 -0.2
    bot_tick_seconds: float = 20  # 假人程式多久巡一輪（現實秒數）
    bot_fill_seconds: float = 3600  # 同一個陣營兩次補人至少隔幾秒（現實時間），看起來像玩家陸續湧入
    bot_naming: bool = True  # 假人首創的配方與絕學定名也請模型取名（企劃者 2026-10-05、10-06）；關掉時假人不開要取名的爐、也不定名
    bot_naming_gap_seconds: float = 120  # 假人兩次請模型取名至少隔幾秒（現實時間；PM 10/5：一次一件，不搶真人的顯卡）
    bot_naming_budget_seconds: float = 30  # 假人一次取名最多花幾秒；取不到：首創的那一爐不開（不用字表名字搶首創），絕學定名改用字表另組
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
    side_trend_cap: int = 5  # 同一回合同一邊所有放手一搏合起來最多推進或倒退多少（正式內容 content/battles.json 2026-10-10 從 5 調成 4，見 BattleTuning.push_max）
    # 放手一搏不再「誰手快誰刷」（Joy 2026-10-10 決戰試玩回饋第 3 點：「跟從預設選項的玩家現在毫無存在感」）：
    # 一個人每一幕最多放手一搏 per_act 次（一場三幕最多三次），其餘回合出固定招
    per_act: int = Field(default=1, ge=1)


class ThirdParty(_Strict):
    """決戰的第三方（戰鬥系統第六節）：自成一方，不推這一場的戰局，只推自己那條大勢線；兩軍打得越膠著，收穫越多。
    第一季是地方豪強推豪強割據。兩招的名字可以改，份量與扣血看 BattleTuning 的 third_*。"""

    faction: str  # 劇本的陣營 id，不能是這一場交戰的兩軍之一
    trend: str  # 收場時推的大勢線（不能是衍生線）
    grab: str = "趁亂搶地盤"  # 用奇襲的份量；名字出自戰鬥系統第六節（待 joy 潤）
    keep: str = "保存實力"  # 用固守的份量，收穫算一半；名字出自戰鬥系統第六節（待 joy 潤）


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
    third: ThirdParty | None = None  # 第三方（戰鬥系統第六節）；沒有就是只有兩軍


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
    start_status: Literal["active", "away"] = "active"  # 輕量接位者開季時還沒出場，接手時才出現
    challenge_off_front: bool = False  # 沒有戰線也能挑戰（何進）；其他人戰線空著時不受挑戰（PM 2026-10-05 定）


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
    duels: dict[str, DuelBoss] = Field(default_factory=dict)  # 單人頭目戰（content/duels.json）；沒有這個檔就是空的
    figures: dict[str, FigureDef] = Field(default_factory=dict)  # 大勢人物（content/figures.json，計畫 T4）；沒有這個檔就是空的
    foreshadows: Foreshadows = Field(default_factory=Foreshadows)  # 關鍵伏筆（content/foreshadows.json，計畫 T7）
    orders: OrdersContent = Field(default_factory=OrdersContent)  # 陣營軍令（content/orders.json，計畫 T6）
    promotions: list[PromotionDef] = Field(default_factory=list)  # 晉升（content/promotions.json，計畫 T5）
    opportunities: list[OppDef] = Field(default_factory=list)  # 機緣（content/opportunities.json，正式版乙一）
    followers: dict[str, FollowerDef] = Field(default_factory=dict)  # 部下模板（content/followers.json，計畫 T5）
    preset_recipes: list[PresetRecipe] = Field(default_factory=list)  # 師門配方（新手引導計畫一）；沒有這個檔就是空的
    secret_recipes: list[SecretRecipe] = Field(default_factory=list)  # 秘方池（content/secret_recipes.json）；沒有這個檔就是空的
    map: MapLayout
    tutorial: Tutorial
    hints: Hints = Field(default_factory=Hints)  # 碰到才說（content/hints.json，新手引導計畫三）；沒有這個檔就是沒有提示
    check_voice: CheckVoice = Field(default_factory=CheckVoice)  # 檢定選項括號裡的那一句（content/check_voice.json，載入時必備）
