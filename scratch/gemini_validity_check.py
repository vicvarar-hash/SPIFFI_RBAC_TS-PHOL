"""Integrity check: is Gemini-2.5-pro's extreme permissivity real, or a parse artifact?
Runs the ACTUAL ValidationService with Gemini on a few correct/wrong/null tasks and prints
the raw model output alongside the parsed is_valid. No table impact — diagnostic only.
"""
import os, sys, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def load_env():
    p = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
    for line in open(p, encoding="utf-8"):
        m = line.strip()
        if m and not m.startswith("#") and "=" in m:
            k, v = m.split("=", 1); os.environ.setdefault(k.strip(), v.strip())

load_env()
from app.loaders.astra_loader import load_astra_dataset
from app.loaders.mcp_loader import load_mcp_personas
from app.services.llm_provider import LLMProvider
from app.services.validation_service import ValidationService
from app.services.experiment_runner import _to_astra_task

tasks = load_astra_dataset(os.path.join("datasets", "astra_03_tools.json"))
personas, _ = load_mcp_personas("mcp_servers")
llm = LLMProvider(api_key=os.environ["GOOGLE_API_KEY"], model="gemini-2.5-pro", provider="google")
val = ValidationService(llm=llm, personas=personas)

# pick 2 of each tag
picks = {"correct": [], "wrong": [], "null": []}
for t in tasks:
    tag = t.get("match_tag") if isinstance(t, dict) else getattr(t, "match_tag", None)
    if tag in picks and len(picks[tag]) < 2:
        picks[tag].append(t)
    if all(len(v) == 2 for v in picks.values()):
        break

for tag, ts in picks.items():
    for t in ts:
        at = _to_astra_task(t)
        r = val.run_validation(at)
        print("=" * 70)
        print(f"tag={tag}  is_valid={r.is_valid}  issue_codes={r.issue_codes}")
        print("candidate tools:", list(at.candidate_tools)[:6])
        raw = (r.raw_output or "")[:400].replace("\n", " ")
        print("RAW:", raw)
