"""
module7/orchestrator.py
Multi-Agent Orchestrator — Module 7 exercise script.

The orchestrator coordinates two specialist agents running in parallel threads,
collects their outputs, detects conflicts, and triggers synthesis or escalation.

Architecture (Orchestrator Mediation pattern)
---------------------------------------------
All messages flow through the orchestrator. Worker agents never communicate
directly with each other — the orchestrator is the single source of truth.

    Event → Orchestrator → [Gate Agent ‖ Rollback Agent] → Conflict Check → Output

Usage
-----
    python module7/orchestrator.py                    # real API calls (parallel)
    python module7/orchestrator.py --mock             # mock mode (no API key)
    python module7/orchestrator.py --scenario <name>  # specific conflict scenario
    MOCK_MODE=1 python module7/orchestrator.py

Scenarios
---------
    no_conflict      Gate: APPROVE,               Rollback: not recommended  → synthesise
    partial_conflict Gate: APPROVE_WITH_CONDITIONS, Rollback: SCHEDULED      → soft escalate
    full_conflict    Gate: APPROVE,               Rollback: IMMEDIATE        → hard escalate (Safety First)

What to complete (Part A exercise)
-----------------------------------
The orchestrator skeleton is provided. Your task:
1. Implement run_gate_agent() — calls the quality gate evaluator.
2. Implement run_rollback_agent() — calls the rollback monitor.
3. Implement detect_conflict() — compares both outputs and flags contradictions.
4. Wire them together in main() using concurrent.futures.ThreadPoolExecutor.

Reference implementation: module7/solutions/solution.py
"""

import os
import sys
import json
import argparse
import concurrent.futures
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from shared.claude_client import ask
from shared.output import save_json, to_step_summary, to_github_issue

# ── Mock mode ──────────────────────────────────────────────────────────────────
MOCK_MODE = "--mock" in sys.argv or os.environ.get("MOCK_MODE") == "1"

# ── Mock responses (one per scenario) ─────────────────────────────────────────
MOCK_SCENARIOS = {
    "no_conflict": {
        "gate_result": {
            "decision":    "APPROVE",
            "confidence":  "HIGH",
            "rationale":   "All 6 quality gates pass. Test coverage 96.2%, zero SAST findings, Lighthouse 91/100.",
            "blocking_issues": [],
            "conditions":  [],
            "risk_score":  "LOW",
            "escalate":    False,
        },
        "rollback_result": {
            "rollback_recommended": False,
            "severity":  "NONE",
            "trigger":   "No rollback-trigger gates failed.",
            "escalate":  False,
        },
        "conflict": {
            "detected": False,
            "type":     None,
            "resolution": "SYNTHESISE",
            "summary":  "Gate Agent: APPROVE. Rollback Agent: no rollback. Consistent — safe to deploy.",
        },
    },
    "partial_conflict": {
        "gate_result": {
            "decision":    "APPROVE_WITH_CONDITIONS",
            "confidence":  "MEDIUM",
            "rationale":   "Coverage at 74% (below 80% threshold) but not regressed. No critical failures.",
            "blocking_issues": [],
            "conditions":  ["Coverage must not regress below 74% in next 3 PRs"],
            "risk_score":  "MEDIUM",
            "escalate":    False,
        },
        "rollback_result": {
            "rollback_recommended": True,
            "severity":   "SCHEDULED",
            "trigger":    "latency_p95_delta: P95 latency increased 7.2% (threshold 10%) — below rollback trigger.",
            "rollback_target": "v1.8.2",
            "escalate":   False,
        },
        "conflict": {
            "detected": True,
            "type":     "SOFT_CONFLICT",
            "resolution": "SOFT_ESCALATE",
            "summary":  "Gate Agent: APPROVE_WITH_CONDITIONS. Rollback Agent: SCHEDULED rollback. Soft conflict — inform on-call but no immediate action required.",
        },
    },
    "full_conflict": {
        "gate_result": {
            "decision":    "APPROVE",
            "confidence":  "HIGH",
            "rationale":   "CI pipeline passed all gates before deploy. Snapshot taken 45 minutes ago.",
            "blocking_issues": [],
            "conditions":  [],
            "risk_score":  "LOW",
            "escalate":    False,
        },
        "rollback_result": {
            "rollback_recommended": True,
            "severity":   "IMMEDIATE",
            "trigger":    "latency_p95_delta exceeded 18.4% and error_rate_pct > 10% post-deploy.",
            "rollback_target": "v1.8.2",
            "escalate":   False,
        },
        "conflict": {
            "detected": True,
            "type":     "HARD_CONFLICT",
            "resolution": "SAFETY_FIRST_ESCALATE",
            "summary":  "Gate Agent: APPROVE (stale pre-deploy snapshot). Rollback Agent: IMMEDIATE rollback (live post-deploy data). Hard conflict — Safety First: escalate and halt all deploys until human reviews.",
        },
    },
}

# ── System prompts ─────────────────────────────────────────────────────────────
GATE_SYSTEM_PROMPT = """\
You are a quality gate evaluation agent. Assess the deployment pipeline data and
return ONLY valid JSON with keys:
- decision (APPROVE|APPROVE_WITH_CONDITIONS|REJECT): overall gate decision
- confidence (HIGH|MEDIUM|LOW): confidence in the assessment
- rationale (string): one-paragraph explanation
- blocking_issues (list of strings): empty if APPROVE
- conditions (list of strings): empty if APPROVE
- risk_score (LOW|MEDIUM|HIGH): deployment risk level
- escalate (boolean): true if human must review before proceeding
"""

