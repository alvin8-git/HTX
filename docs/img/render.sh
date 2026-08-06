#!/usr/bin/env bash
# Regenerate the 101 documentation figures from their Mermaid sources.
# The .mmd files are the single source of truth; the .svg files are build output.
# breadth_depth.svg has no .mmd — it is hand-written SVG (Mermaid's quadrantChart
# does not wrap label text) and is edited directly. This loop leaves it alone.
set -euo pipefail
cd "$(dirname "$0")"
export PUPPETEER_SKIP_DOWNLOAD=1
for f in *.mmd; do
  npx -y @mermaid-js/mermaid-cli@11 -i "$f" -o "${f%.mmd}.svg" -p pconf.json -c mmdconf.json -b transparent
done
