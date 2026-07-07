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

def card(repo, homepage):
    badge = f'\n\n[🔗 live site]({homepage})' if homepage else ''
    url = f'https://github.com/{USERNAME}/{repo}'
    img = f'https://github-readme-stats-eight-theta.vercel.app/api/pin/?username={USERNAME}&repo={repo}&theme=tokyonight&hide_border=true'
    return f'''

[<img src="{img}" width="520"/>]({url}){badge}'''

content_block = '\n'.join(card(r['name'], r['homepage']) for r in deployed)
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
