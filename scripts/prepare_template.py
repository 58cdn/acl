"""Prepare YAML for the real SublinkPro loader, with explicit endpoint failure."""
import argparse
import copy
import json
import urllib.request
from pathlib import Path
from common import ROOT, load, dump, NoRedirect


def probe(url):
    opener = urllib.request.build_opener(NoRedirect)
    with opener.open(urllib.request.Request(url, headers={"User-Agent": "acl-probe"}), timeout=5) as response:
        return response.status == 204


def choose(groups, check=probe):
    failures = []
    for group in groups:
        try:
            if check(group["url"]):
                return group["name"], failures
            failures.append({"group": group["name"], "error": "expected HTTP 204"})
        except Exception as exc:
            failures.append({"group": group["name"], "error": type(exc).__name__})
    raise ValueError("ALL probe endpoints failed; no template published: " + json.dumps(failures, ensure_ascii=False))


def prepare(base, private=False, ipv6=False, probe_endpoints=False, check=probe, overlay=None):
    config = copy.deepcopy(base)
    config["ipv6"] = config["dns"]["ipv6"] = ipv6
    # Mihomo returns empty AAAA in fake-ip mode without an IPv6 pool.
    if ipv6:
        config["dns"]["fake-ip-range6"] = "fc00::/18"
    else:
        config["dns"].pop("fake-ip-range6", None)
    if private:
        overlay = overlay if overlay is not None else load(ROOT / "config/private.override.yaml")
        hooks = {"RULE-SET,PrivateDirect,DIRECT", "RULE-SET,PrivateProxy,节点选择", "RULE-SET,Unity,节点选择", "IP-CIDR,100.64.0.0/10,DIRECT,no-resolve"}
        config["rules"] = overlay["+rules"] + [r for r in config["rules"] if r not in hooks]
        config["rule-providers"].update(overlay["rule-providers"])
        config["dns"]["nameserver-policy"].update(overlay["dns"]["nameserver-policy"])
        config["dns"]["fake-ip-filter"] += overlay["dns"]["fake-ip-filter"]
    if probe_endpoints:
        groups = [g for g in config["proxy-groups"] if g["type"] == "url-test"]
        chosen, failures = choose(groups, check)
        selector = next(g for g in config["proxy-groups"] if g["name"] == "自动选择")
        selector["proxies"] = [chosen] + [name for name in selector["proxies"] if name != chosen]
        print(json.dumps({"selected": chosen, "failed_before_selection": failures}, ensure_ascii=False))
    return config


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--private", action="store_true")
    p.add_argument("--ipv6", action="store_true")
    p.add_argument("--probe", action="store_true", help="try endpoints in order; fail if all fail")
    args = p.parse_args()
    config = prepare(load(ROOT / "config/Clash.ini"), args.private, args.ipv6, args.probe)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(dump(config), encoding="utf-8")
