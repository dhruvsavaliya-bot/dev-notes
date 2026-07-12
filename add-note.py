#!/usr/bin/env python3
"""
dev-notes trigger
Run this script -> it picks one unused item from the content pool,
appends it to the right markdown file, commits, and pushes.
Each run = one meaningful commit = one contribution square.
"""

import json
import random
import subprocess
import sys
from datetime import date
from pathlib import Path

REPO = Path(__file__).parent
POOL = REPO / ".content" / "pool.json"
USED = REPO / ".content" / "used.json"

FILES = {
    "coding-tips": REPO / "coding-tips" / "tips.md",
    "languages": REPO / "languages" / "notes.md",
    "ai": REPO / "ai" / "notes.md",
    "trending-projects": REPO / "trending-projects" / "projects.md",
    "articles": REPO / "articles" / "reading-list.md",
}

HEADERS = {
    "coding-tips": "# Coding Tips\n\nPractical tips collected over time.\n",
    "languages": "# Language Notes\n\nSnippets and gotchas across languages.\n",
    "ai": "# AI / LLM Notes\n\nLessons from building with LLMs.\n",
    "trending-projects": "# Trending Projects\n\nOpen-source projects worth checking out.\n",
    "articles": "# Reading List\n\nArticles and blog posts worth your time.\n",
}

COMMIT_MSG = {
    "coding-tips": "tip",
    "languages": "lang",
    "ai": "ai",
    "trending-projects": "project",
    "articles": "article",
}


def run(*cmd):
    r = subprocess.run(cmd, cwd=REPO, capture_output=True, text=True)
    if r.returncode != 0:
        print(r.stderr.strip() or r.stdout.strip())
        sys.exit(1)
    return r.stdout.strip()


def main():
    pool = json.loads(POOL.read_text())
    used = json.loads(USED.read_text()) if USED.exists() else {}

    # categories that still have unused content
    available = {
        cat: [i for i in items if i not in used.get(cat, [])]
        for cat, items in pool.items()
    }
    available = {c: i for c, i in available.items() if i}

    if not available:
        print("Content pool exhausted! Add more items to .content/pool.json")
        sys.exit(0)

    category = random.choice(list(available.keys()))
    item = random.choice(available[category])

    # append to the markdown file
    target = FILES[category]
    if not target.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(HEADERS[category])
    with target.open("a") as f:
        f.write(f"\n- **{date.today().isoformat()}** — {item}\n")

    # mark as used
    used.setdefault(category, []).append(item)
    USED.write_text(json.dumps(used, indent=2))

    # commit + push
    summary = item.split("—")[0].split(".")[0][:50].strip().rstrip("*")
    run("git", "add", "-A")
    run("git", "commit", "-m", f"{COMMIT_MSG[category]}: add {summary}")
    run("git", "push", "origin", "main")

    print(f"✅ Added to {category}: {item[:70]}...")


if __name__ == "__main__":
    main()
