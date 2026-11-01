"""過渡（開發規範手冊 3.11）：走一趟的規則搬進功能包 tianxia/features/explore/outing_rules.py（主動搬六包第 3＋4 批）。這個名字留成指到
同一個模組的別名：`from tianxia import outing`（還沒搬的舊模組 bot、bot_policy、server、engine〔有所感的 rare_boost〕與測試）照舊拿到
那一份（換掉的屬性兩邊都看得到）。程式裡新寫的一律 import 包；呼叫端改完就拿掉。"""
import sys

from tianxia.features.explore import outing_rules as _rules

sys.modules[__name__] = _rules
