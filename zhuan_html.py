"""過渡（開發規範手冊 3.11）：公開的傳那一頁的 HTML搬進功能包 tianxia/features/zhuan/zhuan_html.py（全部拆包第 29 批）。這個名字留成指到同一個模組的
別名：`import zhuan_html`（server.py、測試）照舊拿到那一份（換掉的屬性兩邊都看得到）。程式裡新寫的一律 import 包；呼叫端改完就拿掉。"""
import sys

from tianxia.features.zhuan import zhuan_html as _zhuan_html

sys.modules[__name__] = _zhuan_html
