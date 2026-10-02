"""在主機上幫帳號設一組新的隨機密碼（帳號密碼登入設計第五節）：沒有這個帳號就建立，可以順便綁角色。

密碼寫到 .local/<小寫帳號>_password.txt（.local/ 不進程式碼庫），畫面上只印檔案位置，不印密碼。
執行：.venv/Scripts/python.exe scripts/set_password.py Rayal --character Rayal
"""
from __future__ import annotations

import argparse
import secrets
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tianxia.accounts import AccountError, AccountStore, check_login, normalize  # noqa: E402
from tianxia.save import load_game, path_for  # noqa: E402
from tianxia.world_state import WorldStateStore  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="幫帳號設一組新的隨機密碼（沒有這個帳號就建立）")
    parser.add_argument("account", help="帳號（英文字母、數字、底線，3～20 字）")
    parser.add_argument("--character", help="順便把這個名號的角色綁到帳號上：存檔要已經存在、不能是伺服器假人")
    parser.add_argument("--saves-dir", default=str(ROOT / "saves"))
    parser.add_argument("--local-dir", default=str(ROOT / ".local"))
    args = parser.parse_args(argv)
    saves_dir = Path(args.saves_dir)
    store = AccountStore(saves_dir / "accounts" / "accounts.json")
    password = secrets.token_urlsafe(9)  # 12 個字
    try:
        check_login(args.account)
        with WorldStateStore(saves_dir / "world" / "state.json").action_lock():
            existing = store.get(args.account)
            if args.character:
                save = path_for(saves_dir, args.character)
                if not save.exists():
                    print(f"找不到角色「{args.character}」的存檔。")
                    return 1
                if load_game(save).player.bot is not None:
                    print(f"「{args.character}」是伺服器假人的存檔，不能綁到帳號上。")
                    return 1
                if store.owner_of(args.character) not in (None, normalize(args.account)):
                    print(f"「{args.character}」已經綁在別的帳號上。")
                    return 1
                if existing is not None and existing.character not in (None, args.character):
                    print(f"帳號 {args.account} 已經有角色「{existing.character}」了。")
                    return 1
            if existing is None:
                store.register(args.account, password)
            else:
                store.set_password(args.account, password)
            if args.character:
                store.bind_character(args.account, args.character)
    except AccountError as exc:
        print(exc)
        return 1
    out = Path(args.local_dir) / f"{normalize(args.account)}_password.txt"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(password + "\n", encoding="utf-8")
    print(f"已設定帳號 {args.account} 的密碼，寫在 {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
