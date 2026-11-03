"""過渡（開發規範手冊 3.11）：碰到才說的規則搬進功能包 tianxia/features/guide/hints.py（全部拆包第 22 批）。這個名字留成指到同一個模組的
別名：`from tianxia import hints`（測試，含 tianxia/features/explore/tests）照舊拿到那一份（換掉的屬性兩邊都看得到）。程式裡新寫的一律 import 包；呼叫端改完就拿掉。"""
import sys

from tianxia.features.guide import hints as _hints

sys.modules[__name__] = _hints
