#!/usr/bin/env python3
"""
Generate ALL GitHub profile stats as self-hosted SVGs.
Zero external service dependencies. Data comes directly from GitHub API.
Run this on GitHub Actions where GITHUB_TOKEN is available.
"""

import os
import json
import urllib.request
from datetime import datetime, timedelta

USERNAME = os.environ.get("GITHUB_REPOSITORY_OWNER", "jeevannar16-web")
TOKEN = os.environ.get("GH_TOKEN", os.environ.get("GITHUB_TOKEN", ""))
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(SCRIPT_DIR, "..", "..", "stats")

HEADERS = {"User-Agent": "GitHub-Stats-Generator", "Accept": "application/vnd.github.v3+json"}
if TOKEN:
    HEADERS["Authorization"] = f"token {TOKEN}"


def api_get(url):
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        resp = urllib.request.urlopen(req, timeout=20)
        return json.loads(resp.read())
    except Exception as e:
        print(f"  WARN: {e}")
        return {}


def graphql_query(query):
    if not TOKEN:
        return {}
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": query}).encode(),
        headers={
            "Authorization": f"bearer {TOKEN}",
            "Content-Type": "application/json",
            "User-Agent": "GitHub-Stats-Generator",
        },
    )
    try:
        return json.loads(urllib.request.urlopen(req, timeout=20).read())
    except Exception as e:
        print(f"  WARN graphql: {e}")
        return {}


def fetch_contribution_calendar():
    """Get contribution calendar via GraphQL (most accurate source)."""
    query = f'''
    {{
      user(login: "{USERNAME}") {{
        contributionsCollection {{
          contributionCalendar {{
            totalContributions
            weeks {{
              contributionDays {{
                contributionCount
                date
              }}
            }}
          }}
        }}
      }}
    }}
    '''
    data = graphql_query(query)
    try:
        cal = data["data"]["user"]["contributionsCollection"]["contributionCalendar"]
        total = cal["totalContributions"]
        days = {}
        for week in cal["weeks"]:
            for day in week["contributionDays"]:
                days[day["date"]] = day["contributionCount"]
        return total, days
    except (KeyError, TypeError):
        return 0, {}


def calc_streaks(contrib_days):
    """Calculate current and longest streak from contribution calendar."""
    if not contrib_days:
        return 0, 0

    today = datetime.now().date()

    # Current streak: count backwards from today (or yesterday if no contributions today)
    current = 0
    d = today
    while True:
        ds = d.strftime("%Y-%m-%d")
        if ds in contrib_days and contrib_days[ds] > 0:
            current += 1
            d -= timedelta(days=1)
        else:
            break

    # Longest streak
    longest = 0
    run = 0
    for ds in sorted(contrib_days.keys()):
        if contrib_days[ds] > 0:
            run += 1
            longest = max(longest, run)
        else:
            run = 0

    return current, longest


def fetch_profile():
    return api_get(f"https://api.github.com/users/{USERNAME}")


def fetch_repos():
    return api_get(f"https://api.github.com/users/{USERNAME}/repos?per_page=100&sort=updated")


def count_commits(repos):
    """Count commits by author across all repos using pagination."""
    total = 0
    for repo in repos:
        name = repo["name"]
        page = 1
        while True:
            data = api_get(
                f"https://api.github.com/repos/{USERNAME}/{name}/commits?author={USERNAME}&per_page=100&page={page}"
            )
            if not isinstance(data, list) or len(data) == 0:
                break
            total += len(data)
            if len(data) < 100:
                break
            page += 1
    return total


def fetch_languages(repos):
    lang_bytes = {}
    for repo in repos:
        data = api_get(repo["languages_url"])
        if isinstance(data, dict):
            for lang, b in data.items():
                lang_bytes[lang] = lang_bytes.get(lang, 0) + b
    return lang_bytes


def fetch_search_count(query):
    data = api_get(f"https://api.github.com/search/issues?q={query}")
    return data.get("total_count", 0)


# ── SVG Generation ──────────────────────────────────────────────────

