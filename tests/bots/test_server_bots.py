import random
from collections import Counter

import pytest

from tianxia.models import Config
from tianxia import server_bots
from tianxia.server_bots import (
    DAY, GIVEN, SURNAMES, TZ_OFFSET, act_chance, active, attends_battle, is_online, make_name,
    pick_personality, reserved_names, schedule, strength,
)
from tianxia.state import BotProfile
import re
from pathlib import Path


def _bot(personality="普通", seed=7, faction="guan", season_number=1):
    return BotProfile(personality=personality, seed=seed, faction=faction, season_number=season_number)


def _at(minute_of_day: int, day: int = 20000) -> float:
    """台灣時間第 day 天的第 minute_of_day 分鐘，換成現實時間戳。"""
    return day * DAY + minute_of_day * 60 - TZ_OFFSET


def test_reserved_names_cover_famous_people_figures_in_the_content_and_admins(content):
    content.config.admins = ["掌門"]
    reserved = reserved_names(content)
    assert "曹操" in reserved and "張角" in reserved  # 三國名人
    assert all(ch.name in reserved for ch in content.characters.values())  # 遊戲裡的人物，跟著內容走
    assert "掌門" in reserved


def test_names_look_like_han_names_and_avoid_taken_ones():
    first = make_name(random.Random(1), set())
    assert 2 <= len(first) <= 3 and first[0] in SURNAMES and all(ch in GIVEN for ch in first[1:])
    assert make_name(random.Random(1), {first}) != first


class _Scripted(random.Random):
    """照劇本抽字：random() 永遠抽到單名，choice() 依序拿 picks 裡的字（先名、後姓）。"""

    def __init__(self, picks):
        super().__init__(0)
        self.picks = list(picks)

    def random(self):
        return 0.0

    def choice(self, seq):
        pick = self.picks.pop(0)
        assert pick in seq
        return pick


@pytest.mark.smoke
def test_names_never_match_a_famous_three_kingdoms_figure():
    """字庫組得出趙雲、周瑜、馬超這種名人；抽到了就重抽，假人不能頂著名人的名號。"""
    assert make_name(_Scripted(["雲", "趙", "雲", "陳"]), set()) == "陳雲"
    assert make_name(_Scripted(["瑜", "周", "超", "馬", "瑜", "林"]), set()) == "林瑜"
    assert {"趙雲", "周瑜", "馬超"} <= server_bots.FAMOUS_NAMES


def test_personalities_follow_the_twenty_fifty_thirty_split():
    rng = random.Random(0)
    counts = Counter(pick_personality(rng) for _ in range(10000))
    assert abs(counts["積極"] / 10000 - 0.2) < 0.03
    assert abs(counts["普通"] / 10000 - 0.5) < 0.03
    assert abs(counts["懶散"] / 10000 - 0.3) < 0.03


def test_the_same_bot_always_has_the_same_schedule_and_it_fits_its_temper():
    eager = _bot("積極", seed=11)
    assert schedule(eager) == schedule(_bot("積極", seed=11))
    total = sum(end - start for start, end in schedule(eager))
    assert 240 <= total <= 300
    for start, end in schedule(eager):
        assert 11 * 60 + 30 <= start < end <= 24 * 60


def test_each_temper_keeps_its_daily_total_and_its_windows_inside_waking_hours():
    ranges = {"積極": (240, 300), "普通": (120, 180), "懶散": (50, 70)}
    window_counts = Counter()
    for personality, (low, high) in ranges.items():
        for seed in range(200):
            spans = schedule(_bot(personality, seed=seed))
            assert low <= sum(end - start for start, end in spans) <= high
            for start, end in spans:
                assert 11 * 60 + 30 <= start < end <= 24 * 60
            window_counts[personality, len(spans)] += 1
    assert window_counts["普通", 1] > 0 and window_counts["普通", 2] > 0  # 一到兩段都有


def test_a_bot_is_online_only_inside_its_windows():
    eager = _bot("積極", seed=11)
    start, end = schedule(eager)[0]
    assert is_online(eager, _at(start))
    assert not is_online(eager, _at(4 * 60))  # 凌晨四點


def test_a_lazy_bot_skips_about_half_of_the_days():
    lazy = _bot("懶散", seed=5)
    start, _ = schedule(lazy)[0]
    online_days = sum(is_online(lazy, _at(start, day)) for day in range(20000, 20200))
    assert 70 <= online_days <= 130


def test_turning_up_for_a_battle_is_reproducible_and_follows_the_temper():
    eager = _bot("積極", seed=3)
    assert attends_battle(eager, 123.0) == attends_battle(eager, 123.0)
    shows = sum(attends_battle(eager, float(key)) for key in range(1000))
    assert 850 <= shows <= 950


