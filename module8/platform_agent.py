"""
module8/platform_agent.py
Capstone Platform Agent — Module 8.

Multi-agent incident pipeline — the full pattern from Modules 1–7 combined.

Architecture
------------
                    INGEST  (Step 1)
                       │
           ┌───────────┴───────────┐
           ▼                       ▼
       DIAGNOSE               GATE
      (parallel)            (parallel)       ← ThreadPoolExecutor, like Module 7
           │                       │
           └───────────┬───────────┘
                       ▼
               Conflict Check               ← Safety First rule from Module 7
                       │
               FIX / ESCALATE  (Step 4)
                       │
                   REPORT  (Step 5)

Key design decisions
--------------------
• DIAGNOSE and GATE are independent specialists — GATE evaluates static quality
  signals from INGEST and does not need the root cause from DIAGNOSE.
• Running them in parallel cuts wall-clock time for the two most expensive steps.
• detect_conflict() applies the Module 7 Safety First rule: if DIAGNOSE says a fix
  is possible (HIGH confidence) but GATE says REJECT, GATE wins — always.

Your task (Steps 2–5)
---------------------
Step 1 (INGEST) is fully implemented as a worked example. Steps 2–5 follow the
exact same three-line pattern. Complete each TODO function in order and run --mock
after each one to verify before moving on.

  Step 2  run_step_diagnose(event, ingest)                   ← TODO
  Step 3  run_step_gate(event, ingest)                       ← TODO  [reads from INGEST, not DIAGNOSE]
  Step 4  run_step_fix_or_escalate(event, diagnose, gate,    ← TODO
                                   conflict, pipeline_id)
  Step 5  generate_report(pipeline_id, steps)                ← TODO

detect_conflict() and run_pipeline() are already wired — do not edit them.

Usage
-----
    python module8/platform_agent.py --simulate --mock
    ANTHROPIC_API_KEY=sk-... python module8/platform_agent.py --simulate

Reference solution: module8/solutions/solution.py
"""

import os
import sys
import json
import argparse
import concurrent.futures  # ← EXTRA CREDIT Level 2: needed for TimeoutError in parallel step handling
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from shared.claude_client import ask
from shared.output import save_json, to_github_issue

# ── Mock mode ──────────────────────────────────────────────────────────────────
MOCK_MODE = "--mock" in sys.argv or os.environ.get("MOCK_MODE") == "1"

