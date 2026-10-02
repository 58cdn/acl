"""Exercise generated fake-IP DNS with the checksum-pinned Mihomo release.

Run after ci/validate.sh has converted build/{base,private,ipv6}.yaml. Only an
isolated child process is started: no TUN, system DNS, routes, proxy listeners,
providers, or public upstreams. DNS UDP/TCP listeners bind ephemeral loopback
ports. All resolver paths point to a local trap; any upstream query fails.

This tests fake-IP answers, not Internet IPv6 reachability or production DoH.
The child alone uses the upstream SKIP_SYSTEM_IPV6_CHECK test switch: the
normal core removes the IPv6 pool on hosts without global-unicast IPv6.
No network settings are changed and no DNS assertions are skipped.
v1.19.31 needs an IPv6 pool as well as the two IPv6 switches:
https://github.com/MetaCubeX/mihomo/blob/v1.19.31/dns/middleware.go
https://github.com/MetaCubeX/mihomo/blob/v1.19.31/config/config.go
"""
import argparse
import copy
import gzip
import hashlib
import io
import ipaddress
import json
import os
import platform
import secrets
import socket
import struct
import subprocess
import tempfile
import time
import zipfile
from contextlib import ExitStack
from pathlib import Path

from common import ROOT, dump, load


def require(condition, message):
    # Do not silently remove regression checks when Python is run with -O.
    if not condition:
        raise AssertionError(message)


def verified_core():
    """Verify the downloaded archive AND its extracted executable before use."""
    lock = json.loads((ROOT / "ci/tools.json").read_text(encoding="utf-8"))
    require(lock["mihomo_version"] == "v1.19.31", "review DNS expectations for a new core")
    system = platform.system()
    asset = lock["mihomo"][system]
    archive = ROOT / ".tools" / asset["file"]
    data = archive.read_bytes()
    require(hashlib.sha256(data).hexdigest() == asset["sha256"], "Mihomo archive SHA256 mismatch")
    if system == "Windows":
        with zipfile.ZipFile(io.BytesIO(data)) as zipped:
            names = [name for name in zipped.namelist() if name.endswith(".exe")]
            require(len(names) == 1, "unexpected Mihomo release archive")
            expected = zipped.read(names[0])
    else:
        expected = gzip.decompress(data)
    core = ROOT / ".tools" / ("mihomo.exe" if system == "Windows" else "mihomo")
    require(core.read_bytes() == expected, "Mihomo executable differs from verified archive")
    version = subprocess.run([str(core), "-v"], check=True, capture_output=True,
                             text=True, timeout=10).stdout.strip()
    require("v1.19.31" in version, f"unexpected core version: {version}")
    print("Verified runtime:", version.splitlines()[0])
    return core


def loopback_sockets(stack):
    """Reserve the same ephemeral port for UDP and TCP, without SO_REUSEPORT."""
    # Retry if a TCP-only listener happens to own the kernel's chosen UDP port.
    for _ in range(20):
        udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        tcp = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            udp.bind(("127.0.0.1", 0))
            tcp.bind(udp.getsockname())
            tcp.listen(1)
        except OSError:
            udp.close()
            tcp.close()
            continue
        stack.enter_context(udp)
        stack.enter_context(tcp)
        udp.setblocking(False)
        tcp.setblocking(False)
        return udp, tcp
    raise RuntimeError("could not reserve an ephemeral loopback UDP/TCP port")


def no_upstream_queries(udp, tcp):
    """Every configured resolver points here; fake-IP must never use it."""
    try:
        data, _ = udp.recvfrom(65535)
    except BlockingIOError:
        pass
    else:
        raise AssertionError(f"unexpected loopback upstream DNS request ({len(data)} bytes)")
    try:
        connection, _ = tcp.accept()
    except BlockingIOError:
        pass
    else:
        connection.close()
        raise AssertionError("unexpected loopback upstream TCP connection")


