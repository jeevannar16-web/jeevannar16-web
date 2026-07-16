#!/usr/bin/env python3
"""
Generate GitHub profile stats as self-hosted SVGs.
Uses curl for API calls (more reliable than urllib in CI).
"""

import os
import json
import subprocess
from datetime import datetime, timedelta

USERNAME = os.environ.get("GITHUB_REPOSITORY_OWNER", "jeevannar16-web")
TOKEN = os.environ.get("GH_TOKEN", os.environ.get("GITHUB_TOKEN", ""))
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(SCRIPT_DIR, "..", "..", "stats")

def log(msg):
    print(msg, flush=True)

def curl_get(url, extra_headers=None):
    cmd = ["curl", "-s", "-f", "--max-time", "20"]
    if TOKEN:
        cmd += ["-H", f"Authorization: token {TOKEN}"]
    cmd += ["-H", "Accept: application/vnd.github.v3+json"]
    if extra_headers:
        for k, v in extra_headers.items():
            cmd += ["-H", f"{k}: {v}"]
    cmd.append(url)
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=25)
        if result.returncode != 0:
            return None
        return json.loads(result.stdout)
    except Exception as e:
        log(f"  curl error: {e}")
        return None

def curl_post(url, body):
    cmd = ["curl", "-s", "-f", "--max-time", "20", "-X", "POST"]
    if TOKEN:
        cmd += ["-H", f"Authorization: bearer {TOKEN}"]
    cmd += ["-H", "Content-Type: application/json"]
    cmd += ["-d", json.dumps(body)]
    cmd.append(url)
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=25)
        if result.returncode != 0:
            log(f"  GraphQL curl failed: {result.stderr[:200]}")
            return None
        return json.loads(result.stdout)
    except Exception as e:
        log(f"  curl error: {e}")
        return None

def curl_html(url):
    cmd = ["curl", "-s", "-f", "--max-time", "20", "-H", "User-Agent: Mozilla/5.0"]
    cmd.append(url)
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=25)
        return result.stdout if result.returncode == 0 else ""
    except:
        return ""

def fetch_profile():
    log("[1] Fetching profile...")
    data = curl_get(f"https://api.github.com/users/{USERNAME}")
    if not data:
        log("  FAILED")
        return {}
    result = {
        "name": data.get("name") or USERNAME,
        "followers": data.get("followers", 0),
        "following": data.get("following", 0),
        "public_repos": data.get("public_repos", 0),
    }
    log(f"  OK: {result['name']}, {result['followers']} followers, {result['public_repos']} repos")
    return result

def fetch_repos():
    log("[2] Fetching repos...")
    data = curl_get(f"https://api.github.com/users/{USERNAME}/repos?per_page=100&sort=updated")
    if not data or not isinstance(data, list):
        log("  FAILED")
        return []
    log(f"  OK: {len(data)} repos")
    return data

def count_commits(repos):
    log("[3] Counting commits per repo...")
    total = 0
    for repo in repos:
        name = repo["name"]
        page = 1
        repo_total = 0
        while True:
            data = curl_get(f"https://api.github.com/repos/{USERNAME}/{name}/commits?author={USERNAME}&per_page=100&page={page}")
            if data is None or not isinstance(data, list) or len(data) == 0:
                break
            repo_total += len(data)
            if len(data) < 100:
                break
            page += 1
        log(f"  {name}: {repo_total}")
        total += repo_total
    log(f"  TOTAL: {total}")
    return total

def fetch_languages(repos):
    log("[4] Fetching languages...")
    lang_bytes = {}
    for repo in repos:
        url = repo.get("languages_url", "")
        if not url:
            continue
        data = curl_get(url)
        if data and isinstance(data, dict):
            for lang, b in data.items():
                lang_bytes[lang] = lang_bytes.get(lang, 0) + b
    if lang_bytes:
        total = sum(lang_bytes.values())
        top = sorted(lang_bytes.items(), key=lambda x: x[1], reverse=True)[:3]
        log(f"  OK: {', '.join(f'{l} ({v*100//total}%)' for l,v in top)}")
    else:
        log("  FAILED: no language data")
    return lang_bytes

def fetch_search_count(query):
    data = curl_get(f"https://api.github.com/search/issues?q={query}")
    return data.get("total_count", 0) if data else 0

