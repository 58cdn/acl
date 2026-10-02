"""Strict YAML, bounded HTTPS downloads and classical text rule validation."""
import ipaddress
import re
import time
import urllib.request
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
MAX_BYTES = 4 * 1024 * 1024


class UniqueLoader(yaml.SafeLoader):
    pass


def mapping(loader, node, deep=False):
    result = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in result:
            raise ValueError(f"duplicate YAML key: {key}")
        result[key] = loader.construct_object(value_node, deep=deep)
    return result


UniqueLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, mapping)


def load(path):
    return yaml.load(Path(path).read_text(encoding="utf-8"), Loader=UniqueLoader)


def dump(value):
    return yaml.safe_dump(value, allow_unicode=True, sort_keys=False, width=120)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError("redirect refused")


def download(url, limit=MAX_BYTES, validate=True):
    if not url.startswith("https://raw.githubusercontent.com/"):
        raise ValueError("only GitHub raw HTTPS sources are allowed")
    opener = urllib.request.build_opener(NoRedirect)
    deadline = time.monotonic() + 45
    req = urllib.request.Request(url, headers={"User-Agent": "58cdn-acl-rule-sync", "Accept": "text/plain"})
    with opener.open(req, timeout=15) as response:
        if response.status != 200 or "html" in response.headers.get("Content-Type", "").lower():
            raise ValueError("non-text/unsuccessful response")
        data = bytearray()
        while True:
            block = response.read(65536)
            if not block:
                break
            data.extend(block)
            if len(data) > limit or time.monotonic() > deadline:
                raise ValueError("download size/time bound exceeded")
    decoded = bytes(data).decode("utf-8-sig")
    if not decoded.strip() or any(x in decoded.lower() for x in ("<html", "<!doctype", "<script", "\x00")):
        raise ValueError("empty/HTML/binary response")
    if validate:
        validate_rules(bytes(data))
    return bytes(data)


def validate_rules(data):
    if not data or len(data) > MAX_BYTES:
        raise ValueError("empty/oversized rule list")
    text = data.decode("utf-8-sig")
    if any(x in text.lower() for x in ("<html", "<!doctype", "<script", "\x00")):
        raise ValueError("HTML/binary rule list")
    rules = []
    for number, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith(("#", "//")):
            continue
        parts = line.split(",")
        kind = parts[0]
        if kind in ("IP-CIDR", "IP-CIDR6"):
            if len(parts) not in (2, 3) or (len(parts) == 3 and parts[2] != "no-resolve"):
                raise ValueError(f"invalid CIDR fields at {number}")
            network = ipaddress.ip_network(parts[1], strict=False)
            if network.version != (6 if kind == "IP-CIDR6" else 4):
                raise ValueError(f"wrong CIDR family at {number}")
        elif kind in ("DOMAIN", "DOMAIN-SUFFIX", "DOMAIN-KEYWORD", "PROCESS-NAME"):
            forbidden = r"[\r\n<>]" if kind == "PROCESS-NAME" else r"[\s<>]"
            if len(parts) != 2 or not parts[1] or re.search(forbidden, parts[1]):
                raise ValueError(f"invalid rule value at {number}")
        else:
            raise ValueError(f"unsupported classical rule {kind!r} at {number}")
        rules.append(line)
    if not rules:
        raise ValueError("comment-only rule list")
    return rules
