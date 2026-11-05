"""過渡（開發規範手冊 3.11）：輿圖的底圖資料與疊層搬進功能包 tianxia/features/map/mapdata.py（全部拆包第 49 批）。這個名字留成指到同一個模組的別名，
`from tianxia import mapdata`（還沒改的舊模組與測試）照舊拿到那一份（換掉的屬性兩邊都看得到）。程式裡新寫的一律 import 包；第 2 階測試改完就拿掉。"""
import sys

from tianxia.features.map import mapdata as _mapdata

sys.modules[__name__] = _mapdata