def test_act_chance_and_strength():
    config = Config(bot_tick_seconds=20, bot_strength=0.9)
    assert act_chance(_bot("普通"), config) == 20 / 120
    assert strength(config, _bot("積極")) == 1.0
    assert strength(Config(bot_strength=0.1), _bot("懶散")) == 0.0
    assert strength(Config(bot_strength=0.6), _bot("普通")) == 0.6


def test_a_bot_is_active_only_when_woken_for_this_season():
    assert active(_bot(faction="guan", season_number=2), 2)
    assert not active(_bot(faction="guan", season_number=1), 2)
    assert not active(_bot(faction=None, season_number=2), 2)


# ── 原 test_fb673_web_no_bot_words.py（整檔搬進來） ──
# FB-673：`web/` 底下送給瀏覽器的檔（js、css、html）不准出現「假人」「機器人」「bot」。
#
# 設計是任何畫面都不透露誰是假人（伺服器假人設計）。渲染出來的頁面與 /api 回應早有測試守著，
# 但 `app.js`、`style.css` 整支隨檔送到每個玩家的瀏覽器（`/static/…`），註解與字串看原始碼的人都讀得到：
# 練功入口（FB-670）新加的一句註解寫了「假人、整季機器人不受影響」，舊的一句寫了「真人假人是同一份名單」。
# 要寫給自己看的說明放 docs 或 Python 端，網頁檔裡用中性的字（「每個角色」「名單」「模擬腳本」）。
#
# 白名單（真的有合理用途的英文字詞）：
# - `bottom`：DOM 的 `getBoundingClientRect().bottom`、CSS 的 `bottom` / `padding-bottom` / `margin-bottom`。
# - `both`：CSS 的 `animation-fill-mode: both`、`clear: both`、`scrollbar-gutter: stable both-edges`。

WEB = Path(__file__).resolve().parents[2] / "web"


# 送給瀏覽器的文字檔；圖片、影片不掃。
TEXT_SUFFIXES = {".js", ".css", ".html", ".htm", ".svg", ".json", ".txt", ".map", ".xml", ".webmanifest"}


# 「bot」不分大小寫，只放行 bottom 與 both 這兩個字（見檔頭）。
BOT_WORD = re.compile(r"bot(?!tom|h\b)", re.IGNORECASE)


FORBIDDEN = (re.compile("假人"), re.compile("機器人"), BOT_WORD)


def leaks(text: str) -> list[tuple[int, str]]:
    """(行號, 那一行裡抓到的字)；一行抓到幾個就列幾個。"""
    found: list[tuple[int, str]] = []
    for number, line in enumerate(text.splitlines(), 1):
        for pattern in FORBIDDEN:
            for hit in pattern.finditer(line):
                found.append((number, line[max(0, hit.start() - 8) : hit.end() + 8]))
    return found


def web_text_files() -> list[Path]:
    return sorted(p for p in WEB.rglob("*") if p.is_file() and p.suffix.lower() in TEXT_SUFFIXES)


def test_the_scan_sees_the_files_the_browser_gets():
    names = {p.name for p in web_text_files()}
    assert {"app.js", "style.css", "index.html"} <= names
    for name in ("app.js", "style.css", "index.html"):
        assert len((WEB / name).read_text(encoding="utf-8")) > 1000


def test_the_scan_catches_the_words_and_lets_the_css_words_through():
    # 掃描器本身要抓得到（不然「一個都沒有」可能只是掃不到）。
    assert leaks("// 假人、整季機器人不受影響")
    assert leaks("const isBot = true;")
    assert leaks("// 真人假人是同一份名單")
    assert leaks("function robotNames() {}")
    assert leaks("// BOT cap")
    # 放行的：bottom、both。
    assert not leaks("const under = bar.getBoundingClientRect().bottom + 8;")
    assert not leaks("padding-bottom: var(--bottom); animation: x 3s ease-out both;")
    assert not leaks("scrollbar-gutter: stable both-edges; clear: both; Bottom")
    # both / bottom 以外的 bot 開頭字不放行。
    assert leaks("bother")


def test_no_web_file_names_the_dummy_players():
    problems = []
    for path in web_text_files():
        text = path.read_text(encoding="utf-8")
        for number, snippet in leaks(text):
            problems.append(f"{path.relative_to(WEB.parent).as_posix()}:{number}: …{snippet}…")
    assert not problems, "web/ 的檔隨檔送到每個玩家的瀏覽器，不能出現假人、機器人、bot：\n" + "\n".join(problems)
