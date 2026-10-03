import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import set_password  # noqa: E402

from tianxia.accounts import AccountStore  # noqa: E402
from tianxia.characters import CharacterStore  # noqa: E402
from tianxia.database import open_database  # noqa: E402
from tianxia.engine import Game  # noqa: E402
from tianxia.state import BotProfile  # noqa: E402


def _db(tmp_path):
    return open_database(tmp_path / "t.db")


def _run(tmp_path, *args):
    return set_password.main([*args, "--db", str(tmp_path / "t.db"), "--local-dir", str(tmp_path / "local")])


def _store(tmp_path):
    return AccountStore(_db(tmp_path))


def _save(tmp_path, state):
    CharacterStore(_db(tmp_path)).save(state)


def _password(tmp_path, login):
    return (tmp_path / "local" / f"{login}_password.txt").read_text(encoding="utf-8").strip()


def test_creates_the_account_binds_the_character_and_only_writes_the_password_to_a_file(tmp_path, capsys, content):
    _save(tmp_path, Game.new(content, "Rayal").state)
    assert _run(tmp_path, "Rayal", "--character", "Rayal") == 0
    password = _password(tmp_path, "rayal")
    out = capsys.readouterr().out
    assert len(password) >= 12
    assert password not in out and "rayal_password.txt" in out
    assert "已經建立新角色" not in out  # 角色本來就在
    assert _store(tmp_path).authenticate("Rayal", password).character == "Rayal"


def test_creates_the_character_when_it_does_not_exist_yet(tmp_path, capsys):
    """換版從零開始：管理者的名號在畫面上取不到，只能用這支腳本建角色（企劃者 2026-10-03）。"""
    assert _run(tmp_path, "Rayal", "--character", "Rayal") == 0
    assert "已經建立新角色" in capsys.readouterr().out
    state = CharacterStore(_db(tmp_path)).load("Rayal")
    assert state is not None and state.player.name == "Rayal" and state.player.bot is None
    assert _store(tmp_path).authenticate("Rayal", _password(tmp_path, "rayal")).character == "Rayal"


def test_running_again_replaces_the_password(tmp_path):
    _run(tmp_path, "Rayal", "--character", "Rayal")
    first = _password(tmp_path, "rayal")
    assert _run(tmp_path, "Rayal") == 0
    second = _password(tmp_path, "rayal")
    assert first != second
    assert _store(tmp_path).authenticate("Rayal", second).character == "Rayal"


def test_refuses_to_bind_a_server_bot(tmp_path, content):
    bot = Game.new(content, "周泰安")
    bot.state.player.bot = BotProfile(personality="普通", seed=1, faction="guan", season_number=1)
    _save(tmp_path, bot.state)
    assert _run(tmp_path, "someone", "--character", "周泰安") == 1
    assert _store(tmp_path).get("someone") is None
    assert not (tmp_path / "local").exists()


def test_refuses_a_name_another_account_owns(tmp_path, content):
    _save(tmp_path, Game.new(content, "沈青衫").state)
    store = _store(tmp_path)
    store.register("owner", "secret-pw")
    store.bind_character("owner", "沈青衫")
    assert _run(tmp_path, "intruder", "--character", "沈青衫") == 1
    assert store.get("intruder") is None


def test_refuses_to_move_an_account_to_another_character(tmp_path, content):
    for name in ("沈青衫", "柳如煙"):
        _save(tmp_path, Game.new(content, name).state)
    _run(tmp_path, "shen", "--character", "沈青衫")
    first = _password(tmp_path, "shen")
    assert _run(tmp_path, "shen", "--character", "柳如煙") == 1
    assert _password(tmp_path, "shen") == first
    assert _store(tmp_path).authenticate("shen", first).character == "沈青衫"


def test_refuses_a_bad_login(tmp_path, capsys):
    assert _run(tmp_path, "有中文") == 1
    assert "帳號只能用英文字母、數字、底線，3～20 字。" in capsys.readouterr().out
    assert not (tmp_path / "local").exists()
