#!/usr/bin/env bash
#SBATCH --job-name=D
#SBATCH --output=D.out
set -euo pipefail

echo "[D] starting on $(hostname) — both B and C have completed"
sleep 5
echo "[D] done"
