"""伺服器假人的身分、個性與作息（伺服器假人設計第五、六節）：純資料與純函式，不讀寫檔案。

假人的名號從漢末常見的姓氏與名字用字組出來；個性決定每天上線多久、在線時多久做一個動作、
戰鬥集結時多常趕來、挑選項時比總強度旋鈕高或低多少。作息由假人自己的種子算出來，同一個
假人每天大致同一個時段上線（台灣時間）。
"""
from __future__ import annotations

import random
from dataclasses import dataclass

from .models import Config
from .state import BotProfile, Personality

DAY = 86400
TZ_OFFSET = 8 * 3600  # 作息照台灣時間（UTC+8）

SURNAMES = (
    "王李張劉陳楊趙黃周吳徐孫朱高林何郭馬羅梁宋鄭謝韓唐馮董蕭程袁鄧許傅沈曾彭呂蘇盧蔣蔡賈丁魏薛葉"
    "閻潘杜戴夏鍾田任姜范方石姚譚廖鄒熊陸孔崔邱秦顧侯邵孟段雷湯尹常龐"
)
GIVEN = (
    "文武德仁義禮智信忠孝勇毅恭寬敏惠廣遠明亮昭彰元伯仲叔季子公長平安和順康泰興隆昌盛"
    "雲山海川林松柏竹梅蘭石玉金鐵鋒剛強威猛虎豹鳳鵬雁鴻飛翔騰躍超越登峻嶽峰岳巖"
    "清澄淵澤濟濤浩洪源淳潤滿盈豐茂榮華英俊傑豪雄偉卓群翼輔弼佐佑贊襄承繼紹嗣先宗"
    "敬肅莊端正直方圓良善淑賢彥彬斌璋瑾瑜琰琮璧珪珣琦瓊瑤懷思念志謀略韜策計籌度量"
)
SKILL_PREFIXES = (
    "青松", "流雲", "斷岳", "驚鴻", "寒江", "落霞", "孤鴻", "飛雪", "長風", "破陣", "蒼龍", "赤霄", "玄冰", "烈陽",
    "歸元", "太初", "回風", "碧濤", "鐵騎", "白虹", "紫電", "鎮山", "穿雲", "摧城", "追月", "奔雷", "鳴鏑", "照膽",
)
SKILL_SUFFIXES = {
    "內功": ("訣", "功", "心經", "真氣", "吐納法"),
    "武學": ("拳", "掌", "劍法", "刀法", "槍法", "腿法", "戟法"),
}


@dataclass(frozen=True)
class Temper:
    windows: tuple[int, ...]  # 每天幾段上線（從中挑一個，種子固定）
    window_minutes: tuple[int, int]  # 每段多長（分鐘）的範圍
    action_seconds: float  # 在線時平均多久做一個動作
    attend: float  # 戰鬥集結時趕來的機率
    strength_bonus: float  # 加在 bot_strength 上
    skip_day: float  # 某一天整天不上線的機率


TEMPERS: dict[Personality, Temper] = {
    "積極": Temper(windows=(2,), window_minutes=(120, 150), action_seconds=60, attend=0.9, strength_bonus=0.2, skip_day=0.0),
    "普通": Temper(windows=(1, 2), window_minutes=(70, 100), action_seconds=120, attend=0.6, strength_bonus=0.0, skip_day=0.0),
    "懶散": Temper(windows=(1,), window_minutes=(50, 70), action_seconds=180, attend=0.3, strength_bonus=-0.2, skip_day=0.5),
}
PERSONALITY_WEIGHTS: dict[Personality, int] = {"積極": 20, "普通": 50, "懶散": 30}


def pick_personality(rng: random.Random) -> Personality:
    return rng.choices(list(PERSONALITY_WEIGHTS), weights=list(PERSONALITY_WEIGHTS.values()), k=1)[0]


def make_name(rng: random.Random, taken: set[str]) -> str:
    """漢末風格的名號（單名、雙名各半），不跟 taken 裡的任何名字重複。"""
    for _ in range(1000):
        given = rng.choice(GIVEN) if rng.random() < 0.5 else rng.choice(GIVEN) + rng.choice(GIVEN)
        name = rng.choice(SURNAMES) + given
        if name not in taken:
            return name
    raise RuntimeError("名號字庫用完了")


def make_skill_name(rng: random.Random, kind: str) -> str:
    """假人自創功法的名字：看起來跟真人取的一樣（不能是「內功123」這種一看就是程式取的名字）。"""
    return rng.choice(SKILL_PREFIXES) + rng.choice(SKILL_SUFFIXES[kind])


def schedule(profile: BotProfile) -> list[tuple[int, int]]:
    """每天的上線時段（台灣時間，從午夜起算的分鐘數，[開始, 結束)），同一個假人永遠一樣。
    第一段在晚上 19～24 點之間，第二段（有的話）在中午 11:30～13:00 開始。"""
    temper = TEMPERS[profile.personality]
    rng = random.Random(profile.seed)
    spans: list[tuple[int, int]] = []
    for i in range(rng.choice(temper.windows)):
        length = rng.randint(*temper.window_minutes)
        start = rng.randint(19 * 60, 24 * 60 - length) if i == 0 else rng.randint(11 * 60 + 30, 13 * 60)
        spans.append((start, start + length))
    return spans


def is_online(profile: BotProfile, now: float) -> bool:
    """照作息，這一刻在不在線（懶散的假人有一半的日子整天不上線）。"""
    temper = TEMPERS[profile.personality]
    local = now + TZ_OFFSET
    day = int(local // DAY)
    if temper.skip_day and random.Random(f"{profile.seed}|day|{day}").random() < temper.skip_day:
        return False
    minute = int(local % DAY // 60)
    return any(start <= minute < end for start, end in schedule(profile))


def attends_battle(profile: BotProfile, battle_key: float) -> bool:
    """一場戰鬥集結時，這個假人會不會趕來（不管在不在上線時段）；同一場戰鬥擲出來永遠一樣。
    battle_key 用那場戰鬥的集結截止時間。"""
    roll = random.Random(f"{profile.seed}|battle|{int(battle_key)}").random()
    return roll < TEMPERS[profile.personality].attend


def act_chance(profile: BotProfile, config: Config) -> float:
    """在線時，這一輪做一個動作的機率：巡邏間隔 ÷ 動作間隔。"""
    return min(1.0, config.bot_tick_seconds / TEMPERS[profile.personality].action_seconds)


def strength(config: Config, profile: BotProfile) -> float:
    """這個假人挑最高分選項的機率：總強度旋鈕加上個性的加減，限制在 0～1。"""
    return max(0.0, min(1.0, config.bot_strength + TEMPERS[profile.personality].strength_bonus))


def active(profile: BotProfile, season_number: int) -> bool:
    """這一季被叫醒、替某個陣營效力中（不是退隱）。"""
    return profile.faction is not None and profile.season_number == season_number