ROLLBACK_SYSTEM_PROMPT = """\
You are a post-deploy rollback monitor agent. Evaluate the live metrics and
return ONLY valid JSON with keys:
- rollback_recommended (boolean): true if rollback is recommended
- severity (IMMEDIATE|SCHEDULED|OPTIONAL|NONE): urgency
- trigger (string): which metric or gate triggered the recommendation
- rollback_target (string): version or SHA to roll back to
- escalate (boolean): true if human must approve before rollback

Safety rules: never recommend IMMEDIATE rollback if db_migration_present=true.
Only recommend rollback if deploy_age_minutes < 30 AND rollback_available=true.
"""

AGENT_CONFIG = {
    "model":      "claude-opus-4-5-20251101",
    "max_tokens": 1024,
}


def load_sample() -> dict:
    sample = Path(__file__).parent / "sample_data.json"
    return json.loads(sample.read_text())


def run_gate_agent(context: dict) -> dict:
    """
    TODO (Part A): Call Claude with GATE_SYSTEM_PROMPT to evaluate quality gates.
    The context dict includes pipeline results and gate thresholds.
    """
    if MOCK_MODE:
        print("[gate_agent] [MOCK] Returning pre-defined gate evaluation.")
        return {}   # filled in by main() from MOCK_SCENARIOS

    # TODO: call ask() with GATE_SYSTEM_PROMPT and return the result
    raise NotImplementedError("Implement run_gate_agent()")


def run_rollback_agent(context: dict) -> dict:
    """
    TODO (Part A): Call Claude with ROLLBACK_SYSTEM_PROMPT to evaluate rollback need.
    The context dict includes post-deploy metrics and deploy metadata.
    """
    if MOCK_MODE:
        print("[rollback_agent] [MOCK] Returning pre-defined rollback assessment.")
        return {}   # filled in by main() from MOCK_SCENARIOS

    # TODO: call ask() with ROLLBACK_SYSTEM_PROMPT and return the result
    raise NotImplementedError("Implement run_rollback_agent()")


def detect_conflict(gate_result: dict, rollback_result: dict) -> dict:
    """
    TODO (Part A): Compare gate and rollback outputs and detect contradictions.

    Logic:
    - HARD_CONFLICT   → gate=APPROVE  AND rollback=IMMEDIATE   → SAFETY_FIRST_ESCALATE
    - SOFT_CONFLICT   → gate=APPROVE* AND rollback=SCHEDULED    → SOFT_ESCALATE
    - No conflict     → consistent outputs                      → SYNTHESISE

    Return a dict with keys: detected (bool), type (str|None), resolution (str), summary (str).
    """
    # TODO: implement conflict detection logic
    raise NotImplementedError("Implement detect_conflict()")


def main():
    parser = argparse.ArgumentParser(description="Module 7 Multi-Agent Orchestrator")
    parser.add_argument(
        "--scenario",
        choices=list(MOCK_SCENARIOS.keys()),
        default="full_conflict",
        help="Conflict scenario (for mock mode). Default: full_conflict",
    )
    parser.add_argument("--mock", action="store_true", help="Run in mock mode")
    args = parser.parse_args()

    context = load_sample()
    print(f"[orchestrator] Loaded incident: {context.get('incident', {}).get('id', 'unknown')}")

    if MOCK_MODE:
        scenario_data = MOCK_SCENARIOS[args.scenario]
        gate_result     = scenario_data["gate_result"]
        rollback_result = scenario_data["rollback_result"]
        conflict        = scenario_data["conflict"]
        print(f"[orchestrator] [MOCK MODE] Using scenario: {args.scenario}\n")
    else:
        print("[orchestrator] Running Gate Agent and Rollback Agent in parallel...")
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            gate_future     = executor.submit(run_gate_agent,     context)
            rollback_future = executor.submit(run_rollback_agent, context)
            gate_result     = gate_future.result()
            rollback_result = rollback_future.result()

        conflict = detect_conflict(gate_result, rollback_result)

    # ── Output ──────────────────────────────────────────────────────────────────
    result = {
        "gate_agent":     gate_result,
        "rollback_agent": rollback_result,
        "conflict":       conflict,
    }

    print("\n── Gate Agent ────────────────────────────────────────────────")
    print(json.dumps(gate_result, indent=2))
    print("\n── Rollback Agent ────────────────────────────────────────────")
    print(json.dumps(rollback_result, indent=2))
    print("\n── Conflict Analysis ─────────────────────────────────────────")
    print(json.dumps(conflict, indent=2))

    save_json(result, module=7, label="orchestrator")
    print(to_step_summary(result, title="Module 7 Orchestrator Result"))

    resolution = conflict.get("resolution", "")
    if "ESCALATE" in resolution:
        print(f"\n🔴 ESCALATION REQUIRED — resolution: {resolution}")
        print(to_github_issue(result, module=7))
    else:
        print("\n✅ No conflict — orchestrator produced a synthesised recommendation")

    return result


if __name__ == "__main__":
    main()
