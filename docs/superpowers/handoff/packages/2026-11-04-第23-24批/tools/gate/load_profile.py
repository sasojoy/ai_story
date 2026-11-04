"""Load the real content under one profile (argv[2]; 'none' = no profile) from the tree argv[1]."""
import io
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
root = Path(sys.argv[1])
sys.path.insert(0, str(root))
profile = None if sys.argv[2] == "none" else sys.argv[2]
from tianxia.content import load_content, profile_line  # noqa: E402

c = load_content(root / "content", profile=profile)
print(sys.argv[2], "events", len(c.events), "battles", len(c.battles), "looks", len(getattr(c, "looks", {}) or {}),
      "duels", len(getattr(c, "duels", {}) or {}), "|", profile_line(c, profile))