MOCK_REPORT = {
    "pipeline_id":   "pipe-2024-0130-012",
    "run_timestamp": "2026-04-03T14:00:00Z",
    "steps": {
        "ingest": {
            "status":        "completed",
            "event_type":    "CI_FAILURE",
            "service":       "platform-service",
            "failure_stage": "integration-tests",
            "severity":      "P2",
            "summary":       "33 integration tests failed due to DB migration lock from a previous deployment.",
        },
        "diagnose": {
            "status":       "completed",
            "error_type":   "MigrationLockTimeout",
            "root_cause":   "A stale migration lock from deploy-2024-0130-011 is blocking the integration test DB setup. This is an infrastructure state issue, not a code defect.",
            "confidence":   "MEDIUM",
            "fix_possible": False,
            "post_mortem": {
                "what_happened":   "Migration lock was not released after the previous deployment.",
                "why_it_happened": "No lock TTL is configured in the migration toolchain.",
                "how_to_prevent":  "Add a 30-minute lock TTL and a pre-flight lock check to the deploy pipeline.",
            },
        },
        "gate": {
            "status":          "completed",
            "decision":        "REJECT",
            "rationale":       "Integration tests cannot run while the DB migration lock is held. Gate evaluation deferred.",
            "blocking_issues": ["DB migration lock held by deploy-2024-0130-011"],
            "risk_score":      "HIGH",
            "escalate":        True,
        },
        "conflict": {
            "detected":   False,
            "type":       "NO_CONFLICT",
            "resolution": "PROCEED",
            "summary":    "DIAGNOSE: MEDIUM confidence. GATE: REJECT. Agents agree — both recommend escalation, no auto-fix attempted.",
        },
        "fix_or_escalate": {
            "status":               "completed",
            "path":                 "ESCALATE",
            "reason":               "MEDIUM confidence + infrastructure state issue — human intervention required before any database operation.",
            "auto_fix_attempted":   False,
            "github_issue_title":   "[Agent] DB Migration Lock Blocking Integration Tests — Manual Intervention Required",
            "github_issue_body":    "## Agent Diagnosis\n\n**Confidence:** MEDIUM\n**Action:** ESCALATE\n\n### Root Cause\nStale migration lock from deploy-2024-0130-011 is blocking 33 integration tests.\n\n### Proposed Fix\n```sql\nDELETE FROM migrations_lock WHERE locked_at < NOW() - INTERVAL '1 hour';\n```\n\n### Next Steps\n1. DBA verifies the lock state\n2. Execute DELETE after approval\n3. Re-trigger the pipeline\n\n---\n_Written by Ajay · ajay@platformetrics.com · ajay@platformengineering.org_",
            "recommended_action":   "ESCALATE",
            "escalate":             True,
        },
        "report": {
            "status":              "completed",
            "post_mortem_summary": "A stale migration lock from the previous deployment blocked 33 integration tests. The agent correctly assessed MEDIUM confidence (infrastructure state, not a code defect) and escalated to a human. Prevention: add a 30-minute migration lock TTL and a pre-flight lock check to the deployment pipeline.",
            "recommendations": [
                "Configure a 30-minute TTL on all migration locks.",
                "Add a pre-flight migration lock check as a required step before integration tests run.",
                "Alert on migration lock age > 15 minutes.",
            ],
        },
    },
    "final_output": {
        "recommended_action":  "ESCALATE",
        "escalate":            True,
        "confidence":          "MEDIUM",
        "conflict": {
            "detected":   False,
            "type":       "NO_CONFLICT",
            "resolution": "PROCEED",
            "summary":    "DIAGNOSE: MEDIUM confidence. GATE: REJECT. Agents agree.",
        },
        "github_issue_title":  "[Agent] DB Migration Lock Blocking Integration Tests — Manual Intervention Required",
        "github_issue_body":   "## Agent Diagnosis\n\n**Confidence:** MEDIUM\n**Action:** ESCALATE\n\n### Root Cause\nStale migration lock from deploy-2024-0130-011 blocking 33 integration tests.\n\n---\n_Written by Ajay · ajay@platformetrics.com · ajay@platformengineering.org_",
        "post_mortem_summary": "Stale migration lock blocked integration tests. Agent escalated correctly at MEDIUM confidence.",
    },
}

# ── System prompts — one per pipeline step ─────────────────────────────────────

INGEST_PROMPT = """\
You are a CI/CD failure classifier. Analyse the failure event and return ONLY valid JSON:
- event_type (CI_FAILURE|DEPLOY_FAILURE|OOMKILL|MIGRATION_FAILURE|UNKNOWN)
- service (string): affected service name
- failure_stage (string): which pipeline stage failed
- severity (P1|P2|P3): incident severity
- summary (string): one sentence describing the failure
"""

DIAGNOSE_PROMPT = """\
You are a root cause analysis agent. Diagnose the CI/CD failure and return ONLY valid JSON:
- error_type (string): exception class or infrastructure error type
- root_cause (string): one paragraph plain-English root cause explanation
- confidence (HIGH|MEDIUM|LOW): HIGH for deterministic code errors, MEDIUM for state inference
- fix_possible (boolean): true only if a safe, deterministic code fix can be generated
- fix_script (string): Python fix script — include only when fix_possible=true, else empty string
- post_mortem (object): { what_happened, why_it_happened, how_to_prevent } — one sentence each
"""

