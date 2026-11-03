"""過渡（開發規範手冊 3.11）：龍頭上陣搬進功能包 tianxia/features/battle/generals.py（全部拆包第 8 批；誰上陣、份量、池子的挑法 on、pick
留在共用規則層 tianxia/chiefs.py，包裡照舊 re-export）。這個名字留成指到同一個模組的別名：`from tianxia import generals`（world._open_claimed
開集結派人上陣、tests/battle/test_generals.py、tests/season/test_measure_battle.py、scripts/measure_battle.py、決戰包的 test_siege_settle）照舊拿到
那一份（換掉的屬性兩邊都看得到）。程式裡新寫的一律 import 包；呼叫端改完就拿掉。"""
import sys

from tianxia.features.battle import generals as _generals

sys.modules[__name__] = _generals
