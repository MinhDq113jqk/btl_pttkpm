"""Run with a configured admin service account; does not perform provider calls."""
import argparse
import os
import time
from uuid import UUID
from fastapi import Request
from app.core.config import Settings
from app.core.database import Database
from app.core.policy import context_for_account
from app.models.account import Account
from app.services.portal_jobs import tick


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--account-id', type=UUID, default=os.getenv('GREENCITY_WORKER_ACCOUNT_ID'))
    parser.add_argument('--site-id', type=UUID, default=os.getenv('GREENCITY_WORKER_SITE_ID'))
    parser.add_argument('--interval', type=int, default=int(os.getenv('GREENCITY_WORKER_INTERVAL_SECONDS','60')))
    parser.add_argument('--once', action='store_true')
    parser.add_argument('--schedule-id',type=UUID,help='Run just this authorized schedule, keeping its persisted cutoff.')
    parser.add_argument('--retry',action='store_true',help='Retry only failed objects; requires --schedule-id and --once.')
    args = parser.parse_args()
    if not args.account_id or not args.site_id:parser.error('account-id and site-id (or worker environment configuration) are required')
    if args.retry and (not args.schedule_id or not args.once):parser.error('retry requires schedule-id and once')
    if not 10 <= args.interval <= 3600:
        parser.error('interval must be between 10 and 3600 seconds')
    database = Database(Settings())
    try:
        while True:
            with database.get_session() as session:
                actor = session.get(Account, args.account_id)
                if actor is None or not actor.is_active:
                    raise RuntimeError('Configured service account is unavailable')
                context = context_for_account(session, actor, args.site_id)
                request=Request({'type':'http','headers':[]})
                from app.api.portal_control import run_due_schedules,run_schedule
                if args.schedule_id:
                    from app.models.operational_control import JobSchedule
                    from app.services.operational_control import load
                    row=load(session,context,JobSchedule,args.schedule_id,('admin','director'),lock=True)
                    run=run_schedule(session,context,request,row,retry=args.retry)
                    result={'run_id':str(run.id),'status':run.status,'result':run.result}
                else:
                    result=tick(session,context,request)
                    result.update(run_due_schedules(session,context,request))
                session.commit()
                print(result)
            if args.once:
                break
            time.sleep(args.interval)
    finally:
        database.close()


if __name__ == '__main__':
    main()
