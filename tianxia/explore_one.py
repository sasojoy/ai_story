"""過渡（開發規範手冊 3.11）：探索一顆的純規則搬進功能包 tianxia/features/explore/explore_rules.py（主動搬六包第 3＋4 批）。這個名字
留成指到同一個模組的別名：`from tianxia import explore_one`（還沒搬的舊模組 howto、mapdata 與測試；測試換掉的 explore_one.draw 兩邊
都看得到）照舊拿到那一份。程式裡新寫的一律 import 包；呼叫端改完就拿掉。"""
import sys

from tianxia.features.explore import explore_rules as _rules

sys.modules[__name__] = _rules
