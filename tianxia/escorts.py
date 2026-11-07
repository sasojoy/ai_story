"""過渡（開發規範手冊 3.11）：隨你出陣的同伴打完回江湖搬進功能包 tianxia/features/battle/escorts.py（全部拆包第 7 批）。這個名字留成指到
同一個模組的別名：`from tianxia import escorts`（tianxia/features/battle/tests/test_companions_battle.py；engine 的 _apply_battle_outcome 第 8 批搬進
features/battle/progress.py、改成包裡直接叫）照舊拿到那一份（換掉的屬性兩邊都看得到）。程式裡新寫的一律 import 包；呼叫端改完就拿掉。"""
import sys

from tianxia.features.battle import escorts as _escorts

sys.modules[__name__] = _escorts
