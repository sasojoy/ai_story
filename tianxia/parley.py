"""過渡（開發規範手冊 3.11）：NPC 智能 2.0 的純規則（開口求人、開條件、先做後付與食言、他主動開口、帶路、陪你出陣）搬進功能包 tianxia/features/companions/parley.py（全部拆包第 20 批）。這個名字留成指到同一個模組的
別名：`from tianxia import parley`（還沒搬的舊模組、server.py、scripts 與測試，含 monkeypatch.setattr(parley, ...)）照舊拿到那一份（換掉的屬性兩邊都看得到）。程式裡新寫的一律 import 包；呼叫端改完就拿掉。"""
import sys

from tianxia.features.companions import parley as _parley

sys.modules[__name__] = _parley
