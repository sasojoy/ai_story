"""The round -> web files table behind gate.py --changed-files (batch 107).

    python scripts/webqa/coverage.py build <summary.json>   write scripts/webqa/coverage.json from a walk's summary.round_files
    python scripts/webqa/coverage.py check                  every round is there, its flow is there, every listed file exists,
                                                            every web/*.js is on the table, in gate.SHELL_FILES or in gate.NOT_ON_TABLE

A round lists a file when the browser called at least one named function in it during that round, on either walk (summary.round_files,
gate.py). Only scripts are measured: a stylesheet goes with the script of the same name (gate.rounds_for). Rebuild it from a fresh
`gate.py --base X --head X --out <dir> --jobs 4` walk (batch 110: not --quick, which misses must-reach scenes; season21, every round)
when the flows or the packages' scripts change; check runs in tests/web/test_webqa.py.
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
REPO = os.path.dirname(os.path.dirname(HERE))
TABLE = os.path.join(HERE, "coverage.json")


def build(summary_path: str, table_path: str = TABLE) -> dict:
    import gate

    with open(summary_path, encoding="utf-8") as f:
        per_round = json.load(f).get("round_files") or {}
    missing = [r for r in gate.ROUNDS if r not in per_round]
    if missing:
        raise SystemExit(f"the walk has no files for rounds {missing}: walk every round")
    table = {r: sorted(per_round[r]) for r in gate.ROUNDS}
    with open(table_path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(table, f, ensure_ascii=False, indent=1)
        f.write("\n")
    return table


def check(table_path: str = TABLE, repo: str = REPO) -> list[str]:
    """What is wrong with the table; empty means fine."""
    import gate

    try:
        with open(table_path, encoding="utf-8") as f:
            table = json.load(f)
    except (OSError, ValueError) as e:
        return [f"cannot read {table_path}: {e}"]
    problems = []
    for r in gate.ROUNDS:
        if not table.get(r):
            problems.append(f"round {r} has no files")
        if not os.path.exists(os.path.join(HERE, "flows", f"{r}.mjs")):
            problems.append(f"round {r} has no flows/{r}.mjs")
    problems += [f"round {r} is not in gate.ROUNDS" for r in table if r not in gate.ROUNDS]
    for r, files in table.items():
        for name in files:
            if not name.startswith("web/") or not os.path.isfile(os.path.join(repo, *name.split("/"))):
                problems.append(f"round {r} lists {name}, which is not a file under web/")
    # batch 110: a script no round reaches says why, or a change to it would walk every round without anyone knowing
    reached = {name for files in table.values() for name in files}
    web = os.path.join(repo, "web")
    scripts = sorted(f"web/{n}" for n in os.listdir(web) if n.endswith(".js")) if os.path.isdir(web) else []
    for name in scripts:
        if name not in reached and name not in gate.SHELL_FILES and name not in gate.NOT_ON_TABLE:
            problems.append(f"{name} is reached by no round: walk a flow into it, or say why in gate.NOT_ON_TABLE")
    for name in sorted(gate.NOT_ON_TABLE):
        if name in reached:
            problems.append(f"{name} is in gate.NOT_ON_TABLE but a round reaches it: take it out")
        if not os.path.isfile(os.path.join(repo, *name.split("/"))):
            problems.append(f"gate.NOT_ON_TABLE names {name}, which is not a file")
    return problems


def main(argv=None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args[:1] == ["build"] and len(args) == 2:
        table = build(args[1])
        print(f"wrote {TABLE}: " + ", ".join(f"{r} {len(v)}" for r, v in table.items()))
        return 0
    if args == ["check"]:
        problems = check()
        for p in problems:
            print(p)
        print("coverage.json fine" if not problems else f"{len(problems)} problems")
        return 1 if problems else 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main())