def fetch_contributions():
    log("[5] Fetching contributions...")
    
    # Method 1: GraphQL
    if TOKEN:
        log("  Trying GraphQL...")
        data = curl_post("https://api.github.com/graphql", {
            "query": """{ user(login: "%s") { contributionsCollection { contributionCalendar { totalContributions weeks { contributionDays { contributionCount date } } } } }""" % USERNAME
        })
        if data and not data.get("errors"):
            try:
                cal = data["data"]["user"]["contributionsCollection"]["contributionCalendar"]
                total = cal["totalContributions"]
                days = {}
                for week in cal["weeks"]:
                    for day in week["contributionDays"]:
                        days[day["date"]] = day["contributionCount"]
                current, longest = calc_streaks(days)
                log(f"  GraphQL OK: {total} contributions, streak: {current}/{longest}")
                return total, current, longest
            except (KeyError, TypeError) as e:
                log(f"  GraphQL parse error: {e}")
        else:
            log(f"  GraphQL failed: {data}")

    # Method 2: Scrape the /users/{login}/contributions page
    log("  Scraping contributions page...")
    import re
    html = curl_html(f"https://github.com/users/{USERNAME}/contributions")
    if not html:
        log("  Scrape failed: no HTML")
        return 0, 0, 0

    match = re.search(r'(\d[\d,]*)\s*contributions?\s*in\s*the\s*last\s*year', html, re.I)
    total = int(match.group(1).replace(',', '')) if match else 0
    cal_data = re.findall(r'data-date="(\d{4}-\d{2}-\d{2})"[^>]*data-level="(\d+)"', html)
    days = {d: int(c) for d, c in cal_data}
    current, longest = calc_streaks(days) if days else (0, 0)
    log(f"  Scrape OK: {total} contributions, streak: {current}/{longest}")
    return total, current, longest

def calc_streaks(contrib_days):
    if not contrib_days:
        return 0, 0
    today = datetime.now().date()
    current = 0
    d = today
    while d.strftime("%Y-%m-%d") in contrib_days and contrib_days[d.strftime("%Y-%m-%d")] > 0:
        current += 1
        d -= timedelta(days=1)
    longest = 0
    run = 0
    for ds in sorted(contrib_days.keys()):
        if contrib_days[ds] > 0:
            run += 1
            longest = max(longest, run)
        else:
            run = 0
    return current, longest

# ── SVG ──────────────────────────────────────────────────────────────

T = {
    "card": "#181825", "border": "#313244",
    "green": "#00ff9c", "blue": "#89b4fa", "yellow": "#f9e2af",
    "red": "#f38ba8", "mauve": "#cba6f7", "teal": "#94e2d5",
    "peach": "#fab387", "text": "#cdd6f4", "sub": "#a6adc8",
}

def esc(t):
    return str(t).replace("&","&amp;").replace("<","&lt;").replace(">","&gt;").replace('"',"&quot;")

