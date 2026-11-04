"""過渡（開發規範手冊 3.11）：人物列傳的規則（寫傳的單子、規則拼的正文、清稿）搬進功能包 tianxia/features/zhuan/biography.py（全部拆包第 29 批）。這個名字留成指到同一個模組的
別名：`from tianxia import biography`（server、還沒搬的舊模組與測試）照舊拿到那一份（換掉的屬性兩邊都看得到）。程式裡新寫的一律 import 包；呼叫端改完就拿掉。"""
import sys

from tianxia.features.zhuan import biography as _biography

sys.modules[__name__] = _biography
