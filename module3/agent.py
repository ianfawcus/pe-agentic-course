"""
module3/agent.py
Entry point for Module 3 exercise: ReAct loop — multi-step incident investigation

MOCK MODE
---------
Run without an API key to see the expected output format:
    python module3/agent.py --mock
    MOCK_MODE=1 python module3/agent.py

In real mode, the agent iterates up to max_iterations times using the ReAct
pattern: Thought → Action → Observation → repeat until finished=true.
Mock mode returns a single completed iteration to show the final output shape.
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
    "thought": "The pod is in CrashLoopBackOff with exit code 137. Exit code 137 is SIGKILL — the kernel OOM killer terminated the process. The restart count of 8 in 20 minutes confirms repeated OOM kills, not an application crash.",
    "action": "Check memory requests/limits in the pod spec and compare against actual usage from the last metrics snapshot.",
    "observation": "Pod requests 512Mi but actual peak usage before kill was 1.2Gi. The memory limit of 512Mi is causing the OOM kill. No application code change triggered this — the limit was always too low for peak load.",
    "finished": True,
    "confidence": "HIGH",
    "recommended_action": "Run: kubectl patch deployment checkout-api -p '{\"spec\":{\"template\":{\"spec\":{\"containers\":[{\"name\":\"checkout-api\",\"resources\":{\"limits\":{\"memory\":\"2Gi\"}}}]}}}}' and monitor for 10 minutes.",
    "escalate": False,
}

# ── Prompt & config ────────────────────────────────────────────────────────────
SYSTEM_PROMPT = (
    "You are a ReAct-pattern incident analysis agent. For each iteration, return ONLY valid JSON with keys: thought (string), action (string), observation (string), finished (boolean), confidence (HIGH|MEDIUM|LOW), recommended_action (string, only when finished=true), escalate (boolean)."
)

AGENT_CONFIG = {
    "model": "claude-opus-4-5-20251101",
    "max_tokens": 1024,
    "max_iterations": 5,
    "context_fields": [
        "incident_id",
        "service",
        "error_rate_pct",
        "logs"
    ]
}

def load_sample() -> str:
    sample = Path(__file__).parent / "sample_data.json"
    return sample.read_text()


def run_agent() -> dict:
    incident = load_sample()

    if MOCK_MODE:
        print("[MOCK MODE] Skipping Claude API — returning pre-defined response.")
        print("[MOCK MODE] In real mode this runs up to 5 ReAct iterations.\n")
        result = MOCK_RESPONSE
    else:
        history = []
        result  = {}

        for i in range(AGENT_CONFIG["max_iterations"]):
            # First call: just the incident. Subsequent calls: incident + full history.
            # Passing the complete history (not just the last step) lets Claude see
            # the full investigative trajectory and avoid repeating actions.
            if history:
                user_msg = (
                    f"Incident:\n{incident}\n\n"
                    f"Previous iterations:\n{json.dumps(history, indent=2)}"
                )
            else:
                user_msg = f"Incident:\n{incident}"

            result = ask(
                system=SYSTEM_PROMPT,
                user=user_msg,
                model=AGENT_CONFIG["model"],
                max_tokens=AGENT_CONFIG["max_tokens"],
            )

            print(f"\n[Iteration {i + 1}{'  — FINISHED' if result.get('finished') else ''}]")
            print(json.dumps(result, indent=2))

            history.append(result)

            # Exit as soon as Claude signals it has enough information.
            # This is the key ReAct property: the agent decides when to stop.
            if result.get("finished"):
                print(f"\n[Loop exited after {i + 1} iteration(s) — finished=True]")
                break
        else:
            # Safety net: loop exhausted without finished=True
            print(f"\n[Loop reached max_iterations={AGENT_CONFIG['max_iterations']} — using last result]")

    print(json.dumps(result, indent=2))
    save_json(result, module=3)
    print(to_step_summary(result, title="Module 3 Agent Result"))

    if result.get("escalate"):
        print("\n🔴 ESCALATION REQUIRED — creating GitHub Issue body:")
        print(to_github_issue(result, module=3))

    return result


if __name__ == "__main__":
    run_agent()
