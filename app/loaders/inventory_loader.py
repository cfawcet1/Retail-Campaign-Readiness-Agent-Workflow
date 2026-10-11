import csv
from pathlib import Path


def load_inventory(path: str = "data/inventory.csv") -> list[dict]:
    rows = []
    with open(Path(path), "r") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append({
                "sku": row["sku"],
                "product_name": row["product_name"],
                "color": row["color"],
                "size": row["size"],
                "units_available": int(row["units_available"]),
                "expected_demand": int(row["expected_demand"]),
                "replenishment_on_order": row["replenishment_on_order"].strip().lower() == "true"
            })
    return rows