def isolated_config(generated, listen_port, upstream_port):
    """Allowlist only tested DNS semantics; never inherit external side effects."""
    original = generated["dns"]
    # Domain filters can be kept verbatim. Rule/geosite-based filters could
    # initialize external providers or download geodata, so fail closed if a
    # later template introduces them instead of silently changing its meaning.
    require(original.get("fake-ip-filter-mode", "blacklist") in ("blacklist", "whitelist"),
            "runtime isolation supports only domain-based fake-IP filters")
    require(all(isinstance(item, str) and ":" not in item and "," not in item
                for item in original.get("fake-ip-filter", [])),
            "runtime isolation refuses provider/geodata fake-IP filters")
    dns = {key: copy.deepcopy(original[key]) for key in (
        "enable", "ipv6", "enhanced-mode", "fake-ip-range", "fake-ip-range6",
        "fake-ip-filter", "fake-ip-filter-mode", "fake-ip-ttl",
    ) if key in original}
    upstream = [f"udp://127.0.0.1:{upstream_port}"]
    dns.update({
        "listen": f"127.0.0.1:{listen_port}",
        "use-hosts": False,
        "use-system-hosts": False,
        "respect-rules": False,
        "default-nameserver": upstream,
        "nameserver": upstream,
        "proxy-server-nameserver": upstream,
        "direct-nameserver": upstream,
        "nameserver-policy": {},
        "proxy-server-nameserver-policy": {},
        "fallback": [],
        "fallback-filter": {"geoip": False, "geosite": [], "ipcidr": [], "domain": []},
    })
    return {
        "ipv6": generated["ipv6"],
        "dns": dns,
        "port": 0, "socks-port": 0, "mixed-port": 0, "redir-port": 0, "tproxy-port": 0,
        "allow-lan": False, "bind-address": "127.0.0.1",
        "external-controller": "", "external-controller-tls": "",
        "external-controller-unix": "", "external-controller-pipe": "",
        "external-ui": "", "external-ui-url": "", "external-doh-server": "",
        "ss-config": "", "vmess-config": "",
        "tun": {"enable": False, "auto-route": False, "auto-redirect": False,
                "auto-detect-interface": False, "dns-hijack": []},
        "iptables": {"enable": False, "dns-redirect": False},
        "tuic-server": {"enable": False},
        "ntp": {"enable": False, "write-to-system": False},
        "sniffer": {"enable": False},
        "geo-auto-update": False,
        "profile": {"store-selected": False, "store-fake-ip": False},
        "clash-for-android": {"append-system-dns": False},
        "proxies": [], "proxy-groups": [], "proxy-providers": {}, "rule-providers": {},
        "listeners": [], "tunnels": [], "hosts": {}, "sub-rules": {},
        "mode": "rule", "rules": ["MATCH,REJECT"], "log-level": "info",
    }


def read_name(packet, offset):
    """Decode DNS labels/compression with bounded traversal and bounds checks."""
    labels, end, seen = [], None, set()
    while True:
        require(offset < len(packet) and offset not in seen, "invalid DNS name")
        seen.add(offset)
        length = packet[offset]
        if length & 0xC0 == 0xC0:
            require(offset + 1 < len(packet), "truncated DNS pointer")
            if end is None:
                end = offset + 2
            offset = ((length & 0x3F) << 8) | packet[offset + 1]
            continue
        require(length <= 63 and offset + 1 + length <= len(packet), "invalid DNS label")
        offset += 1
        if length == 0:
            return b".".join(labels).decode("ascii").lower(), end or offset
        labels.append(packet[offset:offset + length])
        offset += length


def query(port, domain, qtype, timeout=0.3):
    txid = secrets.randbits(16)
    qname = b"".join(bytes([len(label)]) + label.encode("ascii") for label in domain.split(".")) + b"\0"
    request = struct.pack("!6H", txid, 0x0100, 1, 0, 0, 0) + qname + struct.pack("!2H", qtype, 1)
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as client:
        client.settimeout(timeout)
        client.connect(("127.0.0.1", port))
        client.send(request)
        packet = client.recv(65535)
    require(len(packet) >= 12, "truncated DNS response")
    ident, flags, questions, answers, authority, additional = struct.unpack_from("!6H", packet)
    require(ident == txid and flags & 0x8000, "DNS transaction/response mismatch")
    require(not flags & 0x7A0F, f"DNS error/opcode/truncation: flags={flags:#x}")
    require(questions == 1, "DNS question count mismatch")
    name, offset = read_name(packet, 12)
    require(offset + 4 <= len(packet), "truncated DNS question")
    require(name == domain and struct.unpack_from("!2H", packet, offset) == (qtype, 1),
            "DNS echoed question mismatch")
    offset += 4
    addresses = []
    for index in range(answers + authority + additional):
        name, offset = read_name(packet, offset)
        require(offset + 10 <= len(packet), "truncated DNS record")
        kind, cls, _, length = struct.unpack_from("!HHIH", packet, offset)
        offset += 10
        require(offset + length <= len(packet), "truncated DNS record data")
        if index < answers:
            require(name == domain and kind == qtype and cls == 1, "unexpected DNS answer")
            require(length == (4 if qtype == 1 else 16), "invalid DNS address length")
            addresses.append(ipaddress.ip_address(packet[offset:offset + length]))
        offset += length
    require(offset == len(packet), "trailing DNS response bytes")
    return addresses


