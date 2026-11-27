#!/usr/bin/env bash
# Download the public datasets used here. They come from third-party GitHub
# repositories with no stated licence, so they are fetched on demand, not committed.
set -euo pipefail
cd "$(dirname "$0")"
raw=https://raw.githubusercontent.com
# Nifty 50 daily closes 2001-2023
curl -fsSL "$raw/Keshav172931/nifty50-analysis/HEAD/stocks.csv" -o nifty50_index.csv
# India VIX daily 2008-03 to 2024-08
curl -fsSL "$raw/albertodavincishekhawat/IndiaVIXanalysis/HEAD/Data/India%20VIX%20Historical%20Data.csv" -o india_vix_2008_2024.csv
# India VIX and Nifty 50 daily 2015-2025 (Yahoo Finance export)
curl -fsSL "$raw/Rithvik-Rajesh/dynamic-portfolio-allocation/HEAD/data/raw/vix.csv" -o india_vix_2015_2025.csv
curl -fsSL "$raw/Rithvik-Rajesh/dynamic-portfolio-allocation/HEAD/data/raw/nifty.csv" -o nifty50_2015_2025.csv
echo "Saved $(ls *.csv | wc -l) files in options-lab/data/"
