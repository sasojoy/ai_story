"""過渡（開發規範手冊 3.11）：新手引導的規則（說書人的步驟、任務卡）搬進功能包 tianxia/features/guide/rules.py（全部拆包第 22 批）。這個名字留成指到同一個模組的
別名：`from tianxia import guide`、`from tianxia.guide import note_action`（engine 的 Game._note_action：
tests/core/test_engine.py 換的是 tianxia.engine.note_action）與測試照舊拿到那一份（換掉的屬性兩邊都看得到）。程式裡新寫的一律 import 包；呼叫端改完就拿掉。"""
import sys

from tianxia.features.guide import rules as _rules

sys.modules[__name__] = _rules
