#!/usr/bin/env python3
"""
dev-notes trigger (multi-source, multi-entry, target-driven)

Every run:
  1. Syncs with origin, then works out how many commits today still needs
     to reach the day's target -- DAILY_TARGET on weekdays, WEEKEND_TARGET on
     weekends, jittered per date (never more than MAX_PER_RUN in one run)
  2. Gathers candidates from every source that will answer -- GitHub search,
     Hacker News, Lobsters, dev.to, arXiv, Hugging Face -- relaxing the
     quality bar only if the fresh pool comes up short
  3. Files each entry under its matching "## Subcategory" headline and makes
     ONE COMMIT PER ENTRY, then pushes the whole batch once
  4. Never repeats an item (tracked in used.json), and never lets a day end
     with zero commits (heartbeat fallback when every source is down)

Two runners share the target: a GitHub Actions cron and the local Task
Scheduler job. Whichever runs first does the work; the other tops up the
remainder and no-ops once the day's target is met.

Python stdlib only. Every knob below has a DEVNOTES_* environment override.
"""

import gzip
import json
import os
import random
import re
import subprocess
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta
from pathlib import Path

REPO = Path(__file__).parent
USED = REPO / ".content" / "used.json"
PULSE = REPO / ".content" / "pulse.md"
ARCHIVE = REPO / "archive"

# How many recent entries used.json carries (feeds README "Latest additions").
RECENT_KEEP = 10

# The two files both runners rewrite on EVERY run: a count line and a rolling
# list. A conflict here is never a real disagreement -- there is nothing to
# choose between the sides -- so an unattended run settles it itself instead of
# dying at sync. Note files are union-merged by git (.gitattributes); anything
# outside this set is a genuine conflict and still stops the run for a human.
AUTO_RESOLVABLE = {".content/used.json", "README.md"}


def envint(name, default):
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return default


# ---------------- volume knobs (tune anytime) ----------------
DAILY_TARGET = envint("DEVNOTES_DAILY_TARGET", 42)           # Mon-Fri target
WEEKEND_TARGET = envint("DEVNOTES_WEEKEND_TARGET", 24)      # Sat/Sun target
TARGET_JITTER = envint("DEVNOTES_JITTER", 6)                # +/- spread, weekdays
WEEKEND_JITTER = envint("DEVNOTES_WEEKEND_JITTER", 4)       # +/- spread, weekends
MAX_PER_RUN = envint("DEVNOTES_MAX_PER_RUN", 8)             # ceiling for a single run
MAX_ENTRIES_PER_FILE = envint("DEVNOTES_MAX_ENTRIES", 400)  # rotate past this
PACE = os.environ.get("DEVNOTES_PACE", "1") != "0"          # spread target across the day
CATCHUP_AFTER = 0.83                                        # ~20:00: drop pacing, go for target

# ---------------- quality thresholds (tune anytime) ----------------
MIN_REACTIONS = 50        # dev.to: minimum hearts
MIN_READ_MINUTES = 3      # dev.to: skip short listicles
MIN_STARS = 200           # GitHub: minimum stars for brand-new repos
MIN_HN_POINTS = 100       # Hacker News: minimum upvotes
MIN_LOBSTERS_SCORE = 15   # Lobsters: minimum score
MIN_HF_LIKES = 50         # Hugging Face: minimum likes
# -------------------------------------------------------------------

# ---------------- recency windows (days; tune anytime) ----------------
# "Fresh content" is the one thing this repo promises, and most sources will
# happily serve their all-time greatest hits instead: a popularity sort reaches
# back years, and paging deep into a points-filtered archive lands in 2017.
# Every source that ranks by popularity gets an age bound here.
GH_NEW_DAYS = envint("DEVNOTES_GH_NEW_DAYS", 30)        # "brand new" repos
GH_RISING_DAYS = envint("DEVNOTES_GH_RISING_DAYS", 90)  # young, with traction
GH_ACTIVE_DAYS = envint("DEVNOTES_GH_ACTIVE_DAYS", 180)  # pushed lately, not ancient
GH_TOPIC_DAYS = envint("DEVNOTES_GH_TOPIC_DAYS", 365)   # topic sweep: had no bound
GH_LANG_DAYS = envint("DEVNOTES_GH_LANG_DAYS", 180)     # language sweep
HN_STORY_DAYS = envint("DEVNOTES_HN_DAYS", 30)          # deep/show/ask paging
HF_MAX_AGE_DAYS = envint("DEVNOTES_HF_DAYS", 180)       # Hugging Face models/datasets
# ----------------------------------------------------------------------


def bar(value, relax):
    """A threshold, halved for each relaxation round. Never drops below 1."""
    return max(1, int(value * (0.5 ** relax)))


def window(days, relax):
    """A recency window in days, doubled for each relaxation round.

    The mirror image of bar(): where a quality threshold comes down when the
    fresh pool is short, a date window opens up. Both exist so that a run which
    cannot fill itself from this week's content widens its reach rather than
    returning nothing -- the daily target is the thing that must not slip.
    """
    return max(1, days * (2 ** relax))


def since(days, relax):
    """ISO date for a GitHub `created:>` / `pushed:>` bound."""
    return (date.today() - timedelta(days=window(days, relax))).isoformat()


def epoch_since(days, relax):
    """Unix timestamp for a Hacker News `created_at_i>` numeric filter."""
    return int((datetime.now() - timedelta(days=window(days, relax))).timestamp())


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
        "Data Science": "datascience",
        "Computer Vision": "computervision",
    },
    "coding-tips": {
        "Beginner": "beginners",
        "Clean Code & Best Practices": "cleancode",
        "Productivity": "productivity",
        "Testing": "testing",
        "Git & Workflow": "git",
        "Career & Craft": "career",
    },
    "languages": {
        "Python": "python",
        "JavaScript": "javascript",
        "TypeScript": "typescript",
        "Go": "go",
        "Rust": "rust",
        "Java": "java",
        "SQL & Databases": "sql",
        "C++": "cpp",
        "C#": "csharp",
        "PHP": "php",
        "Ruby": "ruby",
        "Kotlin": "kotlin",
        "Swift": "swift",
        "Elixir": "elixir",
    },
    "articles": {
        "Web Development": "webdev",
        "Backend": "backend",
        "DevOps & Cloud": "devops",
        "Security": "security",
        "System Design & Architecture": "architecture",
        "Performance": "performance",
        "Open Source": "opensource",
    },
}

UA = {"User-Agent": "dev-notes-script", "Accept-Encoding": "gzip"}