GATE_PROMPT = """\
You are a quality gate evaluation agent. You run in parallel with the DIAGNOSE agent —
you do NOT have access to the diagnosis. Given only the CI/CD failure event and its
initial classification from the INGEST step, evaluate the quality gates independently.
Return ONLY valid JSON:
- decision (APPROVE|APPROVE_WITH_CONDITIONS|REJECT)
- rationale (string): one paragraph explanation of the gate decision
- blocking_issues (list of strings): what is preventing APPROVE — empty list if APPROVE
- conditions (list of strings): conditions required for APPROVE_WITH_CONDITIONS — empty otherwise
- risk_score (LOW|MEDIUM|HIGH)
- escalate (boolean): true if a human must review before proceeding
"""

FIX_OR_ESCALATE_PROMPT = """\
You are a remediation decision agent. Given root cause diagnosis and gate evaluation,
decide whether to auto-fix or escalate. Return ONLY valid JSON:
- path (AUTO_FIX|ESCALATE)
- reason (string): one sentence justifying the choice
- auto_fix_script (string): Python fix script — only when path=AUTO_FIX and fix is safe, else empty string
- github_issue_title (string): issue title — only when path=ESCALATE, else empty string
- github_issue_body (string): 2-3 sentence plain-text summary (NO markdown, NO tables, NO code blocks, NO newlines) — only when path=ESCALATE, else empty string
- recommended_action (ROLLBACK|FIX_FORWARD|ESCALATE)
- escalate (boolean): true when path=ESCALATE

Rules:
- AUTO_FIX only if confidence=HIGH AND fix_possible=true AND no DB migration is involved.
- ESCALATE for MEDIUM/LOW confidence, infrastructure issues, or when rollback_available=false.
- github_issue_body MUST be a single plain-text string with no embedded newlines.
"""

# ── ⭐ EXTRA CREDIT Level 4: conflict_report added to REPORT_PROMPT ─────────────
# Makes conflict detection an explicit, auditable part of the post-mortem output.
REPORT_PROMPT = """\
You are a post-mortem report writer. Summarise the full pipeline execution. Return ONLY valid JSON:
- post_mortem_summary (string): 2-3 sentences — what happened, what the agent did, how to prevent recurrence
- recommendations (list of strings): 2-4 concrete prevention recommendations
- conflict_report (object): {
    detected (bool): whether a conflict was detected between specialists,
    type (string or null): HARD_CONFLICT | SOFT_CONFLICT | NO_CONFLICT,
    resolution (string): the resolution taken,
    agents_involved (list of strings): which specialists were in conflict,
    safety_first_applied (bool): true if the Safety First rule blocked an auto-fix,
    outcome (string): one sentence — what Safety First prevented, or why no conflict occurred
  }
"""

# ── ⭐ EXTRA CREDIT Level 3: HISTORY_PROMPT — new specialist prompt ─────────────
# Powers the deployment history analyst agent that enriches DIAGNOSE with
# recent deploy patterns before root cause analysis runs.
HISTORY_PROMPT = """\
You are a deployment history analyst. Given recent deployment records and a CI failure event,
identify patterns relevant to the current failure. Return ONLY valid JSON:
- recent_deploys (list of objects): each with sha (string), service (string), outcome (string), deployed_at (string)
- relevant_pattern (string): deployment pattern relevant to this failure, or "no_pattern"
- similar_past_failures (list of strings): SHAs of past deploys with similar failure patterns
- history_summary (string): one sentence summarising deployment health over the recent period
"""

AGENT_CONFIG = {
    "model":      "claude-opus-4-5-20251101",
    "max_tokens": 4096,
}

# ── ⭐ EXTRA CREDIT Level 2: bounded timeout for parallel specialists ────────────
# Prevents the pipeline hanging indefinitely if an API call stalls.
# Fallback functions (_fallback_history, _fallback_gate) are used on expiry.
SPECIALIST_TIMEOUT = 30  # seconds — parallel futures time out after this


# ── Helpers ────────────────────────────────────────────────────────────────────