def run_case(core, label, generated, expect_ipv6):
    """Run, query and always reap one fresh core, even when assertions fail."""
    with ExitStack() as stack:
        upstream_udp, upstream_tcp = loopback_sockets(stack)
        # Release a dual-protocol reservation immediately before launch. The
        # inevitable bind race fails via startup/response checks, never a skip.
        with ExitStack() as reservation:
            dns_udp, _ = loopback_sockets(reservation)
            port = dns_udp.getsockname()[1]
        directory = Path(stack.enter_context(tempfile.TemporaryDirectory(prefix="acl-mihomo-dns-")))
        isolated = isolated_config(generated, port, upstream_udp.getsockname()[1])
        path = directory / "config.yaml"
        path.write_text(dump(isolated), encoding="utf-8")
        log = stack.enter_context((directory / "core.log").open("w+b"))
        process = subprocess.Popen([str(core), "-d", str(directory), "-f", str(path)],
                                   cwd=directory, stdin=subprocess.DEVNULL,
                                   stdout=log, stderr=subprocess.STDOUT,
                                   # Upstream test hook, scoped to this DNS-only child.
                                   # Runner interfaces need not have global IPv6; all
                                   # queries stay on IPv4 loopback and AAAA is synthetic.
                                   env={**os.environ, "SKIP_SYSTEM_IPV6_CHECK": "true"})
        try:
            domain = f"acl-{label}-{secrets.token_hex(8)}.invalid"
            deadline = time.monotonic() + 15
            while True:
                require(process.poll() is None, f"{label}: core exited before DNS was ready")
                try:
                    ipv4 = query(port, domain, 1)
                    break
                except (TimeoutError, ConnectionRefusedError, ConnectionResetError):
                    no_upstream_queries(upstream_udp, upstream_tcp)
                    require(time.monotonic() < deadline, f"{label}: DNS startup timed out")
                    time.sleep(0.05)
            pool4 = ipaddress.ip_network(generated["dns"]["fake-ip-range"], strict=False)
            require(ipv4 and all(ip.version == 4 and ip in pool4 for ip in ipv4),
                    f"{label}: A answer is not in configured fake-IP pool: {ipv4}")
            ipv6 = query(port, domain, 28, timeout=2)
            if expect_ipv6:
                pool6 = ipaddress.ip_network(generated["dns"]["fake-ip-range6"], strict=False)
                require(ipv6 and all(ip.version == 6 and ip in pool6 for ip in ipv6),
                        f"{label}: expected nonempty AAAA in {pool6}, got {ipv6}; "
                        "the isolated child must retain its configured IPv6 pool")
            else:
                require(not ipv6, f"{label}: expected empty AAAA, got {ipv6}")
            no_upstream_queries(upstream_udp, upstream_tcp)
            require(process.poll() is None, f"{label}: core exited during DNS checks")
        except Exception:
            log.flush()
            log.seek(0)
            print(f"--- {label} core log ---\n{log.read().decode('utf-8', errors='replace')}")
            raise
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
        no_upstream_queries(upstream_udp, upstream_tcp)
        print(f"{label}: A={[str(ip) for ip in ipv4]}; AAAA={[str(ip) for ip in ipv6]}; "
              "zero upstream requests")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build-dir", type=Path, default=ROOT / "build")
    args = parser.parse_args()
    core = verified_core()
    configs = {}
    for variant, enabled in (("base", False), ("private", False), ("ipv6", True)):
        config = load(args.build_dir / f"{variant}.yaml")
        require(config.get("proxies"), f"{variant}: run the real CI converter first")
        require(config["ipv6"] is enabled and config["dns"]["ipv6"] is enabled,
                f"{variant}: generated IPv6 switches changed")
        require(config["dns"]["enable"] is True and config["dns"]["enhanced-mode"] == "fake-ip",
                f"{variant}: generated fake-IP DNS is disabled")
        if enabled:
            require(config["dns"].get("fake-ip-range6"), "ipv6: generated IPv6 pool is missing")
        configs[variant] = config
        run_case(core, variant, config, expect_ipv6=enabled)

    # Negative controls reproduce the original bug and exercise explicit off.
    missing_pool = copy.deepcopy(configs["ipv6"])
    missing_pool["dns"].pop("fake-ip-range6")
    run_case(core, "ipv6-missing-pool", missing_pool, expect_ipv6=False)
    disabled = copy.deepcopy(configs["ipv6"])
    disabled["ipv6"] = disabled["dns"]["ipv6"] = False
    run_case(core, "ipv6-explicit-off", disabled, expect_ipv6=False)
    print("Isolated Mihomo fake-IP DNS runtime regressions passed "
          "(child-only SKIP_SYSTEM_IPV6_CHECK=true; no host IPv6 reachability claim)")


if __name__ == "__main__":
    main()
