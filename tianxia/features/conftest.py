"""功能包的測試（tianxia/features/<包>/tests/，開發規範手冊 4.6）共用 tests/conftest.py 的 fixture 與小工具。

pytest 只把一個 conftest 套到它底下的測試，所以這裡把 tests/conftest.py 整份接過來（同一個模組物件：tests/ 先收的時候就是
那一份，只跑包的測試時這裡先載）；那一份自己會把 tests/ 底下的資料夾（kit/……）放上 sys.path。每一包的 tests/ 也放上去，
同 tests/ 底下的資料夾：測試檔可以互相 import（檔名全 repo 不能重複）。測試檔照舊寫 `from conftest import real_content`。

content 這個 fixture 在這裡覆寫（全部拆包第 63 批，手冊 4.1 第二級）：包的測試只拿核心加自己這一包的測試內容（state、game 照名字找 content，一起換）。
這樣的內容不驗；要驗內容（validate）的測試標 @pytest.mark.whole_content，拿整份。real_content、自己 load_content(FIXTURE) 的不經過這裡。
"""
import sys
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve().parent
_TESTS = _HERE.parents[1] / "tests"
for _d in [_TESTS, *sorted(p for p in _HERE.glob("*/tests") if p.is_dir())]:
    if str(_d) not in sys.path:
        sys.path.insert(0, str(_d))

import conftest as _shared  # noqa: E402  tests/conftest.py

globals().update({k: v for k, v in vars(_shared).items() if not k.startswith("__")})


@pytest.fixture
def content(request):  # 要在 globals().update 之後：不然被 tests/conftest.py 那一份蓋回去
    """測試內容：核心加這個測試所在的那一包（資料夾名就是包名）；標了 whole_content 的拿整份。都是這個測試自己的一份。"""
    if request.node.get_closest_marker("whole_content"):
        return _shared.cached_content(_shared.FIXTURE)
    return _shared.cached_content(_shared.FIXTURE, only=Path(request.path).resolve().relative_to(_HERE).parts[0])
