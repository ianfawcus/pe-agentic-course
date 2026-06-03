"""
module1/hello_claude.py
Your first direct API call to Claude — Module 1 exercise script.

Usage
-----
With an API key:
    python module1/hello_claude.py

Without an API key (free Claude.ai — paste the prompt manually):
    python module1/hello_claude.py --manual

MOCK MODE (no API key, automated output for grading/CI):
    python module1/hello_claude.py --mock
    MOCK_MODE=1 python module1/hello_claude.py

The --manual flag prints the formatted prompt so you can paste it into
Claude.ai at https://claude.ai — making every exercise accessible without
an API key. This is a first-class feature, not a workaround.
"""

import os
import sys
import json
import textwrap
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

# ── Mode flags ─────────────────────────────────────────────────────────────────
MANUAL_MODE = "--manual" in sys.argv
MOCK_MODE   = "--mock"   in sys.argv or os.environ.get("MOCK_MODE") == "1"

# ── Mock response (mirrors a real Claude response) ─────────────────────────────
MOCK_RESPONSE = {
    "summary":      "The Node.js test suite failed with 3 assertion errors in auth.test.js. Memory usage reached 87% during the run, suggesting a fixture teardown leak.",
    "likely_cause": "Test fixtures are not cleaned up between test cases, retaining heap references and causing assertion failures on the third retry.",
    "next_step":    "Add explicit cleanup in the afterEach hook for auth.test.js and reduce the fixture dataset from 10,000 to 100 records.",
    "confidence":   "HIGH",
}

# TODO: Write your system prompt here.
# Your prompt must instruct Claude to:
#   1. Take the role of a platform engineering assistant
#   2. Analyse the CI/CD failure log provided by the user
#   3. Return ONLY valid JSON — no explanation, no markdown, just the JSON object
#   4. Include exactly these keys:
#      - summary      (string)            one sentence describing what failed
#      - likely_cause (string)            one sentence on the root cause
#      - next_step    (string)            one concrete remediation action
#      - confidence   (HIGH|MEDIUM|LOW)   your confidence in the diagnosis
#
# Hint: be explicit about the output format. Claude follows precise instructions well.
# Check solutions/solution.py only after you have made your own attempt.
SYSTEM_PROMPT = ""  # Replace this empty string with your prompt

# ── Sample log (embedded so the script is self-contained) ─────────────────────
SAMPLE_LOG = (Path(__file__).parent / "sample_log.txt").read_text()


def run_manual_mode() -> None:
    """Print the formatted prompt for pasting into Claude.ai."""
    separator = "─" * 60
    print(f"\n{separator}")
    print("MANUAL MODE — copy everything between the dashed lines")
    print("and paste it into https://claude.ai")
    print(f"{separator}\n")
    print("SYSTEM PROMPT:")
    print(SYSTEM_PROMPT)
    print("\nUSER MESSAGE:")
    print(f"CI failure log:\n\n{SAMPLE_LOG}")
    print(f"\n{separator}")
    print("After Claude responds, copy the JSON and paste it here.")
    print("Then save it as output/output_module1.json")
    print(f"{separator}\n")


def run_api_mode() -> dict:
    """Call the Claude API and return the parsed JSON response."""
    from shared.claude_client import ask
    return ask(
        system=SYSTEM_PROMPT,
        user=f"CI failure log:\n\n{SAMPLE_LOG}",
        max_tokens=512,
    )


def print_result(result: dict) -> None:
    """Pretty-print the result with field labels."""
    print("\n" + "─" * 60)
    print("CLAUDE RESPONSE")
    print("─" * 60)
    print(json.dumps(result, indent=2))
    print("─" * 60)

    # Save to output directory
    output_dir = Path(__file__).parent.parent / "output"
    output_dir.mkdir(exist_ok=True)
    output_path = output_dir / "output_module1.json"
    output_path.write_text(json.dumps(result, indent=2))
    print(f"\n✅ Saved to {output_path}")
    print("\nParsed fields:")
    for key, value in result.items():
        print(f"  {key:15s} → {value}")


def main():
    if MANUAL_MODE:
        run_manual_mode()
        return

    if MOCK_MODE:
        print("[MOCK MODE] Skipping Claude API — returning pre-defined response.")
        print("[MOCK MODE] Set ANTHROPIC_API_KEY and remove --mock to call the real API.\n")
        result = MOCK_RESPONSE
    else:
        print("[hello_claude] Calling Claude API...\n")
        result = run_api_mode()

    print_result(result)


if __name__ == "__main__":
    main()
