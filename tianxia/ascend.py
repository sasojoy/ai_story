"""過渡（開發規範手冊 3.11）：破境（破境卡與卡上那一句的三段式）搬進功能包 tianxia/features/cultivation/ascend.py（全部拆包第 23 批）。這個名字
留成指到同一個模組的別名：`from tianxia import ascend`（殼 server.py 的 B 段 ascend.read、ascend.fallback 與測試）照舊拿到那一份（換掉的
屬性兩邊都看得到）。程式裡新寫的一律 import 包；呼叫端改完就拿掉。"""
import sys

from tianxia.features.cultivation import ascend as _ascend

sys.modules[__name__] = _ascend
