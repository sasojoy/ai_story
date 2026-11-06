"""舊名：手機通知的五種事，本體在 tianxia/features/notify/notices.py（全部拆包第 53 批）。同一個模組物件：`from tianxia import notices`、
測試的 monkeypatch.setattr(notices, "DUEL_SOURCES", ...)、scripts/same_behavior.py 照舊讀得到。新寫的程式 import 包。"""
import sys

from tianxia.features.notify import notices as _notices

sys.modules[__name__] = _notices
