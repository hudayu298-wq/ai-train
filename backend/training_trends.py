"""Descriptive weekly/cycle/muscle summaries; no inferred strength or diagnosis."""
from datetime import date, timedelta
from fastapi import APIRouter, Query
try:
    from . import workouts, library
except ImportError:
    import workouts, library

def calculate(items, catalog, days):
    end=workouts.today(); start=end-timedelta(days=days-1)
    weeks={}; cycles={}; muscles={}
    for workout in items:
        day=date.fromisoformat(workout['day'])
        if not start<=day<=end:continue
        week=(day-timedelta(days=day.weekday())).isoformat()
        cycle=(workout.get('plan_snapshot') or {}).get('cycle_id') or workout.get('plan_id') or 'unlinked'
        for group,key in ((weeks,week),(cycles,cycle)):
            bucket=group.setdefault(key,{'key':key,'sessions':0,'working_sets':0})
            bucket['sessions']+=1
        for exercise in workout['exercises']:
            count=sum(s.get('set_type','working')=='working' for s in exercise['sets'])
            weeks[week]['working_sets']+=count;cycles[cycle]['working_sets']+=count
            for muscle in set(catalog.get(exercise['exercise_id'],{}).get('primary_muscles') or ['未标注肌群']):
                muscles[muscle]=muscles.get(muscle,0)+count
    # Include empty weeks so missing records cannot look like continuous activity.
    cursor=start-timedelta(days=start.weekday())
    while cursor<=end:
        weeks.setdefault(cursor.isoformat(),{'key':cursor.isoformat(),'sessions':0,'working_sets':0})
        cursor+=timedelta(days=7)
    return {'from':start.isoformat(),'through':end.isoformat(),
        'weeks':[weeks[k] for k in sorted(weeks)],'cycles':list(cycles.values()),
        'muscles':[{'name':k,'working_sets':v} for k,v in sorted(muscles.items())],
        'note':'按确认记录统计；0表示没有记录，不证明未训练。肌群由动作标签归属，同一组可属于多个肌群，不能相加当总组数；标签不代表肌肉激活或专业审核。'}

def router(connection):
    api=APIRouter(prefix='/api/training-trends')
    @api.get('')
    def get(days:int=Query(default=84,ge=7,le=365)):
        with connection() as db:items=workouts.history(db)
        return calculate(items,{e['id']:e for e in library.all_entries(connection,'exercises')},days)
    return api
