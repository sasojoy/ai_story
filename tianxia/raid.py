"""過渡（開發規範手冊 3.11）：raid 搬進功能包 tianxia/features/peers/raid.py（全部拆包第 38 批）。這個名字留成指到同一個模組的別名，
`from tianxia import raid` 照舊拿到那一份（測試換掉的屬性兩邊都看得到）。程式裡新寫的一律 import 包。"""
import sys

from tianxia.features.peers import raid as _raid

sys.modules[__name__] = _raid
