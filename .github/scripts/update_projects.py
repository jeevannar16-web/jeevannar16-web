#!/usr/bin/env python3
"""Update README.md projects section with self-hosted repo cards.
Uses curl for API calls (reliable in CI)."""

import os
import json
import subprocess

USERNAME = os.environ.get("GITHUB_REPOSITORY_OWNER", "jeevannar16-web")
TOKEN = os.environ.get("GH_TOKEN", os.environ.get("GITHUB_TOKEN", ""))
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CARDS_DIR = os.path.join(SCRIPT_DIR, "..", "..", "stats", "repos")
README = os.path.join(SCRIPT_DIR, "..", "..", "README.md")

TOKYO = {
    "card": "#181825", "border": "#313244", "blue": "#89b4fa",
    "yellow": "#f9e2af", "sub": "#a6adc8",
}
LANG_COLORS = {
    "Python": "#3776AB", "JavaScript": "#F7DF1E", "CSS": "#1572B6",
    "HTML": "#E34F26", "C": "#A8B9CC", "C++": "#00599C", "Java": "#ED8B00",
    "Shell": "#4EAA25", "TypeScript": "#3178C6",
}


def log(msg):
    print(msg, flush=True)


def curl_get(url):
    cmd = ["curl", "-s", "-f", "--max-time", "20"]
    if TOKEN:
        cmd += ["-H", f"Authorization: token {TOKEN}"]
    cmd += ["-H", "Accept: application/vnd.github.v3+json"]
    cmd.append(url)
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=25)
        if result.returncode != 0:
            return None
        return json.loads(result.stdout)
    except Exception as e:
        log(f"  curl error: {e}")
        return None


def esc(t):
    return str(t).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def generate_repo_card(r):
    c = TOKYO
    w, h = 495, 120
    name = r.get("name", "repo")
    desc = r.get("description") or "No description"
    if len(desc) > 55:
        desc = desc[:52] + "..."
    stars = r.get("stargazers_count", 0)
    forks = r.get("forks_count", 0)
    lang = r.get("language") or "N/A"
    lc = LANG_COLORS.get(lang, "#6c7086")
    lang_part = f'''  <circle cx="25" cy="{h-22}" r="5" fill="{lc}"/>
  <text x="36" y="{h-18}" font-family="'Segoe UI',Ubuntu,sans-serif" font-size="12" fill="{c['sub']}">{esc(lang)}</text>''' if lang != "N/A" else ""

    return f'''<svg width="{w}" height="{h}" viewBox="0 0 {w} {h}" xmlns="http://www.w3.org/2000/svg">
  <rect width="{w}" height="{h}" rx="6" fill="{c['card']}"/>
  <rect width="{w}" height="{h}" rx="6" fill="none" stroke="{c['border']}"/>
  <text x="25" y="35" font-family="'Segoe UI',Ubuntu,sans-serif" font-size="16" font-weight="700" fill="{c['blue']}">{esc(name)}</text>
  <text x="25" y="58" font-family="'Segoe UI',Ubuntu,sans-serif" font-size="12" fill="{c['sub']}">{esc(desc)}</text>
{lang_part}
  <text x="{w-25}" y="{h-18}" font-family="'Segoe UI',Ubuntu,sans-serif" font-size="12" fill="{c['yellow']}" text-anchor="end">&#11088; {stars}</text>
  <text x="{w-80}" y="{h-18}" font-family="'Segoe UI',Ubuntu,sans-serif" font-size="12" fill="{c['sub']}" text-anchor="end">&#127860; {forks}</text>
</svg>'''


def main():
    log(f"=== Updating project cards for {USERNAME} ===")
    os.makedirs(CARDS_DIR, exist_ok=True)

    repos = curl_get(f"https://api.github.com/users/{USERNAME}/repos?per_page=100&sort=stars&direction=desc")
    if not repos or not isinstance(repos, list):
        log("FAILED to fetch repos")
        return

    deployed = [r for r in repos if r.get("homepage") and not r["fork"] and r["name"] != USERNAME]
    deployed.sort(key=lambda r: r["stargazers_count"], reverse=True)
    log(f"Found {len(deployed)} deployed repos: {[r['name'] for r in deployed]}")

    cards_html = []
    for r in deployed:
        svg = generate_repo_card(r)
        path = os.path.join(CARDS_DIR, f'{r["name"]}.svg')
        with open(path, "w") as f:
            f.write(svg)

        repo_url = r.get("html_url") or f"https://github.com/{USERNAME}/{r['name']}"
        img = f"https://raw.githubusercontent.com/{USERNAME}/{USERNAME}/main/stats/repos/{r['name']}.svg"
        homepage = r.get("homepage")

        buttons = f'<a href="{repo_url}"><img src="https://img.shields.io/badge/REPO-open-89b4fa?style=for-the-badge&logo=github&logoColor=white"/></a>'
        if homepage:
            buttons += f' <a href="{homepage}"><img src="https://img.shields.io/badge/LIVE_SITE-open-a6e3a1?style=for-the-badge&logo=googlechrome&logoColor=white"/></a>'

        cell = f'''    <td align="center" width="50%" style="background:#181825;border:1.5px solid #313244;border-radius:12px;padding:14px;">
      <a href="{repo_url}"><img src="{img}" width="100%" alt="{esc(r["name"])}"/></a><br><br>
      {buttons}
    </td>'''
        cards_html.append(cell)
        log(f"  {r['name']}.svg -> repo:{repo_url} site:{homepage or '—'}")

    if not cards_html:
        content_block = '\n\n_No deployed repos yet — set a Website URL in repo About to appear here._\n'
    else:
        rows = []
        for i in range(0, len(cards_html), 2):
            pair = cards_html[i:i + 2]
            if len(pair) == 1:
                pair[0] = pair[0].replace('width="50%"', 'width="100%" colspan="2"')
            rows.append("  <tr>\n" + "\n".join(pair) + "\n  </tr>")
        table = '<table style="width:100%;border:none;border-spacing:10px 10px;">\n' + "\n".join(rows) + "\n</table>"
        content_block = f'\n\n<div align="center">\n\n{table}\n\n</div>\n'

    with open(README, "r") as f:
        content = f.read()

    marker = "<!-- PROJECTS:start -->"
    end_marker = "<!-- PROJECTS:end -->"
    start = content.find(marker)
    end = content.find(end_marker)
    if start != -1 and end != -1:
        new_content = content[:start + len(marker)] + "\n" + content_block + "\n" + content[end:]
        with open(README, "w") as f:
            f.write(new_content)
        log("README.md updated")
    else:
        log("Markers not found in README.md")


if __name__ == "__main__":
    main()
