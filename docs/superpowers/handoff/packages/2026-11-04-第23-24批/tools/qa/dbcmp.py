"""兩份 sqlite 逐表比（唯讀；每一列轉文字、排序；帳號的 salt／hash、工作階段的 token 抹掉）。python dbcmp.py <A> <B>"""
import difflib
import io
import sqlite3
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
MASK = {"salt", "hash", "token", "session", "cookie"}


def dump(path):
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    out = {}
    for (table,) in con.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").fetchall():
        cols = [r[1] for r in con.execute(f"PRAGMA table_info({table})").fetchall()]
        out[table] = sorted(repr(["<抹掉>" if any(m in c.lower() for m in MASK) else v for c, v in zip(cols, row)])
                            for row in con.execute(f"SELECT * FROM {table}").fetchall())
    con.close()
    return out


a, b = dump(sys.argv[1]), dump(sys.argv[2])
bad = 0
for t in sorted(set(a) | set(b)):
    ra, rb = a.get(t), b.get(t)
    if ra == rb:
        print(f"  {t}: 一樣（{len(ra or [])} 列）")
        continue
    bad += 1
    print(f"  {t}: 不一樣（{len(ra or [])} 對 {len(rb or [])} 列）")
    for line in [x for x in difflib.unified_diff(ra or [], rb or [], lineterm="", n=0) if not x.startswith(("---", "+++", "@@"))][:6]:
        print("      " + line[:600])
print(f"  不一樣的表：{bad}")
