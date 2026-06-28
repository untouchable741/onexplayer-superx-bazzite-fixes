#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
oxpec_dir="$repo_root/decky-plugin/py_modules/oxpec"
found=0

for ko in "$oxpec_dir"/*/oxpec.ko; do
  [[ -f "$ko" ]] || continue
  if grep -a -q "ONEXPLAYER SUPER X" "$ko"; then
    echo "OK: $ko contains ONEXPLAYER SUPER X"
    found=1
  else
    echo "STALE: $ko does not contain ONEXPLAYER SUPER X"
  fi
done

if [[ "$found" -ne 1 ]]; then
  echo "No bundled oxpec.ko contains ONEXPLAYER SUPER X. Rebuild on Bazzite first." >&2
  exit 1
fi
