"""
module1/agent.py
Entry point for Module 1 exercise: Hello Agent — First Claude API call

MOCK MODE
---------
Run without an API key to see the expected output format:
    python module1/agent.py --mock
    MOCK_MODE=1 python module1/agent.py

Mock mode returns a pre-defined response that matches what Claude would produce,
so you can verify your environment, output files, and GitHub Actions step are
wired correctly before spending API credits.
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

# Pre-defined response that mirrors what Claude would return for sample_log.txt
MOCK_RESPONSE = {
    "summary": "The Node.js test suite failed with 3 assertions failing in auth.test.js. Memory usage climbed to 87% during the run, indicating a possible memory leak in the test fixture teardown.",
    "likely_cause": "Uncleaned test fixtures are retaining references between test cases, causing heap growth and eventual assertion failures on the third retry.",
    "next_step": "Add explicit cleanup in the afterEach hook for auth.test.js and reduce the fixture dataset size from 10,000 to 100 records for unit tests.",
}

# ── Prompt & config ────────────────────────────────────────────────────────────
SYSTEM_PROMPT = (
    "You are a platform engineering assistant. Analyse the log snippet and return ONLY valid JSON with keys: summary (string), likely_cause (string), next_step (string)."
)

AGENT_CONFIG = {
    "model": "claude-opus-4-5-20251101",
    "max_tokens": 512,
    "max_iterations": 1,
    "context_fields": [
        "log_snippet"
    ]
}

def load_sample() -> str:
    sample = Path(__file__).parent / "sample_log.txt"
    return sample.read_text()


def run_agent() -> dict:
    context = load_sample()

    if MOCK_MODE:
        print("[MOCK MODE] Skipping Claude API — returning pre-defined response.")
        print("[MOCK MODE] Set ANTHROPIC_API_KEY and remove --mock to call the real API.\n")
        result = MOCK_RESPONSE
    else:
        result = ask(
            system=SYSTEM_PROMPT,
            user=f"Context:\n{context}",
            model=AGENT_CONFIG["model"],
            max_tokens=AGENT_CONFIG["max_tokens"],
        )

    print(json.dumps(result, indent=2))
    save_json(result, module=1)
    print(to_step_summary(result, title="Module 1 Agent Result"))

    if result.get("escalate"):
        print("\n🔴 ESCALATION REQUIRED — creating GitHub Issue body:")
        print(to_github_issue(result, module=1))

    return result


if __name__ == "__main__":
    run_agent()

