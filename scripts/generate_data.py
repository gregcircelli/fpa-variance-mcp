"""Build the synthetic database: python scripts/generate_data.py [path]"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from fpa_variance_mcp.sample_data import build  # noqa: E402

out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parents[1] / "data" / "fpa.db"
build(out)
print(f"Wrote {out}")
