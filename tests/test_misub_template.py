"""Offline structure regressions for config/MiSub.ini, not an engine emulator."""
from pathlib import Path
import re
import unittest
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
RAW_ROOT = "https://raw.githubusercontent.com/58cdn/acl/master/"
EXPECTED_REMOTE_RULES = {
    "private/direct.list": "DIRECT",
    "private/proxy.list": "节点选择",
    "private/unity.list": "节点选择",
    "rules/providers/AI.list": "Ai平台",
    "rules/providers/OpenAi.list": "Ai平台",
    "rules/providers/LocalAreaNetwork.list": "DIRECT",
    "rules/providers/UnBan.list": "DIRECT",
    "rules/providers/BanAD.list": "REJECT",
    "rules/providers/Telegram.list": "节点选择",
    "rules/providers/ProxyGFWlist.list": "节点选择",
    "rules/providers/ChinaDomain.list": "DIRECT",
}


class MiSubTemplateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.content = (ROOT / "config/MiSub.ini").read_text(encoding="utf-8")
        cls.lines = [
            line.strip() for line in cls.content.splitlines()
            if line.strip() and not line.lstrip().startswith((";", "#"))
        ]
        cls.rules = [line[8:].split(",", 1) for line in cls.lines if line.startswith("ruleset=")]
        cls.group_rows = [
            line[len("custom_proxy_group="):].split("`")
            for line in cls.lines if line.startswith("custom_proxy_group=")
        ]
        cls.groups = {parts[0]: parts[1:] for parts in cls.group_rows}

    def test_real_ini_not_yaml(self):
        self.assertEqual(self.lines[0], "[custom]")
        self.assertTrue(all(
            line.startswith(("ruleset=", "custom_proxy_group=")) for line in self.lines[1:]
        ))
        self.assertNotIn("__ALL_PROXIES__", self.content)
        self.assertNotIn("proxies:", self.content)
        self.assertEqual(len(self.rules), 14)

    def test_selected_rule_urls_and_policies(self):
        remote = [(policy, source) for policy, source in self.rules if not source.startswith("[]")]
        self.assertEqual(len(remote), 11)
        actual = {}
        for policy, source in remote:
            self.assertTrue(source.startswith(RAW_ROOT), source)
            url = urlsplit(source)
            self.assertEqual((url.scheme, url.netloc), ("https", "raw.githubusercontent.com"))
            self.assertFalse(url.query or url.fragment or url.username)
            relative = source[len(RAW_ROOT):]
            self.assertNotIn(relative, actual)
            actual[relative] = policy
        self.assertEqual(actual, EXPECTED_REMOTE_RULES)

    def test_avoid_known_provider_format_mismatch(self):
        for _, source in self.rules:
            self.assertNotIn("ChinaCompanyIp.list", source)

    def test_group_names_and_policy_references(self):
        self.assertEqual(len(self.group_rows), len(self.groups))
        self.assertEqual(set(self.groups), {"节点选择", "手动切换", "自动选择", "Ai平台", "漏网之鱼"})
        valid = set(self.groups) | {"DIRECT", "REJECT"}
        for policy, _ in self.rules:
            self.assertIn(policy, valid)
        for name, parts in self.groups.items():
            self.assertIn(parts[0], {"select", "url-test"})
            for member in parts[1:]:
                if member.startswith("[]"):
                    self.assertIn(member[2:], valid)
                    self.assertNotEqual(member[2:], name)

    def test_no_group_reference_cycles(self):
        def visit(name, active):
            self.assertNotIn(name, active, f"group reference cycle: {active} -> {name}")
            for member in self.groups[name][1:]:
                if member.startswith("[]") and member[2:] in self.groups:
                    visit(member[2:], active + (name,))
        for name in self.groups:
            visit(name, ())

    def test_node_groups_use_supported_match_all(self):
        self.assertEqual(self.groups["手动切换"], ["select", ".*"])
        self.assertEqual(self.groups["自动选择"], [
            "url-test", ".*", "https://cp.cloudflare.com/generate_204", "300,,50"
        ])
        for node in ("HK sample", "Singapore sample", "测试节点"):
            self.assertIsNotNone(re.search(self.groups["手动切换"][1], node))
        self.assertEqual(self.groups["节点选择"][1], "[]自动选择")
        self.assertEqual(self.groups["Ai平台"][1], "[]节点选择")
        self.assertEqual(self.groups["漏网之鱼"][1], "[]节点选择")

    def test_rule_precedence_and_final(self):
        self.assertEqual(self.rules[0], ["DIRECT", "[]IP-CIDR,100.64.0.0/10"])
        self.assertEqual(self.rules[-2:], [["DIRECT", "[]GEOIP,CN"], ["漏网之鱼", "[]FINAL"]])
        self.assertEqual([s[len(RAW_ROOT):] for _, s in self.rules[1:6]], [
            "private/direct.list", "private/proxy.list", "private/unity.list",
            "rules/providers/AI.list", "rules/providers/OpenAi.list"
        ])
        self.assertEqual(sum(source == "[]FINAL" for _, source in self.rules), 1)

    def test_docs_contain_published_url_and_engine(self):
        docs = (ROOT / "config/MiSub.md").read_text(encoding="utf-8")
        self.assertIn(RAW_ROOT + "config/MiSub.ini", docs)
        self.assertIn('"transformConfigMode": "custom"', docs)
        self.assertIn('"engineMode": "builtin"', docs)
        self.assertIn("Clash/Mihomo", docs)


if __name__ == "__main__":
    unittest.main()
