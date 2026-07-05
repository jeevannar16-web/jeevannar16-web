import os, json, urllib.request

USERNAME = os.environ['GITHUB_REPOSITORY_OWNER']
TOKEN = os.environ.get('GH_TOKEN', '')

req = urllib.request.Request(
    f'https://api.github.com/users/{USERNAME}/repos?per_page=100&sort=stars&direction=desc',
    headers={'Authorization': f'token {TOKEN}', 'User-Agent': 'GitHub-Actions'}
)
repos = json.loads(urllib.request.urlopen(req).read())

deployed = [r for r in repos if r.get('homepage') and not r['fork'] and r['name'] != USERNAME]
deployed.sort(key=lambda r: r['stargazers_count'], reverse=True)

def pin(repo, homepage):
    badge = f'<br><sub><a href="{homepage}">🔗 live site</a></sub>' if homepage else ''
    url = f'https://github.com/{USERNAME}/{repo}'
    img = f'https://github-readme-stats-eight-theta.vercel.app/api/pin/?username={USERNAME}&repo={repo}&theme=tokyonight&hide_border=true'
    return f'              <a href="{url}">\n                <img src="{img}" width="100%"/>\n              </a>{badge}'

rows = []
i = 0
while i < len(deployed):
    r1 = deployed[i]
    if i + 1 < len(deployed):
        r2 = deployed[i + 1]
        rows.append(f'''          <tr>
            <td width="50%">{pin(r1['name'], r1['homepage'])}</td>
            <td width="50%">{pin(r2['name'], r2['homepage'])}</td>
          </tr>''')
    else:
        rows.append(f'''          <tr>
            <td width="50%">{pin(r1['name'], r1['homepage'])}</td>
            <td width="50%"></td>
          </tr>''')
    i += 2

table = f'''<table>
{chr(10).join(rows)}
        </table>''' if rows else '<p align="center"><i>No deployed repos yet — set a Website URL in repo About to appear here.</i></p>'

with open('README.md', 'r') as f:
    content = f.read()

marker = '<!-- PROJECTS:start -->'
end_marker = '<!-- PROJECTS:end -->'
start = content.find(marker)
end = content.find(end_marker)
if start != -1 and end != -1:
    new_content = content[:start + len(marker)] + '\n' + table + '\n' + content[end:]
    with open('README.md', 'w') as f:
        f.write(new_content)
    print('README.md updated')
else:
    print('Markers not found')
