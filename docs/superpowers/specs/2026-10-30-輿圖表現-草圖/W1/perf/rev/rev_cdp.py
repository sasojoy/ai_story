import io, json, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
c = json.load(open(sys.argv[1], encoding="utf-8"))
for cond in ("3|6", "3|4", "2|6", "2|4"):
    V, R = c[cond + "|V"], c[cond + "|R"]
    for g in ("pan", "pinch", "zoom", "fly"):
        v, r = V[g]["cdp"], R[g]["cdp"]
        line = "  ".join(f"{k} V{v[k]} R{r[k]} ({(v[k]-r[k])/v[k]:+.0%} R less)" for k in ("Layout", "RecalcStyle", "Script", "Task"))
        print(cond, g, line)
    print(cond, "throttle V", V["throttleRatio"], "R", R["throttleRatio"])
