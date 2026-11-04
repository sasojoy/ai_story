"""過渡（開發規範手冊 3.11）：傳功門下搬進功能包 tianxia/features/cultivation/chuangong.py（全部拆包第 23 批）。這個名字留成指到同一個模組的
別名：`from tianxia import chuangong`（還沒搬的舊模組 bot 與測試）照舊拿到那一份（換掉的屬性兩邊都看得到）。程式裡新寫的一律 import 包；
呼叫端改完就拿掉。"""
import sys

from tianxia.features.cultivation import chuangong as _chuangong

sys.modules[__name__] = _chuangong
