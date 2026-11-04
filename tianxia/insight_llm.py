"""過渡（開發規範手冊 3.11）：看圖替自己悟的意境取名（三段式的 B 段）搬進功能包 tianxia/features/sense/insight_llm.py（全部拆包第 24 批）。
這個名字留成指到同一個模組的別名：`from tianxia import insight_llm`（server〔畫完那一筆的 B 段；test_server 換掉 server.insight_llm.name、warm〕、
bot_runner、腳本與測試）照舊拿到那一份（換掉的屬性兩邊都看得到）。程式裡新寫的一律 import 包；呼叫端改完就拿掉。"""
import sys

from tianxia.features.sense import insight_llm as _insight_llm

sys.modules[__name__] = _insight_llm
