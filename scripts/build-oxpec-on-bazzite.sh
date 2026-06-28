#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
build_dir="$repo_root/decky-plugin/py_modules/oxpec/build"
kver="$(uname -r)"
kdir="${KDIR:-/lib/modules/$kver/build}"
out_dir="$repo_root/decky-plugin/py_modules/oxpec/$kver"

if [[ ! -d "$kdir" ]]; then
  echo "Kernel build directory not found: $kdir" >&2
  echo "Install matching kernel-devel/kernel headers for $kver, then retry." >&2
  exit 1
fi

echo "Building oxpec.ko for $kver"
echo "Kernel build dir: $kdir"

make -C "$build_dir" clean KDIR="$kdir"
make -C "$build_dir" KDIR="$kdir"

if ! strings "$build_dir/oxpec.ko" | grep -q "ONEXPLAYER SUPER X"; then
  echo "Built oxpec.ko does not contain ONEXPLAYER SUPER X DMI string" >&2
  exit 1
fi

mkdir -p "$out_dir"
cp "$build_dir/oxpec.ko" "$out_dir/oxpec.ko"

echo "Copied rebuilt module to $out_dir/oxpec.ko"
modinfo "$out_dir/oxpec.ko" || true
