"""過渡（開發規範手冊 3.11）：〈天下形勢〉（每天 22:00 換天那一篇的旁白）搬進功能包 tianxia/features/territory_acts/xingshi.py（全部拆包第 46 批）。這個名字留成指到同一個模組的
別名：`from tianxia import xingshi`（還沒搬的舊模組、server.py、scripts 與測試，含 monkeypatch.setattr(xingshi, ...)）照舊拿到那一份（換掉的屬性兩邊都看得到）。
程式裡新寫的一律 import 包；呼叫端改完就拿掉。"""
import sys

from tianxia.features.territory_acts import xingshi as _xingshi

sys.modules[__name__] = _xingshi
