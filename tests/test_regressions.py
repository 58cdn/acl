import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from common import ROOT, load, validate_rules, UniqueLoader
from prepare_template import choose, prepare
from sync_rules import sync
from validate import validate, route_domain
import yaml


class Regressions(unittest.TestCase):
    def test_bad_downloads(self):
        for data in (b"", b"# comments only", b"<html>bad gateway</html>", b"DOMAIN", b"IP-CIDR,999.0.0.0/8", b"DOMAIN,test.com,DIRECT", b"MATCH,DIRECT"):
            with self.subTest(data=data), self.assertRaises(ValueError):
                validate_rules(data)

    def test_duplicate_yaml(self):
        with self.assertRaises(ValueError):
            yaml.load("dns: {}\ndns: {}", Loader=UniqueLoader)

    def test_endpoint_failure_and_recovery(self):
        groups = [{"name": x, "url": x} for x in ("cf", "google", "china")]
        chosen, failed = choose(groups, lambda url: url == "china")
        self.assertEqual(chosen, "china")
        self.assertEqual(len(failed), 2)
        with self.assertRaisesRegex(ValueError, "ALL probe endpoints failed"):
            choose(groups, lambda url: False)
        def unavailable(url):
            raise TimeoutError()
        with self.assertRaisesRegex(ValueError, "ALL probe endpoints failed"):
            choose(groups, unavailable)

    def test_ipv6_and_private_composition(self):
        config = prepare(load(ROOT / "config/Clash.ini"), private=True, ipv6=True)
        self.assertTrue(config["dns"]["ipv6"] and config["ipv6"])
        self.assertEqual(config["dns"]["nameserver-policy"]["+.git.yun"], "system")
        self.assertLess(config["rules"].index("DOMAIN,ssh.git.yun,DIRECT"), config["rules"].index("MATCH,漏网之鱼"))
        validate(config)

    def test_no_empty_subscription(self):
        config = load(ROOT / "config/Clash.private.yaml")
        config["proxies"] = []
        with self.assertRaisesRegex(AssertionError, "empty subscription"):
            validate(config, generated=True)

    def test_custom_private_override_precedes_match(self):
        overlay = copy.deepcopy(load(ROOT / "config/private.override.yaml"))
        overlay["+rules"].insert(1, "DOMAIN,sample.private.example,DIRECT")
        config = prepare(load(ROOT / "config/Clash.ini"), private=True, overlay=overlay)
        self.assertEqual(route_domain(config, "sample.private.example"), "DIRECT")
        self.assertEqual(config["rules"][1], "DOMAIN,sample.private.example,DIRECT")

    def test_failure_leaves_all_old_snapshots(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "rules/providers").mkdir(parents=True)
            (root / "rules/sources.json").write_text(json.dumps({name: f"https://raw.githubusercontent.com/ACL4SSR/ACL4SSR/master/Clash/{name}.list" for name in ("A", "B")}))
            for name in ("A", "B"):
                (root / f"rules/providers/{name}.list").write_bytes(b"DOMAIN,old.example\n")
            def fetch(url):
                return b"DOMAIN,new.example\n" if "/A.list" in url else b"<html>error</html>"
            with self.assertRaises(ValueError):
                sync(root=root, fetch=fetch, revision="a" * 40)
            for name in ("A", "B"):
                self.assertEqual((root / f"rules/providers/{name}.list").read_bytes(), b"DOMAIN,old.example\n")


if __name__ == "__main__":
    unittest.main()
