import json
from pathlib import Path


def load_checklist(path: str = "data/campaign_checklist.json") -> list[dict]:
    with open(Path(path), "r") as f:
        data = json.load(f)
    return data["campaign_checklist"]