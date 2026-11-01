#!/usr/bin/env bash
# Install the map-shorts skill (SKILL.md, scripts, references, assets) for coding agents that read Agent Skills.
#
#   ./install.sh                  Claude Code + every agent that reads ~/.agents/skills (Codex, Grok Build, ...)
#   ./install.sh claude           only ~/.claude/skills/map-shorts
#   ./install.sh agents           only ~/.agents/skills/map-shorts (Codex, Grok Build, Cline, Warp, Zed, ...)
#   ./install.sh grok codex-old   ~/.grok/skills/map-shorts, ~/.codex/skills/map-shorts (older Codex versions)
#   ./install.sh --project DIR    the same folders inside a project (DIR/.claude/skills, DIR/.agents/skills, ...)
#
# Files are copied, not linked, so run it again after `git pull` to update.
set -euo pipefail
SRC="$(cd "$(dirname "$0")" && pwd)"
NAME=map-shorts
BASE="$HOME"
targets=()
while [ $# -gt 0 ]; do
  case "$1" in
    --project) BASE="$(cd "${2:?--project needs a folder}" && pwd)"; shift 2 ;;
    claude|agents|grok|codex-old) targets+=("$1"); shift ;;
    -h|--help) sed -n '2,10p' "$0"; exit 0 ;;
    *) echo "unknown option: $1 (see --help)" >&2; exit 2 ;;
  esac
done
[ ${#targets[@]} -gt 0 ] || targets=(claude agents)
for t in "${targets[@]}"; do
  case "$t" in
    claude) dir="$BASE/.claude/skills" ;;
    agents) dir="$BASE/.agents/skills" ;;
    grok) dir="$BASE/.grok/skills" ;;
    codex-old) dir="$BASE/.codex/skills" ;;
  esac
  dest="$dir/$NAME"
  mkdir -p "$dest"
  for f in SKILL.md scripts references assets; do
    rm -rf "${dest:?}/$f"
    cp -R "$SRC/$f" "$dest/"
  done
  echo "installed: $dest"
done
echo "Needs: python3 + uv (https://docs.astral.sh/uv/), ffmpeg, curl. Map data downloads on first use to ~/.cache/map-shorts."
