#!/bin/sh
# Link this repo's Grok workflows into ~/.grok/workflows so they are available
# in every project. The Claude Code plugin install does not do this.
# Re-run after git pull. Existing real files are left alone.
set -eu
root=$(CDPATH= cd "$(dirname "$0")/.." && pwd)
dest="${HOME}/.grok/workflows"
mkdir -p "$dest"
found=0
for src in "$root"/grok/workflows/*.rhai; do
  [ -f "$src" ] || continue
  found=1
  name=$(basename "$src")
  target="$dest/$name"
  if [ -e "$target" ] && [ ! -L "$target" ]; then
    echo "leave $target (already a real file, not a link)" >&2
    continue
  fi
  ln -sfn "$src" "$target"
  echo "linked $target -> $src"
done
if [ "$found" -eq 0 ]; then
  echo "no workflows in $root/grok/workflows" >&2
  exit 1
fi
