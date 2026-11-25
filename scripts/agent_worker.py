"""One bounded worker tick; systemd prevents overlapping instances."""
import asyncio
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from backend import app, database as d, auth, workouts
from backend.services import research_worker, model_gateway,privacy
from sqlalchemy import select


async def followup():
    with app.connection() as db:
        rows = list(db.conn.execute(select(d.records_table).where(d.records_table.c.kind == 'agent_followup')).mappings())
    processed = 0
    for row in rows:
        value = row['payload']
        if value['status'] != 'queued' or value.get('attempts', 0) >= 2:
            continue
        owner = d.owner_context.set(row['user_id'])
        session = d.session_context.set(value['session_id'])
        events = []
        try:
            with app.connection() as db:
                db.lock_user()  # Revoked sessions cannot authorize background writes.
                privacy.require(db,value.get('privacy_revision'))
                value.update(attempts=value.get('attempts', 0)+1)
                db.write('agent_followup', row['id'], value)
            auth.rate_limit(app.DB, 'ai-day:'+row['user_id'], 100, 86400)
            with model_gateway.budget(events, max_calls=2, max_tokens=25000):
                review = await app.review_workout(value['workout_id'], workouts.ReviewRequest(coach_id=value['coach_id']))
                with app.connection() as db:
                    db.lock_user()
                    privacy.require(db,value.get('privacy_revision'))
                progression = await app.progress_workout(value['workout_id'])
            with app.connection() as db:
                db.lock_user()
                privacy.require(db,value.get('privacy_revision'))
                db.write('agent_followup', row['id'], {**value, 'status': 'completed', 'usage_events': events,
                    'result': {'summary': review['ai_review']['summary'], 'progression': progression}, 'completed_at': d.now().isoformat()})
        except Exception as exc:
            try:
                with app.connection() as db:
                    db.lock_user()
                    if privacy.current(db,value.get('privacy_revision')):
                        db.write('agent_followup', row['id'], {**value, 'status': 'failed' if value.get('attempts', 0) >= 2 else 'queued',
                            'error': '复盘未完成；训练事实已保存，可在训练记录中重试', 'error_code': type(exc).__name__, 'usage_events': events})
            except Exception:
                pass  # Deleted or revoked accounts cannot be written by a worker.
        finally:
            d.session_context.reset(session)
            d.owner_context.reset(owner)
        processed += 1
        if processed >= 3:
            break


async def main():
    await followup()
    # At most one research job per tick, with its own model budget and lease.
    print(json.dumps(await research_worker.run_once(app.connection)))


if __name__ == '__main__':
    asyncio.run(main())
