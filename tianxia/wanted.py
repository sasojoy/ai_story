"""過渡（開發規範手冊 3.11）：通緝掛上玩家卡搬進功能包 tianxia/features/bounties/wanted.py（全部拆包第 45 批）。這個名字留成指到同一個模組的別名。"""
import sys

from tianxia.features.bounties import wanted as _wanted

sys.modules[__name__] = _wanted
