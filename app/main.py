import argparse
import sys
from app.orchestrator.pipeline import run_pipeline
from app.llms.factory import get_llm_client
from app.report.formatter import format_report


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
    args = parser.parse_args()

    print("Running launch readiness pipeline...")

    try:
        context = run_pipeline(data_dir=args.data_dir)
    except FileNotFoundError as e:
        print(f"Error loading data: {e}")
        sys.exit(1)

    print(f"Pipeline complete. {len(context.signals)} signals detected, "
          f"{len(context.conflicts)} conflicts detected.")

    print("Generating readiness assessment...")
    client = get_llm_client()
    llm_response = client.generate(context)

    report = format_report(context, llm_response)

    print("\n")
    print(report)

    if args.output:
        with open(args.output, "w") as f:
            f.write(report)
        print(f"\nReport written to {args.output}")


if __name__ == "__main__":
    main()