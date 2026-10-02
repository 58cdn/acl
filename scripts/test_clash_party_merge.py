"""Run the exact checksum-pinned Clash Party deepMerge, not a local imitation."""
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from common import ROOT, load, dump, download
from build_private import legacy_overlay

lock = json.loads((ROOT / 'ci/tools.json').read_text())['clash_party']
url = f"https://raw.githubusercontent.com/mihomo-party-org/clash-party/{lock['revision']}/src/main/utils/merge.ts"
source = download(url, validate=False)
if hashlib.sha256(source).hexdigest() != lock['merge_sha256']:
    raise ValueError('Clash Party deepMerge checksum mismatch; refusing execution')
module = ROOT / '.tools/clash-party-merge.mts'
module.parent.mkdir(exist_ok=True)
module.write_bytes(source)
base = load(Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / 'config/Clash.ini')
overlay = load(ROOT / 'config/private.override.yaml')
# Exercise scalar +domain keys and a user-specified resolver list separately.
array_overlay = load(ROOT / 'config/private.override.yaml')
array_overlay['dns']['nameserver-policy']['+.git.yun'] = ['system']
fixture = {'base': base, 'canonical': overlay, 'legacy': load(ROOT / 'config/clash.override.yaml'),
           'arrayCanonical': array_overlay, 'arrayLegacy': legacy_overlay(array_overlay)}
result = subprocess.run(['node', str(ROOT / 'ci/clash-party-merge.mjs')],
                        input=json.dumps(fixture), text=True, capture_output=True, check=True)
merged = json.loads(result.stdout)
output = ROOT / 'build/legacy.yaml'
output.parent.mkdir(exist_ok=True)
output.write_text(dump(merged), encoding='utf-8')
print(f'Pinned Clash Party deepMerge passed: {lock["revision"]}; wrote {output}')