def load_event(simulate: bool, scenario: str = "default") -> dict:
    """Load the CI failure event.

    Scenarios (used with --simulate):
      default       — migration lock, MEDIUM confidence, no auto-fix → ESCALATE (no conflict)
      hard_conflict — clear code bug, HIGH confidence + fix_possible=True, but GATE REJECTs
                      → triggers SAFETY_FIRST_ESCALATE (Level 1 extra credit)
    """
    if not simulate:
        return json.loads((Path(__file__).parent / "sample_data.json").read_text())

    # ── ⭐ EXTRA CREDIT Level 1: hard_conflict scenario ──────────────────────────
    # Deterministic code bug (HIGH confidence, fix_possible=True) paired with a
    # GATE REJECT → designed to trigger SAFETY_FIRST_ESCALATE through detect_conflict().
    if scenario == "hard_conflict":
        return {
            "trigger":       "github_actions_failure",
            "pipeline_id":   f"sim-hard-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}",
            "repo":          "org/checkout-service",
            "branch":        "main",
            "commit_sha":    "def5678",
            "failure_stage": "unit-tests",
            "test_results":  {"total": 200, "passed": 185, "failed": 15},
            "logs": [
                "ERROR [test_checkout] AttributeError: 'NoneType' object has no attribute 'user_id'",
                "ERROR [test_checkout]   File 'checkout/service.py', line 47, in process_order",
                "ERROR [test_checkout]     user = db.get_user(order.customer_id)",
                "ERROR [test_checkout]   user.user_id is None when customer has no account",
                "ERROR [test_checkout] Fix: add null check — if user is None: raise UserNotFoundError",
                "ERROR [test_checkout] 15 tests failed: all in TestOrderProcessing",
            ],
            "rollback_available": True,
        }

    return {
        "trigger":            "github_actions_failure",
        "pipeline_id":        f"sim-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}",
        "repo":               "org/platform-service",
        "branch":             "main",
        "commit_sha":         "abc1234",
        "failure_stage":      "integration-tests",
        "test_results":       {"total": 980, "passed": 947, "failed": 33},
        "logs": [
            "ERROR [integration] DB migration timeout after 30s",
            "ERROR [integration] 33 tests failed: all depend on users table",
            "WARN  [integration] Migration lock held by deploy-2024-0130-011",
        ],
        "rollback_available": True,
    }


def run_step(step_name: str, system_prompt: str, context: dict) -> dict:
    """Call Claude for one pipeline step. Returns the parsed JSON response."""
    print(f"\n── Step: {step_name} ──────────────────────────────────────────")
    result = ask(
        system=system_prompt,
        user=f"Context:\n{json.dumps(context, indent=2)}",
        model=AGENT_CONFIG["model"],
        max_tokens=AGENT_CONFIG["max_tokens"],
    )
    print(json.dumps(result, indent=2))
    return result


# ── ⭐ EXTRA CREDIT Level 2: fallback helpers for timed-out specialists ──────────
# Called by run_pipeline() when future.result(timeout=...) raises TimeoutError.
# HISTORY falls back to empty (safe to continue without history context).
# GATE falls back to REJECT — the safe default: never approve under uncertainty.
def _fallback_history() -> dict:
    return {
        "recent_deploys":       [],
        "relevant_pattern":     "no_pattern",
        "similar_past_failures": [],
        "history_summary":      "Deployment history unavailable — specialist timed out.",
    }


def _fallback_gate() -> dict:
    return {
        "decision":        "REJECT",
        "rationale":       "Gate evaluation timed out — defaulting to REJECT for safety.",
        "blocking_issues": ["Gate specialist timed out"],
        "conditions":      [],
        "risk_score":      "HIGH",
        "escalate":        True,
    }


def save_fix_script(script_content: str, pipeline_id: str) -> Path:
    """Save an auto-fix script to module8/fixes/ and return the path."""
    fixes_dir = Path(__file__).parent / "fixes"
    fixes_dir.mkdir(exist_ok=True)
    fix_path = fixes_dir / f"fix_{pipeline_id}.py"
    fix_path.write_text(script_content)
    print(f"[platform_agent] Auto-fix script saved → {fix_path}")
    return fix_path


