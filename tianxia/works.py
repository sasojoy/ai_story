"""過渡（開發規範手冊 3.11）：屯糧練兵的規則搬進功能包 tianxia/features/stamina_plays/works_rules.py。這個名字留成指到同一個模組的別名，
`from tianxia import works`（scripts/measure_stamina_plays.py、tests/acts/test_conquest_flip.py、包裡的 tests/test_stamina_plays.py；howto 只 import ambush）
照舊拿到那一份，monkeypatch.setattr(works, ...) 也照樣有效（同一個模組物件）。程式裡新寫的一律 import 包；第 2 階測試改完就拿掉。"""
import sys

from tianxia.features.stamina_plays import works_rules as _rules

sys.modules[__name__] = _rules
