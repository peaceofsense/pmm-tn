from pathlib import Path

# Anchors paths to the project root, regardless of where you run the script from
PROJECT_ROOT = Path(__file__).resolve().parent
DATA_DIR = PROJECT_ROOT / "data"
DATA_DIR_RAW = DATA_DIR / "raw"
DATA_DIR_INT = DATA_DIR / "interim"
DATA_DIR_PRO = DATA_DIR / "processed"
