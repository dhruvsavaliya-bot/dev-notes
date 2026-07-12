#!/usr/bin/env python3
"""
dev-notes trigger (LIVE version)
Every run fetches something NEW from the internet:
  - trending-projects : GitHub repos trending this week (GitHub API)
  - articles          : fresh articles from dev.to
  - ai                : latest AI/LLM posts from dev.to
  - coding-tips       : new tips/beginners posts from dev.to
  - languages         : latest posts about a rotating language tag

It never repeats: everything already added is tracked in .content/used.json
Then it commits and pushes automatically. Uses only Python stdlib.
"""

import json
import random
import subprocess
import sys
import urllib.request
from datetime import date, timedelta
from pathlib import Path

REPO = Path(__file__).parent
USED = REPO / ".content" / "used.json"

FILES = {
    "coding-tips": REPO / "coding-tips" / "tips.md",
    "languages": REPO / "languages" / "notes.md",
    "ai": REPO / "ai" / "notes.md",
    "trending-projects": REPO / "trending-projects" / "projects.md",
    "articles": REPO / "articles" / "reading-list.md",
}

HEADERS = {
    "coding-tips": "# Coding Tips\n\nFresh tips and how-tos, added over time.\n",
    "languages": "# Language Notes\n\nNew posts about programming languages.\n",
    "ai": "# AI / LLM Notes\n\nLatest AI and LLM articles worth reading.\n",
    "trending-projects": "# Trending Projects\n\nOpen-source repos trending on GitHub.\n",
    "articles": "# Reading List\n\nFresh dev articles and blog posts.\n",
}

COMMIT_PREFIX = {
    "coding-tips": "tip",
    "languages": "lang",
    "ai": "ai",
    "trending-projects": "project",
    "articles": "article",
}

LANG_TAGS = ["python", "javascript", "typescript", "go", "rust", "java", "sql"]

UA = {"User-Agent": "dev-notes-script"}


def get_json(url):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read().decode("utf-8"))


# ---------------- fetchers: each returns list of (uid, markdown_line) ----------------

def fetch_trending_repos():
    since = (date.today() - timedelta(days=7)).isoformat()
    url = (
        "https://api.github.com/search/repositories"
        f"?q=created:>{since}+stars:>50&sort=stars&order=desc&per_page=25"
    )
    items = get_json(url).get("items", [])
    out = []
    for r in items:
        desc = (r.get("description") or "No description").strip()[:180]
        line = (
            f"**[{r['full_name']}]({r['html_url']})** \u2b50 {r['stargazers_count']}"
            f" \u00b7 {r.get('language') or 'N/A'}  \n  {desc}"
        )
        out.append((r["html_url"], line))
    return out


def fetch_devto(tag):
    url = f"https://dev.to/api/articles?tag={tag}&top=7&per_page=25"
    items = get_json(url)
    out = []
    for a in items:
        desc = (a.get("description") or "").strip()[:180]
        line = (
            f"**[{a['title']}]({a['url']})** by {a['user']['name']}"
            f" \u00b7 \u2764\ufe0f {a.get('positive_reactions_count', 0)}  \n  {desc}"
        )
        out.append((a["url"], line))
    return out


FETCHERS = {
    "trending-projects": fetch_trending_repos,
    "articles": lambda: fetch_devto("programming"),
    "ai": lambda: fetch_devto("ai"),
    "coding-tips": lambda: fetch_devto("tutorial"),
    "languages": lambda: fetch_devto(random.choice(LANG_TAGS)),
}

# --------------------------------------------------------------------------------------


def run(*cmd):
    r = subprocess.run(
        cmd, cwd=REPO, capture_output=True, text=True,
        encoding="utf-8", errors="replace",
    )
    if r.returncode != 0:
        print((r.stderr or "").strip() or (r.stdout or "").strip())
        sys.exit(1)
    return (r.stdout or "").strip()


def main():
    used = json.loads(USED.read_text(encoding="utf-8")) if USED.exists() else {}
    used_ids = set(used.get("ids", []))

    categories = list(FETCHERS.keys())
    random.shuffle(categories)

    picked = None
    for category in categories:
        try:
            candidates = [(uid, line) for uid, line in FETCHERS[category]() if uid not in used_ids]
        except Exception as e:
            print(f"  ({category} source unavailable: {e})")
            continue
        if candidates:
            picked = (category, *random.choice(candidates))
            break

    if not picked:
        print("No new content found from any source right now. Try again later.")
        sys.exit(0)

    category, uid, line = picked

    target = FILES[category]
    if not target.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(HEADERS[category], encoding="utf-8")
    with target.open("a", encoding="utf-8") as f:
        f.write(f"\n- **{date.today().isoformat()}** \u2014 {line}\n")

    used_ids.add(uid)
    used["ids"] = sorted(used_ids)
    USED.write_text(json.dumps(used, indent=2), encoding="utf-8")

    # short ASCII-only commit message
    title = line.split("](")[0].replace("**[", "").replace("**", "")
    title = title.encode("ascii", "ignore").decode().strip()[:60]
    run("git", "add", "-A")
    run("git", "commit", "-m", f"{COMMIT_PREFIX[category]}: add {title}")
    run("git", "push", "origin", "main")

    print(f"OK  Added to {category}: {title}")


if __name__ == "__main__":
    main()