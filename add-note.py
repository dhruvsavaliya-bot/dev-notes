#!/usr/bin/env python3
"""
dev-notes trigger (LIVE + quality-filtered + detailed entries)

Every run fetches something NEW from the internet, with strict quality filters:
  - trending-projects : GitHub repos created this month with 200+ stars
  - articles          : dev.to weekly top posts, 50+ reactions, 3+ min read
  - ai / coding-tips / languages : same filters, topic-specific tags

Each entry is a detailed multi-line block: title, author, stats, tags,
description, and link. Tracks used.json so nothing ever repeats.
Commits and pushes automatically. Python stdlib only.
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

# ---------------- quality thresholds (tune these anytime) ----------------
MIN_REACTIONS = 50        # dev.to: minimum hearts on a post
MIN_READ_MINUTES = 3      # dev.to: skip short listicles
MIN_STARS = 200           # GitHub: minimum stars for a trending repo
TREND_WINDOW_DAYS = 30    # GitHub: how recent a repo must be
# --------------------------------------------------------------------------

FILES = {
    "coding-tips": REPO / "coding-tips" / "tips.md",
    "languages": REPO / "languages" / "notes.md",
    "ai": REPO / "ai" / "notes.md",
    "trending-projects": REPO / "trending-projects" / "projects.md",
    "articles": REPO / "articles" / "reading-list.md",
}

HEADERS = {
    "coding-tips": "# Coding Tips & Tutorials\n\nHigh-quality tutorials, added over time.\n",
    "languages": "# Language Notes\n\nTop posts about programming languages.\n",
    "ai": "# AI / LLM Notes\n\nThe best recent AI and LLM articles.\n",
    "trending-projects": "# Trending Projects\n\nOpen-source repos blowing up on GitHub.\n",
    "articles": "# Reading List\n\nThe week's best dev articles.\n",
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


# ------------- fetchers: each returns list of (uid, detailed_md_block) -------------

def fetch_trending_repos():
    since = (date.today() - timedelta(days=TREND_WINDOW_DAYS)).isoformat()
    url = (
        "https://api.github.com/search/repositories"
        f"?q=created:>{since}+stars:>{MIN_STARS}&sort=stars&order=desc&per_page=30"
    )
    out = []
    for r in get_json(url).get("items", []):
        desc = (r.get("description") or "No description provided.").strip()
        topics = ", ".join(r.get("topics", [])[:6]) or "none listed"
        created = (r.get("created_at") or "")[:10]
        block = (
            f"### [{r['full_name']}]({r['html_url']})\n"
            f"  - Stars: {r['stargazers_count']:,} | Forks: {r['forks_count']:,}"
            f" | Language: {r.get('language') or 'N/A'} | Created: {created}\n"
            f"  - Topics: {topics}\n"
            f"  - What it is: {desc}\n"
            f"  - Why it matters: gained {r['stargazers_count']:,} stars in under"
            f" {TREND_WINDOW_DAYS} days, one of the fastest-growing new repos on GitHub right now."
        )
        out.append((r["html_url"], block))
    return out


def fetch_devto(tag):
    url = f"https://dev.to/api/articles?tag={tag}&top=7&per_page=30"
    out = []
    for a in get_json(url):
        reactions = a.get("positive_reactions_count", 0)
        mins = a.get("reading_time_minutes", 0)
        if reactions < MIN_REACTIONS or mins < MIN_READ_MINUTES:
            continue  # quality gate
        desc = (a.get("description") or "").strip()
        tags = ", ".join(a.get("tag_list", [])[:6])
        pub = (a.get("readable_publish_date") or "").strip()
        comments = a.get("comments_count", 0)
        block = (
            f"### [{a['title']}]({a['url']})\n"
            f"  - Author: {a['user']['name']} | Published: {pub}"
            f" | Read time: {mins} min\n"
            f"  - Community: {reactions} reactions, {comments} comments"
            f" (top-rated this week in #{tag})\n"
            f"  - Tags: {tags}\n"
            f"  - Summary: {desc}"
        )
        out.append((a["url"], block))
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
            candidates = [(u, b) for u, b in FETCHERS[category]() if u not in used_ids]
        except Exception as e:
            print(f"  ({category} source unavailable: {e})")
            continue
        if candidates:
            picked = (category, *random.choice(candidates))
            break

    if not picked:
        print("No new content passed the quality filters right now. Try again later.")
        sys.exit(0)

    category, uid, block = picked

    target = FILES[category]
    if not target.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(HEADERS[category], encoding="utf-8")
    with target.open("a", encoding="utf-8") as f:
        f.write(f"\n---\n\n**Added {date.today().isoformat()}**\n\n{block}\n")

    used_ids.add(uid)
    used["ids"] = sorted(used_ids)
    USED.write_text(json.dumps(used, indent=2), encoding="utf-8")

    title = block.split("](")[0].replace("### [", "")
    title = title.encode("ascii", "ignore").decode().strip()[:60]
    run("git", "add", "-A")
    run("git", "commit", "-m", f"{COMMIT_PREFIX[category]}: add {title}")
    run("git", "push", "origin", "main")

    print(f"OK  Added to {category}: {title}")


if __name__ == "__main__":
    main()