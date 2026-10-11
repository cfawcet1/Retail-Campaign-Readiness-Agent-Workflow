from pathlib import Path


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

        if review.get("product") and review.get("rating") and review.get("text"):
            review["text"] = review["text"].strip()
            reviews.append(review)

    return reviews