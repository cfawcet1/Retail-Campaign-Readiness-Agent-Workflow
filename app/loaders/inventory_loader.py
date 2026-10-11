import csv
from pathlib import Path
from app.validation.inputs import InputValidationError


def load_inventory(path: str = "data/inventory.csv") -> list[dict]:
    rows = []
    with open(Path(path), "r") as f:
        reader = csv.DictReader(f)
        required = {"sku", "product_name", "color", "size", "units_available", "expected_demand", "replenishment_on_order"}
        if not reader.fieldnames or not required.issubset(reader.fieldnames):
            raise InputValidationError("inventory.csv: missing required CSV columns")
        for row in reader:
            flag = row["replenishment_on_order"]
            if not isinstance(flag, str) or flag.strip().lower() not in ("true", "false"):
                raise InputValidationError(f"inventory.csv.row[{reader.line_num}].replenishment_on_order: expected true or false")
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