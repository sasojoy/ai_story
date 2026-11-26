"""主機的唯讀清單 scripts/list_staff_like_names.py（第 240 批）：只印名號像官方的、只印名號、真的只讀。"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import list_staff_like_names  # noqa: E402

from tianxia.characters import CharacterStore  # noqa: E402
from tianxia.database import open_database  # noqa: E402
from tianxia.engine import Game  # noqa: E402
from tianxia.state import BotProfile  # noqa: E402


def test_lists_only_the_staff_like_names(tmp_path, capsys, content):
    path = tmp_path / "t.db"
    store = CharacterStore(open_database(path))
    for name in ("沈浪", "客服小美", "官府中人"):
        game = Game.new(content, name)
        if name == "客服小美":
            game.state.player.bot = BotProfile(personality="普通", seed=1)  # 是不是假人，輸出一樣
        store.save(game.state)
    before = path.read_bytes()
    assert list_staff_like_names.main([str(path)]) == 0
    assert capsys.readouterr().out.splitlines() == ["客服小美", "共 1 個"]
    assert path.read_bytes() == before  # 只讀


def test_a_missing_file_exits_with_one(tmp_path, capsys):
    assert list_staff_like_names.main([str(tmp_path / "nope.db")]) == 1
    assert not (tmp_path / "nope.db").exists()
