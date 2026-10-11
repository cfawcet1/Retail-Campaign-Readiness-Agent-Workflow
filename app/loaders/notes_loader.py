from pathlib import Path


def load_notes(path: str = "data/launch_notes.md") -> str:
    return Path(path).read_text()