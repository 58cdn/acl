"""Check immutable PR-head URLs, or the exact published master URLs after merge."""
import argparse
import concurrent.futures
import hashlib
from common import ROOT, download, load, validate_rules


def check(revision=None):
    providers = load(ROOT / "config/Clash.ini")["rule-providers"]
    def one(item):
        name, provider = item
        url = provider["url"]
        prefix = "https://raw.githubusercontent.com/58cdn/acl/master/"
        if not url.startswith(prefix) or provider.get("format") != "text":
            raise ValueError(f"invalid published provider {name}")
        relative = url[len(prefix):]
        local = (ROOT / relative).resolve()
        if ROOT not in local.parents:
            raise ValueError("provider escapes repository")
        local_bytes = local.read_bytes()
        validate_rules(local_bytes)
        checked_url = url if revision is None else url.replace("/master/", f"/{revision}/")
        content = download(checked_url)
        if content != local_bytes:
            raise ValueError(f"remote bytes differ: {name}")
        return {"name": name, "checked_url": checked_url, "published_url": url,
                "sha256": hashlib.sha256(content).hexdigest()}
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(one, providers.items()))
    import json
    print(json.dumps(results, indent=2))
    print(f"Validated {len(results)} exact provider bodies ({'PR-head mapping' if revision else 'published URLs'})")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--revision", help="immutable head commit before merge; omit for published master URLs")
    check(p.parse_args().revision)
