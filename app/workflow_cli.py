"""Demo CLI over the shared workflow service."""
import argparse
import json
from datetime import date
from app.workflow.service import WorkflowService, WorkflowError
from app.validation.inputs import InputValidationError
from app.llms.factory import get_llm_client


def main():
    parser = argparse.ArgumentParser(description='Persist and review retail readiness assessments')
    parser.add_argument('--db', default='readiness.sqlite3')
    parser.add_argument('--data-dir', default='data')
    parser.add_argument('--as-of', type=date.fromisoformat, default=None)
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('assess')
    commands.add_parser('history')
    show = commands.add_parser('show')
    show.add_argument('id')
    review = commands.add_parser('review')
    review.add_argument('id')
    review.add_argument('--reviewer', required=True)
    review.add_argument('--decision', choices=('approve', 'reject'), required=True)
    review.add_argument('--reason', required=True)
    args = parser.parse_args()
    service = WorkflowService(args.db)
    try:
        if args.command == 'assess':
            result = service.assess(args.data_dir, get_llm_client(), args.as_of)
        elif args.command == 'history':
            result = service.history(args.data_dir, args.as_of)
        elif args.command == 'show':
            result = service.get(args.id, args.data_dir, args.as_of)
        else:
            result = service.review(args.id, args.data_dir, args.reviewer, args.decision, args.reason, args.as_of)
    except (WorkflowError, InputValidationError) as exc:
        parser.exit(1, f'Workflow stopped: {exc}\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