# ── Pipeline step functions ────────────────────────────────────────────────────
# Step 1 is fully implemented. Use it as the pattern for Steps 2–5.

def run_step_ingest(event: dict) -> dict:
    """Step 1 — INGEST: classify the failure event.

    ALREADY IMPLEMENTED — study this before writing Steps 2–5.

    Pattern:
      1. Build a context dict with the data Claude needs.
      2. Call run_step(step_name, system_prompt, context).
      3. Return the result.
    """
    return run_step("INGEST", INGEST_PROMPT, event)


# ── ⭐ EXTRA CREDIT Level 3: HISTORY specialist — new pipeline step ─────────────
# Runs in parallel with GATE. Simulates a /recent-deploys API call, constructs
# the last 3 deployment records, and asks Claude to identify failure patterns.
# Result is passed to run_step_diagnose() to enrich root cause analysis.
def run_step_history(event: dict, ingest: dict) -> dict:
    """HISTORY specialist — enriches diagnosis with recent deployment context.

    Simulates fetching from a /recent-deploys endpoint. In production this
    would query a real deployment registry or CI history API.
    Runs in parallel with GATE (both read only from INGEST).
    """
    service = ingest.get("service", event.get("repo", "unknown"))
    recent_deploys = [
        {
            "sha":          event.get("commit_sha", "current"),
            "service":      service,
            "outcome":      "failure",
            "deployed_at":  datetime.now(timezone.utc).isoformat(),
            "failure_stage": event.get("failure_stage", "unknown"),
        },
        {
            "sha":         "prev001",
            "service":     service,
            "outcome":     "success",
            "deployed_at": "2026-06-08T14:00:00Z",
        },
        {
            "sha":          "prev000",
            "service":      service,
            "outcome":      "failure",
            "deployed_at":  "2026-06-07T10:30:00Z",
            "failure_stage": "integration-tests",
        },
    ]
    context = {
        "event":          event,
        "classification": ingest,
        "recent_deploys": recent_deploys,
    }
    return run_step("HISTORY", HISTORY_PROMPT, context)


# ── ✅ STEP-BY-STEP Task 2/4: run_step_diagnose() ──────────────────────────────
# Build context dict from event + ingest classification, call run_step(), return result.
# ── ⭐ EXTRA CREDIT Level 3: signature updated to accept history for enrichment ──
# The optional `history` param was added in the extra credit commit. When present,
# deployment history is included in context so DIAGNOSE has pattern awareness.
def run_step_diagnose(event: dict, ingest: dict, history: dict | None = None) -> dict:
    """Step 3 — DIAGNOSE: root cause analysis, optionally enriched with deployment history."""
    context = {"event": event, "classification": ingest}
    if history:
        context["deployment_history"] = history
    return run_step("DIAGNOSE", DIAGNOSE_PROMPT, context)


# ── ✅ STEP-BY-STEP Task 3/4: run_step_gate() ──────────────────────────────────
# Same 3-line pattern as run_step_diagnose(). Key constraint: uses ingest, NOT
# diagnose — gate must be independent of root cause to make conflict detection valid.
def run_step_gate(event: dict, ingest: dict) -> dict:
    """Step 3 — GATE: evaluate quality gates independently of DIAGNOSE.

    Reads from INGEST, not DIAGNOSE — runs in parallel with run_step_diagnose().
    """
    context = {"event": event, "classification": ingest}
    return run_step("GATE", GATE_PROMPT, context)


