"""Unpack one commit for the web comparison and point its model at a dead port.

usage: python unpack.py <sha> <dest> [--repo <clone>]
"""
import argparse
import json
import os
import re
import subprocess
import tarfile

DEAD_MODEL = "http://127.0.0.1:9"
# top-level directories the server reads; the top-level *.py files come from the commit itself, so a new one cannot be missed
DIRS = ("tianxia", "content", "web", "scripts")


def items_of(repo: str, sha: str) -> list[str]:
    names = subprocess.run(["git", "-C", repo, "ls-tree", "--name-only", sha], capture_output=True, text=True, encoding="utf-8", check=True).stdout.split("\n")
    return [n for n in names if n.endswith(".py") or n in DIRS]


def dead_model(text: str) -> str:
    """The copy's config with the model on the dead port. One line, so the copy's config stays what the commit says otherwise."""
    if '"ollama_url"' in text:
        text = re.sub(r'"ollama_url"\s*:\s*"[^"]*"', f'"ollama_url": "{DEAD_MODEL}"', text, count=1)
    else:
        text = re.sub(r"^\s*\{", '{"ollama_url": "' + DEAD_MODEL + '",', text, count=1)
    json.loads(text)
    return text


def unpack(repo: str, sha: str, dest: str) -> str:
    os.makedirs(dest, exist_ok=True)
    tar = dest.rstrip("\\/") + ".tar"
    subprocess.run(["git", "-C", repo, "archive", "-o", tar, sha, *items_of(repo, sha)], check=True)
    with tarfile.open(tar) as t:
        t.extractall(dest, filter="data")
    os.remove(tar)
    cfg = os.path.join(dest, "content", "config.json")
    with open(cfg, encoding="utf-8", newline="") as f:
        text = f.read()
    with open(cfg, "w", encoding="utf-8", newline="") as f:
        f.write(dead_model(text))
    return dest


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("sha")
    ap.add_argument("dest")
    ap.add_argument("--repo", default=os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    a = ap.parse_args()
    print(unpack(a.repo, a.sha, a.dest))
