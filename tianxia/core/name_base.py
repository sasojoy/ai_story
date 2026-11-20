"""保留的名號（全部拆包第 58 批：server_bots 的 FAMOUS_NAMES、reserved_names 原樣搬來，server_bots re-export 同一批物件）：
建角色、易名帖（商城包 actions.rename_self）、假人取名共用的「不能拿來當名號的名字」。商城包不 import 假人的模組，改問這裡。
只讀內容與這一張名單，不寫。核心本體（tianxia/core/ 底下的檔），不進 MODULES。

另外跑：改這一個 scripts/test_for.py 照核心挑（核心測試＋煙霧，加上寫到這兩個名字的 tests/bots/test_server_bots.py、tests/figures/test_figures.py）。
本體還在 server_bots 時挑得到的 tianxia/features/mall/tests/test_mall_card_daily.py（易名帖撞保留的名號）、tests/server/test_server.py
（註冊撞保留的名號）、tests/bots/test_bot_runner.py（假人取名）挑不到了，另外跑這三個檔（第 36 批認定第 1 條，第 58 批量過）。

這一季效力中的 active（第二輪第 87 批從 server_bots 搬來，它 re-export 同一個物件）：出陣約戰補位讀它（出陣包 duel_actions.candidates），
包不 import 假人的模組。改 active 另外跑 tests/bots/test_server_bots.py、tianxia/features/sortie/tests/test_sortie_duel_bots.py、tests/bots/test_bot_runner.py。

冒充官方的字 STAFF_WORDS 與 staff_like（第 240 批）：改了另外跑 tests/core/test_identity_base.py、
tianxia/features/identity/tests/test_identity_server.py、tests/server/test_set_password.py、
tests/server/test_list_staff_like_names.py（主機的唯讀清單 scripts/list_staff_like_names.py 讀它）。
"""
from __future__ import annotations

import re
import unicodedata
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..models import Content
    from ..state import BotProfile

FAMOUS_NAMES = frozenset((  # 三國名人：server_bots 的字庫組得出其中一些（趙雲、周瑜、馬超⋯⋯），假人不能頂著這些名號
    "曹操 劉備 孫權 孫策 孫堅 關羽 張飛 趙雲 馬超 黃忠 魏延 諸葛亮 龐統 法正 姜維 周瑜 魯肅 呂蒙 陸遜 甘寧 "
    "太史慈 周泰 黃蓋 程普 韓當 呂布 高順 張遼 陳宮 貂蟬 袁紹 袁術 顏良 文醜 董卓 李傕 郭汜 華雄 馬騰 韓遂 "
    "公孫瓚 劉表 劉璋 劉焉 張魯 夏侯惇 夏侯淵 曹仁 曹洪 典韋 許褚 徐晃 張郃 于禁 樂進 李典 荀彧 荀攸 郭嘉 "
    "賈詡 程昱 司馬懿 司馬昭 鄧艾 鍾會 孟獲 華佗 左慈 于吉 張角 張寶 張梁 皇甫嵩 朱儁 盧植 何進 陶謙 王允 "
    "蔡邕 大喬 小喬 孫尚香 甄宓 關平 關興 張苞 馬岱 嚴顏 王平 廖化 糜竺 糜芳 簡雍 孫乾 徐庶 陳登 臧霸 張繡 "
    "劉禪 曹丕 曹植 曹叡 蔣琬 費禕 董允"
).split())

# identity（帳號與客服第 201 批）：舊的全等名單，擋名號改看 STAFF_WORDS／staff_like（第 240 批）；值不變，留給要列字的人讀
STAFF_NAMES = ("客服", "官方", "管理員", "GM")

# 第 240 批（企劃者 2026-11-20「現在就擋」）：名號含這些字就像在冒充官方。不進 reserved_names（假人取名與易名帖讀那一份）；
# 擋名號經 core/identity_base.blocked_name，看 Config.staff_names_on、不看帳號綁定。簡體繁體各自列，不做轉換
STAFF_WORDS = ("客服", "官方", "管理員", "管理员", "管理者", "系統", "系统", "營運", "运营", "運營", "营运")
_GM = re.compile(r"(?<![a-z])gm(?![a-z])")  # 只看 ASCII 英文字母：中文也算 alpha，用 isalpha 會放過「小美gm」


def staff_like(name: str | None) -> bool:
    """名號像不像官方（純函式，不讀設定、不查資料庫）：NFKC、casefold，只留 Unicode 類別 L、N 開頭的字（空白、標點、符號
    去掉，「客 服」「G.M」現形），含 STAFF_WORDS 任一個，或 gm 前後不接英文字母（擋 ＧＭ、小美GM；不擋 Sigmund、Dogma）。"""
    text = "".join(ch for ch in unicodedata.normalize("NFKC", name or "").casefold()
                   if unicodedata.category(ch)[0] in "LN")
    return any(word.casefold() in text for word in STAFF_WORDS) or _GM.search(text) is not None


def reserved_names(content: Content) -> frozenset[str]:
    """不能拿來當名號的名字（真人與假人共用，FB-004）：三國名人、遊戲內容裡的人物與大勢人物（跟著內容走；彭脫、韓忠
    沒有對話人物，公告照樣寫他們的名字）、管理者的名號。"""
    figures = {fig.name for fig in content.figures.values()}
    return FAMOUS_NAMES | {ch.name for ch in content.characters.values()} | figures | frozenset(content.config.admins)


def active(profile: BotProfile, season_number: int) -> bool:
    """這一季被叫醒、替某個陣營效力中（不是退隱）。"""
    return profile.faction is not None and profile.season_number == season_number
