"""Demo CLI over the shared workflow service."""
import argparse
import json
from datetime import date
from app.workflow.service import WorkflowService, WorkflowError
from app.validation.inputs import InputValidationError
from app.llms.factory import get_llm_client
from app.workflow.delivery import DeliveryService, LocalTaskInbox


def main():
    parser = argparse.ArgumentParser(description='Persist and review retail readiness assessments')
    parser.add_argument('--db', default='readiness.sqlite3')
    parser.add_argument('--data-dir', default='data')
    parser.add_argument('--as-of', type=date.fromisoformat, default=None)
    parser.add_argument('--inbox-db', default='task_inbox.sqlite3')
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('assess')
    commands.add_parser('history')
    commands.add_parser('deliveries')
    commands.add_parser('tasks')
    enqueue = commands.add_parser('enqueue')
    enqueue.add_argument('id', help='Approved assessment ID')
    dispatch = commands.add_parser('dispatch')
    dispatch.add_argument('id', help='Delivery ID')
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
        elif args.command == 'enqueue':
            result = DeliveryService(service).enqueue(args.id, args.data_dir, args.as_of)
        elif args.command == 'dispatch':
            result = DeliveryService(service).dispatch(args.id, args.data_dir, LocalTaskInbox(args.inbox_db), args.as_of)
        elif args.command == 'deliveries':
            result = DeliveryService(service).history()
        elif args.command == 'tasks':
            result = LocalTaskInbox(args.inbox_db).tasks()
        else:
            result = service.review(args.id, args.data_dir, args.reviewer, args.decision, args.reason, args.as_of)
    except (WorkflowError, InputValidationError) as exc:
        parser.exit(1, f'Workflow stopped: {exc}\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
