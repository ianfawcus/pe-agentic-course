"""
module5/solutions/solution.py
Reference solution for Module 5: Quality Gate Agent.

What this module teaches
------------------------
AI-powered release readiness evaluation across multiple threshold dimensions.
The gate evaluates six configurable criteria and returns a structured decision:
  APPROVE               — all gates pass, deploy immediately
  APPROVE_WITH_CONDITIONS — pass with caveats (e.g. coverage below threshold but not regressed)
  REJECT                — one or more blocking issues, do not deploy

The key architectural principle: the thresholds live in quality-gates.json,
not in the system prompt. Changing a threshold requires editing a config file,
not editing agent code. The agent reads the thresholds as part of its context
and applies them without any code change.

The richer SYSTEM_PROMPT in this solution (compared to the exercise file) adds
a sixth dimension — Change Risk — which evaluates deployment timing and change
volume. This demonstrates how to extend the gate without touching the pipeline code.

Compare with: module5/triage_agent.py (the exercise you completed)

Run
---
    python module5/solutions/solution.py --mock
    ANTHROPIC_API_KEY=sk-... python module5/solutions/solution.py
"""

import os
import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from shared.claude_client import ask
from shared.output import save_json, to_step_summary, to_github_issue

# ── Mock mode ──────────────────────────────────────────────────────────────────
MOCK_MODE = "--mock" in sys.argv or os.environ.get("MOCK_MODE") == "1"

# Mock shows APPROVE_WITH_CONDITIONS — the most instructive case:
# all critical gates pass but a non-blocking issue (coverage) plus a contextual
# risk factor (Friday deploy window) result in conditions, not a full APPROVE.
MOCK_RESPONSE = {
    "decision":    "APPROVE_WITH_CONDITIONS",
    "confidence":  "HIGH",
    "rationale": (
        "All critical gates pass: test pass rate 97.3%, zero SAST HIGH findings, "
        "Lighthouse performance 91/100. Coverage is 74.1% — below the 80% threshold "
        "but has not regressed from the previous run. Friday deploy window elevates risk."
    ),
    "blocking_issues": [],
    "conditions": [
        "Coverage must not regress below 74% in the next three PRs",
        "Deploy should target off-peak hours (before 14:00 UTC) given the Friday window",
        "Monitor error rate for 15 minutes post-deploy before closing the incident channel",
    ],
    "risk_score":               "MEDIUM",
    "recommended_deploy_window": "Before 14:00 UTC today or defer to Monday 09:00 UTC",
    # change_risk_score and change_risk_reason are additional dimensions in this
    # solution (not in the exercise file). They show how to extend the gate schema
    # without changing the pipeline code — just update the system prompt and mock.
    "change_risk_score":  "HIGH",
    "change_risk_reason": "Friday deploy with 623 lines changed across 14 files — exceeds the 500-line change risk threshold",
    "escalate": False,
}

# ── System prompt ──────────────────────────────────────────────────────────────
# The five standard gate thresholds are NOT hardcoded here — they are loaded
# from quality-gates.json and injected into the user message at runtime.
# This means changing a threshold requires only a JSON edit, not a code change.
#
# The sixth dimension (Change Risk) IS defined here because it captures
# contextual factors (deploy day, lines changed) that are not metric thresholds
# and don't belong in quality-gates.json. Demonstrating how to extend the gate
# schema without touching pipeline code is the point of this solution.
SYSTEM_PROMPT = (
    "You are a release readiness evaluation agent. You will receive pipeline results "
    "and a list of quality gates, each with a metric name, threshold, and operator. "
    "Evaluate every gate. A gate passes when: metric_value <operator> threshold.\n\n"
    "Additionally, apply a sixth dimension not in the gate list:\n"
    "  Change Risk — HIGH if deploy_day is Friday AND lines_changed > 500.\n\n"
    "Return ONLY valid JSON with keys:\n"
    "  decision (APPROVE|APPROVE_WITH_CONDITIONS|REJECT),\n"
    "  confidence (HIGH|MEDIUM|LOW),\n"
    "  rationale (string — one paragraph),\n"
    "  blocking_issues (list of strings — empty if APPROVE),\n"
    "  conditions (list of strings — empty if APPROVE),\n"
    "  risk_score (LOW|MEDIUM|HIGH),\n"
    "  recommended_deploy_window (string),\n"
    "  change_risk_score (LOW|MEDIUM|HIGH),\n"
    "  change_risk_reason (string),\n"
    "  escalate (boolean — true only if REJECT with a P1 security finding)."
)

AGENT_CONFIG = {
    "model":      "claude-opus-4-5-20251101",
    "max_tokens": 1024,
}


def load_sample() -> dict:
    """Load pipeline results from sample_data.json."""
    return json.loads((Path(__file__).parent.parent / "sample_data.json").read_text())


def load_gates() -> list:
    """Load quality gate thresholds from quality-gates.json.

    Thresholds live in config, not in the system prompt. Editing quality-gates.json
    changes gate behaviour without touching any Python code — that is the
    architectural principle this module demonstrates.
    """
    gates_path = Path(__file__).parent.parent / "quality-gates.json"
    data = json.loads(gates_path.read_text())
    return data.get("gates", [])


def run_agent() -> dict:
    """
    Quality gate evaluation agent: single-shot, returns structured decision.

    The gate is intentionally single-shot (not a ReAct loop) because release
    readiness is an evaluation task, not an investigation task. All the data
    is available upfront in the pipeline results — there is nothing to look up.
    Claude reasons over the complete context in one call and returns a decision.

    Contrast with Module 3 (ReAct): diagnosing an unknown K8s incident benefits
    from iteration because the agent can request more information. Evaluating
    known pipeline metrics against known thresholds does not.
    """
    pipeline = load_sample()
    gates    = load_gates()

    if MOCK_MODE:
        print("[MOCK MODE] Skipping Claude API — returning pre-defined response.")
        print("[MOCK MODE] Shows APPROVE_WITH_CONDITIONS — typical borderline case.\n")
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

    # Print the gate decision in a format suitable for a CI log
    decision = result.get("decision", "UNKNOWN")
    if decision == "APPROVE":
        print("\n✅ Gate APPROVED — safe to deploy")
    elif decision == "APPROVE_WITH_CONDITIONS":
        print(f"\n⚠️  Gate APPROVED WITH CONDITIONS:")
        for c in result.get("conditions", []):
            print(f"   • {c}")
    else:
        print(f"\n🔴 Gate REJECTED — do not deploy")
        for b in result.get("blocking_issues", []):
            print(f"   • {b}")

    if result.get("escalate"):
        print("\n🔴 ESCALATION REQUIRED — GitHub Issue body:")
        print(to_github_issue(result, module=5))

    return result


if __name__ == "__main__":
    run_agent()