def http_get(url, extra_headers=None):
    headers = dict(UA)
    if extra_headers:
        headers.update(extra_headers)
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=20) as r:
        raw = r.read()
        if r.headers.get("Content-Encoding") == "gzip":
            raw = gzip.decompress(raw)
        return raw


def get_json(url, extra_headers=None):
    return json.loads(http_get(url, extra_headers).decode("utf-8", "replace"))


def gh_headers():
    """Authenticate GitHub search when a token is around (5000/hr vs 10/min)."""
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    return {"Authorization": f"Bearer {token}"} if token else None


# ======================================================================
# sources: each is called with a relax level and returns a list of
# (uid, subcategory, markdown_block) triples
# ======================================================================

def repo_subcat(r):
    """Classify a GitHub repo into a domain headline."""
    text = " ".join([
        (r.get("description") or "").lower(),
        " ".join(r.get("topics", [])).lower(),
        (r.get("language") or "").lower(),
    ])
    if any(k in text for k in ("llm", " ai ", "ai-", "agent", "gpt", "machine-learning", "ml ", "neural", "rag", "diffusion")):
        return "AI & Machine Learning"
    if any(k in text for k in ("react", "frontend", "css", "ui ", "vue", "nextjs", "web app", "browser", "svelte")):
        return "Web & Frontend"
    if any(k in text for k in ("cli", "terminal", "devtool", "editor", "vscode", "productivity", "build", "linter")):
        return "Developer Tools"
    if any(k in text for k in ("database", "backend", "api", "server", "kubernetes", "docker", "cloud", "queue")):
        return "Backend & Infrastructure"
    if any(k in text for k in ("security", "crypto", "pentest", "vulnerab", "exploit", "malware")):
        return "Security"
    return "Other Cool Projects"


def repo_block(r):
    desc = (r.get("description") or "No description provided.").strip()
    topics = ", ".join(r.get("topics", [])[:6]) or "none listed"
    created = (r.get("created_at") or "")[:10]
    try:
        age = max(1, (date.today() - date.fromisoformat(created)).days)
    except ValueError:
        age = 1
    stars_per_day = r["stargazers_count"] // age
    return (
        f"### [{r['full_name']}]({r['html_url']})\n"
        f"- **Stats:** {r['stargazers_count']:,} stars | {r['forks_count']:,} forks"
        f" | {r.get('open_issues_count', 0):,} open issues\n"
        f"- **Language:** {r.get('language') or 'N/A'} | **Created:** {created or 'unknown'}"
        f" | **License:** {(r.get('license') or {}).get('spdx_id', 'None')}\n"
        f"- **Topics:** {topics}\n"
        f"- **What it is:** {desc}\n"
        f"- **Growth:** averaging ~{stars_per_day:,} stars/day since launch.\n"
        f"- **Link:** {r['html_url']}"
    )


GH_TOPICS = [
    "cli", "llm", "agents", "rag", "compiler", "devops", "kubernetes", "react",
    "typescript", "rust", "golang", "database", "observability", "testing",
    "security", "wasm", "graphics", "embedded", "api", "self-hosted",
]
GH_LANGS = [
    "Python", "JavaScript", "TypeScript", "Go", "Rust", "Java", "C++", "C#",
    "Ruby", "Swift", "Kotlin", "Zig", "Elixir", "Lua", "Haskell",
]


