import json
from pathlib import Path


def load_catalog(path: str = "data/product_catalog.json") -> dict:
    with open(Path(path), "r") as f:
        data = json.load(f)
    return data