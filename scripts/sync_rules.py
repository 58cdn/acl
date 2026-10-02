"""Download and validate a complete batch before replacing any checked-in list."""
import argparse
import concurrent.futures
import hashlib
import json
import os
import tempfile
import time
from pathlib import Path

from common import ROOT, download, validate_rules


def sync(root=ROOT, fetch=None, check=False, revision=None):
    if fetch is None:
        fetch = lambda url: download(url, validate=False)
    manifest = json.loads((root / "rules/sources.json").read_text(encoding="utf-8"))
    paths = {}
    for name, url in manifest.items():
        if not name.isalnum() or not url.startswith("https://raw.githubusercontent.com/ACL4SSR/ACL4SSR/master/Clash/"):
            raise ValueError("invalid source manifest")
        paths[name] = root / "rules/providers" / f"{name}.list"
    if not revision or len(revision) != 40 or any(c not in "0123456789abcdef" for c in revision):
        raise ValueError("an explicit upstream commit SHA is required")
    urls = [url.replace("/master/", f"/{revision}/") for url in manifest.values()]
    def bounded_fetch(url):
        for attempt in range(3):
            try:
                return fetch(url)
            except (OSError, TimeoutError):
                if attempt == 2:
                    raise
                time.sleep(1)
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        data = dict(zip(paths, pool.map(bounded_fetch, urls)))
    upstream_hashes = {name: hashlib.sha256(content).hexdigest() for name, content in data.items()}
    compatibility_path = root / "rules/compatibility.json"
    compatibility = json.loads(compatibility_path.read_text(encoding="utf-8")) if compatibility_path.exists() else {}
    for name, content in data.items():
        lines = content.decode("utf-8-sig").splitlines()
        converted = []
        for line in lines:
            if line.startswith("URL-REGEX,"):
                if line not in compatibility.get(name, []):
                    raise ValueError(f"new unsupported rule requires review: {name}: {line}")
                line = "# Unsupported by Mihomo; upstream retained: " + line
            converted.append(line)
        data[name] = ("\n".join(converted) + "\n").encode("utf-8")
        validate_rules(data[name])
    changed = [name for name, path in paths.items() if not path.exists() or path.read_bytes() != data[name]]
    if check:
        print(f"Validated {len(data)} upstream lists; {len(changed)} differ from the reviewed snapshot")
        return changed
    staged = []
    try:
        for name in changed:
            target = paths[name]
            target.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(dir=target.parent, delete=False) as handle:
                handle.write(data[name])
                staged.append((Path(handle.name), target))
        for temporary, target in staged:
            os.replace(temporary, target)
        snapshot = {"repository": "ACL4SSR/ACL4SSR", "revision": revision,
                    "license": "CC-BY-SA-4.0", "upstream_sha256": upstream_hashes,
                    "sha256": {name: hashlib.sha256(content).hexdigest() for name, content in data.items()}}
        # Written only after the complete validated batch, with no timestamps/no-op noise.
        (root / "rules/snapshot.json").write_text(json.dumps(snapshot, indent=2) + "\n", encoding="utf-8")
    finally:
        for temporary, _ in staged:
            temporary.unlink(missing_ok=True)
    print(f"Validated {len(data)} upstream lists; updated {len(changed)} files")
    for name in changed:
        print(f"{name}: sha256={hashlib.sha256(data[name]).hexdigest()}")
    return changed


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="validate upstream without writing")
    parser.add_argument("--revision", required=True, help="one ACL4SSR commit for the entire batch")
    args = parser.parse_args()
    sync(check=args.check, revision=args.revision)
