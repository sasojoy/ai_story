"""過渡（開發規範手冊 3.11）：問酒家照問句找事實搬進功能包 tianxia/features/tavern/ask.py（主動搬六包第 10 批）。這個名字留成指到同一個
模組的別名：`from tianxia import tavern_ask`（測試）照舊拿到那一份。程式裡新寫的一律 import 包；呼叫端改完就拿掉。"""
import sys

from tianxia.features.tavern import ask as _ask

sys.modules[__name__] = _ask