TOKYO = {
    "bg": "#1e1e2e", "card": "#181825", "border": "#313244",
    "green": "#00ff9c", "blue": "#89b4fa", "yellow": "#f9e2af",
    "red": "#f38ba8", "mauve": "#cba6f7", "teal": "#94e2d5",
    "peach": "#fab387", "text": "#cdd6f4", "sub": "#a6adc8",
}


def esc(t):
    return str(t).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def svg_card_stats(name, stats):
    """Stats card: stars, commits, PRs, issues, repos."""
    c = TOKYO
    w, h = 495, 200
    mx, my = 25, 20
    year = datetime.now().year

    items = [
        ("Total Stars Earned", str(stats["stars"]), c["yellow"]),
        (f"Commits ({year})", str(stats["commits"]), c["green"]),
        ("Total PRs", str(stats["prs"]), c["mauve"]),
        ("Total Issues", str(stats["issues"]), c["blue"]),
        ("Public Repos", str(stats["repos"]), c["teal"]),
        ("Followers", str(stats["followers"]), c["peach"]),
    ]

    blocks = ""
    col_w = (w - 2 * mx) // 2
    for i, (label, value, color) in enumerate(items):
        col = i % 2
        row = i // 2
        x = mx + col * (col_w + 15)
        y = my + 30 + row * 50
        blocks += f'''  <text x="{x}" y="{y}" font-family="'Segoe UI',Ubuntu,sans-serif" font-size="12" fill="{c['sub']}">{esc(label)}</text>
  <text x="{x}" y="{y + 20}" font-family="'Segoe UI',Ubuntu,sans-serif" font-size="22" font-weight="700" fill="{color}">{esc(value)}</text>
'''

    return f'''<svg width="{w}" height="{h}" viewBox="0 0 {w} {h}" xmlns="http://www.w3.org/2000/svg">
  <rect width="{w}" height="{h}" rx="6" fill="{c['card']}"/>
  <rect width="{w}" height="{h}" rx="6" fill="none" stroke="{c['border']}"/>
  <text x="{mx}" y="{my + 10}" font-family="'Segoe UI',Ubuntu,sans-serif" font-size="18" font-weight="700" fill="{c['text']}">{esc(name)}'s GitHub Stats</text>
{blocks}</svg>'''


def svg_card_langs(languages):
    """Top languages bar chart."""
    c = TOKYO
    if not languages:
        languages = {"Unknown": 1}
    sorted_langs = sorted(languages.items(), key=lambda x: x[1], reverse=True)[:6]
    total = sum(v for _, v in sorted_langs)
    colors = [c["blue"], c["green"], c["yellow"], c["red"], c["mauve"], c["teal"]]

    n = len(sorted_langs)
    w = 300
    h = 45 + n * 34
    mx = 20
    bar_x, bar_w_max = 160, 110

    bars = ""
    for i, (lang, byte_count) in enumerate(sorted_langs):
        pct = (byte_count / total) * 100
        bw = max(pct / 100 * bar_w_max, 4)
        y = 45 + i * 34
        color = colors[i % len(colors)]
        bars += f'''  <text x="{mx}" y="{y + 13}" font-family="'Segoe UI',Ubuntu,sans-serif" font-size="13" fill="{c['text']}">{esc(lang)}</text>
  <rect x="{bar_x}" y="{y}" width="{bw:.1f}" height="18" rx="6" fill="{color}" opacity="0.85"/>
  <text x="{bar_x + bw + 8:.1f}" y="{y + 13}" font-family="'Segoe UI',Ubuntu,sans-serif" font-size="11" fill="{c['sub']}">{pct:.1f}%</text>
'''

    return f'''<svg width="{w}" height="{h}" viewBox="0 0 {w} {h}" xmlns="http://www.w3.org/2000/svg">
  <rect width="{w}" height="{h}" rx="6" fill="{c['card']}"/>
  <rect width="{w}" height="{h}" rx="6" fill="none" stroke="{c['border']}"/>
  <text x="{mx}" y="30" font-family="'Segoe UI',Ubuntu,sans-serif" font-size="14" font-weight="700" fill="{c['text']}">Most Used Languages</text>
{bars}</svg>'''


