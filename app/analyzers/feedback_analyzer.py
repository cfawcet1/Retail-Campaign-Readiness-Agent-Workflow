from app.ontology.models import (
    LaunchSignal, EvidenceRecord, Domain, Severity, SignalType
)

THEMES = {
    "sizing": {
        "keywords": ["sizing", "runs small", "size up", "too small", "inconsistent"],
        "title": "Recurring sizing feedback from similar products",
        "description": "Multiple customer reviews mention sizing running small or inconsistent across similar Soft Lounge products."
    },
    "fabric_opacity": {
        "keywords": ["see-thru", "see through", "transparent", "sheer"],
        "title": "Fabric opacity complaints from similar products",
        "description": "Customer reviews flag fabric transparency as a concern for the Soft Lounge line."
    },
    "waistband": {
        "keywords": ["waistband", "rolling", "rolls"],
        "title": "Waistband rolling reported in similar products",
        "description": "Customer reviews mention waistband rolling in Soft Lounge pants, though at least one review attributes this to incorrect sizing."
    }
}

THEME_REVIEW_THRESHOLD = 2


def analyze_feedback(reviews: list[dict]) -> list[LaunchSignal]:
    signals = []

    for theme_id, theme in THEMES.items():
        matching_reviews = []

        for i, review in enumerate(reviews):
            text = review.get("text", "").lower()
            if any(keyword in text for keyword in theme["keywords"]):
                matching_reviews.append((i, review))

        if len(matching_reviews) >= THEME_REVIEW_THRESHOLD:
            signals.append(LaunchSignal(
                signal_id=f"FBK-{theme_id.upper()}",
                domain=Domain.FEEDBACK,
                severity=Severity.MEDIUM,
                signal_type=SignalType.SENTIMENT_THEME,
                title=theme["title"],
                description=theme["description"],
                evidence=[
                    EvidenceRecord(
                        source_file="customer_feedback.md",
                        field_path=f"review[{i}].text",
                        raw_value=r["rating"],
                        excerpt=f"{r['product']} ({r['rating']}/5): {r['text'][:120]}"
                    )
                    for i, r in matching_reviews
                ],
                requires_llm_interpretation=True
            ))

    return signals