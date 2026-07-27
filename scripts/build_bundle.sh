#!/usr/bin/env bash
# Build a clean, distributable bundle of the CRM Report Card skill.
#
# Includes only what a downloader needs: SKILL.md, README.md, assets/,
# properties.yaml (the default property catalogue SKILL.md cites),
# scripts/crm_report_card/ (kept under a scripts/ subfolder), and one demo
# fixture CSV.
#
# Excludes: docs/ (internal spec + plan), tests/, eval/, .superpowers/,
# fixtures/*.expected.json (eval ground truth), pyproject.toml dev config,
# and all __pycache__ directories.
#
# One documented PYTHONPATH cannot be right in all three layouts, so the copies
# are rewritten on the way in:
#   repo root     PYTHONPATH=crm-report-card/scripts   (README.md, as authored)
#   plugin install PYTHONPATH=${CLAUDE_PLUGIN_ROOT}/scripts (SKILL.md, as authored)
#   this bundle   PYTHONPATH=scripts                   (rewritten below)
# A README or SKILL that names a path which does not exist where it is read is
# a broken first command, so the rewrite is verified before the bundle is done.
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

OUT="${OUT:-dist/crm-report-card}"
rm -rf "$OUT"
mkdir -p "$OUT"

# SKILL.md ships plugin-rooted; inside the bundle the package sits at scripts/.
sed -e 's|"\${CLAUDE_PLUGIN_ROOT}/scripts"|scripts|g' \
    -e 's|\${CLAUDE_PLUGIN_ROOT}/scripts|scripts|g' \
    crm-report-card/skills/crm-report-card/SKILL.md > "$OUT/SKILL.md"

# README.md is authored for a repo-root checkout, where the package sits under
# crm-report-card/scripts. That directory does not exist inside the bundle.
sed -e 's|PYTHONPATH=crm-report-card/scripts|PYTHONPATH=scripts|g' \
    -e 's|`crm-report-card/scripts`|`scripts`|g' \
    -e 's|Run everything from the repo root\.|Run everything from this folder.|' \
    README.md > "$OUT/README.md"

cp -R crm-report-card/assets "$OUT"/
cp crm-report-card/properties.yaml "$OUT"/

# Keep the scripts/crm_report_card/ layout intact so PYTHONPATH=scripts
# matches the rewritten SKILL.md and README.md exactly.
mkdir -p "$OUT/scripts"
cp -R crm-report-card/scripts/crm_report_card "$OUT/scripts"/

mkdir -p "$OUT/fixtures"
cp fixtures/messy-crm-sample.csv "$OUT/fixtures"/

# Strip caches (dev-only, never shipped).
find "$OUT" -name '__pycache__' -type d -prune -exec rm -rf {} +

# Fail loudly rather than shipping a bundle whose first command cannot work.
if grep -RIl -e 'CLAUDE_PLUGIN_ROOT' -e 'PYTHONPATH=crm-report-card/scripts' "$OUT" >/dev/null 2>&1; then
  echo "build_bundle: a bundled file still names a path that does not exist here" >&2
  grep -RIn -e 'CLAUDE_PLUGIN_ROOT' -e 'PYTHONPATH=crm-report-card/scripts' "$OUT" >&2
  exit 1
fi

echo "bundle ready at $OUT"
