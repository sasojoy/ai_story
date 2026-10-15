"""執行期狀態：玩家、門下、世界。全部是可直接序列化成 JSON 的 Pydantic 模型。"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from .martial_arts import Insight
from .models import Content, TravelMode
from .tactics import Bout, BoutSide

PLAYER = "player"  # 沿用舊名，指玩家本人；同伴不再用 key 存在 PlayerState 裡（見下）


class Member(BaseModel):
    """玩家本人的角色表：等級/氣血/內功/武學。同伴不再用這個模型——他們全服唯一，等級/
    武學是共用資料（見 world_state.py::CompanionProgress），不是某個玩家存檔裡的副本。"""

    level: int = 1
    exp: int = 0
    neili: float | None = None  # 氣血，None＝回滿（滿＝上限 − 內傷）
    injury: float = 0.0  # 內傷：氣血自己只回到「上限 − 內傷」，要療傷才能清掉（氣血設計 §1.3）

    # 每人最多學一門內功、一門武學（設計文件六.4），id 指向 tianxia/martial_arts.py 的
    # MartialArt，可能是內容裡的固定武學（本命武學）也可能是玩家自創、存在共用世界狀態
    # 裡的武學。
    neigong_id: str | None = None
    neigong_level: int = 1  # 熟練度，第一成～第十成
    wugong_id: str | None = None
    wugong_level: int = 1
    cap_scale: float = Field(default=1.0, exclude=True)  # 本人氣血上限的倍數（螭首，玉璽一要 PM 定的第 7 條）：重抄抄本時設，不進存檔


class FollowerDrill(BaseModel):
    """傳功給一名部下的（Config.chuangong）：cheng 是在照等級長的那條線之上多練的成數（team.follower_level 加上去、最多十成），
    arm 是傳給他的臂力點數（加在模板上，最多 stat_cap）。"""

    cheng: int = 0
    arm: int = 0


MAX_TEAM_COMPANIONS = 4  # 設計文件四.4：每位玩家最多帶 4 個夥伴，只有一支隊伍，沒有多隊派遣

Personality = Literal["積極", "普通", "懶散"]


class BotProfile(BaseModel):
    """伺服器假人的內部資料（伺服器假人設計第五節）：只存在存檔裡，畫面上任何地方都不顯示。
    faction／season_number：這一季被叫醒、替哪個陣營效力；season_number 跟全服賽季編號
    對不上（或 faction 是 None）就是退隱中，不上線（見 server_bots.active）。"""

    personality: Personality
    seed: int  # 作息、趕來參戰的擲骰都從這裡算，同一個假人永遠一樣
    faction: str | None = None
    season_number: int = 0


class Journey(BaseModel):
    """在路上（地圖擴充設計 3.3）：出發時排好的路線與每一站的抵達時間。時間記在賽季時鐘上（WorldState.time
    的遊戲秒數，跟閉關的 busy_until 一樣），sync／advance 推進時鐘之後補算抵達。"""

    mode: TravelMode
    path: list[str]  # 出發時排好的路線（不含出發地），最後一個是終點
    arrive_at: list[float]  # 每一站的抵達時間，跟 path 一一對應
    reached: int = 0  # 已經抵達幾站
    stop_at: int | None = None  # 喊停：走到 path 的第幾站（索引）就停；None＝走到終點
    # 在路上改道、折返（路上設計 3.1）：新路程從路中間出發，第一段走的是 origin—path[0] 那條路剩下的部分。
    # 舊存檔沒有這兩欄＝從 location 出發的一般路程。
    origin: str | None = None  # 第一段那條路的另一頭；None＝從 location 出發
    share: float = 0.0  # 出發時 origin—path[0] 那條路已經走掉的幾成（第一段只走剩下的）
    # 出發那一刻的步調（裝備四欄 5.3，mounts.pace）：步行、趕路的時間乘它；抵達時刻照它排好，路上的位置（atlas.road_spot）也照它反推，
    # 路上餓了、換了馬都不回頭改。舊存檔沒有這一欄＝沒騎馬（1.0）。不加嚴格的驗證：一筆壞值不該讓整個角色讀不進來
    pace: float = 1.0

    @property
    def last(self) -> int:
        """這一趟最後要抵達的那一站（path 的索引）。"""
        return len(self.path) - 1 if self.stop_at is None else self.stop_at


class Convoy(BaseModel):
    """身上押著的糧車（護糧，計畫 T6）：送到 to_loc 才算數。"""

    order: str  # 哪一道護糧軍令（Order.id）
    grain: int  # 交出去的糧草份量
    from_loc: str
    to_loc: str


class Summons(BaseModel):
    """收到的召見（計畫 T5、晉升文件第一節）：沒有期限；到了 location、演完那一階的奇遇才晉升。
    figure 是發召見那一刻出面的人（江湖紀錄寫他）；到了現場照當下再挑一次（ranks.presenter）。
    第 3、4 階（正式版丙一）的奇遇有好幾段：leg 是這一段排第幾（0 起）、prev 是上一段演完的那一則事件、event 是這一段
    此刻要演的事件（版本照當下的時局挑，每次 check_summons 重挑）；第 2 階三個都用預設。"""

    rank: int
    figure: str | None = None
    location: str
    since: float = 0.0
    leg: int = 0
    prev: str | None = None
    event: str | None = None


class HintNote(BaseModel):
    """排著要在對話框說的一條提示（新手引導計畫三）：排進去的當下就照那時的陣營決定誰說、說什麼。
    shown：已經上過框（記進 hints_seen 與江湖紀錄了）；提示算「說過」是上框的那一刻、不是排進佇列的那一刻（Game._surface_hint）。
    by：這一條是哪一邊的引薦人說的（陣營 id）；師父說的（含散人聽到的那一版）是空字串。叛投時舊陣營那一邊排著的作廢（defection.clear_progress）。"""

    id: str
    speaker: str
    text: str
    shown: bool = False
    by: str = ""


ONBOARDING_VERSION = 3  # 新手引導的版本：2＝有序章的新引導（新手引導計畫一）、3＝再加入伍段（計畫二）。比 2 小的是舊存檔，讀檔時當作走過序章（設計 7.2）；
# 比 3 小而且已經有陣營的，是入伍段上線之前就投靠的老手，讀檔時蓋成入伍段走完（enlist.mark_veteran，設計 7.2）


class Sensing(BaseModel):
    """有所感（悟意境設計第零節）：探索落在悟意境那一支、這一處有場景時，存一份待決的感悟，直到悟成或落空。
    stage 是 "choose"（卡上三四個做法、還沒選）或 "draw"（選對又擲中，進了感悟狀態、等著畫那一筆）。"""

    location: str  # 在哪裡有所感（地點 id）；人不在這裡了（被帶走、內容改版）就作廢
    scene: str  # InsightScene id
    order: list[int]  # 卡上做法的順序（洗過牌）：第 i 個選項是 scene.methods[order[i]]
    stage: Literal["choose", "draw"] = "choose"
    method: str | None = None  # 選了的做法的屬性（剛柔快慢），進了感悟狀態才有
    serial: int = 0  # 這一次感悟的流水號（PlayerState.sense_serial）：鎖外看圖取名回來，C 段照它認是不是同一次


class Tagalong(BaseModel):
    """答應了別人的結伴同行：跟著 leader 走，路線與走法由他定。只記在跟著的那個人身上（帶頭的人照這一欄從資料庫查）。
    since 是答應的現實時刻：帶頭的人 Config.party_wait_seconds 之內沒動身就散了；動身之後一路到終點才散。"""

    leader: str
    since: float


class Equipment(BaseModel):
    """一件裝備（裝備四欄設計 3.1；原本的 Weapon，兵器設計 2.1）。slot 是哪一欄：武器、防具（裝備一），坐騎、寶物（裝備二、三）。
    id 是「兵:N」「甲:N」「騎:N」「寶:N」，共用 PlayerState.weapon_serial 流水號，只在這個角色身上唯一；舊的「兵:N」不能改
    （拆解照 id 的 sha256 挑素材）。舊存檔沒有 slot：預設 weapon（兵器第一、二批的裝備庫裡都是武器）。
    edge 各欄共用、叫法不同（equipment.WEAR_WORDS：鋒利度、耐久度、飽足度）。kind 只有武器有（models.WEAPON_KINDS），其餘是空字串；
    不在讀檔時驗（一件壞資料不該讓整個角色讀不進來），建構的地方（weapons.new_weapon、stock、armor.new_armor）自己給對。
    recipe 是自己打的那一件的組合鍵（兵器「兵|」、防具「鎧|」）；secret 是照隱藏配方打出來的名器（打造隱藏配方設計 4.2）；
    copy_of／original 是神器的仿品與原品（打造第二批）；signature 是名將本命兵器（打造第三批）。"""

    slot: Literal["weapon", "armor", "mount", "treasure"] = "weapon"
    id: str
    name: str
    kind: str = ""  # 武器：models.WEAPON_KINDS；其餘是空字串
    attribute: str = ""  # 陰陽剛柔快慢虛實（武器、防具）
    tier: int = 0  # 1～3（武器、防具、坐騎）；寶物不分階品，是 0（玉璽碎片的抄本也是，玉璽碎片設計 7.4）
    quality: str = ""  # 下品、中品、上品；寶物是空字串
    edge: int = 100  # 0～100：武器的鋒利度、防具的耐久度（equipment.WEAR_WORDS）
    tempers: int = 0  # 淬煉次數（兵器第二批；防具打造那一批）
    recipe: str | None = None
    copy_of: str | None = None
    original: bool = False
    # 內容裡的 id（裝備四欄 3.1）：寶物照 content/gear.json 的寶物表、名將贈禮的名駒照 steeds；馬市與懸賞的馬、武器、防具是 None。
    # 名字照它從內容讀：treasures.refresh_names 在讀檔時把 name 改成內容的名字（joy 改名不動存檔）；內容拿掉了就留著 name 當備份、效果不算
    template: str | None = None
    # 打中的隱藏配方 id（名器，打造隱藏配方設計 4.2）：名字照內容讀（forge_secrets.refresh_names，name 只當備份），加成看 equipment.named
    secret: str | None = None
    # 名將本命兵器的人物 id（打造第三批）：original 一起是 True（加成照神器原品）、secret 是 None（不是打出來的，不用定名）；
    # 名字照內容讀（signature_arms.refresh_names，name 只當備份）
    signature: str | None = None
    heirloom: bool = False  # 傳承（玉璽碎片的抄本，玉璽碎片設計 7.4）：不進裝備庫、不能換下、贈、拆、交懸賞


Weapon = Equipment  # 舊名：兵器第一、二批的程式與測試寫 Weapon(...)，照用（slot 預設 weapon）


class WeaponRecipe(BaseModel):
    """全服登記的兵器配方（兵器設計 4.4；資料庫第 4 版的 gear_recipes 表）：這一季第一個打出來的人取名，之後照著打的人查表。
    名字跟武學、改過的名字、意境共用一個名字空間（sqlite_world._name_taken）。id 就是名字（首創名望回饋 fusion.echo 照它記）。"""

    name: str
    key: str  # 配方鍵 weapons.recipe_key：「兵|種類|主料+輔料」（前綴就是欄位：武器「兵|」，之後防具「鎧|」，裝備四欄設計 4.7）
    kind: str  # models.WEAPON_KINDS
    attribute: str  # 主料與輔料合出來的屬性（insights.merged_attribute，種子是天機＋配方鍵）
    tier: int  # 主料的階
    main: str  # 主料的素材 id
    aux: str  # 輔料的素材 id
    creator: str | None = None  # 首創者的名號（身分）
    creator_shown: str | None = None  # 寫給別人看的名號（登記當下記下；同 MartialArt.creator_shown）
    co_creator: str | None = None  # fusion.echo 讀；兵器沒有論武，一律 None
    note: str = ""  # 模型替這個名字寫的一句說明；退路字表的名字沒有

    @property
    def id(self) -> str:
        return self.name


DIVINE_UNNAMED = "無名神器"  # 待 joy 潤：神器原品還沒定名時的名字（打造隱藏配方設計 5.2）；仿品寫「仿・無名神器」
COPY_NAME = "仿・{name}"  # 待 joy 潤：仿品的名字（5.3）；{name} 是原品的名字，還沒定名是 DIVINE_UNNAMED


class GearFind(BaseModel):
    """全服登記的隱藏配方發現（打造隱藏配方設計 7.1；gear_recipes 表裡鍵「鑄|配方 id」那幾列）：這一季第一個打出這條隱藏配方的人。
    表的名字欄寫鍵本身（不佔名字空間），名器的名字照內容。fusion.echo 讀 id、name、creator、co_creator、creator_shown。
    神器配方那一列另記原品主人、定的名字、仿品數（打造第二批；舊列沒有這幾欄，讀成名器那一筆）。"""

    secret: str  # 隱藏配方 id（ForgeSecret.id）
    slot: Literal["weapon", "armor"]
    kind: str = ""  # 兵器種類；防具是空字串
    attribute: str
    tier: int
    title: str  # 打出來的名字（名器照內容的 name，登記當下記下；傳聞與首創名望回饋照它寫）
    creator: str | None = None  # 首位發現者的名號（身分）
    creator_shown: str | None = None  # 寫給別人看的名號（登記當下記下）
    co_creator: str | None = None  # fusion.echo 讀；打造沒有論武，一律 None
    # 神器（打造第二批；企劃者選 14.1 甲：神器配方一爐必出神器）。照甲首位發現者就是原品主人：forge_secrets.new_find 在登記的那一筆裡
    # 一起記下（claim_gear_find 同一筆交易，誰先寫進去誰拿原品），不另開 claim_divine
    divine: bool = False  # 這一條是神器配方
    owner: str | None = None  # 原品主人的名號（身分）
    master_shown: str | None = None  # 寫給別人看的原品主人名號（打出那一刻記下；同 MartialArt.master_shown）
    divine_name: str | None = None  # 原品定的名字（world.name_divine）；還沒定是 None
    copies: int = 0  # 這一季照這個配方打出的仿品幾把（world.add_copy；神器譜寫「仿品 N 把」，不列人名）

    @property
    def id(self) -> str:
        return f"鑄|{self.secret}"  # 同 forge_secrets.PREFIX：首創名望回饋照它記，不會跟武學 id 或舊的兵器配方名字撞

    @property
    def name(self) -> str:
        """寫給人看的名字（傳聞、首創名望回饋 fusion.echo）：名器是內容的名字（title，登記當下記下）；神器是原品定的名字，
        還沒定名是「無名神器」（7.1）。"""
        if self.divine:
            return self.divine_name or DIVINE_UNNAMED
        return self.title


class SmithDraft(BaseModel):
    """鐵匠鋪「打造兵器…／打造防具…」挑到哪一步（smithing.draft_options）：兵器是種類 → 主料 → 輔料；防具沒有種類，打開時 kind 就是
    smithing.ARMOR_KIND（「防具」），從主料挑起。三樣都有了就是開爐那一步。"""

    kind: str | None = None
    main: str | None = None
    aux: str | None = None


class Manual(BaseModel):
    """武學譜（tianxia/secret_recipes.py）：這一季聽過的口訣與合中過的秘方。秘方每季照天機換一批，所以記著是哪一季的天機，
    對不上就當空的。鑄譜（PlayerState.forge_manual）用同一個型別，多記 made。"""

    tianji: int = 0
    heard: dict[str, list[int]] = Field(default_factory=dict)  # 秘方 id → 聽過第幾句口訣（0 說書、1 人物、2 殘譜）
    solved: list[str] = Field(default_factory=list)  # 合中過的秘方 id，照先後
    made: dict[str, str] = Field(default_factory=dict)  # 鑄譜用：隱藏配方 id → 打中的那一爐的組合鍵（鑄譜寫配方）；武學譜不用
    # 鑄譜用（素材與經濟設計第三節）：神器配方 id → 聽過的片（forge_secrets.KIND 0 種類、MAIN 1 主料、AUX 2 輔料）；武學譜不用
    pieces: dict[str, list[int]] = Field(default_factory=dict)


class DuelState(BaseModel):
    """一場還沒打完的單人頭目戰（tianxia/duel.py）。開打時快照你的份量、職位與氣血池，之後不回頭查；打完才把池子掉的氣血扣回本人。
    move／tell 是他下一回合要出的招與你看到的架勢（回合開始時就擲好：架勢有幾成是真的見 DuelTuning.tell_truth）。"""

    boss: str
    foe: int  # DuelBoss.foes 的第幾個面貌
    round: int = 0  # 打完了幾回合
    edge: float = 50.0  # 氣勢：越高越是你佔上風
    hp: float  # 氣血池剩多少
    hp_cap: float  # 開打時的氣血上限（池子的比例照它算）
    hp_start: float  # 開打時的氣血（打完扣回本人：開打時的 − 剩的）
    power: float  # 你的武學威力快照
    scores: dict[str, float] = Field(default_factory=dict)  # 三招的份量快照
    role: str = ""
    move: str = ""
    tell: str = ""
    lines: list[str] = Field(default_factory=list)  # 每回合一行（戰報的過程）
    difficulty: float | None = None  # 開打時快照的他的難度（江湖水漲，rise.duel）；舊存檔沒有，照內容寫的（duel.foe_difficulty）
    bout: Bout | None = None  # 兩邊的本命戰法（tactics.Bout，本命戰法第二批）；你沒有本命戰法是 None


class ArenaSide(BaseModel):
    """擂台一場裡的一邊（tianxia/arena.py）：開打時快照的威力、三招的份量、職位與氣血池。挑的人是此刻的身手，守的人是他報名時留下的分身。
    池子從滿的開始，打完不扣回角色。"""

    name: str
    power: float
    scores: dict[str, float] = Field(default_factory=dict)
    role: str = ""
    hp: float
    hp_cap: float


class ArenaFight(BaseModel):
    """一場還沒打完的擂台（挑的人身上，PlayerState.arena）。move／tell 是分身下一回合要出的招與你看到的架勢（回合開始時擲好）。
    best_* 是這一場到目前最有戲的那一次放手一搏（battle_instance.more_dramatic；收場時夠險就上天下大事）。"""

    id: int  # 這一季第幾場擂台（WorldState.arena_seq）
    foe_key: str  # 守的人的名號鍵（WorldState.arena 的鍵）
    me: ArenaSide
    foe: ArenaSide
    round: int = 0  # 打完了幾回合
    rounds: int = 5
    edge: float = 50.0  # 氣勢：越高越是挑的人佔上風
    move: str = ""
    tell: str = ""
    lines: list[str] = Field(default_factory=list)  # 每回合一行（戰報的過程）
    best_text: str = ""
    best_story: str = ""
    best_rate: int = 0
    best_won: bool = False
    best_set: bool = False
    bout: Bout | None = None  # 兩邊的本命戰法（tactics.Bout，本命戰法第二批）；兩邊都沒有是 None


class ArenaResult(BaseModel):
    """剛打完的那一場（挑的人身上，PlayerState.arena_last）：擂台那一頁的收場卡照它畫，再挑一場、離開擂台就清掉。"""

    id: int  # 那一場的 ArenaFight.id（網頁看過了照它不再跳出來）
    foe: str
    tier: str
    lines: list[str] = Field(default_factory=list)  # 每回合一行
    changes: list[str] = Field(default_factory=list)  # 戰報的得失（積分、名望）


class ArenaReport(BaseModel):
    """一場擂台留給守的人的一筆（他下次同步時補戰報與江湖紀錄，Game._deliver_arena）。tier 是守的人那一邊的結果。"""

    challenger: str
    tier: str
    time: float
    lines: list[str] = Field(default_factory=list)
    rank: int  # 打完之後守的人的名次
    before: int  # 打之前守的人的名次（被換下去才不一樣）
    power: float = 0.0  # 挑的人的威力（戰報的對手那一格）


class ArenaEntry(BaseModel):
    """一個守擂的人（WorldState.arena：名號鍵 → 這一筆；換季整個重來）。分身是報名或更新那一刻的身手。"""

    name: str
    power: float
    scores: dict[str, float] = Field(default_factory=dict)
    role: str = ""
    hp_cap: float
    arts: list[str] = Field(default_factory=list)  # 身上兩門武學的名字（選單上寫他守擂用什麼）
    kit: BoutSide | None = None  # 報名那一刻身上的本命戰法（team.self_side）；沒有是 None，舊存檔也是
    joined: float = 0.0  # 第一次報名的世界秒
    rank: int = 0  # 名次（1 是天下第一）；報名排到榜尾，挑的人贏了兩人交換（arena.swap）
    wins: int = 0
    losses: int = 0
    draws: int = 0
    streak: int = 0  # 連勝（挑與守都算，沒贏就歸零）
    best_streak: int = 0
    defended: list[int] = Field(default_factory=list)  # 舊存檔的 [遊戲日, 被挑了幾場]；被挑上限 2026-10-15 拿掉，不再寫也不再讀
    inbox: list[ArenaReport] = Field(default_factory=list)  # 被挑了、他還沒看到的
    wages: list[list[int]] = Field(default_factory=list)  # [現實的第幾天, 那一刻的名次]：換日時記（arena.roll_day），本人同步時領
    place: int = 0  # 季末的名次（1～3）；0＝沒進前三
    prized: bool = False  # 季末的獎勵補過了沒

    @property
    def bouts(self) -> int:
        return self.wins + self.losses + self.draws


class AnnalEntry(BaseModel):
    """行狀的一則（玩家傳，tianxia/annals.py）：季末寫《某某傳》的材料。只記事實，不記數值以外的推測；字是當下寫好的
    （時刻照 calendar.stamp_text、地點與人物照名字），季末不必再查這一季的狀態。"""

    kind: str  # annals.KINDS：showdown 決戰、figure 跟歷史人物、fight 單挑（頭目、挑戰本人、截殺）、deed 日常的大事
    time: float  # 世界秒
    when: str  # 寫的當下的時刻（calendar.stamp_text）
    place: str = ""  # 地點的名字
    figure: str = ""  # 人物 id（content.characters）；跟人物無關是空字串
    text: str  # 一句事實，80 字以內
    quote: str = ""  # 你說的那一句（自己說、放手一搏、隨口應對的原句）
    reply: str = ""  # 人物回的那一句，或放手一搏播出的那一版劇情
    weight: int = 1  # 份量 1～5：行狀滿了先丟輕的


class PlayerState(BaseModel):
    name: str
    location: str
    stats: dict[str, int]
    stamina: float
    flags: set[str] = Field(default_factory=set)
    sect: str | None = None
    faction: str | None = None  # 投靠的陣營 id（Scenario.factions）；None＝散人
    pending_faction: str | None = None  # 按了「投靠某陣營」、還在確認畫面上的陣營 id
    pending_defect: str | None = None  # 按了「叛投某陣營」、還在確認畫面上的陣營 id（計畫甲）
    ally: str | None = None  # 豪強分屬兩軍的季（allied.on）：依附哪一軍；其他人、其他季是 None（陣營照舊記在 faction）
    pending_ally: str | None = None  # 投靠豪強或叛投到豪強的確認畫面上挑好的那一軍；還沒挑是 None
    defected: bool = False  # 這一季叛投過了（第一季設計 5.1：一季最多一次）；角色每季重來，新的一季自然是 False
    member: Member = Field(default_factory=Member)  # 玩家本人的角色表

    # ── 同伴（sanguo-companions 合併重寫：全服唯一，見 world_state.py）──
    team: list[str] = Field(default_factory=list)  # 目前帶在身邊出戰的同伴 id，最多 MAX_TEAM_COMPANIONS 人
    affinities: dict[str, int] = Field(default_factory=dict)  # 人物 id -> 0~100 好感度，跟有沒有招到他無關
    relationship_notes: dict[str, str] = Field(default_factory=dict)  # 人物 id -> 一句話關係現況
    # 上一季的交情（第一季設計第十四節；正式版辛）：人物 id → 最近一次有聊過的那一季的關係筆記。換季時把
    # relationship_notes 搬過來（這一季的從頭寫），沒聊過的人物保留更早的那一句。只給模型當背景，畫面不顯示
    past_notes: dict[str, str] = Field(default_factory=dict)
    # 人物 id → dialogue_history 裡這一季的對話從第幾則開始（換季時記下當時的長度）；模型只看這一季的對話
    history_start: dict[str, int] = Field(default_factory=dict)

    # ── 深度對話（companion_agent.py，見設計文件四.3）── 這些是「這個玩家跟這位人物」的
    # 私有對話狀態，不是全服共用的（性情漂移才是全服共用，見 world_state.py）。
    pending_companion: str | None = None  # 目前正在對話中的人物 id；非 None 時 options() 顯示對話選項
    dialogue_history: dict[str, list[dict[str, str]]] = Field(default_factory=dict)  # 人物 id -> 最近對話（role/content）
    used_dialogue_options: dict[str, list[str]] = Field(default_factory=dict)  # 人物 id -> 說過的話（避免重複）
    last_offered_dialogue: dict[str, list[list[str]]] = Field(default_factory=dict)  # 人物 id -> [選項文字清單, 對應tag清單]
    turns_since_consolidation: dict[str, int] = Field(default_factory=dict)  # 人物 id -> 距離上次記憶梳理幾輪
    talks_today: dict[str, list[int]] = Field(default_factory=dict)  # 人物 id -> [第幾個遊戲日（rules.game_day，跟著季長縮）, 當天已聊幾輪]
    picking_audience: bool = False  # 按了「求見」、正在挑要拜會哪一位人物（兩位以上大勢人物的地點）；舊存檔沒這欄就是沒在挑

    # ── 煉製素材（無限煉製第一刀，見 tianxia/materials.py）──
    materials: dict[str, int] = Field(default_factory=dict)  # 素材 id -> 數量；舊存檔沒這欄就是空背包
    # ── 裝備（兵器設計第二節、裝備四欄設計第三節）：身上每欄一件、四欄共用的裝備庫；換季時角色重來自然清空 ──
    # rack ＝ 玩家看到的「裝備庫」（企劃者 2026-10-10 由「兵器架」改名；程式識別字 rack、rack_cap、rack_full 不動）。
    # 每個讀 rack 的地方都照欄位過濾（equipment.in_slot，裝備四欄 3.3）
    weapon: Equipment | None = None
    armor: Equipment | None = None  # 身上的防具（裝備四欄設計第四節）；舊存檔沒有＝沒穿
    rack: list[Equipment] = Field(default_factory=list)
    weapon_serial: int = 0  # 四欄共用的流水號（兵:N、甲:N）
    picking_smith: bool = False  # 打開了鐵匠鋪的第二層選單（同 picking_bounty）
    smith_page: str = "weapon"  # 鐵匠鋪停在哪一頁（"weapon"／"armor"，裝備四欄 4.6）：開門時設成第一個開著的，收起鐵匠鋪時設回來（equipment.open_smith／close_smith）
    edge_warned: bool = False  # 身上那把鈍到 Config.weapons.edge_warn 以下時提醒過一次了；修好就重設
    armor_warned: bool = False  # 身上那件防具耐久低到 Config.armor.edge_warn 以下時提醒過一次了；修好或換一件時重設
    mount: Equipment | None = None  # 身上的坐騎（裝備四欄設計第五節）；舊存檔沒有＝沒騎馬
    hunger_warned: bool = False  # 身上那匹飽足低到 Config.mounts.edge_warn 以下時提醒過一次了；餵過或換一匹時重設
    picking_market: bool = False  # 打開了馬市的第二層選單（同 picking_smith）；離開、存檔修補、同步時人不在馬市、出發都收起來
    picking_arena: bool = False  # 打開了擂台的第二層選單（同 picking_market）；離開、存檔修補、同步時人不在城鎮、出發都收起來
    treasure: Equipment | None = None  # 身上的寶物（裝備四欄設計第六節；隨時能換，2.3）；舊存檔沒有＝沒帶
    heirloom: Equipment | None = None  # 寶物欄的「傳承」那一格：玉璽碎片的抄本（照全服登記重抄，玉璽碎片設計 7.3、7.4）；換季帶走
    seal_seen: int = 0  # 玉璽的補送補到全服登記的第幾號（Game._deliver_seal_results）；換季帶走
    seen_real: float | None = None  # 這個人自己最近一次上線的現實秒（伺服器 act／act_look、假人自己那一輪才寫；Game.sync 不寫）：「這一季上線過」與隱沒看它（5.3、7.6）；換季帶走
    treasure_drops: set[str] = Field(default_factory=set)  # 這一季打贏後掉過寶物的大勢人物 id（6.4：同一位對同一個人每季只掉一次；裝備庫滿了沒擲的不記）
    tier3_drops: dict[str, int] = Field(default_factory=dict)  # 這一季挑戰打贏、掉過三階素材的大勢人物 id → 幾次（兵器設計 4.9；Game._figure_tier3）
    figure_wins: dict[str, int] = Field(default_factory=dict)  # 這一季挑戰打贏大勢人物本人的次數：人物 id → 幾次（大勝、險勝；本命兵器「打贏三次」，Game._challenge）。角色每季重來自然清掉；叛投不清
    figure_rare_drops: int = 0  # 這一季挑戰本人掉了幾個三階（兩條來源合算：預設表、保證的那一個；丁 (c) 的一人一季上限 figure_rare_cap；換季跟著新角色歸零）
    # 寄放著、等裝備庫有空位才補發的（6.5：懸賞的重賞、名將贈禮）：Game._deliver_held_gear 同步與快轉時補（閉關中也補）。不存在 Bounty 上：懸賞下榜就跟著不見了
    held_gear: list[Equipment] = Field(default_factory=list)
    forge_counts: dict[str, int] = Field(default_factory=dict)  # 裝備的組合鍵（兵器「兵|」、防具「鎧|」）→ 這一季你打過幾次（熟手，兵器設計 4.3）；換季跟著角色重來
    shop_line: str = ""  # 店面上掌櫃那一句的情況鍵（店裡最後一件事：進門、買了、打完一爐……；店面獨立介面設計 1.4、6.1）：收起店時清掉
    shop_line_seed: int = 0  # 挑那一句的種子（記下那一下的季的時間，整數秒）：輪詢時同一件事一直是同一句
    shop_hold: str = ""  # 被拒的那一句撐到什麼時候（FB-192，shopview.hold_for）：被拒的原因不成立了就換回平常那一句；收起店時清掉
    shop_clue: str = ""  # 鐵匠順口說出的那一句（forge_secrets.hear_smith，1.4）：蓋過這一下的掌櫃話，下一下就換回掌櫃話；收起店時清掉
    smith_draft: SmithDraft | None = None  # 鐵匠鋪「打造兵器…／打造防具…」挑到哪一步；打開、打完、不打了都清掉，凡是把 picking_smith 收起來的地方（離開、存檔修補、同步時人不在城鎮、出發）一起清
    arts: list[str] = Field(default_factory=list)  # 功法庫：煉出來但沒配上身的功法 id
    art_levels: dict[str, int] = Field(default_factory=dict)  # 每門學過的功法各自的「成」；改練時存進來／取出來
    # ── 武學與成長（設計第三、四節）──
    insights: list[str] = Field(default_factory=list)  # 悟得的意境 id，照悟得的先後
    # ── 悟意境（悟意境設計第零節、0.2b；舊存檔沒這幾欄就是空的）──
    sensing: Sensing | None = None  # 有所感、還沒了結的那一次
    sense_serial: int = 0  # 有所感的流水號（每次有所感 +1）
    sense_misses: dict[str, int] = Field(default_factory=dict)  # 地點 id → 選錯做法是第幾個遊戲日（rules.game_day）：那一個遊戲日這裡探索不再落在悟意境
    # 私有的意境（畫圖悟來的，或拿私有的合併出來的）：id「悟:流水號」→ 本體；id 同時也記在 insights（學會了哪些）裡
    own_insights: dict[str, Insight] = Field(default_factory=dict)
    own_serial: int = 0  # 私有意境的流水號
    stat_points: int = 0  # 升級得到、還沒分配的屬性點（武學與成長設計 6.2）
    art_quality: dict[str, str] = Field(default_factory=dict)  # 功法 id → 自己那一份的品質（沒記＝全服登記的品質）
    art_mastery: dict[str, int] = Field(default_factory=dict)  # 功法 id → 修練往下一品失敗了幾次（熟練度）
    # 功法 id → 合成時擲到的品質（Config.fuse_quality_odds）：熔的時候當成「登記時就有」，只有修練上去的幾階才有加給
    art_rolled: dict[str, str] = Field(default_factory=dict)
    naming: str | None = None  # 第一個修到絕學、等著取正式名字的功法 id
    stamina_pills: int = 0  # 回體丹（Config.stamina_pill_name）的數量：建立角色時的內測贈送；跨季保留（Game._reset_player_for_new_season）
    # 回體丹補到過幾顆（企劃者 2026-10-12 拿掉一鍵補滿、改送合適的數量）：Config.beta_gift_stamina_pills 比它多時，讀檔那一刻手上不到那個數的
    # 補到那個數、寫一行紀錄，再記成那個數（一個數只補一次；之後再調高會再補一次）。新角色建立時就記成送的數。
    pills_topped_to: int = 0
    # 一天最多服幾顆（Config.stamina_pills_per_day，企劃者 2026-10-12）：上次服丹是哪一天（現實時間照 pill_day_utc_offset_hours 換日，
    # 從 1970-01-01 起算的第幾天；-1 是沒服過）與那一天服了幾顆。跨季保留（換季不能多吃一輪）
    pill_day: int = -1
    pills_today: int = 0
    # 出陣（出陣探索與地盤設計 2.3）：上次出陣是哪一天（同 pill_day 的換日）與那一天出了幾次；跨季保留（換季不能多出一輪）
    sortie_day: int = -1
    sorties_today: int = 0
    # 素材與經濟（2026-10-15，tianxia/economy.py）：同 pill_day 的換日；跨季保留（換季不能多換一輪、多捐一輪）
    upgrade_day: int = -1  # 鐵匠鋪升階：上次升階是哪一天
    upgrades_today: dict[int, int] = Field(default_factory=dict)  # 那一天換到幾階 → 換了幾個（只記有每日上限的階，Config.economy.upgrade_per_day）
    upgrade_seq: int = 0  # 這一季升階了幾次：升階擲哪一種的種子（economy.upgrade_rng），換季歸零（種子另帶季數）
    donate_day: int = -1  # 大本營捐軍備：上次捐是哪一天
    donated_today: int = 0  # 那一天捐了幾點貢獻（Config.economy.donate_daily_cap）
    picking_donate: bool = False  # 大本營的捐軍備選單開著（act:donate → donate:<素材>:<個數>／donate:back），不花體力
    legend_items: int = 0  # 破境丹（Config.legend_item_name）的數量：探索撿到，玩家在修練頁勾了、衝絕學那一次才服一枚；角色每季重來

    seen_events: set[str] = Field(default_factory=set)
    # （舊的 event_seen 看過次數已拿掉：joy #16 的輪替取代了 FB-058 的 0.5^次數 遞減。舊存檔裡還有這一欄也讀得進來——
    # PlayerState 沒禁止多餘的欄位，讀的時候直接略過，下次存檔就不見了）
    # 防重複（events.pick_event 照它抽、events.note_round 在 Game._present 真的端出事件時才記）：池子（「地點:行動」或「*:行動」）→ 這一輪看過的事件 id，照看到的先後；輪完清空。
    # 舊存檔沒這欄就是每個池子都還沒看過；角色每季重來，所以每季自然清空
    event_rounds: dict[str, list[str]] = Field(default_factory=dict)
    mark_days: dict[str, int] = Field(default_factory=dict)  # 地方痕跡：這個人上次替這個痕跡算進一次是第幾個遊戲日（rules.game_day；一個遊戲日只算一次；角色每季重來，跟著清空）
    explore_seq: int = 0  # 這一季第幾次探索三選一（explore_modes.rng_for 的種子；角色每季重來）
    anonymous: bool = False
    # 性別（PM 2026-10-12，企劃者「創建角色時可以選擇性別」）：「男」／「女」，不影響任何數值；稱呼換字一律走 tianxia/gender.py。
    # 舊角色沒這欄是男、gender_chosen 是 False：設定頁給一次改的機會（Game.set_gender，改完記 True）；建角色時選過的直接是 True
    gender: str = "男"
    gender_chosen: bool = False
    busy_until: float | None = None  # 閉關結束的遊戲時間
    seclusion_start: float = 0.0
    seclusion_done: float | None = None  # 上一次出關的遊戲時間（天時地利的「心靜」）；沒閉關過是 None
    manual: Manual = Field(default_factory=Manual)  # 武學譜（口訣與秘方）
    forge_manual: Manual = Field(default_factory=Manual)  # 鑄譜（打造的隱藏配方：聽過的口訣、打中過的；tianxia/forge_secrets.py）
    resting_since: float | None = None  # 打坐 2026-10-12 拿掉了：只留著讓舊存檔讀得進來，讀檔就清掉（Game._drop_stale_references）
    journey: Journey | None = None  # 在路上；None＝人在某個地點（location）
    # 路上小事（路上設計第四節）：這一段路上已經做過的（road: 選項的 id 後半，例如 think）。到了另一站就清空；
    # 掉頭回到剛離開的那一站不算換段，所以不跟著那一趟 Journey 走，記在玩家身上（不然折返一下就能重做）。
    leg_actions: set[str] = Field(default_factory=set)
    surveyed: set[str] = Field(default_factory=set)  # 留意地形摸清的地點：大地圖上跟去過一樣算記得（atlas.location_view）
    recent_sights: list[str] = Field(default_factory=list)  # 最近看過的路上見聞 id（舊的在前）；挑的時候先排除（路上設計第五節）
    # 路上收穫的每天上限（企劃者 2026-10-03 決定）："task"（邊走邊想、路邊採集）／"sight"（路上見聞）->
    # [第幾個遊戲日, 當天已拿幾次]，跟 talks_today 同一種寫法；記的是前幾天就當沒拿過
    road_rewards_today: dict[str, list[int]] = Field(default_factory=dict)
    tutorial_step: int = 0  # 等於引導步數時代表引導結束
    guide_done: list[str] = Field(default_factory=list)  # 最近一次行動完成引導的那幾行（✔ 與獎勵），對話框顯示；下一次行動清掉
    guide_skipped: bool = False  # 按過「略過新手引導」：之後（含換季、第一季多出的步驟）都不畫對話框；步驟照樣記著
    guide_outro: bool = False  # 引導剛走完、結語還沒按「知道了」（對話框顯示結語）；略過的、早就做完的是 False
    onboarding: int = 0  # 這個角色的引導是照哪一版記的（ONBOARDING_VERSION）；舊存檔沒有這個欄位＝0
    enlist_step: int | None = None  # 入伍段（新手引導計畫二）：None＝還沒開始；等於步數＝走完
    enlist_end: bool = False  # 入伍段剛走完、引薦人的結尾還沒按「知道了」
    # 入伍段目前這一步是從世界時間（秒，季裡的時鐘，不是電腦時鐘）的哪一刻開始的（FB-094）：最後一步（第一道軍令）一週（季曆）
    # 還沒做完，引薦人照樣說結語、入伍段關起來（enlist.expire）。這一版之前存的角色沒有，None＝下一次檢查才從那一刻算起
    enlist_since: float | None = None
    # ── 碰到才說（新手引導計畫三）──
    hints_seen: set[str] = Field(default_factory=set)  # 說過（上過框）的提示 id；換季保留，整個遊戲每一條只說一次
    hint_queue: list[HintNote] = Field(default_factory=list)  # 排著還沒按「知道了」的提示，對話框一次一條；換季不帶
    hints_off: bool = False  # 設定頁的「不再提示」（跟略過新手引導分開，設計 7.3）；換季保留
    visited: set[str] = Field(default_factory=set)  # 去過的地點
    fortune: bool = False  # 本季的新立門戶福緣已經發生（或已經改送賀禮）
    # 新手福利（氣血回復加倍、新立門戶福緣）從哪一刻起算（第一季設計第十四節「從自己加入的那天起算」）：這個角色進這一季時的
    # 賽季時間（世界秒）。新角色與換季重來的角色先是 None，第一次同步補算完賽季之後才蓋上（Game._stamp_join）——建角的那一刻
    # 賽季可能已經好幾個鐘頭沒人補算，那時就蓋會把福利白白吃掉一段。舊存檔沒有這一欄讀成 0.0：從季初算，跟以前一樣。
    # 新手福利只在第一季的規則開著時從這裡算（roster.since_join；beta 從季初算）；截殺與通緝的新手期每季都從這裡算
    # （roster.raid_newbie，懸賞榜設計 14.1 丁）
    joined_at: float | None = 0.0

    # ── 共享賽季（跨玩家，見 world_state.py::SharedWorldState.season）────
    season_number: int = 1  # 這個玩家的角色屬於第幾季；跟共用賽季的編號對不上時，
    # Game._drop_stale_references() 會知道共用的賽季已經換過一輪，幫這個玩家的角色重開
    # 新的一季（關係現況/對話紀錄保留、好感度只帶一成，角色本身的等級/位置/隊伍重新開始，見設計討論）。
    bot: BotProfile | None = None  # 伺服器假人才有（伺服器假人設計第五節）；任何畫面都不能顯示或透露
    # 處理過的收場決戰（BattleInstance.record_id）：自己參戰、已經補進江湖紀錄與戰報的，以及看過不是自己參戰的
    # （FB-027，見 Game._deliver_battle_results）。跨季保留：決戰常常把季收掉，下一季才回來的人也要補、而且只補一次
    battle_results_seen: list[int] = Field(default_factory=list)
    # 補回被洗掉的決戰戰報（Game._restore_showdowns）做過的那一季：一季只查一次 battles 表。舊存檔沒有是 0
    showdowns_restored: int = 0
    # 這一季參戰幾場、當過幾次首功（Joy 2026-10-10 個人戰功；玩家卡寫）。角色每季重來，跟著清空；舊存檔沒有就是 0
    showdowns: int = 0
    top_merits: int = 0
    # 這一季已經補進江湖紀錄的時刻表大事 id（FB-038，見 Game._deliver_big_events）。大事 id 每季都一樣，
    # 所以這份每季重來：換季時新角色自然是空的（跟 battle_results_seen 不同，不跨季保留）
    events_seen: list[str] = Field(default_factory=list)
    # 已經通知過（或不必通知）的絕學定名（FB-083，Game._deliver_renames）：武學 id。自己定的、拿到時就已經是定過名的、
    # 通知過的都記在這裡，同一門只通知一次。武學跟著季走，所以這份也每季重來
    renames_told: list[str] = Field(default_factory=list)
    # 行狀（玩家傳，tianxia/annals.py）：這一季值得寫進傳裡的事，照份量留最多 Config.biography.cap 則。角色每季重來，換季前存進
    # biographies 表（Game._reset_player_for_new_season）
    annals: list[AnnalEntry] = Field(default_factory=list)
    # 上一次看過的幾樣狀態（陣營、門派、階、等級、名號、同伴、寶物、情誼……，annals.watch）：每個動作結束時拿現在的跟它比，變了的記一筆。
    # None＝還沒看過（新角色、這一版之前的存檔）：第一次只記下來、不補記以前的事
    annals_mark: dict | None = None

    # ── 推力與貢獻帳（計畫 T3、第一季設計第七節）；角色每季重來，跟著新角色清空 ──
    # 遊俠名號（ranger.py；散人的成長階梯）：散人時攢的善名、惡名（只算加的）與懸賞的功績；投靠了陣營就不再記（凍結）
    ranger_good: int = 0
    ranger_evil: int = 0
    ranger_deeds: int = 0
    bounties_done: int = 0  # 這一季完成了幾張懸賞（量表與人物卡用）
    picking_bounty: bool = False  # 打開了懸賞榜（第二層選單，不花體力）
    # 懸賞榜第三層：正在替哪一張求藝、求兵挑東西（懸賞 id，懸賞榜設計 4.4）。按「交出…」記下；回到懸賞榜、返回、交完、打開懸賞榜時清掉。
    # 那一張下榜了、交不出了，選單當它不存在（Game._bounty_options），所以存檔修補、出發都不必另外收
    bounty_pick: str | None = None
    contrib: int = 0  # 本季替目前陣營推大勢記下的貢獻（散人不記）
    contrib_weeks: dict[int, int] = Field(default_factory=dict)  # 季曆第幾週 → 那一週記的貢獻
    pushed: dict[str, float] = Field(default_factory=dict)  # 「曆日:大勢線 id」→ 當天這條線推得動多少（人數緩衝之後）；只留今天與昨天

    # ── 捐獻紀錄（計畫 T6，軍備文件 4.1）：「據點 id:糧草」→ 累積的份量。T7 的伏筆只讀它；寫入是 T6 護糧的事 ──
    donations: dict[str, int] = Field(default_factory=dict)
    convoy: Convoy | None = None  # 押著的糧車（計畫 T6 護糧）；None＝沒有。角色每季重來，跟著清空
    # ── 晉升（計畫 T5）；角色每季重來 ──
    rank: int = 0  # 晉升過的階；0 是還沒晉升過（有陣營時算第 1 階，見 ranks.rank_of）
    summons: Summons | None = None  # 還沒去的召見
    followers: list[str] = Field(default_factory=list)  # 部下（followers.json 的模板 id）
    # 傳功給每名部下的（Config.chuangong）：跟 followers 同一個位置一一對應（短了當沒傳過，team.drill_of）；叛投時跟部下一起清掉
    follower_drill: list[FollowerDrill] = Field(default_factory=list)
    runic_pieces: int = 0  # 符文殘片（伏筆文件第七節；基準量，黃巾第 4 階的密令給的；玉璽大勢任務讀它）；角色每季重來
    qualified: bool = False  # 第 4 階的資格（候缺，正式版丙一）：rank 停在 3、沒在任時頭銜寫「…（…候缺）」；上任與席次見 seats.py（正式版丁）
    rank_hinted: list[int] = Field(default_factory=list)  # 說過「只缺一個機會」那一句的階（每階一次；跟新手引導的 hints_seen 無關）
    # 卡在哪裡、說過「沒有人能引見」那一句（企劃者裁決 E3，ranks._stalled）：「陣營:階:段」；空字串是沒卡住。存在角色的 JSON，不升 SCHEMA_VERSION
    summons_stall: str = ""

    # ── 大勢人物（計畫 T4、軍令文件 4.5）：剛被你打敗的人物 id → 到哪個「現實」時間（秒，Game.now）之前不見你、也不跟你交手。
    # 看現實時間、不看賽季時鐘（管理者快轉不會讓他提早見你）；角色每季重來，跟著清空 ──
    snubbed_until: dict[str, float] = Field(default_factory=dict)

    # ── 伏筆（計畫 T7、伏筆文件）；角色每季重來，跟著新角色清空（不在跨季保留的清單上）──
    fragments: dict[str, list[int]] = Field(default_factory=dict)  # 鏈 id → 聽過的片段（fragments 的索引）
    clue_items: dict[str, int] = Field(default_factory=dict)  # 伏筆專用物品 id → 數量
    fs_counters: dict[str, int] = Field(default_factory=dict)  # 隱藏計數：guanyin（官銀）、two_buyers（豪強兩頭賣糧的起點）
    fs_done: list[str] = Field(default_factory=list)  # 做完的鏈 id；多趟的鏈每做完一趟另記「鏈 id:第幾趟」（從 0 起）
    fs_cooldown_until: dict[str, float] = Field(default_factory=dict)  # 鏈 id → 答錯之後要等到哪個世界秒才能再做
    fs_asking: str | None = None  # 正在答最後一步的題的那條鏈；None＝沒在答（選單照常）
    fs_asked: int = 0  # 答到第幾題（0＝question，1 起是 then 的追問）

    # ── 機緣（正式版乙一、機緣文件）；角色每季重來，叛投時 opportunities.clear 清掉（opp_clues 例外，見 clear）──
    opp_done: list[str] = Field(default_factory=list)  # 完成的機緣 id
    opp_counts: dict[str, int] = Field(default_factory=dict)  # 累積型：機緣 id → 記了幾次
    opp_items: dict[str, str] = Field(default_factory=dict)  # 機緣 id → 拿到、還沒交的東西（名字）
    opp_fronts: dict[str, str] = Field(default_factory=dict)  # 機緣 id → 那件東西要送去哪條戰線
    opp_clues: list[str] = Field(default_factory=list)  # 聽過線索的機緣 id；叛投不清（企劃者裁決 E5.2，同伏筆片段）
    # 失敗過、同一回（或同一曆日）不能再試的記號。鍵：天時地利型與推理型的指認是機緣 id（值是時段鍵／曆日）；拼圖的一樣東西是
    # 「機緣 id:東西 key」；密謀的一處是「plot:密謀 id:處的 key」（值都是曆日）
    opp_tried: dict[str, int] = Field(default_factory=dict)
    rank2_days: dict[int, int] = Field(default_factory=dict)  # 曆日 → 那天做了幾次第 2 階行動；只留今天
    rank_action_weeks: dict[str, int] = Field(default_factory=dict)  # 「季曆週:行動 id」→ 這一週做了幾次第 3、4 階行動；只留這一週（正式版戊一）
    # ── 機緣・乙二（拼圖、推理與集體密謀）；同樣每季重來、叛投時 opportunities.clear 清掉（opp_settled 例外，見 clear）──
    opp_pieces: dict[str, list[str]] = Field(default_factory=dict)  # 拼圖型：機緣 id → 已經拿到的東西的 key
    patron: str | None = None  # 靠山（晉升奇遇 4.2）：yuan、cao、self；計畫丙升第 3 階時寫入，叛投清掉
    opp_settled: list[int] = Field(default_factory=list)  # 結算過的集體密謀 id（只結算一次；換季跟著新角色清空）

    # ── 玩家之間的互動（第二層：結伴同行；邀請本身在 WorldState.invites）；角色每季重來，跟著清空。存在角色的 JSON，不升 SCHEMA_VERSION ──
    duel: DuelState | None = None  # 正在打的單人頭目戰（tianxia/duel.py）；None＝沒有
    arena: ArenaFight | None = None  # 正在打的擂台（tianxia/arena.py）；None＝沒有
    arena_last: ArenaResult | None = None  # 剛打完的那一場（擂台那一頁的收場卡）；再挑一場、離開擂台就清掉
    arena_day: int = 0  # 擂台挑擂次數記在哪一天（同 pill_day：Config.pill_day_utc_offset_hours 的 00:00 換日）
    arena_today: int = 0  # 那一天挑了幾次（ArenaTuning.per_day）
    duel_tally: dict[str, int] = Field(default_factory=dict)  # 「季號:頭目 id」→ 這一季遇上幾次（Config.duel.per_boss_season）
    duel_last: list[float] = Field(default_factory=list)  # 上一場頭目戰開打的 [季號, 世界秒]（Config.duel.cooldown_seconds）；空的是沒打過
    tagalong: Tagalong | None = None  # 跟著誰結伴同行；None＝沒有


RumorLayer = Literal["world", "faction", "local", "personal"]  # 天下大事／陣營軍情／地方傳聞／個人線索（傳聞分層設計第二節）


class Rumor(BaseModel):
    """一則傳聞，或一則江湖史（江湖史只用到 id、time、text、location）。"""

    time: float
    text: str
    location: str | None = None  # 發生地（地點 id）；江湖史、舊存檔與不在特定地點的傳聞為 None
    id: int | None = None  # 資料庫的流水號；None＝還沒寫進資料庫（存的時候新增一列，見 sqlite_world）
    layer: RumorLayer = "world"
    faction: str | None = None  # 陣營軍情：哪個陣營的人看得到
    region: str | None = None  # 發生地所在的大區（atlas.region_of）；地方傳聞照它給人看
    character: str | None = None  # 個人線索：只有這個名號看得到
    named: bool = True  # 具名；觸發者選了匿名（「某位少俠」）時是 False


class TimelineResult(BaseModel):
    """一件大事結算的結果（時刻表，計畫 T2）。key 是結果鍵（"成"、"甲:guan:大勝"…；跳過的是 timetable.SKIPPED）。"""

    key: str
    time: float  # 結算的世界秒
    locked_by: str | None = None  # 鎖定者的名號（江湖史、結算畫面的稱號依據）；沒人鎖定是 None
    losers: list[str] = Field(default_factory=list)  # 搶輸的人
    text: str = ""  # 公告全文（不含「【江湖大事】」）；跳過的是空的


class Plot(BaseModel):
    """一場集體密謀（機緣文件 1.1；正式版乙二）：全服共用，參與者各自回來時才結算（opportunities.settle）。
    一場密謀只有自己陣營的人看得到、做得了；一季結束整個賽季跟著換新，所以只增不減到季末（一人一次牽頭一場、
    每場最多 plot_days 個曆日，量不大）。"""

    # 這一季的密謀編號。選項 id（opp:join:<id>、opp:part:<id>）會原樣送到前端，所以不能是全服連號——連號的空缺會洩漏別的
    # 陣營發起過幾場、大約什麼時候（審查 I-1）。改由陣營、機緣、發起人與發起時刻（遊戲時間）的雜湊決定（opportunities.plot_id），
    # 一季之內不重複；從編號看不出別的陣營的任何事。opp_settled 也存這個編號
    id: int
    opp: str  # 機緣 id
    faction: str
    leader: str  # 發起人的名號
    # 寫在陣營軍情與響應選項上的名字：陣營內一律具名（企劃者 2026-10-06：只有地方傳聞匿名，同叛投與軍令的軍情），所以就是
    # 名號、不是顯示名（匿名的「某位少俠」會讓兩個匿名發起人的軍情與選項一模一樣，審查 I-2）
    shown: str
    members: list[str] = Field(default_factory=list)
    parts: dict[str, str] = Field(default_factory=dict)  # 那一處的 key → 誰做的
    deadline: float  # 世界秒
    status: Literal["open", "done", "failed"] = "open"


class Lock(BaseModel):
    """關鍵伏筆的鎖定（伏筆文件 2.4；T7 寫入，T2 結算時讀）。"""

    side: str  # 陣營 id
    name: str  # 名號（真名：時間軸的 locked_by、losers 與 T9 的稱號用它）
    time: float
    shown: str | None = None  # 公告與江湖史寫的名字：None＝寫名號（現在一律不記）；這一版之前匿名鎖定的是「某位少俠」，照舊


class FigureState(BaseModel):
    """大勢人物當下的樣子（計畫 T4；T2 先放最小版，時刻表結果改它）。"""

    prestige: int = 60
    status: Literal["active", "away", "retired", "crippled", "jailed"] = "active"  # 在場／未出場／退場／重創／下獄
    front: str | None = None  # 在推哪條戰線
    location: str = ""


class Order(BaseModel):
    """一道軍令（計畫 T6）：每週一發、期限到下週一。陣營的進度＝progress 加總；湊滿 quota 那一刻達成、套一次效果。
    text 是發的那一刻填好插槽的發布文字（主將之後換人也不改）。applied 是達成時實際推了戰況幾點（守城收回對方攻城的
    一半時讀它）。上週沒達成的在下週一清掉；達成的留到季末（守城看「敵方上週達成攻城」、整季模擬數軍令都讀它）。"""

    id: str
    template: str  # 種類（OrderTemplate.kind）；同一個陣營每種只有一筆模板
    faction: str
    week: int
    front: str | None = None  # 戰線（打擊是目標人物發令時所在的戰線）
    location: str | None = None  # 截糧的 {地點}、護糧的 {起點}、打擊時人物的所在
    start: str | None = None  # 護糧的 {起點}
    end: str | None = None  # 護糧的 {終點}
    figure: str | None = None  # 打擊的 {人物}
    quota: int
    text: str
    progress: dict[str, int] = Field(default_factory=dict)  # 名號 → 做了幾次
    shown: dict[str, str] = Field(default_factory=dict)  # 名號 → 軍情寫的名字（現在一律是名號；這一版之前匿名的記成「某位少俠」）
    done: bool = False
    done_time: float | None = None
    applied: int = 0


class Bounty(BaseModel):
    """懸賞榜上的一張（bounties.py；PM 2026-10-08 派工「加強散人玩法」）。陣營的每週一自動掛（討伐、打探、護送），
    玩家花銀兩掛的是通緝（wanted：懸賞一個敵對陣營的人，接了的人照截殺的規則打他）。前 quota 個完成的人各拿一份賞
    （通緝只有一份）；接了還沒完成的記在 takers。求藝（art）、求兵（arms）是劇本的每個陣營每週一掛的，不用揭、在懸賞榜上直接交
    （懸賞榜設計第四節）：location、end、squad、takers 都不用。"""

    id: str
    kind: str  # "strike" 討伐、"scout" 打探、"escort" 護送、"wanted" 通緝、"art" 求藝、"arms" 求兵
    faction: str | None  # 掛單的陣營（通緝是掛單人的陣營）；散人兩邊都能接，陣營的人只能接自己陣營的
    week: int  # 掛出來的那一週（季曆）
    expires: float  # 世界秒：過了就下榜、不能揭（通緝沒人完成時把押金退給掛單的人）；過期但還有人揭著的留到他們同步（deliver_lapses）
    silver: int
    deeds: int  # 完成時給散人的俠名（ranger.add_deeds）
    quota: int = 1
    location: str | None = None  # 討伐：對手所在；打探：要去探索的地方；護送：起點（在這裡接）
    end: str | None = None  # 護送的終點
    squad: str | None = None  # 討伐的對手（Squad.id）
    attribute: str | None = None  # 求藝、求兵要的屬性（Config.bounties.give_attributes）
    weapon_kind: str | None = None  # 求兵要的兵器種類（models.WEAPON_KINDS）
    poster: str | None = None  # 通緝：掛單人的名號
    target: str | None = None  # 通緝：要打的人的名號
    takers: list[str] = Field(default_factory=list)  # 接了、還沒完成的名號
    done_by: list[str] = Field(default_factory=list)
    refunded: bool = False  # 通緝下榜時押金退過了
    # 重賞（裝備四欄 6.4）：週一掛單時擲中的「寶物一件」或「良駒一匹」，只給第一個交差的人；哪一件到交差時才定（treasures.bounty_prize）
    prize: Literal["treasure", "horse"] | None = None


class Invite(BaseModel):
    """玩家向同一地點的另一個玩家發的邀請（invites.py；玩家互動第二層）。payload 是這一種邀請自己要的東西（論武雙方出的武學或意境）。"""

    id: str
    kind: str  # "spar"（切磋）、"discuss"（論武）、"travel"（結伴同行）、"greet"（打招呼，payload 的 gesture 是哪一種禮節）
    sender: str  # 名號（身分）
    target: str
    location: str  # 發邀請時兩人所在的地點 id；接受時兩人都還要在這裡
    sent_at: float  # 世界秒
    expires_at: float
    payload: dict[str, str] = Field(default_factory=dict)


class Echo(BaseModel):
    """一門首創的武學或意境，這一季照著合出來的人（首創名望回饋，Config.first_echo）。名望由首創者自己的 Game 在同步時補
    （paid 記補到第幾個人），合的那一下不去動別人的角色。"""

    creator: str  # 首創者的名號（身分）
    co_creator: str | None = None  # 論武合出來的：另一個首創者（名望一樣補給他，補到第幾個人記在 co_paid）
    name: str  # 寫給首創者看的名字，連括號（武學【】、意境「」），合出來那一刻的顯示名字
    followers: list[str] = Field(default_factory=list)  # 照著合出來的人，一人只算一次，最多 first_echo.cap 個
    paid: int = 0  # 已經補給首創者的人數
    co_paid: int = 0  # 已經補給 co_creator 的人數
    made: str = "練"  # 照著做出來的動詞：武學、意境是「練」，兵器配方是「打」（smithing.forge）


class SignatureClaim(BaseModel):
    """一把名將本命兵器這一季給了誰（兵器設計 4.10；WorldState.signature_arms）：owner 是名號（身分，也是寫給人看的名字），
    via 是怎麼拿到的：gift 情誼到了他送的、seized 打贏他本人幾次他讓你奪走的。"""

    owner: str
    via: Literal["gift", "seized"]


class TerritoryWeek(BaseModel):
    """地盤某一週的樣子（輿圖升級設計第九節）：那一週最後一次重算時的控制方、每條戰線拔河看的值、割據（沒有這條線是 None）。"""

    control: dict[str, str] = Field(default_factory=dict)
    fronts: dict[str, int] = Field(default_factory=dict)
    geju: int | None = None


class TerritoryState(BaseModel):
    """這一季的地盤（tianxia/territory.py）：WorldState.territory；None＝這一季還沒算過（開季、舊存檔、中途上線）。"""

    control: dict[str, str] = Field(default_factory=dict)  # 地點 → 此刻的控制方（大本營、固定的地點、可易手的地點）
    tug: dict[str, str] = Field(default_factory=dict)  # 可易手的地點 → 拔河算出的那一方（±band 不動看它）
    geju: list[str] = Field(default_factory=list)  # 豪強割據佔著的地點，照佔下的先後
    pinned: dict[str, str] = Field(default_factory=dict)  # 大事指定的地點 → 指定那一刻規則算出的控制方（規則改變那一刻才回到規則）
    held: dict[str, list[str]] = Field(default_factory=dict)  # 地點 → 這一季佔過它的各方（照先後）：再拿回來寫「收復」（FB-252）
    # 週次 → 那一週的樣子（territory._snapshot：每次重算蓋掉這一週那一格，所以一週結束時就是週末的樣子）；沒記到的週照前一週補
    # （territory.week_at）；新的一季是新的 WorldState，自然是空的（輿圖升級設計第九節）。0 是開季那一刻（territory.START_WEEK，
    # 這一季第一次算地盤就在第 1 週時才有，FB-264）
    weeks: dict[int, TerritoryWeek] = Field(default_factory=dict)


class WorldState(BaseModel):
    time: float = 0.0  # 賽季開始後經過的遊戲秒數
    trends: dict[str, int] = Field(default_factory=dict)
    revealed: set[str] = Field(default_factory=set)
    flags: set[str] = Field(default_factory=set)
    flag_times: dict[str, float] = Field(default_factory=dict)  # 世界旗標第一次成立的遊戲時間
    fired_thresholds: set[str] = Field(default_factory=set)
    rumors: list[Rumor] = Field(default_factory=list)
    chronicle: list[Rumor] = Field(default_factory=list)
    sim_accum: float = 0.0  # 累積但還不滿一小時的時間，給虛擬玩家用
    ended: bool = False
    ending_title: str = ""
    ending_text: str = ""
    ending_id: str = ""  # 收季時的結局 id（Ending.id）；舊存檔是空的
    # 第一季的結算畫面（計畫 T9）：收季那一刻的戰況（顯示中的每條線）與各陣營出力前五（名號, 貢獻；排行榜不能匿名）
    final_trends: dict[str, int] = Field(default_factory=dict)
    final_rankings: dict[str, list[tuple[str, int]]] = Field(default_factory=dict)
    storyline: str = ""  # 目前主線 id
    act: int = 0  # 目前第幾幕（從 0 起算）
    act_reached: int = 0  # 本季到過的最遠一幕；主線改寫會把 act 歸零，隊伍數與統御上限看這個（見 roster.stage）
    marks: dict[str, int] = Field(default_factory=dict)  # 地方痕跡：「地點 id:痕跡名」→ 累積次數（全服共用，換季整個重來）
    pending_battle: str | None = None  # 背景推進跨過開戰門檻時記下要開的戰鬥 id；那時人在 mutate_season 的
    # callback 裡，不能再 mutate 開戰（巢狀的 mutate 內層寫的會被蓋掉，會丟錯），callback 結束後由
    # world.start_pending_battle 開戰並清掉
    # ── 開季時蓋的章（計畫 T2「舊季不會被補算」）：world_state.stamp_season 照當下的 Config 寫入——種季、換季時蓋，
    # 籌備中的季在管理者開季時再蓋一次（第一次啟動忘了設 TIANXIA_PROFILE 也救得回來）──
    # 開關打開時還在跑的舊季照它自己的章走：不跑季曆與時刻表，也不會因為設定的季長變短就一口氣收掉。
    season_one: bool = False  # 這一季開季時第一季濃縮版的規則是不是開著
    haoqiang_allied: bool = False  # 這一季開季時豪強分屬兩軍是不是開著（allied.on 還要第一季的章）；舊季讀檔是 False
    length_days: float | None = None  # 這一季的長度（遊戲日）；None＝T2 之前開的季，一律照 models.DEFAULT_SEASON_DAYS（FB-037）
    # ── 時刻表（計畫 T2；鎖定、搶輸、豪強、一般伏筆修正由 T7 寫入）──
    timeline: dict[str, TimelineResult] = Field(default_factory=dict)  # 大事 id → 結算結果（有就不再結算）
    locks: dict[str, Lock] = Field(default_factory=dict)  # 大事 id → 第一個做完關鍵伏筆的人
    lock_losers: dict[str, list[Lock]] = Field(default_factory=dict)  # 大事 id → 之後才做完的人
    third_party: dict[str, list[str]] = Field(default_factory=dict)  # 大事 id → 做完豪強伏筆的名號（真名）
    # 大事 id → {名號: 公告寫的名字}：這一版之前做完時匿名的豪強（「某位少俠」）；現在不再記，沒記的照名號寫
    third_party_shown: dict[str, dict[str, str]] = Field(default_factory=dict)
    event_mods: dict[str, float] = Field(default_factory=dict)  # 大事 id → 一般伏筆、軍令的成功率修正（合計夾在 ±0.20）
    event_bonus: dict[str, float] = Field(default_factory=dict)  # 大事 id → 時刻表結果帶來的修正（例：波才北上，不夾）
    schedule: dict[str, float] = Field(default_factory=dict)  # 決戰 id 與 "finale" → 世界秒；開季時填預設、管理者可改
    mandate: bool = False  # 天命之季（玉璽碎片設計 8.1；換季時由 seal.stamp_mandate 蓋，季的規則看它）
    mandate_result: str | None = None  # 天命之爭得天命的那一軍；"" 是天命未定；None 是還沒定（季末看它，world.evaluate_ending）
    hooked_week: int = 0  # 週初的掛鉤（world.WEEK_HOOKS）已經跑到第幾週；0＝還沒跑過
    # ── 時刻表決戰開集結（計畫 T8）：季的事在 mutate 裡只記號，mutate 外面才開（world.open_waiting_showdown）──
    showdowns_waiting: list[str] = Field(default_factory=list)  # 時間到了、還沒開成的決戰 id，照時間先後（另一場還在打就等）
    showdowns_opened: dict[str, str] = Field(default_factory=dict)  # 開過集結的決戰 id → 開的那一筆 BattleDef；開過就不再開
    figures: dict[str, FigureState] = Field(default_factory=dict)  # 大勢人物 id → 聲威、狀態、所在（T4：第一季開季時種；其他季第一次被打贏才寫，沒被打過的照人物表讀）
    orders: list[Order] = Field(default_factory=list)  # 陣營軍令（計畫 T6）：這一週的，加上之前達成的
    plots: list[Plot] = Field(default_factory=list)  # 集體密謀（正式版乙二）：發起的、做完的、作罷的都留著到季末（編號是雜湊，見 Plot.id）
    # 升第 2 階的每日彙整（計畫 T5）：「曆日:陣營:階」→ 名號（陣營軍情一律具名）；過了那個曆日由季的事發成一則陣營軍情（傳聞只能新增，不能改）
    promoted_today: dict[str, list[str]] = Field(default_factory=dict)
    # ── 推力規則（計畫 T3）──
    trend_accum: dict[str, float] = Field(default_factory=dict)  # 不足一點的推力（全服共用，滿一點才真的推；正負會抵銷）：大勢線 id、"geju"、"fig:<人物 id>"（大勢人物每天的推動）、"prestige:<人物 id>"（挑戰打贏扣聲威不足一點的部分）、"regen:<人物 id>"（沒有時刻表的季聲威回復不足一點的部分）、"lost:<人物 id>:<遊戲日>"（沒有時刻表的季這一天被打掉了多少，一天上限用）
    active_pushers: dict[str, dict[str, float]] = Field(default_factory=dict)  # 陣營 id → 名號 → 最後一次推大勢的世界秒（人數緩衝用，過期的順手清掉）
    bounties: list[Bounty] = Field(default_factory=list)  # 懸賞榜（bounties.py）：陣營掛的還沒過期的單、還沒退押金的通緝，加上過期但還有人揭著的（留到他們同步，deliver_lapses）；換季整個重來
    bounty_seq: int = 0  # 懸賞的流水號
    # 陣營的軍備（素材與經濟設計第六節第 3 點；economy.donate）：陣營 id → 素材屬性（慢、快、剛、柔）→ 累積的份量（一階 1、二階 3、三階 9）。
    # 名字照 Config.economy.armaments（慢 → 糧秣……）。這一季的；在決戰怎麼起作用還沒定（跟 joy 對，第 2 塊），先只存
    armaments: dict[str, dict[str, int]] = Field(default_factory=dict)
    # 自動掛單已經掛到第幾週（季曆；bounties.issue 的第二道擋）：第一季那一條（WEEK_HOOKS，照 hooked_week）與規則關著的季那一條
    # （bounties.tick）都直接叫 issue，同一週叫幾次都只掛一次。不借 hooked_week：規則關著的季它一直是 0（懸賞榜設計 3.2）
    bounty_week: int = 0
    invites: list[Invite] = Field(default_factory=list)  # 玩家之間還在等回覆的邀請（invites.py；換季整個重來）
    spar_tally: dict[str, list[int]] = Field(default_factory=dict)  # 切磋的每日次數：「名號鍵|名號鍵」（排序）→ [遊戲日, 次數]
    gift_tally: dict[str, list[int]] = Field(default_factory=dict)  # 贈物的每日次數（FB-116）：同 spar_tally，不分誰送誰
    discuss_tally: dict[str, list[int]] = Field(default_factory=dict)  # 論武的每日次數（FB-116）：同 spar_tally
    # 截殺（Config.raid）：「發起的名號鍵>目標的名號鍵」→ 上一次截殺的世界秒（同一個人對同一個目標的冷卻）；
    # 目標的名號鍵 → 上一次被截殺的世界秒（被截殺過的人一陣子之內誰都不能再截殺他）。換季整個重來
    raids: dict[str, float] = Field(default_factory=dict)
    raided: dict[str, float] = Field(default_factory=dict)
    echoes: dict[str, Echo] = Field(default_factory=dict)  # 首創的武學或意境 id → 這一季照著合出來的人（Config.first_echo；換季整個重來）
    # ── 第四階席次（第一季設計 5.4；正式版丁）。週一的掛鉤讀不到別人的存檔，所以有資格的人每次行動、同步時把自己每週的貢獻抄一份到
    # 這裡（seats.report）；插入順序＝拿到資格的先後（同分時先拿到的優先）。陣營私有，跟 orders、plots 一樣不進推送指紋 ──
    seat_ledger: dict[str, dict[str, dict[int, int]]] = Field(default_factory=dict)  # 陣營 id → 名號 → {季曆週：那一週的貢獻}
    seats: dict[str, list[str]] = Field(default_factory=dict)  # 陣營 id → 這一週在任的名號
    # ── 裝備三（裝備四欄設計第六節）──
    # 名將贈禮給了誰：人物 id → 名號（6.4：每位名將每季全服只送一人；換季整個重來）。跟懸賞榜第二批的求藝送兵器（bounty-gift）、
    # 玩家之間的贈物無關，所以不叫 gifts
    general_gifts: dict[str, str] = Field(default_factory=dict)
    # 名將本命兵器給了誰：人物 id → SignatureClaim（兵器設計 4.10：每位名將每季全服一人；換季整個重來）。神器譜跨季讀 seasons 表
    # 的這一欄（WorldStateStore.signature_records），所以舊季的也留著
    signature_arms: dict[str, SignatureClaim] = Field(default_factory=dict)
    # 這一季的天機（SharedWorldState.tianji 在開季、換季時蓋進來，sqlite_world.open_season／next_season）：週初掛單的重賞亂數用（6.4），
    # bounties.issue 只拿得到季、讀不到全服那一列。功能上線前開的季是 0
    tianji: int = 0
    # 素材與經濟（企劃者 2026-10-15）：開季時照 Config.forge_secrets 蓋的章（world_state.stamp_season）；舊季沒有這兩欄＝False（照舊）
    forge_divine_per_kind: bool = False  # 神器配方每種兵器一季最多一條（forge_secrets.active）
    forge_split_clues: bool = False  # 神器配方的線索拆三片（forge_secrets.hear、hear_smith、view）
    territory: TerritoryState | None = None  # 地盤易手（出陣探索與地盤設計第四節）；None＝還沒算過
    # ── 擂台賽（tianxia/arena.py；換季整個重來）──
    arena: dict[str, ArenaEntry] = Field(default_factory=dict)  # 名號鍵 → 守擂的人
    arena_pairs: dict[str, float] = Field(default_factory=dict)  # 「挑的名號鍵>守的名號鍵」→ 上一次挑的世界秒（冷卻）
    arena_seq: int = 0  # 這一季開過幾場擂台
    arena_closed: bool = False  # 季末前三名排過了（world.end_season）
    arena_day: int = -1  # 擂台的俸發到哪一天（現實的第幾天，arena.roll_day）；-1＝還沒看過


class Fighter(BaseModel):
    name: str
    level: int


class LevelUps(BaseModel):
    """一場打完升級的人（FB-074）：「剛剛」的戰鬥卡片拿它畫一行簡短的「升到第 N 級」（battlelog.levelup_line），
    戰報頁與江湖紀錄照舊寫完整的句子。誰升到第幾級是結構化存下來的，不從句子的字裡讀回來。"""

    you: int | None = None  # 本人最後升到第幾級；本人沒升級是 None
    points: int = 0  # 本人升級之後還沒配的屬性點總數（那一刻的；畫卡片時改用現在的，見 levelup_line）
    mates: list[tuple[str, int]] = Field(default_factory=list)  # 升級的同伴（名字，最後升到第幾級），照隊伍順序
    lines: list[str] = Field(default_factory=list)  # 這一場寫進 notes 的升級句子原文（卡片不再重複，戰報頁照舊寫）


class BattleRecord(BaseModel):
    """一場遭遇/劇情戰的紀錄（sanguo-companions 合併重寫：單次判定，取代舊的逐回合戰報，
    見 tianxia/encounter.py）。kind 是 showdown 的是全服決戰補送給參戰者的那一筆（FB-027）：沒有我方威力與
    對手難度（記 0），tier 是決戰的結果（例如「官軍大勝」），side 是自己站的那一邊，見 battlelog 的畫法。"""

    id: int  # 流水號，本季從 1 起算
    time: float  # 開打時的遊戲時間（決戰是收場時的）
    location: str  # 地點名稱（決戰是大區名；上一季打的前面加「第 N 季・」）
    kind: Literal["train", "event", "wild", "showdown", "spar", "raid", "duel", "seal", "arena", "sortie"]  # 遊歷／劇情／探索撞上的野怪／全服決戰／跟玩家切磋／截殺（發起或被截殺）／頭目戰／奪璽單挑（玉璽碎片設計 5.9）／出陣（出陣探索與地盤設計；舊戰報的 train 照舊顯示「遊歷」，不遷移）
    event: str = ""  # 劇情戰的事件標題；決戰是決戰的名稱
    opponent: str  # 敵方隊伍名稱；決戰是敵方陣營名
    ours: list[Fighter]  # 我方陣容，第一位是隊長；等級是開打時的等級（決戰不記，是空的）
    tier: str  # 大勝/險勝/僵持/落敗（encounter.EncounterResult.tier）；決戰是結果的標題
    our_power: float
    difficulty: float
    side: str = ""  # 決戰時自己站的陣營名；其他 kind 是空字串
    exp: int = 0  # 每人獲得的經驗
    xinde: int = 0
    silver: int = 0  # 正數為獲得、負數為失落
    materials: list[str] = Field(default_factory=list)  # 這一戰掉落的素材，已經是「精鐵砂 ×1」這樣的句子
    notes: list[str] = Field(default_factory=list)  # 敘事文字：選項效果、升級、拜師、傳聞等（不是數字，見 changes）
    changes: list[str] = Field(default_factory=list)  # 其他數值變化，如屬性、名望、善惡名（經驗／心得／銀兩已有專屬欄位）
    rounds: list[str] = Field(default_factory=list)  # 回合演出，一回合一行（武學與成長設計 8.2）；決戰與舊戰報是空的
    # 大場面模型寫的過程（武學與成長設計 8.3）：照結果挑佔上風或落下風那一版；有就取代範本句子的回合（rounds 照樣算好）。
    # 叫 narration 不叫 story：battlelog 的 story_text／_story_block 已經是「結果」那一段（計畫三 G11）
    narration: str = ""
    guarded: bool = False  # 護命把落敗改判成僵持（武學與成長設計 13.4）；那一句演出寫在 notes 裡（跟 DODGE_NOTE 一樣，結果那一段）
    gauge: dict | None = None  # 決戰收場那一刻的戰局條（battle_instance.gauge，站在自己那一邊看）；不是決戰、舊戰報是 None
    # 功效的演出句（13.6，content/trait_lines.json）：一句一行、前面標〔功效名〕，只在功效真的改到結果時才有（engine.Game._trait_lines）。
    # 放在「過程」裡回合（或大場面模型那一段）的前與後
    trait_before: list[str] = Field(default_factory=list)  # 開打前：先手、穩、破甲、險、連環、借力
    trait_after: list[str] = Field(default_factory=list)  # 受傷、結果出來、戰鬥外：化勁、厚、不動、乘勝、吸取、悟招、回春、輕身
    levelups: LevelUps | None = None  # 這一場有人升級才有（FB-074）；舊戰報沒有，卡片照 notes 原文
    # 決戰的完整戰況（Joy 2026-10-14「決戰能不能把完整戰報在戰報那邊可以展開」）：一回合一段的 Markdown（「##### 第 N 回合」加清單，
    # 照先後；Game._round_blocks 收場時快照，每一段最後一條是自己出了什麼）。不是決戰、舊戰報是空的
    log: list[str] = Field(default_factory=list)
    battle_ref: int | None = None  # 決戰是資料庫裡那一場的流水號（BattleInstance.record_id）：戰報頁照它重讀完整戰況、補回被洗掉的戰報認它；其他是 None


class JournalEntry(BaseModel):
    """江湖紀錄的一則：玩家的一次行動，整理成給畫面看的樣子（原始訊息仍照舊寫在 GameState.log）。"""

    time: float  # 行動時的遊戲時間；舊存檔轉來的紀錄沒有時間，記為 journal.LEGACY_TIME
    title: str  # 例如「前往 揚州城」「遊歷・揚州城郊」「酒樓鬥毆・上前勸架」
    tag: str = ""  # 簡短的結果，例如「遇上【酒樓鬥毆】」「擊退劫道山賊（4 回合）」「韓鐵出手・失敗」
    lines: list[str] = Field(default_factory=list)  # 敘事文字
    changes: list[str] = Field(default_factory=list)  # 數值變化，例如「銀兩 -5」「心得 +12」
    battle_id: int | None = None  # 這次行動打的那一場（BattleRecord.id）
    # 這次行動順便完成的新手引導（「✔ 引導完成」、獎勵、說書人的下一步）：江湖紀錄的列表照舊畫，「剛剛」卡片不畫——
    # 說書人的話改在行動列上方的對話框（引導重做設計 8.1）
    guide: list[str] = Field(default_factory=list)
    glyph: list[list[int]] = Field(default_factory=list)  # 有所感畫的那一筆（0～100 的點位）：紀錄裡畫一張小縮圖；舊紀錄沒有


class GameState(BaseModel):
    player: PlayerState
    # 共用賽季：只在記憶體裡，不進角色存檔（線上架構設計 3.1）。Game 建構與每次 sync 都把它指向全服狀態裡的
    # 那一份（Game._reconcile_season）；舊存檔裡夾帶的 world 讀得進來，但隨即被取代。
    world: WorldState = Field(default_factory=WorldState, exclude=True)
    pending_event: str | None = None
    battles: list[BattleRecord] = Field(default_factory=list)  # 最近的戰鬥紀錄，最新的在前
    battle_seq: int = 0  # 最近一場戰鬥的流水號
    battle_card: int | None = None  # 場景裡顯示卡片的那一場；下一次行動時清掉
    log: list[str] = Field(default_factory=list)  # 原始訊息，每次行動之間夾一個 journal.LOG_BREAK
    journal: list[JournalEntry] = Field(default_factory=list)  # 江湖紀錄，最新的在前，最多 journal.MAX_ENTRIES 則
    last_real: float | None = None  # 上次同步的現實時間（time.time()）
    # 上次同步時的賽季時間（世界秒）：「你不在的時候」從這一刻之後算（Game._deliver_away）。None＝還沒記過（舊存檔、
    # 換季重來的角色），那一次從這一季開頭算
    last_world: float | None = None


def new_game_state(content: Content, name: str) -> GameState:
    """同伴全服唯一（設計文件四.4），開局不再自動塞給玩家任何一位——每個新玩家都是孤身
    一人起步，招募是要在遊戲裡真的去搶的行動，不是開局贈品（不然「唯一」第一時間就矛盾：
    每個新玩家都自動擁有同一位歷史人物是不可能的）。

    開局送 `Config.starter_skills` 的兩門基礎武學（第一成），新角色與每季重來的角色都一樣
    （武學與成長設計 3.3；自創武學已經作廢，沒有空欄位要自己取名）。"""
    from .rules import seed_trends  # rules → state：在函式裡 import，避免循環

    cfg = content.config
    player = PlayerState(
        name=name,
        location=content.scenario.start_location,
        stats=dict(cfg.start_stats),
        stamina=float(cfg.stamina_max),
        tutorial_step=0,
        # 有序章的內容才蓋新引導的章（新手引導計畫一）：沒有序章時步數還是舊編號，先蓋章會讓序章上線後的舊存檔跳過換算
        onboarding=ONBOARDING_VERSION if content.tutorial.location is not None else 0,
        member=Member(),
        joined_at=None,  # 第一次同步補算完賽季才蓋（Game._stamp_join）
    )
    for skill_id in cfg.starter_skills:  # 開局送的基礎內功、基礎武學（武學與成長設計 3.3）
        slot = "neigong_id" if content.skills[skill_id].kind == "內功" else "wugong_id"
        setattr(player.member, slot, skill_id)
    world = WorldState(storyline=content.scenario.storylines[0].id)
    seed_trends(world, content)
    return GameState(player=player, world=world)
