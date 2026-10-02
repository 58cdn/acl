"""Regression checks over repository sources and real converter output."""
import argparse
import hashlib
import json
import ipaddress
from pathlib import Path
from common import ROOT, load, dump, validate_rules
from build_private import build

CGNAT = "IP-CIDR,100.64.0.0/10,DIRECT,no-resolve"


def validate(config, generated=False):
    assert config["dns"]["enhanced-mode"] == "fake-ip"
    assert config["ipv6"] == config["dns"]["ipv6"]
    if config["ipv6"]:
        assert ipaddress.ip_network(config["dns"]["fake-ip-range6"]).version == 6
    else:
        assert "fake-ip-range6" not in config["dns"]
    assert len(config["dns"]["nameserver"]) >= 2
    assert config["dns"]["proxy-server-nameserver"]
    assert any(x.startswith("tls://") for x in config["dns"]["fallback"])
    assert all(x.endswith("#自动选择") for x in config["dns"]["fallback"]), "foreign DNS must use proxy-only egress"
    assert config["dns"]["nameserver"] == ["https://dns.alidns.com/dns-query", "https://doh.pub/dns-query"]
    assert config["dns"]["proxy-server-nameserver"] == config["dns"]["nameserver"]
    assert config["dns"]["default-nameserver"] == ["223.5.5.5", "119.29.29.29"]
    rules = config["rules"]
    assert rules[0] == CGNAT, "CGNAT must precede every proxy rule"
    assert rules[-1] == "MATCH,漏网之鱼"
    for rule in rules:
        if rule.startswith("DOMAIN-SUFFIX,") and rule.endswith(",Ai平台"):
            assert "+." + rule.split(",")[1] in config["dns"]["fallback-filter"]["domain"]
    assert rules.index("RULE-SET,AI,Ai平台") < rules.index("RULE-SET,Bing,DIRECT")
    assert rules.index("RULE-SET,OpenAi,Ai平台") < rules.index("RULE-SET,Microsoft,DIRECT")
    groups = {g["name"]: g for g in config["proxy-groups"]}
    assert groups["Ai平台"]["type"] == "select"
    assert groups["Ai平台"]["proxies"][0] == "节点选择"
    assert "DIRECT" in groups["Ai平台"]["proxies"]
    assert groups["节点选择"]["proxies"][0] == "自动选择"
    assert groups["自动选择"]["type"] == "select"
    assert all(groups[n]["type"] == "url-test" for n in groups["自动选择"]["proxies"])
    tests = [g for g in groups.values() if g["type"] == "url-test"]
    assert len(tests) == 3 and len({g["url"] for g in tests}) == 3
    for group in tests:
        assert isinstance(group["url"], str) and "urls" not in group
        assert group["include-all-proxies"] is True
        assert group["expected-status"] == 204
        assert "DIRECT" not in group.get("proxies", [])
        assert "__ALL_PROXIES__" not in group.get("proxies", [])
    if generated:
        names = {p["name"] for p in config.get("proxies", [])}
        assert names, "empty subscription must fail closed before publishing"
        assert not names.intersection(groups), "proxy/group name collision"
        assert all(p["type"] not in ("direct", "reject") for p in config["proxies"])
        assert "__ALL_PROXIES__" not in dump(config)
        assert set(groups["手动切换"]["proxies"]) == names
        for group in groups.values():
            assert all(n in names or n in groups or n in ("DIRECT", "REJECT") for n in group.get("proxies", []))
    for rule in rules:
        if rule.startswith("RULE-SET,"):
            assert rule.split(",")[1] in config["rule-providers"]
    for name, provider in config["rule-providers"].items():
        assert provider["type"] == "http" and provider["behavior"] == "classical" and provider["format"] == "text"
        relative = provider["url"].split("/master/", 1)[1]
        assert provider["url"].startswith("https://raw.githubusercontent.com/58cdn/acl/master/")
        validate_rules((ROOT / relative).read_bytes())


