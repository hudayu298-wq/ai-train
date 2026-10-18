"""Reminder preferences; delivery is scheduled locally on the user's device."""
from typing import Annotated, Literal
from datetime import datetime, timezone

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field, model_validator

try:
    from . import coach, coaches
except ImportError:
    import coach
    import coaches

Clock = Annotated[str, Field(pattern=r'^([01]\d|2[0-3]):[0-5]\d$')]
Weekday = Annotated[int, Field(ge=1, le=7, strict=True)]


class ReminderSettings(BaseModel):
    model_config = ConfigDict(extra='forbid')
    coach_id: coaches.CoachId = 'steady'
    coach_name: str = Field(default='阿衡', min_length=1, max_length=16, pattern=r'.*\S.*')
    timezone: Literal['Asia/Shanghai'] = 'Asia/Shanghai'
    training_enabled: bool = False
    training_days: list[Weekday] = Field(default_factory=lambda: [1, 3, 5], max_length=7)
    training_time: Clock = '19:00'
    lead_minutes: int = Field(default=15, ge=0, le=60, strict=True)
    meals_enabled: bool = False
    meal_times: dict[Literal['breakfast', 'lunch', 'dinner'], Clock] = Field(
        default_factory=lambda: {'breakfast': '07:30', 'lunch': '12:00', 'dinner': '18:30'})

    @model_validator(mode='after')
    def validate_schedule(self):
        if len(set(self.training_days)) != len(self.training_days):
            raise ValueError('训练日不能重复')
        if self.training_enabled and not self.training_days:
            raise ValueError('至少选择一个训练日')
        if self.meals_enabled and not self.meal_times:
            raise ValueError('至少选择一餐')
        return self


def preferences(db):
    stored = coach.read(db, 'coach_reminders', 'local-coach-reminders')
    if not stored:
        return ReminderSettings().model_dump()
    return {**ReminderSettings().model_dump(), **stored,
            'coach_name': '阿衡' if stored.get('coach_name') == '林教练' else stored.get('coach_name', '阿衡')}


def router(connection, profile_model):
    api = APIRouter(prefix='/api/coach')

    @api.get('/reminders')
    def get_settings():
        with connection() as db:
            return preferences(db)

    @api.put('/reminders')
    def put_settings(settings: ReminderSettings):
        payload = settings.model_dump()
        with connection() as db:
            db.lock_user()
            coach.write(db, 'coach_reminders', 'local-coach-reminders',
                        {**payload, 'updated_at': datetime.now(timezone.utc).isoformat()})
            if settings.training_enabled:
                labels = ['周一', '周二', '周三', '周四', '周五', '周六', '周日']
                schedule = '、'.join(labels[d - 1] for d in sorted(settings.training_days))
                coach.apply_profile(db, {'days': len(settings.training_days), 'training_weekdays': sorted(settings.training_days), 'preferred_time': settings.training_time,
                    'schedule': f'{schedule} {settings.training_time}训练（北京时间）'},
                    profile_model, 'reminder_settings')
            return {**payload, 'profile': coach.state(db)}

    return api
