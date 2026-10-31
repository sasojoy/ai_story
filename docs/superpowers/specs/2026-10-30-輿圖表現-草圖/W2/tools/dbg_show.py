import io, json, sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
raw = open(sys.argv[1], "rb").read().decode("utf-8-sig", errors="replace")
if "\x00" in raw:
    raw = open(sys.argv[1], "rb").read().decode("utf-16", errors="replace").lstrip("﻿")
d = json.loads(raw)
print(d["cam"], d["room"], d["g"])
for x in d["d"]:
    print(x["id"], x["w"], x["inside"])
    for t in x["tries"]:
        print("   ", t["bx"], t["fits"], t["hits"])
