"""Task-sized views of existing facts; raw series and full transcripts stay out of prompts."""
import copy
from . import privacy


def compact(context):
    value = copy.deepcopy(context)
    nutrition = value.get('nutrition', {})
    value['nutrition'] = {k: nutrition.get(k) for k in ('day', 'totals', 'target', 'comparison', 'diary', 'interpretation')}
    basis=nutrition.get('target_basis',{})
    value['nutrition']['target_basis']={k:basis.get(k) for k in ('version','status','target_source','steps','warnings','calibration_id')}
    if 'current_plan' in value:
        value['current_plan']=[privacy.plan_targets(plan,invalidated=False) for plan in value['current_plan']]
        for plan in value['current_plan']:
            schedule=plan.pop('cycle_schedule',[])
            plan['cycle_overview']=[{k:week.get(k) for k in ('week','phase')} for week in schedule]
    memory = value.get('training_memory', {})
    value['training_memory'] = {k: memory.get(k) for k in ('session_count', 'training_days_last_28',
        'last_training_day', 'exercise_progress', 'recent_discomfort', 'note')}
    value['training_memory']['recent_sessions'] = [{k: r.get(k) for k in
        ('id', 'day', 'readiness', 'completion_reason', 'completion_notes', 'duration_minutes', 'summary')}
        for r in memory.get('recent_sessions', [])[:4]]
    value.pop('recent_training', None)
    return value
