"""過渡（開發規範手冊 3.11）：領地爭奪每天的鐘與攻城時段（戰書挑時段、22:00 換天）搬進功能包 tianxia/features/territory_acts/conquest_day.py（全部拆包第 46 批）。這個名字留成指到同一個模組的
別名：`from tianxia import conquest_day`（還沒搬的舊模組、server.py、scripts 與測試，含 monkeypatch.setattr(conquest_day, ...)）照舊拿到那一份（換掉的屬性兩邊都看得到）。
程式裡新寫的一律 import 包；呼叫端改完就拿掉。"""
import sys

from tianxia.features.territory_acts import conquest_day as _conquest_day

sys.modules[__name__] = _conquest_day
