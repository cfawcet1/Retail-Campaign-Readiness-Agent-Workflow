from datetime import date
from app.loaders.catalog_loader import load_catalog
from app.loaders.inventory_loader import load_inventory
from app.loaders.feedback_loader import load_feedback
from app.loaders.checklist_loader import load_checklist
from app.loaders.notes_loader import load_notes

from app.analyzers.catalog_analyzer import analyze_catalog
from app.analyzers.inventory_analyzer import analyze_inventory
from app.analyzers.feedback_analyzer import analyze_feedback
from app.analyzers.checklist_analyzer import analyze_checklist
from app.analyzers.notes_analyzer import analyze_notes

from app.ontology.models import (
    LaunchReadinessContext,
    ConflictRecord,
    ResolutionStatus,
    LaunchSignal
)


def detect_conflicts(
    catalog: dict,
    inventory: list[dict],
    checklist: list[dict],
    notes_text: str
) -> list[ConflictRecord]:
    conflicts = []

    catalog_skus = {
        p["sku_base"]: p["status"]
        for p in catalog.get("products", [])
    }

    inventory_sku_bases = set()
    for row in inventory:
        parts = row["sku"].split("-")
        if len(parts) < 2:
            continue
        sku_base = "-".join(parts[:2])
        inventory_sku_bases.add(sku_base)

    for sku_base in inventory_sku_bases:
        if catalog_skus.get(sku_base) == "draft":
            conflicts.append(ConflictRecord(
                field="product_status",
                source_a="product_catalog.json",
                value_a=f"{sku_base} — status: draft",
                source_b="inventory.csv",
                value_b=f"{sku_base} — present in inventory",
                resolution=ResolutionStatus.UNRESOLVED
            ))

    sms_item = next(
        (item for item in checklist if item.get("id") == "CC-003"),
        None
    )
    notes_lower = notes_text.lower()
    if sms_item and sms_item.get("status") == "incomplete":
        if "sms" in notes_lower and "awaiting" in notes_lower:
            conflicts.append(ConflictRecord(
                field="sms_schedule",
                source_a="campaign_checklist.json",
                value_a="CC-003 — SMS drop notification: incomplete",
                source_b="launch_notes.md",
                value_b="CRM awaiting final SKU confirmation before scheduling SMS",
                resolution=ResolutionStatus.NEEDS_HUMAN_REVIEW
            ))

    size_guide_item = next(
        (item for item in checklist if item.get("id") == "CC-009"),
        None
    )
    if size_guide_item and size_guide_item.get("status") == "incomplete":
        if "size guide" in notes_lower:
            conflicts.append(ConflictRecord(
                field="size_guide_status",
                source_a="campaign_checklist.json",
                value_a="CC-009 — Size guide update: incomplete",
                source_b="launch_notes.md",
                value_b="Launch notes flag size guide not updated for Soft Lounge fabric stretch profile",
                resolution=ResolutionStatus.UNRESOLVED
            ))

    return conflicts


def compute_completeness_score(
    catalog: dict,
    inventory: list[dict],
    feedback: list[dict],
    checklist: list[dict],
    notes_text: str
) -> float:
    score = 0.0
    total = 5.0

    if catalog.get("products"):
        score += 1.0
    if inventory:
        score += 1.0
    if feedback:
        score += 1.0
    if checklist:
        score += 1.0
    if notes_text and len(notes_text.strip()) > 0:
        score += 1.0

    return score / total


def extract_notes_excerpt(notes_text: str, max_chars: int = 1500) -> str:
    sections_to_extract = ["## Open Items", "## Risk Summary"]
    extracted = []

    lines = notes_text.splitlines()
    capture = False
    current_section = []

    for line in lines:
        if any(line.strip().startswith(section) for section in sections_to_extract):
            if current_section:
                extracted.extend(current_section)
            current_section = [line]
            capture = True
        elif line.startswith("## "):
            if capture:
                extracted.extend(current_section)
            current_section = []
            capture = False
            if any(line.strip().startswith(section) for section in sections_to_extract):
                current_section = [line]
                capture = True
        elif capture:
            current_section.append(line)

    if current_section:
        extracted.extend(current_section)

    excerpt = "\n".join(extracted).strip()
    return excerpt[:max_chars]


def run_pipeline(data_dir: str = "data") -> LaunchReadinessContext:

    catalog = load_catalog(f"{data_dir}/product_catalog.json")
    inventory = load_inventory(f"{data_dir}/inventory.csv")
    feedback = load_feedback(f"{data_dir}/customer_feedback.md")
    checklist = load_checklist(f"{data_dir}/campaign_checklist.json")
    notes_text = load_notes(f"{data_dir}/launch_notes.md")

    signals: list[LaunchSignal] = []
    signals.extend(analyze_catalog(catalog))
    signals.extend(analyze_inventory(inventory))
    signals.extend(analyze_feedback(feedback))
    signals.extend(analyze_checklist(checklist))
    signals.extend(analyze_notes(notes_text))

    conflicts = detect_conflicts(catalog, inventory, checklist, notes_text)

    completeness = compute_completeness_score(
        catalog, inventory, feedback, checklist, notes_text
    )

    launch_date_str = catalog.get("launch_date", "")
    try:
        launch_date = date.fromisoformat(launch_date_str)
    except ValueError:
        launch_date = date.today()

    return LaunchReadinessContext(
        launch_name=catalog.get("launch", "Unknown Launch"),
        launch_date=launch_date,
        signals=signals,
        conflicts=conflicts,
        data_completeness_score=completeness,
        notes=extract_notes_excerpt(notes_text)
    )