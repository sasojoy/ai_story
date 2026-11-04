"""過渡（開發規範手冊 3.11）：擂台的場邊事件搬進功能包 tianxia/features/bout/arena_crowd.py（全部拆包第 12 批）。這個名字留成指到同一個
模組的別名：`from tianxia import arena_crowd`（server 的鎖外重寫那一句與看台的反應、scripts 與測試，含 monkeypatch.setattr(arena_crowd, ...)）
照舊拿到那一份（換掉的屬性兩邊都看得到）。程式裡新寫的一律 import 包；呼叫端改完就拿掉。"""
import sys

from tianxia.features.bout import arena_crowd as _crowd

sys.modules[__name__] = _crowd
