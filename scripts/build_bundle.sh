#!/usr/bin/env bash
# Build a clean, distributable bundle of the CRM Report Card skill.
#
# Includes only what a downloader needs: SKILL.md, README.md, assets/,
# scripts/crm_report_card/ (kept under a scripts/ subfolder so the documented
# `PYTHONPATH=scripts python3 -m crm_report_card.cli ...` invocation works
# unchanged inside the bundle), and one demo fixture CSV.
#
# Excludes: docs/ (internal spec + plan), tests/, eval/, .superpowers/,
# fixtures/*.expected.json (eval ground truth), pyproject.toml dev config,
# and all __pycache__ directories.
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

OUT="dist/crm-report-card"
rm -rf "$OUT"
mkdir -p "$OUT"

cp SKILL.md README.md "$OUT"/
cp -R assets "$OUT"/

# Keep the scripts/crm_report_card/ layout intact so PYTHONPATH=scripts
# matches SKILL.md and README.md exactly, both outside and inside the bundle.
mkdir -p "$OUT/scripts"
cp -R scripts/crm_report_card "$OUT/scripts"/

mkdir -p "$OUT/fixtures"
cp fixtures/messy-crm-sample.csv "$OUT/fixtures"/

# Strip caches (dev-only, never shipped).
find "$OUT" -name '__pycache__' -type d -prune -exec rm -rf {} +

echo "bundle ready at $OUT"
