#!/usr/bin/env bash
#SBATCH --job-name=E
#SBATCH --output=E.out
#SBATCH --mem=40G
set -euo pipefail

echo "[E] starting on $(hostname) — D has completed"
sleep 5
echo "[E] done"
