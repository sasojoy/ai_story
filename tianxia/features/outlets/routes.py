"""銀兩出口的動作表（功能包 tianxia/features/outlets/；原本寫在 server.py 的 MAIN_ACTIONS，全部拆包第 68 批）：殼照 FEATURES 接（main_actions 掛鉤）。
這個檔只在殼建動作表時才 import（__init__ 的掛鉤裡面才 from . import routes）；殼的東西一律照 shell.<名字> 當下讀（測試換掉的也看得到）。
donate_items（整理網頁送來的 items）、DONATE_ITEMS_MAX 留在殼：測試叫 server.donate_items。"""
from . import donate_actions


def main_actions(shell) -> dict:
    return {
        # 自家大本營捐軍備（素材與經濟設計第六節）：一次捐一種素材 count 個（上限切一半：收得下的收）；軍需帳那一頁送 items
        # （[{material, count}, …]，挑好的幾種一起捐、一則紀錄）
        "donate": lambda g, b: donate_actions.donate_items(g, shell.donate_items(b)) if "items" in b else donate_actions.donate(g, str(b.get("material", "")), max(1, shell._int(b.get("count"), 1))),
    }