def detect_conflict(diagnose: dict, gate: dict) -> dict:
    """Detect conflicts between the DIAGNOSE and GATE specialist agents.

    Applies the Module 7 Safety First rule to the capstone pipeline:
    - HARD_CONFLICT: DIAGNOSE says HIGH confidence + fix possible, but GATE says REJECT.
      → GATE wins. Auto-fix is blocked. Escalate to human.
    - SOFT_CONFLICT: GATE approves but DIAGNOSE confidence is MEDIUM or LOW.
      → Agents disagree on certainty. Inform on-call, proceed with caution.
    - NO_CONFLICT: agents agree on the path forward.

    This function is provided — do not modify it.
    """
    gate_decision = gate.get("decision", "REJECT")
    confidence    = diagnose.get("confidence", "LOW")
    fix_possible  = diagnose.get("fix_possible", False)

    if gate_decision == "REJECT" and fix_possible and confidence == "HIGH":
        return {
            "detected":   True,
            "type":       "HARD_CONFLICT",
            "resolution": "SAFETY_FIRST_ESCALATE",
            "summary": (
                f"DIAGNOSE: HIGH confidence, fix_possible=true. "
                f"GATE: REJECT — {gate.get('blocking_issues', [])}. "
                "Hard conflict — Safety First: block auto-fix, escalate to human."
            ),
        }
    if gate_decision in ("APPROVE", "APPROVE_WITH_CONDITIONS") and confidence in ("MEDIUM", "LOW"):
        return {
            "detected":   True,
            "type":       "SOFT_CONFLICT",
            "resolution": "SOFT_ESCALATE",
            "summary": (
                f"DIAGNOSE: {confidence} confidence. "
                f"GATE: {gate_decision} — but uncertain root cause warrants human review."
            ),
        }
    return {
        "detected":   False,
        "type":       "NO_CONFLICT",
        "resolution": "PROCEED",
        "summary":    f"DIAGNOSE: {confidence} confidence. GATE: {gate_decision}. Agents agree.",
    }


# ── ✅ STEP-BY-STEP Task 4/4: run_step_fix_or_escalate() ───────────────────────
# Build context with event, diagnosis, gate, and conflict verdict.
# Call run_step(), then handle the AUTO_FIX path: if a fix script is returned,
# save it to disk with save_fix_script() and store the path in the result.
def run_step_fix_or_escalate(
    event: dict, diagnose: dict, gate: dict, conflict: dict, pipeline_id: str
) -> dict:
    """Step 4 — FIX/ESCALATE: decide the remediation path."""
    context = {
        "event":     event,
        "diagnosis": diagnose,
        "gate":      gate,
        "conflict":  conflict,
    }
    result = run_step("FIX_OR_ESCALATE", FIX_OR_ESCALATE_PROMPT, context)
    if result.get("path") == "AUTO_FIX" and result.get("auto_fix_script"):
        fix_path = save_fix_script(result["auto_fix_script"], pipeline_id)
        result["fix_script_path"] = str(fix_path)
    return result


# ── ✅ STEP-BY-STEP Task 5/4: generate_report() ────────────────────────────────
# Build context from pipeline_id + full steps dict, call run_step(), return result.
# ── ⭐ EXTRA CREDIT Level 4: conflict key surfaced explicitly in context ─────────
# Passing `conflict` as a top-level key (not just buried in steps) makes it
# easier for REPORT_PROMPT to reason about what conflict resolution occurred.
def generate_report(pipeline_id: str, steps: dict) -> dict:
    """Step 5 — REPORT: write the post-mortem, including a structured conflict section."""
    context = {
        "pipeline_id":    pipeline_id,
        "steps":          steps,
        "conflict":       steps.get("conflict", {}),  # ← EXTRA CREDIT Level 4: explicit conflict context
    }
    return run_step("REPORT", REPORT_PROMPT, context)


# ── Orchestrator ───────────────────────────────────────────────────────────────

