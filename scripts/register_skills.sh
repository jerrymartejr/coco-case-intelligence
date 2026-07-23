#!/usr/bin/env bash
# Register the Case Intelligence CoCo Agent Skills with your local CoCo (cortex).
# Skill registration is machine-local, so each teammate runs this once.
set -euo pipefail
DIR="$(cd "$(dirname "$0")/.." && pwd)"
for s in ask_case_intelligence diagnose_top_drivers recommend_action deliver_action; do
  cortex skill add "$DIR/coco/skills/$s"
done
echo "---"
cortex skill list | grep -A6 "Persisted skill" || true
