"""過渡（開發規範手冊 3.11）：往來紀錄的小檔搬進功能包 tianxia/features/companions/talk_log.py（主幹合回 D 段）。這個名字留成指到同一個模組的別名：
殼 server.py 的 `from tianxia import talk_log`（鎖外包裝 talk_store、_log_talk 與 act 前後那兩行留在殼）與測試照舊拿到那一份。程式裡新寫的一律 import 包；呼叫端改完就拿掉。"""
import sys

from tianxia.features.companions import talk_log as _talk_log

sys.modules[__name__] = _talk_log
