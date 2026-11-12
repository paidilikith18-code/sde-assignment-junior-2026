import json
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
FIXTURES_DIR = BASE_DIR / "assignment-b-workflow" / "fixtures"


def load_config():
    config_path = FIXTURES_DIR / "campaigns.json"

    with open(config_path, "r", encoding="utf-8") as file:
        config = json.load(file)

    return config