def run_pipeline(event: dict) -> dict:
    """Multi-agent orchestrator.

    Step structure (extra credit):
      1. INGEST        — sequential classifier
      2. HISTORY+GATE  — parallel specialists (both read from INGEST only)
      3. DIAGNOSE      — enriched with HISTORY result
         conflict check — Safety First
      4. FIX/ESCALATE  — receives DIAGNOSE + GATE + conflict verdict
      5. REPORT        — post-mortem with structured conflict section
    """
    pipeline_id = event.get("pipeline_id", "unknown")
    steps = {}

    print("\n" + "═" * 60)
    print(f"PLATFORM AGENT — pipeline_id: {pipeline_id}")
    print("═" * 60)

    # Step 1 — INGEST
    print("\n[Step 1/5] INGEST")
    steps["ingest"] = {**run_step_ingest(event), "status": "completed"}

    # ⭐ EXTRA CREDIT Level 3: HISTORY specialist added to the parallel block
    # ⭐ EXTRA CREDIT Level 2: futures wrapped with timeout=SPECIALIST_TIMEOUT + fallbacks
    # Step 2 — HISTORY + GATE in parallel (both read from INGEST only, never from each other)
    print("\n[Step 2/5] HISTORY + GATE running in parallel...")
    with ThreadPoolExecutor(max_workers=2) as executor:
        future_history = executor.submit(run_step_history, event, steps["ingest"])  # ← Level 3: new specialist
        future_gate    = executor.submit(run_step_gate,    event, steps["ingest"])
        try:
            history_result = future_history.result(timeout=SPECIALIST_TIMEOUT)  # ← Level 2: bounded timeout
        except concurrent.futures.TimeoutError:
            print(f"⚠️  HISTORY timed out after {SPECIALIST_TIMEOUT}s — using fallback")
            history_result = _fallback_history()  # ← Level 2: safe fallback
        try:
            gate_result = future_gate.result(timeout=SPECIALIST_TIMEOUT)  # ← Level 2: bounded timeout
        except concurrent.futures.TimeoutError:
            print(f"⚠️  GATE timed out after {SPECIALIST_TIMEOUT}s — defaulting to REJECT")
            gate_result = _fallback_gate()  # ← Level 2: safe fallback (always REJECT)

    steps["history"] = {**history_result, "status": "completed"}
    steps["gate"]    = {**gate_result,    "status": "completed"}

    # ⭐ EXTRA CREDIT Level 3: DIAGNOSE now receives history as a third argument
    # Step 3 — DIAGNOSE enriched with deployment history
    print("\n[Step 3/5] DIAGNOSE (enriched with deployment history)")
    diagnose_result   = run_step_diagnose(event, steps["ingest"], steps["history"])  # ← Level 3: history enrichment
    steps["diagnose"] = {**diagnose_result, "status": "completed"}

    # Conflict check — Safety First rule
    conflict = detect_conflict(steps["diagnose"], steps["gate"])
    steps["conflict"] = conflict
    if conflict["detected"]:
        print(f"\n⚠️  CONFLICT: {conflict['type']} → {conflict['resolution']}")
        print(f"   {conflict['summary']}")

    # Step 4 — FIX OR ESCALATE
    print("\n[Step 4/5] FIX OR ESCALATE")
    fix = run_step_fix_or_escalate(
        event, steps["diagnose"], steps["gate"], conflict, pipeline_id
    )
    steps["fix_or_escalate"] = {**fix, "status": "completed"}

    # Step 5 — REPORT (Level 4: conflict_report in output)
    print("\n[Step 5/5] REPORT")
    steps["report"] = {**generate_report(pipeline_id, steps), "status": "completed"}

    return {
        "pipeline_id":   pipeline_id,
        "run_timestamp": datetime.now(timezone.utc).isoformat(),
        "steps":         steps,
        "final_output": {
            "recommended_action":  fix.get("recommended_action", "ESCALATE"),
            "escalate":            fix.get("escalate", True),
            "confidence":          steps["diagnose"].get("confidence", "LOW"),
            "conflict":            conflict,
            "github_issue_title":  fix.get("github_issue_title", ""),
            "github_issue_body":   fix.get("github_issue_body", ""),
            "post_mortem_summary": steps["report"].get("post_mortem_summary", ""),
            "conflict_report":     steps["report"].get("conflict_report", {}),  # ← EXTRA CREDIT Level 4: structured conflict audit trail
        },
    }


# ── Entry point ────────────────────────────────────────────────────────────────

