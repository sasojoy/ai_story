"""過渡（開發規範手冊 3.11）：商城的規則搬進功能包 tianxia/features/mall/rules.py。這個名字留成指到同一個模組的別名，
`from tianxia import mall`（測試）照舊拿到那一份（換掉的屬性兩邊都看得到）。程式裡新寫的一律 import 包；第 2 階測試改完就拿掉。"""
import sys

from tianxia.features.mall import rules as _rules

sys.modules[__name__] = _rules
