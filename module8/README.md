# Module 8 — Capstone: Build Your Production Platform Agent

This is the final module. You complete a real 5-step pipeline agent that diagnoses CI failures, evaluates quality gates, decides whether to auto-fix or escalate, and writes a structured post-mortem — all without human involvement.

---

## How the Capstone Works

Open `module8/platform_agent.py`. Step 1 (INGEST) is fully implemented as a worked example — read it, then complete Steps 2–5 by implementing the four TODO functions and run the full pipeline yourself.

**Budget: ~45 minutes.**

---

## The Pipeline

| Step | Function to complete | Runs | What Claude does |
|------|----------------------|------|------------------|
| 1 | `run_step_ingest()` | Sequential | Classifies the failure event — **already done, use as your pattern** |
| 2 | `run_step_diagnose()` | **Parallel** with Step 3 | Root cause analysis — confidence HIGH/MEDIUM/LOW, fix_possible true/false |
| 3 | `run_step_gate()` | **Parallel** with Step 2 | Quality gate evaluation from INGEST (not DIAGNOSE) — APPROVE / REJECT |
| — | `detect_conflict()` | After Steps 2+3 | Safety First conflict check — **provided, do not edit** |
| 4 | `run_step_fix_or_escalate()` | Sequential | AUTO_FIX or ESCALATE — receives diagnose + gate + conflict verdict |
| 5 | `generate_report()` | Sequential | Post-mortem summary and prevention recommendations |

Steps 2 and 3 run in parallel via `ThreadPoolExecutor` inside `run_pipeline()`, which is already wired. Do not edit `run_pipeline()` or `detect_conflict()`.

---

## Setup

```bash
# From the repo root
export ANTHROPIC_API_KEY=your_key_here
python module1/verify_setup.py
```

---

## Step-by-Step Instructions

### Part 1 — Run mock mode first

Before writing any code, run the agent in mock mode to see the shape of each step's output:

```bash
python module8/platform_agent.py --simulate --mock
```

You will see five JSON blocks — INGEST, DIAGNOSE, GATE, FIX/ESCALATE, REPORT — followed by the final report and a 🔴 ESCALATION message. This is exactly what your completed functions will produce.

### Part 2 — Read the worked example

Open `platform_agent.py` and read `run_step_ingest()` carefully. Every other pipeline step follows the same three-line pattern:

```python
def run_step_ingest(event: dict) -> dict:
    return run_step("INGEST", INGEST_PROMPT, event)
```

The difference for pipeline Steps 2–5 is that you need to build a richer `context` dict that passes results from earlier steps to Claude.

### Part 3 — Complete `run_step_diagnose()` (Pipeline Step 2)

Build a context dict that contains both the original `event` and the `ingest` result, then call `run_step()` with `DIAGNOSE_PROMPT`. Follow the same pattern as `run_step_ingest()` — the docstring in the function describes exactly what the context needs to contain.

Once you implement DIAGNOSE, remove `--mock` to verify it calls Claude correctly before continuing:

```bash
ANTHROPIC_API_KEY=sk-... python module8/platform_agent.py --simulate
```

### Part 4 — Complete `run_step_gate()` (Pipeline Step 3)

Same pattern. Context combines `event` and the `ingest` result — **not** `diagnose`. Gate evaluates static quality signals from INGEST independently of the root cause analysis. See the docstring hint in the function for the expected context shape.

### Part 5 — Complete `run_step_fix_or_escalate()` (Pipeline Step 4)

This step has the key branching logic. After calling `run_step()`:

- If `result['path'] == 'AUTO_FIX'` and `result.get('auto_fix_script')` is non-empty → call `save_fix_script(result['auto_fix_script'], pipeline_id)` and add the returned path to `result['fix_script_path']`.
- Otherwise return the result as-is (ESCALATE path).

AUTO_FIX only triggers when **all four** of these conditions are true:
  - `diagnose['confidence'] == 'HIGH'`
  - `diagnose['fix_possible'] == True`
  - `conflict['resolution'] != 'SAFETY_FIRST_ESCALATE'`
  - `'migration'` is not present in the event logs

For the default `--simulate` event, the expected result is ESCALATE.

### Part 6 — Complete `generate_report()` (Pipeline Step 5)

Build context from `pipeline_id` and the full `steps` dict, call `run_step()` with `REPORT_PROMPT`.

### Part 7 — Run the full pipeline live

```bash
ANTHROPIC_API_KEY=sk-... python module8/platform_agent.py --simulate
```

All five steps should complete, each printing a JSON block. The final output will show either 🔴 ESCALATION REQUIRED or ✅ Pipeline resolved.

### Part 8 — Trigger via GitHub Actions

