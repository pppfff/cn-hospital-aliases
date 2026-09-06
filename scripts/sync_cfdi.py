"""Download public CFDI institution filings with resumable, polite pagination."""
import argparse
import json
from pathlib import Path

from cn_hospital_aliases.sources.cfdi import fetch_institutions

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path("data/raw/cfdi/2026-09-05-batch100"))
    args = parser.parse_args()
    print(json.dumps(fetch_institutions(args.output_dir), ensure_ascii=False, indent=2))
