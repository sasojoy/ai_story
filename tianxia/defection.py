"""過渡（開發規範手冊 3.11）：叛投的規則搬進功能包 tianxia/features/faction/defection.py（全部拆包第 35 批）。這個名字留成指到同一個模組的
別名：`from tianxia import defection`（engine、測試、腳本，含 monkeypatch.setattr(defection, ...)）照舊拿到那一份（換掉的屬性兩邊都看得到）。
程式裡新寫的一律 import 包；呼叫端改完就拿掉。"""
import sys

from tianxia.features.faction import defection as _defection

sys.modules[__name__] = _defection
