"""過渡（開發規範手冊 3.11）：玉璽碎片的規則搬進功能包 tianxia/features/seal/seal.py（全部拆包第 27 批）。這個名字留成指到同一個模組的別名：
`from tianxia import seal`（engine 頂端與還沒搬的第 28 批 Game 方法、舊模組 bot_runner、howto、skillview、seal_duel、seal_acts，殼的 server.py、
run_bots.py〔ensure_salt〕，scripts/measure_seal.py 與測試，含 monkeypatch.setattr(seal, "find"...)、mock.patch.object(seal, "tier_for"／"lean_shift"...)、
same_behavior 換的 seal.secrets.token_hex）照舊拿到那一份（換掉的屬性兩邊都看得到）。程式裡新寫的一律 import 包；呼叫端改完就拿掉。"""
import sys

from tianxia.features.seal import seal as _seal

sys.modules[__name__] = _seal
