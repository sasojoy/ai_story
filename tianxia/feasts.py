"""過渡（開發規範手冊 3.11）：宴客的規則搬進功能包 tianxia/features/feast/rules.py。這個名字留成指到同一個模組的別名，
`from tianxia import feasts`（測試，含 monkeypatch.setattr(feasts, ...)）照舊拿到那一份。程式裡新寫的一律 import 包；第 2 階測試改完就拿掉。"""
import sys

from tianxia.features.feast import rules as _rules

sys.modules[__name__] = _rules
