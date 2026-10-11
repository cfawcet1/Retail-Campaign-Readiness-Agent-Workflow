from pathlib import Path
from app.validation.inputs import InputValidationError


def load_feedback(path: str = "data/customer_feedback.md") -> list[dict]:
    text = Path(path).read_text()
    reviews = []
    blocks = text.split("---")

    for block in blocks:
        block = block.strip()
        if not block:
            continue
        review = {}
        lines = block.splitlines()

        for line in lines:
            line = line.strip()
            if line.startswith("**Product:**"):
                review["product"] = line.replace("**Product:**", "").strip()
            elif line.startswith("**Rating:**"):
                raw = line.replace("**Rating:**", "").strip()
                review["rating"] = int(raw.split("/")[0])
            elif line and not line.startswith("#") and not line.startswith("**"):
                review["text"] = review.get("text", "") + " " + line

        if "**Product:**" in block or "**Rating:**" in block:
            if not review.get("product") or type(review.get("rating")) is not int or not 1 <= review["rating"] <= 5 or not review.get("text", "").strip():
                raise InputValidationError("customer_feedback.md: each review requires product, rating 1-5, and text")
        if review.get("product") and review.get("rating") and review.get("text"):
            review["text"] = review["text"].strip()
            reviews.append(review)

    return reviews