import runpy
from pathlib import Path

# read kajol's kajol.config.py
conf = runpy.run_path(Path(__file__).parents[1] / "kajol.config.py")["conf"]