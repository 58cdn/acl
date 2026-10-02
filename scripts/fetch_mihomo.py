"""Download the pinned official core, verify before extracting or executing."""
import gzip
import hashlib
import io
import json
import platform
import subprocess
import zipfile
from pathlib import Path
from common import ROOT

lock = json.loads((ROOT / "ci/tools.json").read_text())
system = platform.system()
asset = lock["mihomo"][system]
directory = ROOT / ".tools"
directory.mkdir(exist_ok=True)
archive = directory / asset["file"]
url = f'https://github.com/MetaCubeX/mihomo/releases/download/{lock["mihomo_version"]}/{asset["file"]}'
curl = "curl.exe" if system == "Windows" else "curl"
subprocess.run([curl, "--fail", "--location", "--proto", "=https", "--max-time", "180", "--retry", "2", "--max-filesize", "80000000", "--output", str(archive), url], check=True)
data = archive.read_bytes()
if hashlib.sha256(data).hexdigest() != asset["sha256"]:
    raise ValueError("Mihomo SHA256 mismatch; refusing execution")
if system == "Windows":
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        names = [n for n in z.namelist() if n.endswith(".exe")]
        if len(names) != 1:
            raise ValueError("unexpected release archive")
        binary = z.read(names[0])
else:
    binary = gzip.decompress(data)
target = directory / ("mihomo.exe" if system == "Windows" else "mihomo")
target.write_bytes(binary)
target.chmod(0o755)
print(f"Verified official Mihomo {lock['mihomo_version']}: {asset['sha256']}")
geo = directory / "Country.mmdb"
geo_url = f'https://raw.githubusercontent.com/MetaCubeX/meta-rules-dat/{lock["geoip_revision"]}/country.mmdb'
subprocess.run([curl, "--fail", "--location", "--proto", "=https", "--max-time", "120", "--retry", "2", "--max-filesize", "20000000", "--output", str(geo), geo_url], check=True)
data = geo.read_bytes()
if hashlib.sha1(f"blob {len(data)}\0".encode() + data).hexdigest() != lock["geoip_git_blob"]:
    raise ValueError("GeoIP snapshot Git blob mismatch")
print("Verified official GeoIP snapshot:", lock["geoip_revision"])
