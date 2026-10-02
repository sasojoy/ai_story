import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import set_password  # noqa: E402

from tianxia.accounts import AccountStore  # noqa: E402
from tianxia.engine import Game  # noqa: E402
from tianxia.save import path_for, save_game  # noqa: E402
from tianxia.state import BotProfile  # noqa: E402


def _run(tmp_path, *args):
    return set_password.main([*args, "--saves-dir", str(tmp_path / "saves"), "--local-dir", str(tmp_path / "local")])


def _store(tmp_path):
    return AccountStore(tmp_path / "saves" / "accounts" / "accounts.json")


def test_creates_the_account_binds_the_character_and_only_writes_the_password_to_a_file(tmp_path, capsys, content):
    save_game(Game.new(content, "Rayal").state, path_for(tmp_path / "saves", "Rayal"))
    assert _run(tmp_path, "Rayal", "--character", "Rayal") == 0
    password = (tmp_path / "local" / "rayal_password.txt").read_text(encoding="utf-8").strip()
    out = capsys.readouterr().out
    assert len(password) >= 12
    assert password not in out and "rayal_password.txt" in out
    assert _store(tmp_path).authenticate("Rayal", password).character == "Rayal"


def test_running_again_replaces_the_password(tmp_path, content):
    save_game(Game.new(content, "Rayal").state, path_for(tmp_path / "saves", "Rayal"))
    _run(tmp_path, "Rayal", "--character", "Rayal")
    first = (tmp_path / "local" / "rayal_password.txt").read_text(encoding="utf-8").strip()
    assert _run(tmp_path, "Rayal") == 0
    second = (tmp_path / "local" / "rayal_password.txt").read_text(encoding="utf-8").strip()
    assert first != second
    assert _store(tmp_path).authenticate("Rayal", second).character == "Rayal"


def test_refuses_to_bind_a_server_bot_or_a_missing_save(tmp_path, capsys, content):
    bot = Game.new(content, "周泰安")
    bot.state.player.bot = BotProfile(personality="普通", seed=1, faction="guan", season_number=1)
    save_game(bot.state, path_for(tmp_path / "saves", "周泰安"))
    assert _run(tmp_path, "someone", "--character", "周泰安") == 1
    assert _run(tmp_path, "someone", "--character", "沒有這個人") == 1
    assert _store(tmp_path).get("someone") is None
    assert not (tmp_path / "local").exists()


def test_refuses_a_name_another_account_owns(tmp_path, content):
    save_game(Game.new(content, "沈青衫").state, path_for(tmp_path / "saves", "沈青衫"))
    store = _store(tmp_path)
    store.register("owner", "secret-pw")
    store.bind_character("owner", "沈青衫")
    assert _run(tmp_path, "intruder", "--character", "沈青衫") == 1
    assert store.get("intruder") is None
