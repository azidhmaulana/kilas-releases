"""Only offer a published MSI after downloading and verifying its release checksum."""
import hashlib
import json
import os
import pathlib
import re
import urllib.request

repository = os.environ['GH_REPOSITORY']
headers = {'User-Agent': 'KILAS-update-channel', 'Accept': 'application/vnd.github+json'}
token = os.environ.get('GH_TOKEN')
if token:
    headers['Authorization'] = 'Bearer ' + token
request = urllib.request.Request(f'https://api.github.com/repos/{repository}/releases?per_page=100', headers=headers)
with urllib.request.urlopen(request, timeout=30) as response:
    releases = json.load(response)

def version(release):
    match = re.fullmatch(r'v?(\d+)\.(\d+)\.(\d+)(?:-beta\.\d+)?', release['tag_name'])
    return tuple(map(int, match.groups())) if match else None

candidates = [r for r in releases if not r['draft'] and version(r)]
release = max(candidates, key=lambda r: (version(r), r['published_at']))
core = '.'.join(map(str, version(release)))
assets = {asset['name']: asset for asset in release['assets']}
installer = assets[f'Kilas-{core}-beta-x64.msi']
checksum = assets[f'Kilas-{core}-beta-x64.sha256']
with urllib.request.urlopen(checksum['browser_download_url'], timeout=60) as response:
    text = response.read(65537)
    if len(text) > 65536:
        raise ValueError('Checksum file exceeds limit')
entries = dict((parts[1].lstrip('*'), parts[0].lower()) for line in text.decode('utf-8-sig').splitlines() if len(parts := line.split()) == 2)
expected = entries[installer['name']]
if not re.fullmatch('[a-f0-9]{64}', expected):
    raise ValueError('Invalid checksum')
digest = hashlib.sha256()
size = 0
with urllib.request.urlopen(installer['browser_download_url'], timeout=180) as response:
    if not response.url.startswith('https://'):
        raise ValueError('Installer redirect must use HTTPS')
    first = response.read(8)
    if first != bytes.fromhex('d0cf11e0a1b11ae1'):
        raise ValueError('Asset is not an MSI container')
    digest.update(first)
    size += len(first)
    while chunk := response.read(1024 * 1024):
        size += len(chunk)
        if size > 512 * 1024 * 1024:
            raise ValueError('Installer exceeds limit')
        digest.update(chunk)
if digest.hexdigest() != expected or size != installer['size']:
    raise ValueError('Published installer does not match checksum or size')
path = pathlib.Path('update.json')
if path.exists():
    previous = json.loads(path.read_text(encoding='utf-8-sig'))
    old_core = tuple(map(int, previous['version'].split('-')[0].split('.')))
    if old_core > version(release):
        raise ValueError('Refusing to downgrade the update channel')
manifest = {'enabled': True, 'version': core, 'url': release['html_url'],
            'installer_url': installer['browser_download_url'], 'sha256': expected,
            'notes': 'Pembaruan KILAS tersedia. Lihat halaman rilis untuk daftar perubahan.'}
path.write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
print('Verified update channel for KILAS ' + core)
