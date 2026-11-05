"""過渡（開發規範手冊 3.11）：輿圖的設色山水搬進功能包 tianxia/features/map/mapart.py（全部拆包第 49 批）。這個名字留成指到同一個模組的別名，
`from tianxia import mapart`（還沒改的舊模組與測試）照舊拿到那一份（換掉的屬性兩邊都看得到）。程式裡新寫的一律 import 包；第 2 階測試改完就拿掉。"""
import sys

from tianxia.features.map import mapart as _mapart

sys.modules[__name__] = _mapart
