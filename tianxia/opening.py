"""過渡（開發規範手冊 3.11）：開局第一分鐘搬進功能包 tianxia/features/guide/opening.py（全部拆包第 22 批）。這個名字留成指到同一個模組的
別名：`from tianxia import opening`（舊模組 weekcard 與測試）照舊拿到那一份（換掉的屬性兩邊都看得到）。程式裡新寫的一律 import 包；呼叫端改完就拿掉。"""
import sys

from tianxia.features.guide import opening as _opening

sys.modules[__name__] = _opening
