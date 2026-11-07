"""過渡（開發規範手冊 3.11）：人物對話（跟大勢人物說話的三段式：組單子、請模型、套用）搬進功能包 tianxia/features/companions/companion_agent.py（全部拆包第 20 批）。這個名字留成指到同一個模組的
別名：`from tianxia import companion_agent`（還沒搬的舊模組、server.py、scripts 與測試，含 monkeypatch.setattr(companion_agent, ...)）照舊拿到那一份（換掉的屬性兩邊都看得到）。程式裡新寫的一律 import 包；呼叫端改完就拿掉。"""
import sys

from tianxia.features.companions import companion_agent as _companion_agent

sys.modules[__name__] = _companion_agent
