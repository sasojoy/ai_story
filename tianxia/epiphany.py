"""過渡（開發規範手冊 3.11）：特殊頓悟的規則搬進功能包 tianxia/features/sense/epiphany.py（全部拆包第 24 批）。這個名字留成指到同一個模組的
別名：`from tianxia import epiphany`（engine〔登記一條線的鉤子那一行、委派的型別註記〕、server〔靜心思名的三段式〕、bot_policy、bot_runner
與測試，含 mock.patch.object(epiphany, "_trial"…)）照舊拿到那一份（換掉的屬性兩邊都看得到）。程式裡新寫的一律 import 包；呼叫端改完就拿掉。"""
import sys

from tianxia.features.sense import epiphany as _epiphany

sys.modules[__name__] = _epiphany
