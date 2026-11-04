"""過渡（開發規範手冊 3.11）：列傳為終點的規則（休季用票、紀念印、人物評曰）搬進功能包 tianxia/features/zhuan/zhuan_end.py（全部拆包第 29 批）。這個名字留成指到同一個模組的
別名：`from tianxia import zhuan_end`（server、還沒搬的舊模組、腳本與測試）照舊拿到那一份（換掉的屬性兩邊都看得到）。程式裡新寫的一律 import 包；呼叫端改完就拿掉。"""
import sys

from tianxia.features.zhuan import zhuan_end as _zhuan_end

sys.modules[__name__] = _zhuan_end
