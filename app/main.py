import argparse
import sys
from datetime import date
from app.validation.inputs import InputValidationError
from app.orchestrator.pipeline import run_pipeline
from app.llms.factory import get_llm_client
from app.report.formatter import format_report
from app.policy.readiness import enforce_readiness


def main():
    parser = argparse.ArgumentParser(
        description=" Retail Launch Readiness Copilot"
    )
    parser.add_argument(
        "--data-dir",
        default="data",
        help="Path to directory containing launch data files (default: data/)"
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Optional path to write report to file"
    )
    parser.add_argument("--as-of", type=date.fromisoformat, default=None, help="Assessment date for source freshness (YYYY-MM-DD; default: today)")
    args = parser.parse_args()

    print("Running launch readiness pipeline...")

    try:
        context = run_pipeline(data_dir=args.data_dir, as_of=args.as_of)
    except InputValidationError as e:
        print(f"Assessment stopped: invalid input: {e}")
        sys.exit(1)

    print(f"Pipeline complete. {len(context.signals)} signals detected, "
          f"{len(context.conflicts)} conflicts detected.")

    print("Generating readiness assessment...")
    try:
        client = get_llm_client()
    except ValueError as exc:
        parser.exit(1, f'Assessment stopped: {exc}\n')
    llm_response = enforce_readiness(context, client.generate(context))

    report = format_report(context, llm_response)

    print("\n")
    print(report)

    if args.output:
        with open(args.output, "w") as f:
            f.write(report)
        print(f"\nReport written to {args.output}")


if __name__ == "__main__":
    main()
