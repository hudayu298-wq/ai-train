"""Owner preferences may tighten, never relax the versioned progression limits."""
from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field
from typing import Literal

class Settings(BaseModel):
    model_config=ConfigDict(extra='forbid',allow_inf_nan=False)
    enabled: bool=True
    mode: Literal['either','weight','reps']='either'
    min_sessions: int=Field(default=2,ge=2,le=6,strict=True)
    rpe_ceiling: float=Field(default=8,ge=5,le=8)
    max_weight_increase_fraction: float=Field(default=.05,ge=0,le=.05)
    max_rep_change: int=Field(default=1,ge=0,le=1,strict=True)

def settings(db):
    return Settings.model_validate(db.read('progression_settings','current') or {}).model_dump()

def router(connection):
    api=APIRouter(prefix='/api/training-settings')
    @api.get('')
    def get():
        with connection() as db:return settings(db)
    @api.put('')
    def put(body:Settings):
        with connection() as db:
            db.lock_user(); db.write('progression_settings','current',body.model_dump())
            return settings(db)
    return api
