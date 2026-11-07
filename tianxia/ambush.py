"""過渡（開發規範手冊 3.11）：設伏劫道的規則搬進功能包 tianxia/features/stamina_plays/ambush_rules.py。這個名字留成指到同一個模組的別名，
`from tianxia import ambush`（howto、scripts/measure_stamina_plays.py、測試，含 monkeypatch.setattr(ambush, ...)）照舊拿到那一份。程式裡新寫的一律 import 包；第 2 階測試改完就拿掉。"""
import sys

from tianxia.features.stamina_plays import ambush_rules as _rules

sys.modules[__name__] = _rules