# Unauthenticated GitHub search allows 10 requests/minute. Relaxation rounds can
# ask for more than that, and the 403 it returns looks like an outage rather than
# a quota. Spend a deliberate budget instead, so GitHub sources bow out cleanly
# and the other five sources still fill the run.
GH_CALL_BUDGET = envint("DEVNOTES_GH_CALLS", 50 if (os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")) else 8)
_gh_calls = 0


def gh_page(query, sort, page):
    global _gh_calls
    if _gh_calls >= GH_CALL_BUDGET:
        raise RuntimeError(f"GitHub search budget spent ({GH_CALL_BUDGET} calls/run)")
    _gh_calls += 1
    url = (
        "https://api.github.com/search/repositories?q="
        + urllib.parse.quote(query)
        + f"&sort={sort}&order=desc&per_page=50&page={page}"
    )
    return get_json(url, gh_headers())


def gh_items(query, sort="stars"):
    """Page 1, plus a random deeper page that actually exists.

    Guessing a page number blind returned nothing whenever the result set was
    smaller than the guess -- `language:Elixir` has two matching repos, not 250.
    Page 1's total_count tells us how deep we may go (search caps at 1000).
    """
    first = gh_page(query, sort, 1)
    items = list(first.get("items", []))
    pages = max(1, -(-min(first.get("total_count", 0), 1000) // 50))
    if pages > 1:
        items += gh_page(query, sort, random.randint(2, min(pages, 10))).get("items", [])
    return items


def gh_search(query, sort="stars"):
    return [(r["html_url"], repo_subcat(r), repo_block(r)) for r in gh_items(query, sort)]


def src_gh_new(relax):
    return gh_search(
        f"created:>{since(GH_NEW_DAYS, relax)} stars:>{bar(MIN_STARS, relax)}")


def src_gh_rising(relax):
    return gh_search(
        f"created:>{since(GH_RISING_DAYS, relax)} stars:>{bar(500, relax)}")


def src_gh_active(relax):
    # `pushed:` alone matches every maintained repo on GitHub, which is how
    # decade-old projects ended up filed under "Trending Projects". Pair it with
    # a creation bound so this stays "young repo still moving", not "repo alive".
    pushed = (date.today() - timedelta(days=7)).isoformat()
    return gh_search(
        f"pushed:>{pushed} created:>{since(GH_ACTIVE_DAYS, relax)}"
        f" stars:>{bar(2000, relax)}", sort="updated")


def src_gh_topic(relax):
    topic = random.choice(GH_TOPICS)
    return gh_search(
        f"topic:{topic} created:>{since(GH_TOPIC_DAYS, relax)}"
        f" stars:>{bar(300, relax)}")


def src_gh_lang(relax):
    lang = random.choice(GH_LANGS)
    return gh_search(
        f"language:{lang} created:>{since(GH_LANG_DAYS, relax)}"
        f" stars:>{bar(300, relax)}")


def hn_block(h, subcat):
    points = h.get("points") or 0
    story_url = h.get("url") or f"https://news.ycombinator.com/item?id={h['objectID']}"
    domain = story_url.split("/")[2] if "://" in story_url else "news.ycombinator.com"
    hn_link = f"https://news.ycombinator.com/item?id={h['objectID']}"
    created = (h.get("created_at") or "")[:10]
    title = (h.get("title") or h.get("story_title") or "Untitled").strip()
    block = (
        f"### [{title}]({story_url})\n"
        f"- **Source:** {domain} | **Posted:** {created} | **By:** {h.get('author', 'unknown')}\n"
        f"- **Community:** {points} points, {h.get('num_comments', 0)} comments on Hacker News\n"
        f"- **Why it's here:** it cleared the Hacker News points bar, the most"
        f" competitive dev content filter on the internet.\n"
        f"- **Discussion:** {hn_link}\n"
        f"- **Link:** {story_url}"
    )
    return (hn_link, subcat, block)


def hn_page(query, page):
    return get_json(f"https://hn.algolia.com/api/v1/search?{query}&page={page}")


def hn_search(query, min_points, subcat, deep=0):
    """Page 0, plus one random deeper page that actually exists.

    The trap gh_items() documents applies here too: a blind page number
    returns nothing whenever the result set is smaller than the guess. Bounding
    these searches by story age shrank every result set -- "Show HN above 60
    points in the last month" is a couple of pages deep, not twelve -- so the
    reply's nbPages decides how far the paging may reach.
    """
    first = hn_page(query, 0)
    hits = list(first.get("hits", []))
    pages = max(1, int(first.get("nbPages") or 1))
    if deep and pages > 1:
        hits += hn_page(query, random.randint(1, min(pages - 1, deep))).get("hits", [])

    out = []
    for h in hits:
        if not (h.get("title") or h.get("story_title")):
            continue
        if (h.get("points") or 0) < min_points:
            continue
        out.append(hn_block(h, subcat))
    return out


def src_hn_front(relax):
    # The live front page is one page long and inherently fresh: no paging, no
    # age bound -- whatever is on it right now is the point.
    return hn_search("tags=front_page&hitsPerPage=50", bar(MIN_HN_POINTS, relax), "Hacker News Picks")


# Paging deep into a points-filtered search walks backwards through the whole
# archive -- page 24 of "stories over 100 points" is years old. created_at_i
# keeps the paging inside the recency window instead of inside all of history.
def src_hn_deep(relax):
    pts = bar(MIN_HN_POINTS, relax)
    return hn_search(
        f"tags=story&numericFilters=points>{pts},"
        f"created_at_i>{epoch_since(HN_STORY_DAYS, relax)}"
        f"&hitsPerPage=50",
        pts, "Hacker News Picks", deep=24,
    )


def src_hn_show(relax):
    pts = bar(60, relax)
    return hn_search(
        f"tags=show_hn&numericFilters=points>{pts},"
        f"created_at_i>{epoch_since(HN_STORY_DAYS, relax)}"
        f"&hitsPerPage=50",
        pts, "Show & Ask HN", deep=12,
    )


def src_hn_ask(relax):
    pts = bar(60, relax)
    return hn_search(
        f"tags=ask_hn&numericFilters=points>{pts},"
        f"created_at_i>{epoch_since(HN_STORY_DAYS, relax)}"
        f"&hitsPerPage=50",
        pts, "Show & Ask HN", deep=12,
    )


LOBSTERS_TAGS = [
    "programming", "python", "rust", "javascript", "go", "devops", "ai",
    "security", "databases", "web", "compilers", "testing", "performance",
    "linux", "osdev", "distributed",
]
LOBSTERS_LANGS = {
    "python": "Python", "javascript": "JavaScript", "rust": "Rust",
    "go": "Go", "java": "Java", "ruby": "Ruby", "elixir": "Elixir",
}


def lobsters(url, min_score, subcat):
    out = []
    for s in get_json(url):
        if (s.get("score") or 0) < min_score:
            continue
        comments = s.get("comments_url") or ""
        if not comments:
            continue
        link = s.get("url") or comments
        tags = ", ".join(s.get("tags", [])[:6]) or "none listed"
        desc = (s.get("description_plain") or s.get("description") or "").strip()
        desc = (desc[:400] + "...") if len(desc) > 400 else (desc or "No summary provided.")
        domain = link.split("/")[2] if "://" in link else "lobste.rs"
        submitter = s.get("submitter_user")
        if isinstance(submitter, dict):
            submitter = submitter.get("username", "unknown")
        block = (
            f"### [{(s.get('title') or 'Untitled').strip()}]({link})\n"
            f"- **Source:** {domain} | **Posted:** {(s.get('created_at') or '')[:10]}"
            f" | **By:** {submitter or 'unknown'}\n"
            f"- **Community:** {s.get('score', 0)} score, {s.get('comment_count', 0)} comments on Lobsters\n"
            f"- **Tags:** {tags}\n"
            f"- **Summary:** {desc}\n"
            f"- **Discussion:** {comments}\n"
            f"- **Link:** {link}"
        )
        out.append((comments, subcat, block))
    return out


def src_lobsters_hot(relax):
    return lobsters("https://lobste.rs/hottest.json", bar(MIN_LOBSTERS_SCORE, relax), "Lobsters Picks")


def src_lobsters_new(relax):
    return lobsters("https://lobste.rs/newest.json", bar(MIN_LOBSTERS_SCORE, relax), "Lobsters Picks")


def src_lobsters_tag(relax):
    tag = random.choice(LOBSTERS_TAGS)
    return lobsters(f"https://lobste.rs/t/{tag}.json", bar(MIN_LOBSTERS_SCORE, relax), "Lobsters Picks")


def src_lobsters_lang(relax):
    tag, name = random.choice(list(LOBSTERS_LANGS.items()))
    return lobsters(f"https://lobste.rs/t/{tag}.json", bar(MIN_LOBSTERS_SCORE, relax), name)


# languages/ starved for years on dev.to alone (16 entries against trending's 177):
# its tags return almost nothing above the reaction bar. These two file GitHub
# repos and HN stories under the LANGUAGE headline rather than a domain one, which
# is what finally gives that category a pool worth picking from.
# headline -> (GitHub `language:` value or None, Hacker News search term).
# "SQL & Databases" has no GitHub language, hence the None -- asking for
# `language:SQL` returns a flat zero.
LANG_QUERIES = {
    "Python": ("Python", "python"),
    "JavaScript": ("JavaScript", "javascript"),
    "TypeScript": ("TypeScript", "typescript"),
    "Go": ("Go", "golang"),
    "Rust": ("Rust", "rust"),
    "Java": ("Java", "java"),
    "C++": ("C++", "c++"),
    "C#": ("C#", "c#"),
    "Ruby": ("Ruby", "ruby"),
    "Kotlin": ("Kotlin", "kotlin"),
    "Swift": ("Swift", "swift"),
    "Elixir": ("Elixir", "elixir"),
    "PHP": ("PHP", "php"),
    "SQL & Databases": (None, "sql database"),
}


def src_gh_lang_notes(relax):
    """GitHub repos filed under the language's own headline."""
    choices = [(n, gh) for n, (gh, _) in LANG_QUERIES.items() if gh]
    name, lang = random.choice(choices)
    query = (f'language:"{lang}" created:>{since(GH_LANG_DAYS, relax)}'
             f' stars:>{bar(400, relax)}')
    return [(r["html_url"], name, repo_block(r)) for r in gh_items(query)]


# Searching "java" on Hacker News returns JavaScript stories, and Algolia has no
# term exclusion to say otherwise -- so the headline screens its own false
# positives. Five of the first twenty "Java" entries were JavaScript posts.
LANG_REJECT = {"Java": re.compile(r"javascript|\.js\b", re.I)}


def src_hn_lang(relax):
    """Hacker News stories about one language, filed under its headline."""
    name, (_, term) = random.choice(list(LANG_QUERIES.items()))
    pts = bar(80, relax)
    hits = hn_search(
        f"query={urllib.parse.quote(term)}&tags=story"
        f"&numericFilters=points>{pts},"
        f"created_at_i>{epoch_since(HN_STORY_DAYS, relax)}"
        f"&hitsPerPage=50",
        pts, name, deep=8,
    )
    reject = LANG_REJECT.get(name)
    if reject:
        hits = [h for h in hits if not reject.search(h[2].split("](")[0])]
    return hits


ARXIV_CATS = ["cs.LG", "cs.CL", "cs.AI", "cs.SE", "cs.CR", "cs.DC", "cs.PL"]
ATOM = "{http://www.w3.org/2005/Atom}"


def src_arxiv(relax):
    cat = random.choice(ARXIV_CATS)
    # arXiv has no quality bar to relax -- reach deeper into the backlog instead
    start = random.randint(0, 300 * (relax + 1))
    url = (
        "https://export.arxiv.org/api/query?search_query=cat:" + cat
        + f"&sortBy=submittedDate&sortOrder=descending&start={start}&max_results=40"
    )
    root = ET.fromstring(http_get(url))
    out = []
    for e in root.findall(ATOM + "entry"):
        link = (e.findtext(ATOM + "id") or "").strip()
        title = " ".join((e.findtext(ATOM + "title") or "").split())
        if not link or not title:
            continue
        summary = " ".join((e.findtext(ATOM + "summary") or "").split())
        summary = (summary[:500] + "...") if len(summary) > 500 else (summary or "No abstract provided.")
        authors = [a.findtext(ATOM + "name") or "" for a in e.findall(ATOM + "author")]
        cats = [c.get("term") for c in e.findall(ATOM + "category") if c.get("term")]
        block = (
            f"### [{title}]({link})\n"
            f"- **Authors:** {', '.join(authors[:4]) or 'unknown'}"
            f"{' et al.' if len(authors) > 4 else ''}\n"
            f"- **Published:** {(e.findtext(ATOM + 'published') or '')[:10]}"
            f" | **Primary category:** {cat}\n"
            f"- **Categories:** {', '.join(cats[:6]) or cat}\n"
            f"- **Abstract:** {summary}\n"
            f"- **Why it's here:** fresh off arXiv {cat} -- where the research"
            f" behind next year's tooling shows up first.\n"
            f"- **Link:** {link}"
        )
        out.append((link, "Research Papers", block))
    return out


def hf_block(item, kind):
    ident = item.get("id") or item.get("modelId") or ""
    if not ident:
        return None
    url = f"https://huggingface.co/{'datasets/' if kind == 'dataset' else ''}{ident}"
    tags = [t for t in item.get("tags", []) if ":" not in t][:6]
    block = (
        f"### [{ident}]({url})\n"
        f"- **Stats:** {item.get('likes', 0):,} likes | {item.get('downloads', 0):,} downloads\n"
        f"- **Kind:** Hugging Face {kind} | **Task:** {item.get('pipeline_tag') or 'n/a'}"
        f" | **Created:** {(item.get('createdAt') or '')[:10]}\n"
        f"- **Tags:** {', '.join(tags) or 'none listed'}\n"
        f"- **What it is:** a {kind} on the Hugging Face Hub with real community"
        f" pull -- useful when you need something that already works.\n"
        f"- **Link:** {url}"
    )
    return (url, "Models & Datasets", block)


def hf_fetch(endpoint, kind, min_likes, relax):
    """Models/datasets with community pull that are also actually new.

    `likes` and `downloads` are all-time totals, so sorting by either returns
    the Hub's greatest hits -- which is how year-old models got filed under a
    "fresh content" banner. trendingScore is Hugging Face's own recency-weighted
    ranking, so it leads the rotation, and every candidate is held to the age
    window regardless of which sort produced it.
    """
    sort = random.choice(["trendingScore", "trendingScore", "likes", "downloads"])
    # Popularity sorts need the deep skip to stay varied; trendingScore is short
    # and ordered by recency already, so reaching past it only finds stale rows.
    skip = random.randint(0, 100 if sort == "trendingScore" else 400)
    url = f"https://huggingface.co/api/{endpoint}?sort={sort}&direction=-1&limit=50&skip={skip}"
    cutoff = since(HF_MAX_AGE_DAYS, relax)
    out = []
    for item in get_json(url):
        if (item.get("likes") or 0) < min_likes:
            continue
        # A missing createdAt cannot be shown to be fresh, so it does not pass.
        if (item.get("createdAt") or "")[:10] < cutoff:
            continue
        triple = hf_block(item, kind)
        if triple:
            out.append(triple)
    return out


def src_hf_models(relax):
    return hf_fetch("models", "model", bar(MIN_HF_LIKES, relax), relax)


def src_hf_datasets(relax):
    return hf_fetch("datasets", "dataset", bar(MIN_HF_LIKES, relax), relax)


def devto_source(category):
    """Build a dev.to fetcher for one category, varying tag/window/page per run."""
    def fetch(relax):
        name, tag = random.choice(list(SUBCATS[category].items()))
        top = random.choice([7, 30, 365])
        page = random.randint(1, 3)
        url = f"https://dev.to/api/articles?tag={tag}&top={top}&per_page=50&page={page}"
        min_reactions = bar(MIN_REACTIONS, relax)
        min_minutes = bar(MIN_READ_MINUTES, relax)
        out = []
        for a in get_json(url):
            reactions = a.get("positive_reactions_count", 0)
            mins = a.get("reading_time_minutes", 0)
            if reactions < min_reactions or mins < min_minutes:
                continue  # quality gate
            desc = (a.get("description") or "").strip() or "No summary provided."
            tags = ", ".join(a.get("tag_list", [])[:6])
            block = (
                f"### [{a['title']}]({a['url']})\n"
                f"- **Author:** {a['user']['name']} | **Published:**"
                f" {(a.get('readable_publish_date') or '').strip()}"
                f" | **Read time:** {mins} min\n"
                f"- **Community:** {reactions} reactions, {a.get('comments_count', 0)} comments"
                f" -- a top post in #{tag}\n"
                f"- **Tags:** {tags}\n"
                f"- **Summary:** {desc}\n"
                f"- **Link:** {a['url']}"
            )
            out.append((a["url"], name, block))
        return out

    fetch.__name__ = f"src_devto_{category.replace('-', '_')}"
    return fetch


SOURCES = {
    "trending-projects": [src_gh_new, src_gh_rising, src_gh_active, src_gh_topic, src_gh_lang],
    "articles": [src_hn_front, src_hn_deep, src_lobsters_hot, src_lobsters_tag,
                 devto_source("articles")],
    "ai": [devto_source("ai"), src_arxiv, src_hf_models, src_hf_datasets],
    "coding-tips": [devto_source("coding-tips"), src_hn_show, src_hn_ask, src_lobsters_new],
    "languages": [devto_source("languages"), src_lobsters_lang,
                  src_gh_lang_notes, src_hn_lang],
}


# ======================================================================
# file plumbing
# ======================================================================

def rotate_if_needed(category):
    """Keep category files readable: past MAX_ENTRIES_PER_FILE, move to archive/."""
    path = FILES[category]
    if not path.exists():
        return
    text = path.read_text(encoding="utf-8")
    if text.count("### [") < MAX_ENTRIES_PER_FILE:
        return
    ARCHIVE.mkdir(parents=True, exist_ok=True)
    stamp = date.today().strftime("%Y-%m")
    dest = ARCHIVE / f"{category}-{stamp}.md"
    n = 2
    while dest.exists():
        dest = ARCHIVE / f"{category}-{stamp}-{n}.md"
        n += 1
    dest.write_text(text, encoding="utf-8")
    path.write_text(TITLES[category], encoding="utf-8")
    print(f"  (rotated {path.name} -> {dest.relative_to(REPO).as_posix()})")


def insert_under_headline(path, title_block, subcat, entry):
    """Place entry under '## subcat' inside the file, creating file/headline as needed."""
    if path.exists():
        text = path.read_text(encoding="utf-8")
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        text = title_block

    stamped = f"\n**Added {date.today().isoformat()}**\n\n{entry}\n"
    headline = f"## {subcat}"

    # Match the headline as a WHOLE LINE. A plain substring test puts every
    # "## Java" entry at the end of the "## JavaScript" section and never
    # creates a Java section at all -- which is exactly what it did, for twenty
    # entries, before this was anchored. The same trap waits for any headline
    # that is a prefix of another ("Backend" / "Backend & Infrastructure").
    found = re.search(rf"^{re.escape(headline)}[ \t]*$", text, re.M)
    if found:
        # insert at the end of this section (before next '## ' or EOF)
        nxt = text.find("\n## ", found.end())
        if nxt == -1:
            text = text.rstrip() + "\n" + stamped
        else:
            text = text[:nxt].rstrip() + "\n" + stamped + "\n" + text[nxt:]
    else:
        text = text.rstrip() + f"\n\n{headline}\n" + stamped

    path.write_text(text, encoding="utf-8")


def count_entries(category):
    """Entries live in the active file plus any rotated archive files."""
    path = FILES[category]
    total = path.read_text(encoding="utf-8").count("### [") if path.exists() else 0
    if ARCHIVE.exists():
        for p in sorted(ARCHIVE.glob(f"{category}-*.md")):
            total += p.read_text(encoding="utf-8").count("### [")
    return total


README_ORDER = ["trending-projects", "ai", "articles", "coding-tips", "languages"]
README_LABELS = {
    "trending-projects": "Trending Projects",
    "ai": "AI / LLM Notes",
    "articles": "Reading List",
    "coding-tips": "Coding Tips",
    "languages": "Language Notes",
}


def update_readme(recent):
    counts = {c: count_entries(c) for c in FILES}
    total = sum(counts.values())

    rows = "\n".join(
        f"| [{README_LABELS[c]}]({FILES[c].relative_to(REPO).as_posix()}) | {counts[c]} |"
        for c in README_ORDER
    )
    latest = "\n".join(
        f"- **{e['date']}** · *{e['subcat']}* — [{e['title']}]({e['url']})"
        for e in reversed(recent[-5:])
    ) or "- (first entries coming soon)"

    readme = (
        "# \U0001F4DA dev-notes\n\n"
        "Auto-curated developer knowledge base — fresh content lands **every hour,\n"
        "around the clock**, from GitHub, Hacker News, Lobsters, dev.to, arXiv and\n"
        "the Hugging Face Hub.\n\n"
        f"**{total} entries and counting** · Last updated: {date.today().isoformat()}\n\n"
        "## Categories\n\n"
        "| Section | Entries |\n|---|---|\n"
        f"{rows}\n\n"
        "## Latest additions\n\n"
        f"{latest}\n\n"
        "## How it works\n\n"
        "A Python script runs on a schedule — in GitHub Actions around the clock,\n"
        "with a local Task Scheduler job as backup. Each run pulls the\n"
        "highest-signal new dev content from six sources — filtered both for\n"
        "quality (stars, points, reactions, likes) and for age, so a popularity\n"
        "ranking cannot pass a year-old item off as new — files each one under a\n"
        "topic headline, and commits it here: one commit per entry. No\n"
        "duplicates, counting an article and its discussion thread as the same\n"
        "item. Long sections rotate into `archive/`.\n"
    )
    (REPO / "README.md").write_text(readme, encoding="utf-8")


# ======================================================================
# git plumbing
# ======================================================================

def notify(msg):
    """Non-blocking Windows popup (auto-closes in 10s). Silent no-op elsewhere."""
    if os.environ.get("CI"):
        return
    try:
        subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "(New-Object -ComObject Wscript.Shell)"
             f".Popup('{msg.replace(chr(39), chr(39) * 2)}',10,'dev-notes',48)"],
            capture_output=True, timeout=15,
        )
    except Exception:
        pass


def fail(context, detail):
    print(f"FAILED at {context}: {detail}")
    notify(f"dev-notes failed at {context}. Check .content/auto-log.txt")
    sys.exit(1)


def run_ok(*cmd):
    """Run a git command, returning (returncode, output) without exiting."""
    r = subprocess.run(
        cmd, cwd=REPO, capture_output=True, text=True,
        encoding="utf-8", errors="replace",
    )
    return r.returncode, ((r.stdout or "") + (r.stderr or "")).strip()


def run(*cmd):
    code, out = run_ok(*cmd)
    if code != 0:
        fail(" ".join(cmd[:2]), out[:300])
    return out


def _entry_id(item):
    """Identity of one used.json list item: a url for entries, the value itself
    for plain strings (ids, tip texts)."""
    if isinstance(item, dict):
        return item.get("url") or json.dumps(item, sort_keys=True)
    return item


def _stage(number, path):
    """One side of a conflicted file, straight out of the index."""
    code, out = run_ok("git", "show", f":{number}:{path}")
    return out if code == 0 else ""


def union_merge_used():
    """Union-merge both sides of used.json as data, not as text.

    Concatenating JSON lines the way git's union driver does would produce
    invalid JSON and crash the next run, so the merge happens on parsed
    objects: every list becomes the union of both sides. Stage 2 is the side
    already on the branch and stage 3 the commit being replayed, so stage-3
    items are the newer ones and go last.
    """
    rel = USED.relative_to(REPO).as_posix()
    try:
        ours = json.loads(_stage(2, rel) or "{}")
        theirs = json.loads(_stage(3, rel) or "{}")
    except json.JSONDecodeError as exc:
        print(f"  !! used.json unparseable on one side ({exc}); not resolving")
        return False

    merged = {}
    for key in list(ours) + [k for k in theirs if k not in ours]:
        a, b = ours.get(key), theirs.get(key)
        if isinstance(a, list) and isinstance(b, list):
            seen = {_entry_id(x) for x in a}
            merged[key] = a + [x for x in b if _entry_id(x) not in seen]
        else:
            merged[key] = a if a is not None else b

    if isinstance(merged.get("ids"), list):
        merged["ids"] = sorted(set(merged["ids"]))
    if isinstance(merged.get("recent"), list):
        merged["recent"] = merged["recent"][-RECENT_KEEP:]

    USED.write_text(json.dumps(merged, indent=2), encoding="utf-8")
    print(f"  (used.json union-merged: {len(merged.get('ids', []))} ids)")
    return True


def rebase_in_progress():
    for name in ("rebase-merge", "rebase-apply"):
        code, out = run_ok("git", "rev-parse", "--git-path", name)
        if code == 0 and (REPO / out).exists():
            return True
    return False


def resolve_bookkeeping():
    """Carry a conflicted rebase through, if only bookkeeping files are stuck.

    Returns True when the rebase ran to completion. False means "this is a real
    conflict" -- the caller aborts and fails the run, as before. Without this,
    one overlapping hour between the two runners wedges every later run: the
    pull conflicts, the run bails, and nothing is committed until someone
    notices by hand.
    """
    for _ in range(20):  # one pass per replayed commit
        stuck = run("git", "diff", "--name-only", "--diff-filter=U").splitlines()
        unexpected = [f for f in stuck if f not in AUTO_RESOLVABLE]
        if unexpected:
            print(f"  !! conflict outside bookkeeping files: {', '.join(unexpected)}")
            return False

        if any(f == USED.relative_to(REPO).as_posix() for f in stuck):
            if not union_merge_used():
                return False
        # README is derived, never merged: rebuild it from the notes on disk.
        used = json.loads(USED.read_text(encoding="utf-8")) if USED.exists() else {}
        update_readme(used.get("recent", []))

        run("git", "add", "-A")
        code, out = run_ok("git", "-c", "core.editor=true", "rebase", "--continue")
        if code != 0:
            low = out.lower()
            if "no changes" in low or "nothing to commit" in low:
                code, out = run_ok("git", "rebase", "--skip")
            if code != 0:
                print(f"  !! rebase --continue refused: {out[:200]}")
                return False
        if not rebase_in_progress():
            return True

    print("  !! still conflicting after 20 passes; giving up")
    return False


# A pull that dies because the network blinked is neither a conflict nor a
# reason to lose the run -- six runs in the log went to "Could not resolve
# host" alone. Retry those; fail fast on everything else.
NETWORK_HINTS = (
    "could not resolve host", "failed to connect", "connection reset",
    "connection timed out", "operation timed out", "temporary failure",
    "network is unreachable", "unexpected disconnect", "early eof",
    "the remote end hung up", "rpc failed",
)


def pull_rebase():
    """git pull --rebase, auto-resolving the bookkeeping-only conflicts.

    Returns (ok, detail). On a real conflict the rebase is aborted first, so
    the tree is always left clean either way.
    """
    for attempt in range(3):
        code, out = run_ok("git", "pull", "--rebase", "origin", "main")
        if code == 0:
            return True, out
        if not any(h in out.lower() for h in NETWORK_HINTS):
            break
        if attempt == 2:
            return False, out
        delay = 15 * (attempt + 1)
        print(f"  (pull failed on a network error, attempt {attempt + 1}/3;"
              f" retrying in {delay}s: {out.strip()[:120]})")
        time.sleep(delay)

    # Anything that is not a halted rebase -- a dirty tree, a bad token, a
    # protected branch -- has no conflict to resolve, and trying would stage the
    # whole tree and then blame the rebase for refusing to continue.
    if not rebase_in_progress():
        return False, out
    print("  (pull stopped on a conflict; trying to resolve bookkeeping files)")
    if resolve_bookkeeping():
        print("  (resolved; rebase completed)")
        return True, out
    run_ok("git", "rebase", "--abort")
    return False, out


def sync():
    """Pull latest, tolerating a dirty working tree.

    An unattended run must never wedge itself on leftover uncommitted
    changes (a manual edit, a half-finished run). If the tree is dirty we
    stash those changes aside -- recoverable with `git stash list` -- and
    proceed, rather than letting `git pull --rebase` abort the whole run.
    """
    # A rebase left half-finished -- killed run, closed console, power cut --
    # makes every later run fail at the pull with no obvious cause. Clear it
    # first; --abort returns to the pre-rebase commits, which the pull below
    # then replays normally, so nothing is lost.
    if rebase_in_progress():
        print("  !! leftover rebase from an interrupted run; aborting it first")
        run_ok("git", "rebase", "--abort")

    dirty = run("git", "status", "--porcelain")
    if dirty:
        print("  (working tree dirty at start; stashing aside before pull)")
        # Burying someone's half-finished edit without saying so is how an hour of
        # work disappears: an unattended run fires, stashes, and the next thing
        # the editor sees is their file reverted. Name the files and the way back.
        code = [ln[3:] for ln in dirty.splitlines() if ln[3:].endswith((".py", ".yml", ".bat"))]
        if code:
            print(f"  !! stashed IN-PROGRESS CODE EDITS: {', '.join(code)}")
            print("  !! recover with: git stash pop")
        run("git", "stash", "push", "-u", "-m",
            f"dev-notes auto-stash {datetime.now():%Y-%m-%d %H:%M}")
    ok, out = pull_rebase()
    if not ok:
        fail("git pull", out[:300])


def commits_today():
    """How many commits already landed today, from either runner (call after sync)."""
    today = date.today().isoformat()
    out = run("git", "log", "--since=36 hours ago", "--date=short", "--pretty=%ad")
    return sum(1 for line in out.splitlines() if line.strip() == today)


def commit(message):
    run("git", "add", "-A")
    if not run("git", "status", "--porcelain"):
        print("  (nothing staged; skipping commit)")
        return False
    run("git", "commit", "-m", message)
    return True


def push():
    """Push, rebasing onto whatever the other runner pushed in the meantime."""
    for attempt in range(4):
        code, out = run_ok("git", "push", "origin", "main")
        if code == 0:
            return
        print(f"  (push rejected on attempt {attempt + 1}; rebasing: {out[:120]})")
        ok, detail = pull_rebase()
        if not ok:
            # Retrying the push would hit the same wall three more times and
            # then blame the push, sending the next reader to the wrong place.
            fail("git push", f"conflict while rebasing: {detail[:250]}")
    fail("git push", "still rejected after 4 attempts")


def heartbeat():
    """Last resort: keep the day from ending empty when every source is down."""
    PULSE.parent.mkdir(parents=True, exist_ok=True)
    if PULSE.exists():
        lines = PULSE.read_text(encoding="utf-8").rstrip().splitlines()
    else:
        lines = [
            "# Pulse",
            "",
            "Runs where every content source was unreachable, logged here so the",
            "run history stays continuous even when nothing could be fetched.",
            "",
        ]
    lines.append(f"- {datetime.now().isoformat(timespec='seconds')} — all sources unreachable, no entry added")
    PULSE.write_text("\n".join(lines[:5] + lines[5:][-200:]) + "\n", encoding="utf-8")
    if commit("chore: heartbeat (no source reachable this run)"):
        push()
        print("OK  heartbeat committed")


# ======================================================================
# candidate gathering
# ======================================================================

def entry_uids(uid, block):
    """Every URL that identifies one item.

    A story posted to both Hacker News and Lobsters arrives twice under two
    different uids -- the HN item link and the Lobsters comments link -- with
    the same article URL inside. Matching on the uid alone files the second
    copy as new, so the target link counts as identity too. Every block ends
    in a `- **Link:**` line, which is where that URL comes from.
    """
    uids = {uid}
    match = re.search(r"\n- \*\*Link:\*\* (\S+)", block)
    if match:
        uids.add(match.group(1))
    return uids


def sweep(pool, used_ids, relax, claimed):
    """One pass: pull from a random source in EVERY category.

    Sweeping by category rather than draining sources one at a time is what
    keeps a run varied -- a single source can return 50 items, and draining it
    first would hand spread() nothing but arXiv papers to choose from.

    `claimed` carries every url the pool already covers, under all of an
    entry's identities, so the same article cannot enter twice via two sources.
    """
    categories = list(SOURCES)
    random.shuffle(categories)
    for category in categories:
        source = random.choice(SOURCES[category])
        try:
            items = source(relax)
        except Exception as e:
            print(f"  ({category}/{source.__name__} unavailable: {e})")
            continue
        for uid, subcat, block in items:
            uids = entry_uids(uid, block)
            if uids & used_ids or uids & claimed:
                continue
            claimed |= uids
            pool[uid] = (category, uid, subcat, block)


def gather(need, used_ids):
    """Collect fresh candidates, relaxing thresholds only if we come up short."""
    pool = {}
    claimed = set()
    for relax in (0, 1, 2):
        for _ in range(2):
            sweep(pool, used_ids, relax, claimed)
            spread_ok = len({v[0] for v in pool.values()}) >= min(3, len(SOURCES))
            if len(pool) >= need and spread_ok:
                return list(pool.values())
        if relax < 2:
            print(f"  (only {len(pool)} fresh candidates across"
                  f" {len({v[0] for v in pool.values()})} categories; relaxing quality bar)")
    return list(pool.values())


def spread(candidates, n):
    """Pick n candidates round-robin across categories so no file hogs a run."""
    buckets = {}
    for c in candidates:
        buckets.setdefault(c[0], []).append(c)
    for v in buckets.values():
        random.shuffle(v)
    # Sparsest category first. Round-robin gives everyone one pick per pass, so
    # ordering by current entry count is what hands a run's EXTRA picks to the
    # files that are behind -- languages sat at 16 entries against trending's 177
    # because the old picker took the first category that had anything fresh.
    # Shuffle before the stable sort so equal-count categories break ties randomly.
    order = list(buckets)
    random.shuffle(order)
    order.sort(key=count_entries)
    picked = []
    while len(picked) < n and any(buckets.values()):
        for category in order:
            if buckets[category] and len(picked) < n:
                picked.append(buckets[category].pop())
    return picked


def todays_target(when=None):
    """The commit target for one calendar day.

    A flat count seven days a week is the one pattern no human produces -- real
    graphs have lighter weekends. Weekends still get a healthy number rather than
    zero, so every square stays green and the streak stays unbroken.

    The jitter is seeded by the date, not by the clock, for two reasons: every run
    on a given day must agree on the same number, and the two runners (Actions and
    the local task) have to agree with each other or they would fight over the
    remainder. Identical totals every single day is its own tell.
    """
    day = when or date.today()
    weekend = day.weekday() >= 5
    base = WEEKEND_TARGET if weekend else DAILY_TARGET
    # Weekends get a tighter spread on purpose. GitHub shades relative to your
    # busiest day, so once weekdays push the max to ~48 the bands land at
    # 1-9 / 10-19 / 20-28 / 29+. A wide weekend spread would dip below 20 and
    # render at the palest green right beside a maxed-out weekday; 24 +/- 4 keeps
    # every weekend inside the 20-28 band -- a visible step down, never washed out.
    spread = WEEKEND_JITTER if weekend else TARGET_JITTER
    if spread <= 0:
        return base
    rng = random.Random(day.toordinal())   # own instance: leaves global random alone
    return max(1, base + rng.randint(-spread, spread))


def allowance(done):
    """How many commits this run may add.

    With pacing on, a run may only carry the day up to the share of the target
    the clock has already earned -- otherwise 24 hourly runs would fire the
    whole day's target off before lunch and then idle. A runner that was
    asleep for hours catches up by itself, because its share grew while it
    slept. Past CATCHUP_AFTER the brake comes off so a slow day can still
    reach the target before midnight.
    """
    target = todays_target()
    if not PACE:
        return min(MAX_PER_RUN, max(0, target - done))
    now = datetime.now()
    elapsed = (now.hour * 60 + now.minute) / (24 * 60)
    earned = target if elapsed >= CATCHUP_AFTER else int(target * elapsed) + 1
    return min(MAX_PER_RUN, max(0, min(earned, target) - done))


TITLE_MAX = 55


def entry_title(block, fallback):
    """The entry title, trimmed to fit a one-line commit subject.

    Cut at a word boundary: a hard slice ends subjects mid-word ("worth
    keepin", "Every Time I Switched L"), which reads like a truncated log line
    instead of a title.
    """
    title = block.split("](")[0].replace("### [", "")
    title = title.encode("ascii", "ignore").decode().strip()
    if len(title) > TITLE_MAX:
        cut = title[:TITLE_MAX].rstrip()
        if " " in cut[TITLE_MAX // 2:]:
            cut = cut[:cut.rindex(" ")]
        title = cut.rstrip(" ,.;:-") + "..."
    return title or fallback


# ======================================================================

def backfill_links():
    """Teach used.json the article URLs of entries filed before entry_uids().

    Until the target link counted as identity, only the uid was tracked -- so a
    story already filed from Hacker News could be filed again from Lobsters.
    This walks every note file (active and archived), collects the url out of
    each entry's `- **Link:**` line, and folds them into `ids`. Additive and
    idempotent: it only ever widens the set, and commits nothing.
    """
    used = json.loads(USED.read_text(encoding="utf-8")) if USED.exists() else {}
    ids = set(used.get("ids", []))
    before = len(ids)

    paths = list(FILES.values())
    if ARCHIVE.exists():
        paths += sorted(ARCHIVE.glob("*.md"))
    for path in paths:
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.startswith("- **Link:** "):
                url = line[len("- **Link:** "):].strip()
                if url:
                    ids.add(url)

    used["ids"] = sorted(ids)
    USED.parent.mkdir(parents=True, exist_ok=True)
    USED.write_text(json.dumps(used, indent=2), encoding="utf-8")
    print(f"backfill: {before} -> {len(ids)} tracked ids "
          f"(+{len(ids) - before} article urls); nothing committed")


USAGE = "usage: add-note.py [--count N] [--dry-run] [--backfill-links]"
FLAGS = {"--count", "--dry-run", "--backfill-links", "--help", "-h"}


def main():
    argv = sys.argv[1:]
    # A mistyped flag used to run for real: "--dryrun" is not "--dry-run", the
    # membership tests simply did not see it, and a check became 8 commits.
    unknown = [a for i, a in enumerate(argv)
               if (a.startswith("-") and a not in FLAGS)
               or (not a.startswith("-") and (i == 0 or argv[i - 1] != "--count"))]
    if "--help" in argv or "-h" in argv:
        print(USAGE)
        return
    if unknown:
        fail("args", f"unknown argument(s): {' '.join(unknown)} -- {USAGE}")

    dry_run = "--dry-run" in argv

    if "--backfill-links" in argv:
        backfill_links()
        return

    forced = None
    if "--count" in argv:
        try:
            forced = int(argv[argv.index("--count") + 1])
        except (IndexError, ValueError):
            fail("args", "--count needs a number")

    # sync first so edits made elsewhere (other runner, GitHub web) never break the push.
    # A dry run must leave the repo exactly as it found it -- sync() stashes a dirty
    # tree, so running one while mid-edit used to bury the edit it was called to check.
    if dry_run:
        print("(dry run: skipping sync; counts reflect the local checkout)")
    else:
        sync()

    done = commits_today()
    need = forced if forced is not None else allowance(done)
    target = todays_target()
    kind = "weekend" if date.today().weekday() >= 5 else "weekday"
    print(f"today: {done} commits | {kind} target {target} | this run wants {need}")

    if need <= 0:
        print("Daily target already met. Nothing to do.")
        return

    used = json.loads(USED.read_text(encoding="utf-8")) if USED.exists() else {}
    used_ids = set(used.get("ids", []))
    recent = used.get("recent", [])

    picked = spread(gather(need, used_ids), need)

    if not picked:
        print("No new content passed the quality filters right now.")
        if done == 0 and not dry_run:
            heartbeat()
        return

    if dry_run:
        for category, uid, subcat, block in picked:
            print(f"  DRY {category} -> {subcat}: {entry_title(block, subcat)}")
        print(f"(dry run: {len(picked)} entries, nothing written)")
        return

    added = 0
    for category, uid, subcat, block in picked:
        rotate_if_needed(category)
        insert_under_headline(FILES[category], TITLES[category], subcat, block)

        title = entry_title(block, subcat)
        recent.append({
            "date": date.today().isoformat(),
            "subcat": subcat,
            "title": title,
            "url": uid,
        })
        used["recent"] = recent[-RECENT_KEEP:]
        used_ids.update(entry_uids(uid, block))
        used["ids"] = sorted(used_ids)
        USED.write_text(json.dumps(used, indent=2), encoding="utf-8")

        update_readme(used["recent"])

        if commit(f"{COMMIT_PREFIX[category]}: [{subcat}] {title}"):
            added += 1
            print(f"OK  {category} -> {subcat}: {title}")

    if added:
        push()
    print(f"done: {added} commits this run ({done + added}/{target} today)")


if __name__ == "__main__":
    main()
