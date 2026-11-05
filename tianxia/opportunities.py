"""過渡（開發規範手冊 3.11）：機緣的規則（六種機緣、第 2 階行動、密謀、線索）搬進功能包 tianxia/features/military/opp_rules.py（全部拆包第 34 批）。
這個名字留成指到同一個模組的別名：`from tianxia import opportunities`（腳本與測試，含 monkeypatch.setattr(opportunities, ...)）照舊拿到那一份（換掉的屬性兩邊都看得到）。
程式裡新寫的一律 import 包；呼叫端改完就拿掉。"""
import sys

from tianxia.features.military import opp_rules as _opp_rules

sys.modules[__name__] = _opp_rules
