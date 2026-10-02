"""Publish canonical private overrides as native provider lists and legacy overlay."""
import argparse
from common import ROOT, load, dump, validate_rules


def outputs():
    overlay = load(ROOT / "config/private.override.yaml")
    groups = {"DIRECT": [], "节点选择": []}
    for line in overlay["+rules"]:
        parts = line.split(",")
        if line in ("RULE-SET,Unity,节点选择", "IP-CIDR,100.64.0.0/10,DIRECT,no-resolve"):
            continue
        if len(parts) not in (3, 4) or parts[2] not in groups:
            raise ValueError(f"unsupported private policy: {line}")
        groups[parts[2]].append(",".join(parts[:2] + parts[3:]))
    result = {}
    for name, policy in (("direct", "DIRECT"), ("proxy", "节点选择")):
        content = "# Generated from config/private.override.yaml; do not edit.\n" + "\n".join(groups[policy]) + "\n"
        validate_rules(content.encode())
        result[ROOT / f"private/{name}.list"] = content
    result[ROOT / "config/clash.override.yaml"] = "# Generated compatibility alias; edit private.override.yaml, then build_private.py.\n" + dump(overlay)
    from prepare_template import prepare
    result[ROOT / "config/Clash.private.yaml"] = "# Generated SublinkPro template with private overlay; edit the sources, then build_private.py.\n" + dump(prepare(load(ROOT / "config/Clash.ini"), private=True))
    return result


def build(check=False):
    for path, content in outputs().items():
        if check:
            if not path.exists() or path.read_text(encoding="utf-8") != content:
                raise ValueError(f"stale generated private file: {path.name}")
        else:
            path.write_text(content, encoding="utf-8")
    print("Private provider lists and legacy overlay are consistent")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--check", action="store_true")
    build(p.parse_args().check)
