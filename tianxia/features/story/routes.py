"""一條線的動作表（功能包 tianxia/features/story/；原本寫在 server.py 的 MAIN_ACTIONS，全部拆包第 68 批）：殼照 FEATURES 接（main_actions 掛鉤）。
這個檔只在殼建動作表時才 import（__init__ 的掛鉤裡面才 from . import routes）；殼的東西一律照 shell.<名字> 當下讀（測試換掉的也看得到）。"""
from . import actions


def main_actions(shell) -> dict:
    return {
        "story_seen": lambda g, b: actions.story_seen(g),  # 特殊事件的跳顯框按「收下」：看過的卡清掉
    }