def svg_card_streak(current, longest, total_contribs):
    """Streak card."""
    c = TOKYO
    w, h = 495, 130
    mx, my = 25, 20

    return f'''<svg width="{w}" height="{h}" viewBox="0 0 {w} {h}" xmlns="http://www.w3.org/2000/svg">
  <rect width="{w}" height="{h}" rx="6" fill="{c['card']}"/>
  <rect width="{w}" height="{h}" rx="6" fill="none" stroke="{c['border']}"/>
  <text x="{mx}" y="{my + 10}" font-family="'Segoe UI',Ubuntu,sans-serif" font-size="16" font-weight="700" fill="{c['text']}">🔥 Contribution Streak</text>

  <text x="{mx}" y="{my + 50}" font-family="'Segoe UI',Ubuntu,sans-serif" font-size="12" fill="{c['sub']}">Current Streak</text>
  <text x="{mx}" y="{my + 75}" font-family="'Segoe UI',Ubuntu,sans-serif" font-size="32" font-weight="700" fill="{c['green']}">{current}</text>
  <text x="{mx + 55}" y="{my + 75}" font-family="'Segoe UI',Ubuntu,sans-serif" font-size="14" fill="{c['sub']}">days</text>

  <text x="{w // 3 + mx}" y="{my + 50}" font-family="'Segoe UI',Ubuntu,sans-serif" font-size="12" fill="{c['sub']}">Longest Streak</text>
  <text x="{w // 3 + mx}" y="{my + 75}" font-family="'Segoe UI',Ubuntu,sans-serif" font-size="32" font-weight="700" fill="{c['yellow']}">{longest}</text>
  <text x="{w // 3 + mx + 55}" y="{my + 75}" font-family="'Segoe UI',Ubuntu,sans-serif" font-size="14" fill="{c['sub']}">days</text>

  <text x="{2 * w // 3 + mx}" y="{my + 50}" font-family="'Segoe UI',Ubuntu,sans-serif" font-size="12" fill="{c['sub']}">Total Contributions</text>
  <text x="{2 * w // 3 + mx}" y="{my + 75}" font-family="'Segoe UI',Ubuntu,sans-serif" font-size="32" font-weight="700" fill="{c['mauve']}">{total_contribs}</text>
  <text x="{2 * w // 3 + mx + 55}" y="{my + 75}" font-family="'Segoe UI',Ubuntu,sans-serif" font-size="14" fill="{c['sub']}">this year</text>
</svg>'''


def svg_card_repo(repo):
    """Single pinned repo card."""
    c = TOKYO
    w = 495
    h = 120
    name = repo.get("name", "repo")
    desc = repo.get("description") or "No description"
    if len(desc) > 55:
        desc = desc[:52] + "..."
    stars = repo.get("stargazers_count", 0)
    forks = repo.get("forks_count", 0)
    lang = repo.get("language") or "N/A"
    lang_colors = {
        "Python": "#3776AB", "JavaScript": "#F7DF1E", "CSS": "#1572B6",
        "HTML": "#E34F26", "C": "#A8B9CC", "C++": "#00599C", "Java": "#ED8B00",
        "Shell": "#4EAA25", "TypeScript": "#3178C6",
    }
    lc = lang_colors.get(lang, "#6c7086")

    lang_part = f'''  <circle cx="25" cy="{h - 22}" r="5" fill="{lc}"/>
  <text x="36" y="{h - 18}" font-family="'Segoe UI',Ubuntu,sans-serif" font-size="12" fill="{c['sub']}">{esc(lang)}</text>''' if lang != "N/A" else ""

    return f'''<svg width="{w}" height="{h}" viewBox="0 0 {w} {h}" xmlns="http://www.w3.org/2000/svg">
  <rect width="{w}" height="{h}" rx="6" fill="{c['card']}"/>
  <rect width="{w}" height="{h}" rx="6" fill="none" stroke="{c['border']}"/>
  <text x="25" y="35" font-family="'Segoe UI',Ubuntu,sans-serif" font-size="16" font-weight="700" fill="{c['blue']}">{esc(name)}</text>
  <text x="25" y="58" font-family="'Segoe UI',Ubuntu,sans-serif" font-size="12" fill="{c['sub']}">{esc(desc)}</text>
{lang_part}
  <text x="{w - 25}" y="{h - 18}" font-family="'Segoe UI',Ubuntu,sans-serif" font-size="12" fill="{c['yellow']}" text-anchor="end">&#11088; {stars}</text>
  <text x="{w - 80}" y="{h - 18}" font-family="'Segoe UI',Ubuntu,sans-serif" font-size="12" fill="{c['sub']}" text-anchor="end">&#127860; {forks}</text>
</svg>'''


