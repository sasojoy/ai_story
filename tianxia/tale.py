"""過渡（開發規範手冊 3.11）：戰記（備料、寫字、組篇、存放）搬進功能包 tianxia/features/tale/tale.py（全部拆包第 52 批）。這個名字留成指到同一個模組的
別名：`from tianxia import tale`（server.py、測試、scripts/same_behavior.py）照舊拿到那一份（換掉的屬性兩邊都看得到）。程式裡新寫的一律 import 包；呼叫端改完就拿掉。"""
import sys

from tianxia.features.tale import tale as _tale

sys.modules[__name__] = _tale
