#!/usr/bin/env python3
"""
dev-notes trigger (LIVE + subcategories + detailed entries)

Every run:
  1. Picks a random category, then a random SUBCATEGORY inside it
     (e.g. ai -> "Gen AI" / "LLMs" / "Machine Learning")
  2. Fetches fresh, strictly dev-related content for that subcategory
     (GitHub API + dev.to topic tags, quality-filtered)
  3. Files the entry under the matching "## Subcategory" headline
     inside that category's markdown file (creates headline if new)
  4. Commits and pushes. Never repeats an item (tracked in used.json).

Python stdlib only. Quality thresholds at the top.
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

# ---------------- quality thresholds (tune anytime) ----------------
MIN_REACTIONS = 50        # dev.to: minimum hearts
MIN_READ_MINUTES = 3      # dev.to: skip short listicles
MIN_STARS = 200           # GitHub: minimum stars
TREND_WINDOW_DAYS = 30    # GitHub: repo must be created within this window
# ---------------------------------------------------------------------

FILES = {
    "coding-tips": REPO / "coding-tips" / "tips.md",
    "languages": REPO / "languages" / "notes.md",
    "ai": REPO / "ai" / "notes.md",
    "trending-projects": REPO / "trending-projects" / "projects.md",
    "articles": REPO / "articles" / "reading-list.md",
}

TITLES = {
    "coding-tips": "# Coding Tips & Tutorials\n\nHigh-quality dev tutorials and guides, organized by level and topic.\n",
    "languages": "# Language Notes\n\nTop community posts, organized by programming language.\n",
    "ai": "# AI / LLM Notes\n\nThe best recent AI engineering content, organized by area.\n",
    "trending-projects": "# Trending Projects\n\nFast-growing open-source repos, organized by domain.\n",
    "articles": "# Reading List\n\nThe week's best dev articles, organized by field.\n",
}

COMMIT_PREFIX = {
    "coding-tips": "tip",
    "languages": "lang",
    "ai": "ai",
    "trending-projects": "project",
    "articles": "article",
}

# subcategory headline -> dev.to tag (all strictly programming topics)
SUBCATS = {
    "ai": {
        "Gen AI": "generativeai",
        "LLMs": "llm",
        "Machine Learning": "machinelearning",
        "AI Engineering": "ai",
    },
    "coding-tips": {
        "Beginner": "beginners",
        "Clean Code & Best Practices": "cleancode",
        "Productivity": "productivity",
    },
    "languages": {
        "Python": "python",
        "JavaScript": "javascript",
        "TypeScript": "typescript",
        "Go": "go",
        "Rust": "rust",
        "Java": "java",
        "SQL & Databases": "sql",
    },
    "articles": {
        "Web Development": "webdev",
        "Backend": "backend",
        "DevOps & Cloud": "devops",
        "Security": "security",
        "System Design & Architecture": "architecture",
    },
}

UA = {"User-Agent": "dev-notes-script"}


def get_json(url):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read().decode("utf-8"))


# ------------- fetchers: return list of (uid, subcategory, md_block) -------------

def repo_subcat(r):
    """Classify a GitHub repo into a domain headline."""
    text = " ".join([
        (r.get("description") or "").lower(),
        " ".join(r.get("topics", [])).lower(),
        (r.get("language") or "").lower(),
    ])
    if any(k in text for k in ("llm", " ai ", "ai-", "agent", "gpt", "machine-learning", "ml ", "neural", "rag")):
        return "AI & Machine Learning"
    if any(k in text for k in ("react", "frontend", "css", "ui ", "vue", "nextjs", "web app", "browser")):
        return "Web & Frontend"
    if any(k in text for k in ("cli", "terminal", "devtool", "editor", "vscode", "productivity", "build")):
        return "Developer Tools"
    if any(k in text for k in ("database", "backend", "api", "server", "kubernetes", "docker", "cloud")):
        return "Backend & Infrastructure"
    return "Other Cool Projects"


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
        stars_per_day = r["stargazers_count"] // max(
            1, (date.today() - date.fromisoformat(created)).days
        )
        block = (
            f"### [{r['full_name']}]({r['html_url']})\n"
            f"- **Stats:** {r['stargazers_count']:,} stars | {r['forks_count']:,} forks"
            f" | {r.get('open_issues_count', 0):,} open issues\n"
            f"- **Language:** {r.get('language') or 'N/A'} | **Created:** {created}"
            f" | **License:** {(r.get('license') or {}).get('spdx_id', 'None')}\n"
            f"- **Topics:** {topics}\n"
            f"- **What it is:** {desc}\n"
            f"- **Growth:** averaging ~{stars_per_day:,} stars/day since launch —"
            f" one of the fastest-growing new repos on GitHub right now.\n"
            f"- **Link:** {r['html_url']}"
        )
        out.append((r["html_url"], repo_subcat(r), block))
    return out


def fetch_devto(tag, subcat_name):
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
        block = (
            f"### [{a['title']}]({a['url']})\n"
            f"- **Author:** {a['user']['name']} | **Published:** {pub}"
            f" | **Read time:** {mins} min\n"
            f"- **Community:** {reactions} reactions, {a.get('comments_count', 0)} comments"
            f" — a top post of the week in #{tag}\n"
            f"- **Tags:** {tags}\n"
            f"- **Summary:** {desc}\n"
            f"- **Link:** {a['url']}"
        )
        out.append((a["url"], subcat_name, block))
    return out


MIN_HN_POINTS = 100  # Hacker News: minimum upvotes


def fetch_hackernews():
    """Front-page HN stories - the most heavily curated dev content anywhere."""
    url = "https://hn.algolia.com/api/v1/search?tags=front_page&hitsPerPage=30"
    out = []
    for h in get_json(url).get("hits", []):
        points = h.get("points") or 0
        if points < MIN_HN_POINTS:
            continue  # quality gate
        story_url = h.get("url") or f"https://news.ycombinator.com/item?id={h['objectID']}"
        domain = story_url.split("/")[2] if "://" in story_url else "news.ycombinator.com"
        hn_link = f"https://news.ycombinator.com/item?id={h['objectID']}"
        created = (h.get("created_at") or "")[:10]
        block = (
            f"### [{h['title']}]({story_url})\n"
            f"- **Source:** {domain} | **Posted:** {created} | **By:** {h.get('author', 'unknown')}\n"
            f"- **Community:** {points} points, {h.get('num_comments', 0)} comments"
            f" on Hacker News front page\n"
            f"- **Why it's here:** HN front page is the most competitive dev content"
            f" filter on the internet - only ~30 stories/day make it out of thousands.\n"
            f"- **Discussion:** {hn_link}\n"
            f"- **Link:** {story_url}"
        )
        out.append((hn_link, "Hacker News Picks", block))
    return out


def make_devto_fetcher(category):
    def fetch():
        name, tag = random.choice(list(SUBCATS[category].items()))
        return fetch_devto(tag, name)
    return fetch


def mixed_fetcher(category, hn_chance):
    """Sometimes pull from Hacker News instead of dev.to for extra quality."""
    devto = make_devto_fetcher(category)

    def fetch():
        if random.random() < hn_chance:
            return fetch_hackernews()
        return devto()
    return fetch


FETCHERS = {
    "trending-projects": fetch_trending_repos,
    "articles": mixed_fetcher("articles", hn_chance=0.5),
    "ai": make_devto_fetcher("ai"),
    "coding-tips": mixed_fetcher("coding-tips", hn_chance=0.35),
    "languages": make_devto_fetcher("languages"),
}

# --------------------------------------------------------------------------------------


def insert_under_headline(path, title_block, subcat, entry):
    """Place entry under '## subcat' inside the file, creating file/headline as needed."""
    if path.exists():
        text = path.read_text(encoding="utf-8")
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        text = title_block

    stamped = f"\n**Added {date.today().isoformat()}**\n\n{entry}\n"
    headline = f"## {subcat}"

    if headline in text:
        # insert at the end of this section (before next '## ' or EOF)
        start = text.index(headline)
        nxt = text.find("\n## ", start + len(headline))
        if nxt == -1:
            text = text.rstrip() + "\n" + stamped
        else:
            text = text[:nxt].rstrip() + "\n" + stamped + "\n" + text[nxt:]
    else:
        text = text.rstrip() + f"\n\n{headline}\n" + stamped

    path.write_text(text, encoding="utf-8")


def notify(msg):
    """Non-blocking Windows popup (auto-closes in 10s). Silent no-op elsewhere."""
    try:
        subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             f"(New-Object -ComObject Wscript.Shell).Popup('{msg}',10,'dev-notes',48)"],
            capture_output=True, timeout=15,
        )
    except Exception:
        pass


def fail(context, detail):
    print(f"FAILED at {context}: {detail}")
    notify(f"dev-notes failed at {context}. Check .content/auto-log.txt")
    sys.exit(1)


def run(*cmd):
    r = subprocess.run(
        cmd, cwd=REPO, capture_output=True, text=True,
        encoding="utf-8", errors="replace",
    )
    if r.returncode != 0:
        fail(" ".join(cmd[:2]), (r.stderr or r.stdout or "").strip()[:300])
    return (r.stdout or "").strip()


README_ORDER = ["trending-projects", "ai", "articles", "coding-tips", "languages"]
README_LABELS = {
    "trending-projects": "Trending Projects",
    "ai": "AI / LLM Notes",
    "articles": "Reading List",
    "coding-tips": "Coding Tips",
    "languages": "Language Notes",
}


def update_readme(recent):
    counts = {}
    for cat, path in FILES.items():
        counts[cat] = path.read_text(encoding="utf-8").count("### [") if path.exists() else 0
    total = sum(counts.values())

    rows = "\n".join(
        f"| [{README_LABELS[c]}]({FILES[c].relative_to(REPO).as_posix()}) | {counts[c]} |"
        for c in README_ORDER
    )
    latest = "\n".join(
        f"- **{e['date']}** \u00b7 *{e['subcat']}* \u2014 [{e['title']}]({e['url']})"
        for e in reversed(recent[-3:])
    ) or "- (first entries coming soon)"

    readme = (
        "# \U0001F4DA dev-notes\n\n"
        "Auto-curated developer knowledge base \u2014 fresh content added **twice daily**\n"
        "from GitHub Trending, Hacker News (100+ points), and dev.to's top posts.\n\n"
        f"**{total} entries and counting** \u00b7 Last updated: {date.today().isoformat()}\n\n"
        "## Categories\n\n"
        "| Section | Entries |\n|---|---|\n"
        f"{rows}\n\n"
        "## Latest additions\n\n"
        f"{latest}\n\n"
        "## How it works\n\n"
        "A Python script runs on a schedule, pulls the highest-signal new dev content\n"
        "(quality-filtered by stars, points, and reactions), files each item under a\n"
        "topic headline, and commits it here. No duplicates \u2014 every entry is tracked.\n"
    )
    (REPO / "README.md").write_text(readme, encoding="utf-8")


def sync():
    """Pull latest, tolerating a dirty working tree.

    An unattended run must never wedge itself on leftover uncommitted
    changes (a manual edit, a half-finished run). If the tree is dirty we
    stash those changes aside — recoverable with `git stash list` — and
    proceed, rather than letting `git pull --rebase` abort the whole run.
    """
    if run("git", "status", "--porcelain"):
        print("  (working tree dirty at start; stashing aside before pull)")
        run("git", "stash", "push", "-u", "-m", "dev-notes auto-stash before sync")
    run("git", "pull", "--rebase", "origin", "main")


def main():
    # sync first so edits made elsewhere (e.g. GitHub web) never break the push
    sync()

    used = json.loads(USED.read_text(encoding="utf-8")) if USED.exists() else {}
    used_ids = set(used.get("ids", []))

    categories = list(FETCHERS.keys())
    random.shuffle(categories)

    picked = None
    for category in categories:
        try:
            candidates = [
                (u, s, b) for u, s, b in FETCHERS[category]() if u not in used_ids
            ]
        except Exception as e:
            print(f"  ({category} source unavailable: {e})")
            continue
        if candidates:
            picked = (category, *random.choice(candidates))
            break

    if not picked:
        print("No new content passed the quality filters right now. Try again later.")
        sys.exit(0)

    category, uid, subcat, block = picked

    insert_under_headline(FILES[category], TITLES[category], subcat, block)

    title = block.split("](")[0].replace("### [", "")
    title = title.encode("ascii", "ignore").decode().strip()[:55]

    # track recent entries + refresh README dashboard
    recent = used.get("recent", [])
    recent.append({
        "date": date.today().isoformat(),
        "subcat": subcat,
        "title": title,
        "url": uid,
    })
    used["recent"] = recent[-10:]

    used_ids.add(uid)
    used["ids"] = sorted(used_ids)
    USED.write_text(json.dumps(used, indent=2), encoding="utf-8")

    update_readme(used["recent"])

    run("git", "add", "-A")
    run("git", "commit", "-m", f"{COMMIT_PREFIX[category]}: [{subcat}] {title}")
    run("git", "push", "origin", "main")

    print(f"OK  {category} -> {subcat}: {title}")


if __name__ == "__main__":
    main()