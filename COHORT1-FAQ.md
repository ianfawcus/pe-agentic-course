# Cohort 1 — Frequently Asked Questions

> Questions from participants across LinkedIn, Slack, and live sessions.
> Last updated: May 2026

---

## General / Setup

### Q: Do we get API credits as part of the course? The Anthropic console is showing $20 and $50 plans.

**Asked by:** Uzma Syed

The API key is not required to complete any exercise — every script in the course supports `--mock` mode, which simulates a real API response locally without making any API call or incurring any cost. You can work through the full course this way.

That said, the total API usage across all 8 modules is small — a few dollars at most, depending on how many times you run each exercise. We'd encourage you to invest that — getting responses from the actual model rather than a simulation is where the real learning happens. You'll see how confidence levels shift with different prompts, how the model handles edge cases in your logs, and how structured JSON output behaves under real conditions. Mock mode is there so nobody is blocked, but live mode is where the course comes to life.

To get an API key:
1. Go to [console.anthropic.com](https://console.anthropic.com)
2. Sign up and add a small credit (the minimum top-up covers the entire course several times over)
3. Generate a key and set it in your environment: `export ANTHROPIC_API_KEY=your_key_here`

No credits are provided as part of the course enrollment.

---

## Module 1

### Q: Where do I find and run the exercise files (verify_setup.py, hello_claude.py, etc.)?

**Asked by:** Anju Bala

All exercise files live in the course GitHub repository. Here is how to get to them:

**Step 1 — Clone the course repo**

If you haven't already, clone (or fork and clone) the course repository to your local machine:

```bash
git clone https://github.com/InternalDeveloperPlatform/pe-agentic-course.git
cd pe-agentic-course
```

**Step 2 — Navigate to the Module 1 folder**

Each module has its own folder. All the files you listed are inside `module1/`:

```
module1/
├── verify_setup.py       ← Run this first — pre-flight environment check
├── hello_claude.py       ← Primary exercise script — write your system prompt here
├── agent.py              ← Alternative entry point that saves output to file
├── sample_log.txt        ← Sample CI failure log (agent input)
├── agent-config.yml      ← Model and output schema configuration
└── solutions/
    └── solution.py       ← Reference implementation — read after your own attempt
```

**Step 3 — Run the pre-flight check first**

From the root of the repo, run:

```bash
python module1/verify_setup.py
```

This checks that your Python version, dependencies, and API key are all configured correctly. Fix any issues it flags before moving on to `hello_claude.py`.

**Step 4 — Set your API key (if using the Claude API)**

```bash
export ANTHROPIC_API_KEY=your_key_here
```

`hello_claude.py` supports two flags for running without making a live API call:

- `--manual` — prints the formatted prompt so you can paste it into Claude.ai for free. No API key needed.
- `--mock` — simulates a real API response locally. Useful for testing your code without consuming tokens.

```bash
python module1/hello_claude.py --manual   # paste prompt into Claude.ai manually
python module1/hello_claude.py --mock     # local mock response, no API call
```

---

> **A note on getting support:** LinkedIn works, but the fastest way to get help between sessions is the **Platform Engineering Slack workspace** — there's a dedicated course channel. Email support@platformengineering.org with your name and email address to be added. Questions posted there benefit the whole cohort, and often get answered by peers before the instructor gets to them.

---

### Q: The instructions say to clone the repo, but I need to fork it to add secrets for GitHub Actions. Which is correct?

**Asked by:** Steven

Fork first, then clone your fork. The distinction matters because GitHub Actions secrets (where you store your `ANTHROPIC_API_KEY`) can only be added to repositories you own. If you clone the original repo directly, you won't have a Settings tab and won't be able to add secrets.

Correct flow:
1. Go to [github.com/InternalDeveloperPlatform/pe-agentic-course](https://github.com/InternalDeveloperPlatform/pe-agentic-course) and click **Fork**
2. Clone your fork: `git clone https://github.com/YOUR_USERNAME/pe-agentic-course.git`
3. Add your API key: Settings → Secrets and variables → Actions → New repository secret → `ANTHROPIC_API_KEY`

The README has been updated to reflect this.

---

### Q: The exercise says to write the SYSTEM_PROMPT but it's already filled in inside hello_claude.py and agent.py. What am I supposed to do?

**Asked by:** Steven

Good catch — this was a bug in the exercise files. `hello_claude.py` has been updated: `SYSTEM_PROMPT` is now an empty string with TODO comments describing what the prompt must do. Your task is to write the prompt from scratch.

`agent.py` is intentionally pre-filled — it's the runner that GitHub Actions calls and is not the exercise file. The exercise file is `hello_claude.py` only.

If you already completed Module 1 with the filled-in prompt, you've still learned the key lesson (how the API call works and how structured output is produced). To get the full exercise value, clear the `SYSTEM_PROMPT` in your fork and write your own before checking `solutions/solution.py`.

---

### Q: The GitHub Actions workflow fails immediately — something about pip and a missing requirements.txt

**Asked by:** Steven

Correct — `requirements.txt` was missing from the root of the repo. It has been added. Pull the latest from the upstream repo (or add a `requirements.txt` containing just `anthropic` to the root of your fork) and the workflow will complete cleanly.

---

## Module 5

### Q: What are the threshold definitions and allowable values in quality-gates.json? What do the SAST findings thresholds mean?

**Asked by:** Kevin

Each gate has three fields: `metric` (what gets measured), `threshold` (the value to compare against), and `operator` (which direction the comparison runs). A gate passes when `metric <operator> threshold` is true.

Here's what each of the six gates actually does:

`test_coverage` checks `coverage_pct >= 95`. The sample data ships with 81.4%, so this gate fails out of the box. Lower the threshold to `80` in `quality-gates.json` and it passes — no code change required, which is the whole point of the architecture.

`coverage_branch` checks `coverage_branch_pct >= 80`. This measures if/else paths exercised by tests, not just lines — it's a stricter bar than line coverage, so the threshold is set lower.

`sast_findings` is the one you asked about. It checks `security_scan.high <= 0` — zero HIGH-severity findings allowed, period. Even one finding blocks the deploy. The sample data has `"high": 1`, so it fails deliberately — that's by design for the exercise. Set the threshold to `1` if you want to see it pass, but keep it at `0` in any real production gate. This is also one of the two `rollback_trigger` gates, so if it fires post-deploy, `monitor.py` escalates.

`lighthouse_score` checks `lighthouse_score >= 85`. The sample data has 91, so this one passes cleanly.

`latency_p95_delta` checks `latency_p95_delta_pct <= 10` — that's a percentage increase in P95 latency vs the previous deploy, not an absolute millisecond value. The sample data has 18.4%, so it fails and is what drives the rollback decision in `monitor.py`. This is the other `rollback_trigger` gate.

`cost_per_request_delta` checks `cost_per_request_delta_pct <= 10`. Same delta-percentage pattern as latency. Sample data has 3.2%, so it passes.

The `operator` field only ever takes `>=` (coverage and Lighthouse — higher is better) or `<=` (findings count and deltas — lower is better).

Both `triage_agent.py` and `monitor.py` read `quality-gates.json` at runtime. `monitor.py` loads only the two rollback-trigger gates. `triage_agent.py` loads all six and passes them to Claude as data alongside the pipeline results — that's the config-driven architecture the module is built around. Edit the JSON, the gate behaviour changes, no Python touched.

One thing worth knowing: the `MOCK_RESPONSE` in `triage_agent.py` shows `coverage: 74.1%`, which is a hand-crafted scenario. The actual `sample_data.json` has `coverage_pct: 81.4`. They're intentionally different — two distinct gate scenarios to illustrate different outcomes.

A good sequence to try:

1. `python module5/triage_agent.py --mock` — see the APPROVE_WITH_CONDITIONS scenario
2. Set `test_coverage.threshold` to `70` in `quality-gates.json` and run live — the coverage gate now passes, watch the decision shift
3. `python module5/monitor.py --mock` — see the rollback scenario triggered by 18.4% P95 latency
4. Set `latency_p95_delta.threshold` to `20` — latency gate passes, rollback recommendation disappears
5. Set `sast_findings.threshold` to `1` — security gate now lets one HIGH finding through

---

*More questions will be added here as they come in. If you have a question, post it in the Slack course channel.*
