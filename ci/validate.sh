#!/usr/bin/env bash
set -euo pipefail
root="$(pwd)"
python scripts/build_private.py --check
python scripts/validate.py
python -m unittest discover -s tests -v
python scripts/fetch_mihomo.py
mkdir -p build .tools/sublink/acl-check
cp ci/sublink/main.go .tools/sublink/acl-check/main.go
(
  cd .tools/sublink
  go build -o "$root/.tools/sublink-check" ./acl-check
)
python scripts/prepare_template.py --private --ipv6 --output build/ipv6.template.yaml
for variant in base private ipv6; do
  case "$variant" in
    base) template="$root/config/Clash.ini" ;;
    private) template="$root/config/Clash.private.yaml" ;;
    ipv6) template="$root/build/ipv6.template.yaml" ;;
  esac
  .tools/sublink-check "$template" "$root/build/$variant.yaml"
  python scripts/validate.py --generated "build/$variant.yaml" --flatten "build/$variant.flattened.yaml"
  .tools/mihomo -t -d "$root/.tools" -f "$root/build/$variant.yaml"
  .tools/mihomo -t -d "$root/.tools" -f "$root/build/$variant.flattened.yaml"
done
