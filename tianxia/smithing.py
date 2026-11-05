"""過渡（開發規範手冊 3.11）：打造與淬煉的規則搬進功能包 tianxia/features/smithy/smithing.py（全部拆包第 41 批）。這個名字留成指到同一個模組的
別名：`from tianxia import smithing`（engine〔核心原位讀 draft_here、GO_VERB 等〕、bot、shopview、skillview、scripts 與測試，含 mock.patch.object(smithing, ...)）
照舊拿到那一份（換掉的屬性兩邊都看得到）。程式裡新寫的一律 import 包；呼叫端改完就拿掉。"""
import sys

from tianxia.features.smithy import smithing as _smithing

sys.modules[__name__] = _smithing