def _write_step_summary(result: dict) -> None:
    """Write a rich GitHub Step Summary with collapsible <details> blocks.

    Flat table for final_output scalar fields (no truncation); <details> sections
    for nested JSON (conflict objects, per-step outputs, raw JSON).
    No-ops when GITHUB_STEP_SUMMARY is not set (i.e. outside CI).
    """
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if not summary_path:
        return

    pipeline_id = result.get("pipeline_id", "unknown")
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    final = result.get("final_output", {})
    steps = result.get("steps", {})

    def _details(label: str, data) -> str:
        body = json.dumps(data, indent=2) if not isinstance(data, str) else data
        return (
            f"<details><summary>{label}</summary>\n\n"
            f"```json\n{body}\n```\n\n</details>"
        )

    lines = [
        "## Module 8 — Capstone Platform Agent",
        f"_Pipeline: `{pipeline_id}` | {ts}_",
        "",
        "### Summary",
        "",
        "| Field | Value |",
        "|-------|-------|",
        f"| `recommended_action` | {final.get('recommended_action', '')} |",
        f"| `escalate` | {final.get('escalate', '')} |",
        f"| `confidence` | {final.get('confidence', '')} |",
        f"| `post_mortem_summary` | {final.get('post_mortem_summary', '')} |",
        f"| `github_issue_title` | {final.get('github_issue_title', '')} |",
        "",
        "### Conflict Details",
        "",
    ]

    for k in ("conflict", "conflict_report"):
        v = final.get(k)
        if v:
            lines.append(_details(f"`{k}`", v))
            lines.append("")

    issue_body = final.get("github_issue_body", "")
    if issue_body:
        lines.append(_details("`github_issue_body`", issue_body))
        lines.append("")

    lines += ["### Pipeline Steps", ""]

    step_order = [
        ("ingest",          "Step 1 — INGEST"),
        ("history",         "Step 2a — HISTORY"),
        ("gate",            "Step 2b — GATE"),
        ("diagnose",        "Step 3 — DIAGNOSE"),
        ("conflict",        "Conflict Check"),
        ("fix_or_escalate", "Step 4 — FIX / ESCALATE"),
        ("report",          "Step 5 — REPORT"),
    ]
    for key, label in step_order:
        if key in steps:
            lines.append(_details(label, steps[key]))
            lines.append("")

    lines += ["### Full Output", "", _details("📄 Raw JSON", result)]

    with open(summary_path, "a") as f:
        f.write("\n".join(lines) + "\n\n")


def main():
    parser = argparse.ArgumentParser(description="Module 8 Capstone Platform Agent")
    parser.add_argument("--simulate", action="store_true",
                        help="Inject a synthetic CI failure event instead of reading sample_data.json")
    parser.add_argument("--mock", action="store_true",
                        help="Return pre-defined responses — no API key needed")
    parser.add_argument("--scenario", choices=["default", "hard_conflict"], default="default",  # ← EXTRA CREDIT Level 1
                        help="Simulation scenario: default (migration lock) or hard_conflict (Level 1 safety test)")
    args = parser.parse_args()

    event = load_event(simulate=args.simulate, scenario=args.scenario)

    if MOCK_MODE:
        print("[MOCK MODE] Returning pre-defined 5-step pipeline report.")
        print("[MOCK MODE] Remove --mock and set ANTHROPIC_API_KEY to run the real pipeline.\n")
        result = MOCK_REPORT
    else:
        result = run_pipeline(event)

    print("\n" + "═" * 60)
    print("PLATFORM AGENT — FINAL REPORT")
    print("═" * 60)
    print(json.dumps(result, indent=2))

    save_json(result, module=8, label="platform_agent")
    _write_step_summary(result)

    final = result.get("final_output", {})
    if final.get("escalate"):
        print("\n🔴 ESCALATION REQUIRED")
        print(f"   Action : {final.get('recommended_action')}")
        print(f"   Issue  : {final.get('github_issue_title')}")
        print(to_github_issue(result, module=8))
    else:
        print("\n✅ Pipeline resolved — no escalation required.")

    return result


if __name__ == "__main__":
    main()
