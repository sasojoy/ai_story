"""在主機上幫帳號設一組新的隨機密碼（帳號密碼登入設計第五節）：沒有這個帳號就建立，可以順便綁角色。

密碼寫到 .local/<小寫帳號>_password.txt（.local/ 不進程式碼庫），畫面上只印檔案位置，不印密碼。
--character 的角色還不存在時，直接建立一個新角色再綁上去：管理者的名號在畫面上取不到（名號檢查會擋），
線上架構第 1 期換版從零開始之後（企劃者 2026-10-03 決定不搬舊存檔），管理者的角色只能這樣建。
執行：.venv/Scripts/python.exe scripts/set_password.py Rayal --character Rayal
建角色時的設定照伺服器那一份（TIANXIA_PROFILE）：伺服器開著週末設定，就先設 $env:TIANXIA_PROFILE = "weekend" 再執行
（建好時印一行「設定：…」，跟伺服器啟動時印的一樣）。
"""
from __future__ import annotations

import argparse
import secrets
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tianxia.accounts import AccountError, AccountStore, check_login, normalize  # noqa: E402
from tianxia.characters import CharacterStore  # noqa: E402
from tianxia.content import env_profile, load_content, profile_line  # noqa: E402
from tianxia.database import default_path, open_database  # noqa: E402
from tianxia.engine import Game  # noqa: E402
from tianxia.sqlite_world import SqliteWorldStore  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="幫帳號設一組新的隨機密碼（沒有這個帳號就建立）")
    parser.add_argument("account", help="帳號（英文字母、數字、底線，3～20 字）")
    parser.add_argument("--character", help="順便把這個名號的角色綁到帳號上：還沒有這個角色就建立一個；不能是伺服器假人")
    parser.add_argument("--db", default=None, help="資料庫檔（預設：環境變數 TIANXIA_DB，沒設就是 saves/tianxia.db）")
    parser.add_argument("--local-dir", default=str(ROOT / ".local"))
    args = parser.parse_args(argv)
    db = open_database(Path(args.db) if args.db else default_path())
    store = AccountStore(db)
    characters = CharacterStore(db)
    password = secrets.token_urlsafe(9)  # 12 個字
    created = False
    try:
        check_login(args.account)
        # 讀內容檔很慢：在交易外先讀好。設定照伺服器那一份（TIANXIA_PROFILE，content.env_profile）：不然週末設定的伺服器上，
        # 這裡建的角色拿到的是預設設定（例如開場那一則的贈禮那一行）
        profile = env_profile()
        content = load_content(ROOT / "content", profile=profile) if args.character else None
        with db.transaction():  # 跟伺服器、假人程式寫同一個資料庫：一筆交易做完，不會跟假人取名撞在一起
            existing = store.get(args.account)
            state = None
            if args.character:
                try:
                    state = characters.load(args.character)
                except ValueError:  # pydantic 的 ValidationError
                    print(f"角色「{args.character}」的存檔讀不懂，先處理那份存檔。")
                    return 1
                if state is not None and state.player.bot is not None:
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
                if state is None:
                    game = Game.new(content, args.character, world=SqliteWorldStore(db))
                    characters.save(game.state)
                    created = True
                store.bind_character(args.account, args.character)
    except AccountError as exc:
        print(exc)
        return 1
    out = Path(args.local_dir) / f"{normalize(args.account)}_password.txt"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(password + "\n", encoding="utf-8")
    if created:
        print(f"角色「{args.character}」原本不存在，已經建立新角色。")
        print(profile_line(content, profile))  # 跟伺服器啟動時印的同一行：設定讀錯時一眼看得出來
    print(f"已設定帳號 {args.account} 的密碼，寫在 {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
