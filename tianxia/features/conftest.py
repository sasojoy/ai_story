"""功能包的測試（tianxia/features/<包>/tests/，開發規範手冊 4.6）共用 tests/conftest.py 的 fixture 與小工具。

pytest 只把一個 conftest 套到它底下的測試，所以這裡把 tests/conftest.py 整份接過來（同一個模組物件：tests/ 先收的時候就是
那一份，只跑包的測試時這裡先載）；那一份自己會把 tests/ 底下的資料夾（kit/……）放上 sys.path。每一包的 tests/ 也放上去，
同 tests/ 底下的資料夾：測試檔可以互相 import（檔名全 repo 不能重複）。測試檔照舊寫 `from conftest import real_content`。
"""
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_TESTS = _HERE.parents[1] / "tests"
for _d in [_TESTS, *sorted(p for p in _HERE.glob("*/tests") if p.is_dir())]:
    if str(_d) not in sys.path:
        sys.path.insert(0, str(_d))

import conftest as _shared  # noqa: E402  tests/conftest.py

globals().update({k: v for k, v in vars(_shared).items() if not k.startswith("__")})
