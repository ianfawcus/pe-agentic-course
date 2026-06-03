"""
module5/triage_agent.py
Entry point for Module 5 exercise: Quality gate agent — evaluate release readiness and decide deploy/hold

MOCK MODE
---------
Run without an API key to see the expected output format:
    python module5/triage_agent.py --mock
    MOCK_MODE=1 python module5/triage_agent.py

The mock response shows APPROVE_WITH_CONDITIONS — the typical borderline case
where most gates pass but a coverage delta or risk factor triggers a condition.
"""

import os
import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from shared.claude_client import ask
from shared.output import save_json, to_step_summary, to_github_issue

# ── Mock mode flag ─────────────────────────────────────────────────────────────
MOCK_MODE = "--mock" in sys.argv or os.environ.get("MOCK_MODE") == "1"

MOCK_RESPONSE = {
    "decision": "APPROVE_WITH_CONDITIONS",
    "confidence": "HIGH",
    "rationale": "All critical gates pass: test pass rate 97.3%, zero SAST HIGH findings, Lighthouse performance 91/100. Coverage is 74.1% — below the 80% threshold but has not regressed from the previous run (was 74.3%). The borderline coverage combined with a Friday deploy window creates elevated risk.",
    "blocking_issues": [],
    "conditions": [
        "Coverage must not regress below 74% in the next three PRs",
        "Deploy should target off-peak hours (before 14:00 UTC) given the Friday window",
        "Monitor error rate for 15 minutes post-deploy before closing the incident channel"
    ],
    "risk_score": "MEDIUM",
    "recommended_deploy_window": "Before 14:00 UTC today or defer to Monday 09:00 UTC",
    "escalate": False,
}

# ── Prompt & config ────────────────────────────────────────────────────────────
SYSTEM_PROMPT = (
    "You are a release readiness evaluation agent. Assess the pipeline results and return ONLY valid JSON with keys: decision (APPROVE|APPROVE_WITH_CONDITIONS|REJECT), confidence (HIGH|MEDIUM|LOW), rationale (string), blocking_issues (list of strings), conditions (list of strings, empty if decision=APPROVE), risk_score (LOW|MEDIUM|HIGH), recommended_deploy_window (string), escalate (boolean)."
)

AGENT_CONFIG = {
    "model":      "claude-opus-4-5-20251101",
    "max_tokens": 1024,
}


def load_sample() -> dict:
    """Load pipeline results from sample_data.json."""
    sample = Path(__file__).parent / "sample_data.json"
    return json.loads(sample.read_text())


def load_gates() -> list:
    """Load all quality gate thresholds from quality-gates.json.

    Keeping thresholds in a config file (not in the system prompt) means you
    can change a gate threshold with a one-line JSON edit — no code change
    required. The agent receives the thresholds as data and applies them.
    """
    gates_path = Path(__file__).parent / "quality-gates.json"
    data = json.loads(gates_path.read_text())
    return data.get("gates", [])


def run_agent() -> dict:
    pipeline = load_sample()
    gates    = load_gates()

    if MOCK_MODE:
        print("[MOCK MODE] Skipping Claude API — returning pre-defined response.")
        print("[MOCK MODE] This shows APPROVE_WITH_CONDITIONS — the typical borderline gate result.\n")
        result = MOCK_RESPONSE
    else:
        context = {
            "pipeline_results": pipeline,
            "quality_gates":    gates,
        }
        result = ask(
            system=SYSTEM_PROMPT,
            user=f"Evaluate this pipeline against the provided quality gates:\n\n{json.dumps(context, indent=2)}",
            model=AGENT_CONFIG["model"],
            max_tokens=AGENT_CONFIG["max_tokens"],
        )

    print(json.dumps(result, indent=2))
    save_json(result, module=5)
    print(to_step_summary(result, title="Module 5 Agent Result"))

    if result.get("escalate"):
        print("\n🔴 ESCALATION REQUIRED — creating GitHub Issue body:")
        print(to_github_issue(result, module=5))

    return result


if __name__ == "__main__":
    run_agent()
