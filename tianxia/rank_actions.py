"""過渡（開發規範手冊 3.11）：第 3、4 階行動的規則（誰做得了、在哪裡做得了、這週還剩幾次）搬進功能包 tianxia/features/military/rank_rules.py（全部拆包第 33 批）。
這個名字留成指到同一個模組的別名：`from tianxia import rank_actions`（腳本與測試，含 monkeypatch.setattr(rank_actions, ...)）照舊拿到那一份（換掉的屬性兩邊都看得到）。
程式裡新寫的一律 import 包；呼叫端改完就拿掉。"""
import sys

from tianxia.features.military import rank_rules as _rank_rules

sys.modules[__name__] = _rank_rules
