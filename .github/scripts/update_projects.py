#!/usr/bin/env python3
"""Update README.md projects section with self-hosted repo cards."""

import os
import json
import urllib.request

USERNAME = os.environ['GITHUB_REPOSITORY_OWNER']
TOKEN = os.environ.get('GH_TOKEN', os.environ.get('GITHUB_TOKEN', ''))
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CARDS_DIR = os.path.join(SCRIPT_DIR, '..', '..', 'stats', 'repos')

TOKYO = {
    "card": "#181825", "border": "#313244", "blue": "#89b4fa",
    "yellow": "#f9e2af", "sub": "#a6adc8",
}
LANG_COLORS = {
    "Python": "#3776AB", "JavaScript": "#F7DF1E", "CSS": "#1572B6",
    "HTML": "#E34F26", "C": "#A8B9CC", "C++": "#00599C", "Java": "#ED8B00",
    "Shell": "#4EAA25", "TypeScript": "#3178C6",
}

HEADERS = {"User-Agent": "GitHub-Actions", "Accept": "application/vnd.github.v3+json"}
if TOKEN:
    HEADERS["Authorization"] = f"token {TOKEN}"


def api_get(url):
    req = urllib.request.Request(url, headers=HEADERS)
    return json.loads(urllib.request.urlopen(req, timeout=15).read())


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


os.makedirs(CARDS_DIR, exist_ok=True)

repos = api_get(f'https://api.github.com/users/{USERNAME}/repos?per_page=100&sort=stars&direction=desc')
deployed = [r for r in repos if r.get('homepage') and not r['fork'] and r['name'] != USERNAME]
deployed.sort(key=lambda r: r['stargazers_count'], reverse=True)

content_block = ""
for r in deployed:
    svg = generate_repo_card(r)
    path = os.path.join(CARDS_DIR, f'{r["name"]}.svg')
    with open(path, "w") as f:
        f.write(svg)
    url = f"https://github.com/{USERNAME}/{r['name']}"
    img = f"https://raw.githubusercontent.com/{USERNAME}/{USERNAME}/main/stats/repos/{r['name']}.svg"
    badge = f'\n\n[🔗 live site]({r["homepage"]})' if r.get('homepage') else ''
    content_block += f'\n\n[<img src="{img}" width="520"/>]({url}){badge}'

if not content_block:
    content_block = '\n\n_No deployed repos yet — set a Website URL in repo About to appear here._\n'

with open('README.md', 'r') as f:
    content = f.read()

marker = '<!-- PROJECTS:start -->'
end_marker = '<!-- PROJECTS:end -->'
start = content.find(marker)
end = content.find(end_marker)
if start != -1 and end != -1:
    new_content = content[:start + len(marker)] + '\n' + content_block + '\n' + content[end:]
    with open('README.md', 'w') as f:
        f.write(new_content)
    print('README.md updated')
else:
    print('Markers not found')