def route_domain(config, domain):
    """First-match regression over the domain rules used by these fixtures."""
    for rule in config["rules"]:
        parts = rule.split(",")
        if parts[0] == "RULE-SET":
            provider = config["rule-providers"][parts[1]]
            relative = provider["url"].split("/master/", 1)[1]
            candidates = [(r.split(","), parts[2]) for r in validate_rules((ROOT / relative).read_bytes())]
        else:
            candidates = [(parts[:2], parts[2] if len(parts) > 2 else parts[1])]
        for p, policy in candidates:
            if p[0] == "DOMAIN" and domain == p[1]:
                return policy
            if p[0] == "DOMAIN-SUFFIX" and (domain == p[1] or domain.endswith("." + p[1])):
                return policy
            if p[0] == "DOMAIN-KEYWORD" and p[1] in domain:
                return policy
    return None


def flatten(config):
    """Feed every provider rule through the actual core parser, not just -t's lazy provider setup."""
    rules = []
    for rule in config["rules"]:
        parts = rule.split(",")
        if parts[0] != "RULE-SET":
            rules.append(rule)
            continue
        relative = config["rule-providers"][parts[1]]["url"].split("/master/", 1)[1]
        for entry in validate_rules((ROOT / relative).read_bytes()):
            fields = entry.split(",")
            rules.append(",".join(fields[:2] + [parts[2]] + fields[2:]))
    config["rules"] = rules
    config.pop("rule-providers")
    return config


def sources():
    build(check=True)
    for pattern in ("config/*.yaml", ".github/workflows/*.yml", ".github/actions/*/*.yml"):
        for path in ROOT.glob(pattern):
            assert isinstance(load(path), dict), path
    manifest = json.loads((ROOT / "rules/sources.json").read_text())
    lock = json.loads((ROOT / "ci/tools.json").read_text())
    action = load(ROOT / ".github/actions/validate/action.yml")
    upstream = next(s for s in action["runs"]["steps"] if s.get("with", {}).get("repository") == "ZeroDeng01/sublinkPro")
    assert upstream["with"]["ref"] == lock["sublink_revision"]
    snapshot = json.loads((ROOT / "rules/snapshot.json").read_text())
    assert set(manifest) == set(snapshot["sha256"])
    for name, digest in snapshot["sha256"].items():
        data = (ROOT / f"rules/providers/{name}.list").read_bytes()
        assert hashlib.sha256(data).hexdigest() == digest
        validate_rules(data)
    for path in (ROOT / "config/Clash.ini", ROOT / "config/Clash.private.yaml"):
        config = load(path)
        validate(config)
        for domain in ("ssh.git.yun", "sub.git.yun", "open.yun", "thh.cc", "todesk.com", "todesk.io", "115.com", "docs.qq.com", "lib.ituohuang.com", "sa.linux.yun", "api.pub.dxx.cld.pub"):
            assert route_domain(config, domain) == "DIRECT", domain
        for domain in ("keke.patricialflores3637.workers.dev", "yixi.tv", "kekenet.com", "unity.com", "unity3d.com", "unitychina.cn", "plasticscm.com", "packages.unity.com", "upm-cdn.unity.com", "download.packages.unity.com", "aka.ms", "dl.google.com", "go.microsoft.com", "storage.googleapis.com"):
            assert route_domain(config, domain) == "节点选择", domain
        for domain in ("openai.com", "chatgpt.com", "claude.ai", "anthropic.com", "gemini.google.com", "copilot.microsoft.com", "copilot.cloud.microsoft", "api.githubcopilot.com"):
            assert route_domain(config, domain) == "Ai平台", domain
    print("Sources, YAML, private domains, Unity, CGNAT and AI precedence passed")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--generated", type=Path)
    p.add_argument("--flatten", type=Path)
    args = p.parse_args()
    if args.generated:
        config = load(args.generated)
        validate(config, generated=True)
        if args.flatten:
            args.flatten.write_text(dump(flatten(config)), encoding="utf-8")
        print("Real generated configuration validated:", args.generated)
    else:
        sources()
