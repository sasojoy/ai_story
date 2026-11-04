"""過渡（開發規範手冊 3.11）：月旦評的規則搬進功能包 tianxia/features/figure_acts/yuedan.py（全部拆包第 31 批）。這個名字留成指到同一個模組的
別名：`from tianxia import yuedan`（world.py、social.py、figures.py、server.py、scripts 與測試，含 monkeypatch.setattr(yuedan, ...)）照舊拿到那一份（換掉的屬性兩邊都看得到）。
程式裡新寫的一律 import 包；呼叫端改完就拿掉。"""
import sys

from tianxia.features.figure_acts import yuedan as _yuedan

sys.modules[__name__] = _yuedan
