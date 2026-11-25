"""Show operational routing configuration without secrets or user data."""
import json
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

ROOT=Path(__file__).resolve().parent.parent
load_dotenv(ROOT/'.env',override=False)
sys.path.insert(0,str(ROOT))
from backend.services import agent_routing as routing

if __name__=='__main__':
    print(json.dumps({'version':routing.VERSION,'policy_hash':routing.fingerprint(),
        'mode':os.environ.get('AGENT_ROUTING_MODE','hybrid'),
        'decision_layer':routing.decision_gateway.status(),
        'local_encoder_present':routing.neural.assets_present('embedding')},ensure_ascii=False,indent=2))