# ── Main ─────────────────────────────────────────────────────────────

def main():
    print(f"=== Generating self-hosted stats for {USERNAME} ===")
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    os.makedirs(os.path.join(OUTPUT_DIR, "repos"), exist_ok=True)

    # 1. Profile
    print("[1/6] Fetching profile...")
    profile = fetch_profile()
    display_name = profile.get("name") or USERNAME
    followers = profile.get("followers", 0)
    repos_data = fetch_repos()
    repos_list = repos_data if isinstance(repos_data, list) else []

    # 2. Repos stats
    print("[2/6] Counting repos...")
    total_stars = sum(r.get("stargazers_count", 0) for r in repos_list)
    total_forks = sum(r.get("forks_count", 0) for r in repos_list)
    num_repos = len(repos_list)

    # 3. Commits
    print("[3/6] Counting commits (per-repo)...")
    total_commits = count_commits(repos_list)
    print(f"  => {total_commits} total commits")

    # 4. PRs and Issues
    print("[4/6] Counting PRs and issues...")
    total_prs = fetch_search_count(f"author:{USERNAME}+type:pr")
    total_issues = fetch_search_count(f"author:{USERNAME}+type:issue")
    print(f"  => {total_prs} PRs, {total_issues} issues")

    # 5. Languages
    print("[5/6] Fetching languages...")
    languages = fetch_languages(repos_list)

    # 6. Contribution calendar + streak
    print("[6/6] Fetching contribution calendar (GraphQL)...")
    total_contribs, contrib_days = fetch_contribution_calendar()
    current_streak, longest_streak = calc_streaks(contrib_days)
    print(f"  => {total_contribs} contributions, streak: {current_streak}/{longest_streak}")

    # Build stats dict
    stats = {
        "name": display_name,
        "stars": total_stars,
        "forks": total_forks,
        "commits": total_commits,
        "prs": total_prs,
        "issues": total_issues,
        "repos": num_repos,
        "followers": followers,
        "total_contributions": total_contribs,
        "current_streak": current_streak,
        "longest_streak": longest_streak,
        "languages": languages,
    }

    # Save raw data
    with open(os.path.join(OUTPUT_DIR, "data.json"), "w") as f:
        json.dump(stats, f, indent=2)

    # Generate SVGs
    print("\nGenerating SVGs...")

    svg = svg_card_stats(display_name, stats)
    with open(os.path.join(OUTPUT_DIR, "github-stats.svg"), "w") as f:
        f.write(svg)
    print(f"  github-stats.svg")

    svg = svg_card_langs(languages)
    with open(os.path.join(OUTPUT_DIR, "top-langs.svg"), "w") as f:
        f.write(svg)
    print(f"  top-langs.svg")

    svg = svg_card_streak(current_streak, longest_streak, total_contribs)
    with open(os.path.join(OUTPUT_DIR, "streak.svg"), "w") as f:
        f.write(svg)
    print(f"  streak.svg")

    # Deployed repos
    deployed = [r for r in repos_list if r.get("homepage") and not r["fork"] and r["name"] != USERNAME]
    for r in deployed:
        svg = svg_card_repo(r)
        with open(os.path.join(OUTPUT_DIR, "repos", f'{r["name"]}.svg'), "w") as f:
            f.write(svg)
        print(f"  repos/{r['name']}.svg")

    print(f"\n=== Done! All stats in {OUTPUT_DIR}/ ===")
    print(json.dumps({k: v for k, v in stats.items() if k != "languages"}, indent=2))


if __name__ == "__main__":
    main()
