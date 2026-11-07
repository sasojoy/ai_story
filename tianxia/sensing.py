"""過渡（開發規範手冊 3.11）：有所感的規則搬進功能包 tianxia/features/sense/sensing.py（全部拆包第 24 批）。這個名字留成指到同一個模組的
別名：`from tianxia import sensing`（還沒搬的舊模組 mapdata、bot、bot_policy、腳本與測試）照舊拿到那一份（換掉的屬性兩邊都看得到）。engine 第二輪第 98 批起不經這裡
（探索包的測試換 tianxia.features.sense.sensing.missed_today）。程式裡新寫的一律 import 包；呼叫端改完就拿掉。"""
import sys

from tianxia.features.sense import sensing as _sensing

sys.modules[__name__] = _sensing
