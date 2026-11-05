"""過渡（開發規範手冊 3.11）：伏筆的規則（聽片段、對話片段、最後一步、效果三格）搬進功能包 tianxia/features/military/fs_rules.py（全部拆包第 34 批）。
這個名字留成指到同一個模組的別名：`from tianxia import foreshadow`（腳本與測試，含 monkeypatch.setattr(foreshadow, ...)）照舊拿到那一份（換掉的屬性兩邊都看得到）。
程式裡新寫的一律 import 包；呼叫端改完就拿掉。"""
import sys

from tianxia.features.military import fs_rules as _fs_rules

sys.modules[__name__] = _fs_rules
