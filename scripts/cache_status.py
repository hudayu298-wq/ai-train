"""Local operational status, without URLs, passwords, queries or user values."""
import sys
import json
from pathlib import Path
from dotenv import load_dotenv

ROOT=Path(__file__).resolve().parent.parent
load_dotenv(ROOT/'.env',override=False)
sys.path.insert(0,str(ROOT/'backend'))
from services import cache

if __name__=='__main__':print(json.dumps(cache.status(),ensure_ascii=False,indent=2))