Push any commit to your fork to trigger the workflow manually, or use the Actions tab → "Module 8 — Capstone Agent" → "Run workflow".

The workflow also fires automatically if the `module4-broken-pipeline` workflow fails in your repo.

Check: Actions tab → select the run → verify the Step Summary tab shows the report and the artifact `module8-capstone-report` is attached.

---

## Your Deliverable — A 2–3 Minute Screen Recording

Record your screen while running the live pipeline. The video proves the agent ran (Claude's reasoning is visible, the pipeline_id is unique to your run) and is a portfolio artifact you can share in any engineering interview or team demo. No editing required.

**What to show in the recording:**

1. **Your code** — open `platform_agent.py` briefly and point to one completed TODO function.
2. **Mock mode** — run this so the 5-step structure is visible before the live run:
   ```bash
   python module8/platform_agent.py --simulate --mock
   ```
3. **Live run** — let all five steps stream in real time:
   ```bash
   ANTHROPIC_API_KEY=sk-... python module8/platform_agent.py --simulate
   ```
4. **The output file** — open `output/platform_agent_module8.json` and scroll through it to show Claude's verbatim reasoning for each step.
5. **GitHub Actions** — open the Actions tab in your browser and show the completed workflow run with the Step Summary visible.

---

## Expected Output

```
════════════════════════════════════════════════════════════
PLATFORM AGENT — pipeline_id: sim-20260403-142200
════════════════════════════════════════════════════════════

[Step 1/5] INGEST
── Step: INGEST ──────────────────────────────────────────
{ "event_type": "CI_FAILURE", "service": "platform-service",
  "failure_stage": "integration-tests", "severity": "P2", ... }

[Step 2/5] DIAGNOSE
── Step: DIAGNOSE ─────────────────────────────────────────
{ "error_type": "MigrationLockTimeout",
  "confidence": "MEDIUM", "fix_possible": false, ... }

[Step 3/5] GATE EVALUATION
── Step: GATE ─────────────────────────────────────────────
{ "decision": "REJECT", "risk_score": "HIGH", "escalate": true, ... }

[Step 4/5] FIX OR ESCALATE
── Step: FIX_OR_ESCALATE ─────────────────────────────────
{ "path": "ESCALATE", "github_issue_title": "[Agent] ...", ... }

[Step 5/5] REPORT
── Step: REPORT ───────────────────────────────────────────
{ "post_mortem_summary": "...", "recommendations": [...] }

════════════════════════════════════════════════════════════
PLATFORM AGENT — FINAL REPORT
════════════════════════════════════════════════════════════

🔴 ESCALATION REQUIRED
   Action : ESCALATE
   Issue  : [Agent] DB Migration Lock Blocking Integration Tests — Manual Intervention Required
```

**Files written:**

| File | Contents |
|------|----------|
| `output/platform_agent_module8.json` | Full structured report — all 5 steps + final_output |
| `module8/fixes/fix_<pipeline_id>.py` | Auto-fix script (only written on AUTO_FIX path) |

---

## Key Takeaway

- The capstone is a multi-agent pipeline, not a single sequential agent. DIAGNOSE and GATE run in parallel via `ThreadPoolExecutor` — the same pattern Module 7 introduced — because they are genuinely independent specialists.
- **GATE reads from INGEST, not DIAGNOSE.** Gate evaluation (severity, stage, deployment risk) does not depend on root cause analysis. Wiring it to DIAGNOSE would be a false dependency that serialises two calls that don't need to be.
- `detect_conflict()` applies the Module 7 Safety First rule: if DIAGNOSE says a fix is possible (HIGH confidence) but GATE says REJECT, GATE wins — auto-fix is blocked and the pipeline escalates.
- The four TODO functions are all three-line patterns — the architecture lives in `run_pipeline()`, which is provided. Students implement the specialists; the orchestrator wires them together.
- The recording deliverable exists for the same reason: a live pipeline run with visible conflict detection and escalation is something you can show in an engineering interview.

---

## Extra Credit

These extensions go beyond the core exercise and are genuinely how production incident pipelines evolve. None require changes to the core TODO functions — they all extend `run_pipeline()` or add new utility functions.

**Level 1 — Scenario Coverage**

Edit `--simulate` to inject a HIGH-confidence scenario (change `confidence` in the mock event so the agent returns `fix_possible: True` with `confidence: HIGH`). Then also set `GATE` to return `REJECT`. Verify that `detect_conflict()` correctly triggers `SAFETY_FIRST_ESCALATE` and that no auto-fix script is written. This is the hard-conflict scenario — the most important safety test.

**Level 2 — Timeout Handling**

Parallel calls can hang if the API is slow. Wrap each `executor.submit()` call in a `try/except` with a `future.result(timeout=30)` and a fallback response dict. A real production orchestrator never blocks indefinitely on a specialist.

**Level 3 — Third Parallel Specialist**

Add a `run_step_history(event, ingest)` specialist that queries a hypothetical `/recent-deploys` endpoint and returns the last 3 deploy SHAs with their outcomes. Pass its result into `run_step_diagnose()` context so Claude has deployment history alongside the event. This mirrors how real AIOps systems enrich incidents before diagnosis.

**Level 4 — Structured Conflict Report**

Extend `generate_report()` to include a `conflict_summary` key in its context and a dedicated section in the post-mortem: what conflict was detected, which agent won, and what the Safety First rule prevented. A post-mortem that doesn't explain the conflict resolution is incomplete.

---

## GitHub Actions

**Workflow file:** `.github/workflows/module8-capstone.yml`

| Property | Value |
|----------|-------|
| Workflow name | `Module 8 — Capstone Agent` |
| Trigger | Manual via Actions tab (with optional `simulate` input), **or** automatically when the "Module 4 — Broken Pipeline (Demo)" workflow fails |
| Script run | `python module8/platform_agent.py --simulate` (default) or `python module8/platform_agent.py` (when `simulate=false`) |
| Output artifact | `module8-capstone-report` → `output/platform_agent_module8.json` |

This workflow has two trigger modes:

**Manual trigger:** Actions tab → "Module 8 — Capstone Agent" → Run workflow. You can optionally set `simulate` to `false` to run against `sample_data.json` instead of the synthetic event.

**Automatic trigger:** When the `module4-broken-pipeline` ("Module 4 — Broken Pipeline (Demo)") workflow in your repo fails, this workflow fires automatically — but only if the conclusion is `failure`. This connects the two workflows: Module 4 intentionally breaks, Module 8 responds. This is a realistic pattern for production incident pipelines where a CI failure triggers an autonomous diagnosis and remediation agent.

The workflow only runs when `github.event_name == 'workflow_dispatch'` OR `github.event.workflow_run.conclusion == 'failure'`. If Module 4's workflow passes (which it won't — it's intentionally broken), Module 8 does not trigger.

**Prerequisite:** Add your API key as a repository secret named `ANTHROPIC_API_KEY` (Settings → Secrets and variables → Actions → New repository secret). The workflow file must be on your default branch before it appears in the Actions tab.

---

## Success Criteria

- All five steps complete and print JSON to the terminal without errors.
- `output/platform_agent_module8.json` is written and contains all five steps plus `final_output`.
- ESCALATE path: `final_output.github_issue_title` and `github_issue_body` are non-empty strings.
- AUTO_FIX path (optional — requires editing `sample_data.json` to a HIGH confidence scenario): a fix script appears in `module8/fixes/`.
- GitHub Actions workflow completes and `module8-capstone-report` artifact is attached to the run.

---

## Troubleshooting

**`NotImplementedError: Complete run_step_diagnose()`**
You haven't implemented that step yet. Follow the pattern from `run_step_ingest()` — build a context dict and call `run_step()`.

**`ModuleNotFoundError: No module named 'shared'`**
Run from the repo root, not from inside `module8/`:
```bash
# Correct
python module8/platform_agent.py --mock

# Wrong
cd module8 && python platform_agent.py --mock
```

**`JSONDecodeError` in a pipeline step**
Claude returned text that wasn't valid JSON. Check the system prompt constant for that step — it must contain "Return ONLY valid JSON". You can also add `print(raw_response)` before the parse in `shared/claude_client.py` to see what Claude actually returned.

**Step 4 always takes ESCALATE even with HIGH confidence**
Check that your `run_step_fix_or_escalate()` passes the `diagnose` result in the context dict. If Claude doesn't see `fix_possible: true` and `confidence: HIGH` in the context, it will default to ESCALATE.

**GitHub Actions workflow does not appear**
The workflow file must be on your default branch. Push your changes to `main` first, then the workflow becomes available in the Actions tab.

**`ANTHROPIC_API_KEY` secret not found in Actions**
Go to your repo → Settings → Secrets and variables → Actions → New repository secret. Name it `ANTHROPIC_API_KEY`.

---

## Files

| File | Purpose |
|------|---------|
| `platform_agent.py` | **Exercise file** — Step 1 is complete; implement Steps 2–5 |
| `sample_data.json` | Sample CI failure event (used when `--simulate` is not set) |
| `agent-config.yml` | Agent configuration (model, thresholds) |
| `solutions/solution.py` | **Reference implementation** — only read after attempting your own |
| `fixes/` | Auto-fix scripts are saved here on AUTO_FIX path |