def svg_stats(name, s):
    c = T; w, h = 495, 200; mx, my = 25, 20
    items = [
        ("Total Stars Earned", str(s["stars"]), c["yellow"]),
        (f"Commits ({datetime.now().year})", str(s["commits"]), c["green"]),
        ("Total PRs", str(s["prs"]), c["mauve"]),
        ("Total Issues", str(s["issues"]), c["blue"]),
        ("Public Repos", str(s["repos"]), c["teal"]),
        ("Followers", str(s["followers"]), c["peach"]),
    ]
    b = ""
    cw = (w-2*mx)//2
    for i,(lab,val,col) in enumerate(items):
        x = mx + (i%2)*(cw+15); y = my+30+(i//2)*50
        b += f'  <text x="{x}" y="{y}" font-family="\'Segoe UI\',Ubuntu,sans-serif" font-size="12" fill="{c["sub"]}">{esc(lab)}</text>\n'
        b += f'  <text x="{x}" y="{y+20}" font-family="\'Segoe UI\',Ubuntu,sans-serif" font-size="22" font-weight="700" fill="{col}">{esc(val)}</text>\n'
    return f'<svg width="{w}" height="{h}" viewBox="0 0 {w} {h}" xmlns="http://www.w3.org/2000/svg">\n  <rect width="{w}" height="{h}" rx="6" fill="{c["card"]}"/>\n  <rect width="{w}" height="{h}" rx="6" fill="none" stroke="{c["border"]}"/>\n  <text x="{mx}" y="{my+10}" font-family="\'Segoe UI\',Ubuntu,sans-serif" font-size="18" font-weight="700" fill="{c["text"]}">{esc(name)}\'s GitHub Stats</text>\n{b}</svg>'

def svg_langs(langs):
    c = T
    if not langs: langs = {"Unknown": 1}
    sl = sorted(langs.items(), key=lambda x: x[1], reverse=True)[:6]
    total = sum(v for _,v in sl)
    colors = [c["blue"],c["green"],c["yellow"],c["red"],c["mauve"],c["teal"]]
    n = len(sl); w, h = 300, 45+n*34; mx, bx, bm = 20, 160, 110
    bars = ""
    for i,(lang,bc) in enumerate(sl):
        pct = bc/total*100; bw = max(pct/100*bm,4); y = 45+i*34; col = colors[i%len(colors)]
        bars += f'  <text x="{mx}" y="{y+13}" font-family="\'Segoe UI\',Ubuntu,sans-serif" font-size="13" fill="{c["text"]}">{esc(lang)}</text>\n'
        bars += f'  <rect x="{bx}" y="{y}" width="{bw:.1f}" height="18" rx="6" fill="{col}" opacity="0.85"/>\n'
        bars += f'  <text x="{bx+bw+8:.1f}" y="{y+13}" font-family="\'Segoe UI\',Ubuntu,sans-serif" font-size="11" fill="{c["sub"]}">{pct:.1f}%</text>\n'
    return f'<svg width="{w}" height="{h}" viewBox="0 0 {w} {h}" xmlns="http://www.w3.org/2000/svg">\n  <rect width="{w}" height="{h}" rx="6" fill="{c["card"]}"/>\n  <rect width="{w}" height="{h}" rx="6" fill="none" stroke="{c["border"]}"/>\n  <text x="{mx}" y="30" font-family="\'Segoe UI\',Ubuntu,sans-serif" font-size="14" font-weight="700" fill="{c["text"]}">Most Used Languages</text>\n{bars}</svg>'

def svg_streak(cur, lng, tot):
    c = T; w, h = 495, 130; mx, my = 25, 20
    return f'''<svg width="{w}" height="{h}" viewBox="0 0 {w} {h}" xmlns="http://www.w3.org/2000/svg">
  <rect width="{w}" height="{h}" rx="6" fill="{c['card']}"/>
  <rect width="{w}" height="{h}" rx="6" fill="none" stroke="{c['border']}"/>
  <text x="{mx}" y="{my+10}" font-family="'Segoe UI',Ubuntu,sans-serif" font-size="16" font-weight="700" fill="{c['text']}">&#128293; Contribution Streak</text>
  <text x="{mx}" y="{my+50}" font-family="'Segoe UI',Ubuntu,sans-serif" font-size="12" fill="{c['sub']}">Current Streak</text>
  <text x="{mx}" y="{my+75}" font-family="'Segoe UI',Ubuntu,sans-serif" font-size="32" font-weight="700" fill="{c['green']}">{cur}</text>
  <text x="{mx+55}" y="{my+75}" font-family="'Segoe UI',Ubuntu,sans-serif" font-size="14" fill="{c['sub']}">days</text>
  <text x="{w//3+mx}" y="{my+50}" font-family="'Segoe UI',Ubuntu,sans-serif" font-size="12" fill="{c['sub']}">Longest Streak</text>
  <text x="{w//3+mx}" y="{my+75}" font-family="'Segoe UI',Ubuntu,sans-serif" font-size="32" font-weight="700" fill="{c['yellow']}">{lng}</text>
  <text x="{w//3+mx+55}" y="{my+75}" font-family="'Segoe UI',Ubuntu,sans-serif" font-size="14" fill="{c['sub']}">days</text>
  <text x="{2*w//3+mx}" y="{my+50}" font-family="'Segoe UI',Ubuntu,sans-serif" font-size="12" fill="{c['sub']}">Total Contributions</text>
  <text x="{2*w//3+mx}" y="{my+75}" font-family="'Segoe UI',Ubuntu,sans-serif" font-size="32" font-weight="700" fill="{c['mauve']}">{tot}</text>
  <text x="{2*w//3+mx+55}" y="{my+75}" font-family="'Segoe UI',Ubuntu,sans-serif" font-size="14" fill="{c['sub']}">this year</text>
</svg>'''

def svg_repo(r):
    c = T; w, h = 495, 120
    name = r.get("name","repo"); desc = r.get("description") or "No description"
    if len(desc)>55: desc=desc[:52]+"..."
    stars=r.get("stargazers_count",0); forks=r.get("forks_count",0)
    lang=r.get("language") or "N/A"
    lc={"Python":"#3776AB","JavaScript":"#F7DF1E","CSS":"#1572B6","HTML":"#E34F26","C":"#A8B9CC","C++":"#00599C","Java":"#ED8B00","Shell":"#4EAA25"}.get(lang,"#6c7086")
    lp = f'  <circle cx="25" cy="{h-22}" r="5" fill="{lc}"/>\n  <text x="36" y="{h-18}" font-family="\'Segoe UI\',Ubuntu,sans-serif" font-size="12" fill="{c["sub"]}">{esc(lang)}</text>' if lang!="N/A" else ""
    return f'''<svg width="{w}" height="{h}" viewBox="0 0 {w} {h}" xmlns="http://www.w3.org/2000/svg">
  <rect width="{w}" height="{h}" rx="6" fill="{c['card']}"/>
  <rect width="{w}" height="{h}" rx="6" fill="none" stroke="{c['border']}"/>
  <text x="25" y="35" font-family="'Segoe UI',Ubuntu,sans-serif" font-size="16" font-weight="700" fill="{c['blue']}">{esc(name)}</text>
  <text x="25" y="58" font-family="'Segoe UI',Ubuntu,sans-serif" font-size="12" fill="{c['sub']}">{esc(desc)}</text>
{lp}
  <text x="{w-25}" y="{h-18}" font-family="'Segoe UI',Ubuntu,sans-serif" font-size="12" fill="{c['yellow']}" text-anchor="end">&#11088; {stars}</text>
  <text x="{w-80}" y="{h-18}" font-family="'Segoe UI',Ubuntu,sans-serif" font-size="12" fill="{c['sub']}" text-anchor="end">&#127860; {forks}</text>
</svg>'''

# ── Main ─────────────────────────────────────────────────────────────

def main():
    log(f"=== Generating stats for {USERNAME} ===")
    log(f"Token: {'YES (' + str(len(TOKEN)) + ' chars)' if TOKEN else 'NO'}")
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    os.makedirs(os.path.join(OUTPUT_DIR, "repos"), exist_ok=True)

    profile = fetch_profile()
    repos = fetch_repos()
    total_stars = sum(r.get("stargazers_count", 0) for r in repos)
    total_commits = count_commits(repos)
    total_prs = fetch_search_count(f"author:{USERNAME}+type:pr")
    total_issues = fetch_search_count(f"author:{USERNAME}+type:issue")
    log(f"  PRs: {total_prs}, Issues: {total_issues}")
    languages = fetch_languages(repos)
    total_contribs, current_streak, longest_streak = fetch_contributions()

    stats = {
        "name": profile.get("name") or USERNAME,
        "stars": total_stars,
        "commits": total_contribs if total_contribs > 0 else total_commits,
        "prs": total_prs,
        "issues": total_issues,
        "repos": profile.get("public_repos", len(repos)),
        "followers": profile.get("followers", 0),
    }

    log(f"\n=== FINAL: {json.dumps(stats)} ===")
    log(f"Streak: {current_streak}/{longest_streak}, Contribs: {total_contribs}")

    log("\nWriting SVGs...")
    with open(os.path.join(OUTPUT_DIR, "github-stats.svg"), "w") as f:
        f.write(svg_stats(stats["name"], stats))
    with open(os.path.join(OUTPUT_DIR, "top-langs.svg"), "w") as f:
        f.write(svg_langs(languages))
    with open(os.path.join(OUTPUT_DIR, "streak.svg"), "w") as f:
        f.write(svg_streak(current_streak, longest_streak, total_contribs))

    deployed = [r for r in repos if r.get("homepage") and not r["fork"] and r["name"] != USERNAME]
    for r in deployed:
        with open(os.path.join(OUTPUT_DIR, "repos", f'{r["name"]}.svg'), "w") as f:
            f.write(svg_repo(r))
        log(f"  repos/{r['name']}.svg")

    log("=== DONE ===")

if __name__ == "__main__":
    main()
