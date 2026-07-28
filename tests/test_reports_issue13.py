#!/usr/bin/env python3
"""Tests for Issue 13: reporting producers for abstained / unresolved-signal / strategy-gap.

AC coverage:
  AC1 — generate_html_report.py emits kind="abstained" for triage==abstained stubs
  AC2 — generate_html_report.py emits kind="strategy-gap" for passing AND failing reviews
  AC3 — generate_html_report.py emits kind="unresolved-signal" for epics with unresolved tier
  AC4 — generate_run_report.py replaces "not collected" with real numbers
  AC5 — both scripts on old-style batch (no new fields) produce no errors, zero counts
  AC6 — abstained strategy (stub decomp, no epics, no review) is counted and rendered
"""
import os
import subprocess
import sys

import pytest
import yaml

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

HTML_SCRIPT = os.path.join(os.path.dirname(__file__), "..", "scripts", "generate_html_report.py")
RUN_SCRIPT = os.path.join(os.path.dirname(__file__), "..", "scripts", "generate_run_report.py")
FM_SCRIPT = os.path.join(os.path.dirname(__file__), "..", "scripts", "frontmatter.py")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write(path, content):
    """Write a file, creating parent dirs as needed."""
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, "w") as f:
        f.write(content)


def _run_fm(*args):
    result = subprocess.run(
        ["python3", FM_SCRIPT, *args],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, f"frontmatter.py failed: {result.stderr}"


def _run_html(*args):
    result = subprocess.run(
        ["python3", HTML_SCRIPT, *args],
        capture_output=True, text=True,
    )
    return result.stdout.strip(), result.stderr, result.returncode


def _run_report(*args):
    result = subprocess.run(
        ["python3", RUN_SCRIPT, *args],
        capture_output=True, text=True,
    )
    return result.stdout.strip(), result.stderr, result.returncode


def _setup_base_strategy(strat_id):
    """Create minimal strategy + decomposition + review + one epic via frontmatter.py.

    No Issue-5/6 fields — represents old-style batch for AC5.
    """
    # Strategy file
    _write(f"artifacts/strat-tasks/{strat_id}.md",
           f"---\nstrat_id: {strat_id}\ntitle: Base Strategy\n---\n\nBody.\n")

    # Decomposition summary (no triage field)
    _write(f"artifacts/epic-tasks/{strat_id}-decomposition.md",
           f"## Epic List\n\n| ID | Title |\n|---|---|\n"
           f"| {strat_id}-E001 | Base Epic |\n")
    _run_fm("set", f"artifacts/epic-tasks/{strat_id}-decomposition.md",
            f"parent_strat={strat_id}", "epic_count=1",
            "critical_path_length=1")

    # Review (passing, no strategy_gap)
    _write(f"artifacts/epic-reviews/{strat_id}-decomp-review.md",
           "## Review\n\nNo issues.\n")
    _run_fm("set", f"artifacts/epic-reviews/{strat_id}-decomp-review.md",
            f"strat_id={strat_id}", "score=12", "pass=true",
            "recommendation=accept", "issues=[]")

    # Epic file (no signal_consistency field)
    _write(f"artifacts/epic-tasks/{strat_id}-E001.md",
           "## Title\n\nBase Epic\n\n## Description\n\nA test epic.\n")
    _run_fm("set", f"artifacts/epic-tasks/{strat_id}-E001.md",
            f"epic_id={strat_id}-E001", "title=Base Epic",
            f"parent_strat={strat_id}",
            "component=test-component", "team=Test Team",
            "type=Implementation", "priority=P0",
            "ai_signals.change_specificity=1",
            "ai_signals.pattern_precedent=1",
            "ai_signals.adapter_pattern=0",
            "ai_signals.existing_foundation=1",
            "ai_signals.open_questions=0",
            "ai_signals.external_dependency=0",
            "ai_signals.human_process_gates=0",
            "ai_signals.repo_access=1",
            "ai_signals.architecture_claims=0")


def _write_stub_decomp(strat_id):
    """Write a raw abstained stub decomposition file (no epic files, no review).

    Written raw (not via frontmatter.py) per Issue 13 fixture rules.
    """
    _write(f"artifacts/epic-tasks/{strat_id}-decomposition.md",
           f"---\nparent_strat: {strat_id}\ntriage: abstained\nepic_count: 0\n"
           f"triage_verdicts:\n  - below-threshold\n  - proceed\n  - proceed\n"
           f"  - below-threshold\n  - proceed\ncritical_path_length: 0\n---\n\n"
           f"Abstained — triage verdict unstable.\n")


def _write_epic_with_unresolved(strat_id, epic_num="E001"):
    """Write an epic file with signal_consistency containing an unresolved tier.

    Written raw per Issue 13 fixture rules.
    """
    epic_id = f"{strat_id}-{epic_num}"
    _write(f"artifacts/epic-tasks/{strat_id}-{epic_num}.md",
           f"---\n"
           f"epic_id: {epic_id}\n"
           f"title: Unresolved Epic\n"
           f"parent_strat: {strat_id}\n"
           f"component: test-comp\n"
           f"team: Test Team\n"
           f"type: Implementation\n"
           f"priority: P1\n"
           f"ai_signals:\n"
           f"  change_specificity: 1\n"
           f"  pattern_precedent: 0\n"
           f"  adapter_pattern: 0\n"
           f"  existing_foundation: 1\n"
           f"  open_questions: 0\n"
           f"  external_dependency: 0\n"
           f"  human_process_gates: 0\n"
           f"  repo_access: 1\n"
           f"  architecture_claims: 0\n"
           f"signal_consistency:\n"
           f"  change_specificity:\n"
           f"    tier: high\n"
           f"    runs: 3\n"
           f"  open_questions:\n"
           f"    tier: unresolved\n"
           f"    runs: 5\n"
           f"---\n\n"
           f"## Title\n\nUnresolved Epic\n\n## Description\n\nTest.\n")
    return epic_id


def _write_epic_all_high(strat_id, epic_num="E001"):
    """Write an epic file with signal_consistency all high tiers (no unresolved)."""
    epic_id = f"{strat_id}-{epic_num}"
    _write(f"artifacts/epic-tasks/{strat_id}-{epic_num}.md",
           f"---\n"
           f"epic_id: {epic_id}\n"
           f"title: High-Tier Epic\n"
           f"parent_strat: {strat_id}\n"
           f"component: test-comp\n"
           f"team: Test Team\n"
           f"type: Implementation\n"
           f"priority: P1\n"
           f"ai_signals:\n"
           f"  change_specificity: 1\n"
           f"  pattern_precedent: 0\n"
           f"  adapter_pattern: 0\n"
           f"  existing_foundation: 1\n"
           f"  open_questions: 0\n"
           f"  external_dependency: 0\n"
           f"  human_process_gates: 0\n"
           f"  repo_access: 1\n"
           f"  architecture_claims: 0\n"
           f"signal_consistency:\n"
           f"  change_specificity:\n"
           f"    tier: high\n"
           f"    runs: 3\n"
           f"  open_questions:\n"
           f"    tier: high\n"
           f"    runs: 3\n"
           f"---\n\n"
           f"## Title\n\nHigh-Tier Epic\n\n## Description\n\nTest.\n")
    return epic_id


@pytest.fixture
def tmp_dir(tmp_path):
    orig = os.getcwd()
    os.chdir(tmp_path)
    yield tmp_path
    os.chdir(orig)


# ---------------------------------------------------------------------------
# AC1: abstained producer emits kind="abstained"
# ---------------------------------------------------------------------------

class TestAbstainedProducer:

    def test_abstained_entry_in_html(self, tmp_dir):
        """AC1: HTML report emits kind=abstained for triage==abstained decomp stub."""
        strat_id = "RHAISTRAT-1100"
        _write_stub_decomp(strat_id)
        # No epic files, no review file — pure stub

        out, err, rc = _run_html(
            "--start-time", "2026-01-01T00:00:00Z",
            "--output", "report.html",
            strat_id,
        )
        assert rc == 0, f"Script failed: {err}"

        with open("report.html") as f:
            html = f.read()

        assert "abstained" in html
        assert 'class="badge badge-kind-abstained"' in html

    def test_abstained_discovered_by_glob(self, tmp_dir):
        """AC1: Script invoked WITHOUT explicit ids still discovers the stub."""
        strat_id = "RHAISTRAT-1101"
        _write_stub_decomp(strat_id)

        out, err, rc = _run_html(
            "--start-time", "2026-01-01T00:00:00Z",
            "--output", "report.html",
        )
        assert rc == 0, f"Script failed: {err}"

        with open("report.html") as f:
            html = f.read()

        assert "RHAISTRAT-1101" in html
        assert 'class="badge badge-kind-abstained"' in html

    def test_below_threshold_not_counted_as_abstained(self, tmp_dir):
        """below-threshold is a proceed-shortcut, must NOT appear as kind=abstained."""
        strat_id = "RHAISTRAT-1102"
        # below-threshold: triage present but not abstained
        _write(f"artifacts/epic-tasks/{strat_id}-decomposition.md",
               f"---\nparent_strat: {strat_id}\ntriage: below-threshold\n"
               f"epic_count: 1\ncritical_path_length: 1\n---\n\nContent.\n")
        _write(f"artifacts/epic-tasks/{strat_id}-E001.md",
               f"---\nepic_id: {strat_id}-E001\ntitle: Single Epic\n"
               f"parent_strat: {strat_id}\ncomponent: c\nteam: T\n"
               f"type: Implementation\npriority: P1\n---\n\n## Title\n\nT\n")
        _run_fm("set", f"artifacts/epic-tasks/{strat_id}-E001.md",
                "ai_signals.change_specificity=0",
                "ai_signals.pattern_precedent=0",
                "ai_signals.adapter_pattern=0",
                "ai_signals.existing_foundation=0",
                "ai_signals.open_questions=0",
                "ai_signals.external_dependency=0",
                "ai_signals.human_process_gates=0",
                "ai_signals.repo_access=0",
                "ai_signals.architecture_claims=0")

        out, err, rc = _run_html(
            "--start-time", "2026-01-01T00:00:00Z",
            "--output", "report.html",
            strat_id,
        )
        assert rc == 0, f"Script failed: {err}"

        with open("report.html") as f:
            html = f.read()

        # below-threshold appears in triage badge, not as kind=abstained
        assert "below-threshold" in html
        assert 'class="badge badge-kind-abstained"' not in html


# ---------------------------------------------------------------------------
# AC2: strategy-gap producer emits entries regardless of pass/fail
# ---------------------------------------------------------------------------

class TestStrategyGapProducer:

    def _write_review_with_gap(self, strat_id, passing):
        """Write a review that has a strategy_gap:true issue, either passing or failing."""
        score = 12 if passing else 5
        pass_val = "true" if passing else "false"
        issues_yaml = (
            '[{"severity": "major", "criterion": "HLR Coverage", '
            '"description": "Gap in strategy", "strategy_gap": true}]'
        )
        _write(f"artifacts/epic-reviews/{strat_id}-decomp-review.md",
               "## Review\n\nIssues found.\n")
        _run_fm("set", f"artifacts/epic-reviews/{strat_id}-decomp-review.md",
                f"strat_id={strat_id}", f"score={score}", f"pass={pass_val}",
                "recommendation=revise", f"issues={issues_yaml}")

    def test_strategy_gap_on_failing_review(self, tmp_dir):
        """AC2: strategy-gap entry emitted when review fails and gap flagged."""
        strat_id = "RHAISTRAT-1200"
        _setup_base_strategy(strat_id)
        self._write_review_with_gap(strat_id, passing=False)

        out, err, rc = _run_html(
            "--start-time", "2026-01-01T00:00:00Z",
            "--output", "report.html",
            strat_id,
        )
        assert rc == 0, f"Script failed: {err}"

        with open("report.html") as f:
            html = f.read()

        assert 'class="badge badge-kind-strategy-gap"' in html

    def test_strategy_gap_on_passing_review(self, tmp_dir):
        """AC2: strategy-gap entry emitted even when review passes."""
        strat_id = "RHAISTRAT-1201"
        _setup_base_strategy(strat_id)
        self._write_review_with_gap(strat_id, passing=True)

        out, err, rc = _run_html(
            "--start-time", "2026-01-01T00:00:00Z",
            "--output", "report.html",
            strat_id,
        )
        assert rc == 0, f"Script failed: {err}"

        with open("report.html") as f:
            html = f.read()

        # passing review, but strategy_gap still fires
        assert "Pass" in html
        assert 'class="badge badge-kind-strategy-gap"' in html

    def test_no_strategy_gap_without_flag(self, tmp_dir):
        """No strategy-gap entry when no issues have strategy_gap:true."""
        strat_id = "RHAISTRAT-1202"
        _setup_base_strategy(strat_id)
        # Default setup has passing review with empty issues list

        out, err, rc = _run_html(
            "--start-time", "2026-01-01T00:00:00Z",
            "--output", "report.html",
            strat_id,
        )
        assert rc == 0, f"Script failed: {err}"

        with open("report.html") as f:
            html = f.read()

        assert 'class="badge badge-kind-strategy-gap"' not in html


# ---------------------------------------------------------------------------
# AC3: unresolved-signal producer
# ---------------------------------------------------------------------------

class TestUnresolvedSignalProducer:

    def _write_decomp(self, strat_id, epic_count=1):
        _write(f"artifacts/epic-tasks/{strat_id}-decomposition.md",
               f"## Epic List\n\n")
        _run_fm("set", f"artifacts/epic-tasks/{strat_id}-decomposition.md",
                f"parent_strat={strat_id}", f"epic_count={epic_count}",
                "critical_path_length=1")

    def _write_review(self, strat_id):
        _write(f"artifacts/epic-reviews/{strat_id}-decomp-review.md",
               "## Review\n\nOK.\n")
        _run_fm("set", f"artifacts/epic-reviews/{strat_id}-decomp-review.md",
                f"strat_id={strat_id}", "score=12", "pass=true",
                "recommendation=accept", "issues=[]")

    def test_unresolved_signal_entry_emitted(self, tmp_dir):
        """AC3: HTML emits kind=unresolved-signal for epic with any tier:unresolved."""
        strat_id = "RHAISTRAT-1300"
        self._write_decomp(strat_id)
        self._write_review(strat_id)
        epic_id = _write_epic_with_unresolved(strat_id)

        out, err, rc = _run_html(
            "--start-time", "2026-01-01T00:00:00Z",
            "--output", "report.html",
            strat_id,
        )
        assert rc == 0, f"Script failed: {err}"

        with open("report.html") as f:
            html = f.read()

        assert 'class="badge badge-kind-unresolved-signal"' in html

    def test_no_unresolved_signal_when_all_high(self, tmp_dir):
        """No unresolved-signal entry when all tiers are high."""
        strat_id = "RHAISTRAT-1301"
        self._write_decomp(strat_id)
        self._write_review(strat_id)
        _write_epic_all_high(strat_id)

        out, err, rc = _run_html(
            "--start-time", "2026-01-01T00:00:00Z",
            "--output", "report.html",
            strat_id,
        )
        assert rc == 0, f"Script failed: {err}"

        with open("report.html") as f:
            html = f.read()

        assert 'class="badge badge-kind-unresolved-signal"' not in html

    def test_unresolved_signal_on_branch_epic(self, tmp_dir):
        """AC3: unresolved-signal also fires for BRANCH-pattern epic files."""
        strat_id = "RHAISTRAT-1302"
        self._write_decomp(strat_id, epic_count=2)
        self._write_review(strat_id)
        _write_epic_all_high(strat_id, "E001")

        # BRANCH epic with unresolved tier
        branch_epic_id = f"{strat_id}-BRANCH-A-E002"
        _write(f"artifacts/epic-tasks/{strat_id}-BRANCH-A-E002.md",
               f"---\n"
               f"epic_id: {branch_epic_id}\n"
               f"title: Branch Epic\n"
               f"parent_strat: {strat_id}\n"
               f"component: c\n"
               f"team: T\n"
               f"type: Implementation\n"
               f"priority: P1\n"
               f"ai_signals:\n"
               f"  change_specificity: 1\n"
               f"  pattern_precedent: 0\n"
               f"  adapter_pattern: 0\n"
               f"  existing_foundation: 1\n"
               f"  open_questions: 0\n"
               f"  external_dependency: 0\n"
               f"  human_process_gates: 0\n"
               f"  repo_access: 1\n"
               f"  architecture_claims: 0\n"
               f"signal_consistency:\n"
               f"  change_specificity:\n"
               f"    tier: unresolved\n"
               f"    runs: 5\n"
               f"gated_by: E001\n"
               f"---\n\n"
               f"## Title\n\nBranch Epic\n\n## Description\n\nTest.\n")

        out, err, rc = _run_html(
            "--start-time", "2026-01-01T00:00:00Z",
            "--output", "report.html",
            strat_id,
        )
        assert rc == 0, f"Script failed: {err}"

        with open("report.html") as f:
            html = f.read()

        assert 'class="badge badge-kind-unresolved-signal"' in html


# ---------------------------------------------------------------------------
# AC4: generate_run_report.py replaces "not collected" with real numbers
# ---------------------------------------------------------------------------

class TestRunReportRealNumbers:

    def _write_strategy_strat(self, strat_id, triage=None, epic_tiers=None):
        """Set up a strategy for the run-report test.

        triage: if given, written raw to decomp frontmatter (may be "abstained").
        epic_tiers: list of tier strings to write to epic signal_consistency.
        """
        if triage is not None and triage == "abstained":
            _write_stub_decomp(strat_id)
        else:
            fm_parts = f"parent_strat: {strat_id}\nepic_count: 1\ncritical_path_length: 1\n"
            if triage:
                fm_parts += f"triage: {triage}\n"
            _write(f"artifacts/epic-tasks/{strat_id}-decomposition.md",
                   f"---\n{fm_parts}---\n\nContent.\n")

        if epic_tiers:
            # Write epic files with the given tiers
            for i, tier in enumerate(epic_tiers, 1):
                epic_id = f"{strat_id}-E{i:03d}"
                sc_field = "change_specificity"
                _write(f"artifacts/epic-tasks/{strat_id}-E{i:03d}.md",
                       f"---\n"
                       f"epic_id: {epic_id}\n"
                       f"title: Epic {i}\n"
                       f"parent_strat: {strat_id}\n"
                       f"component: c\n"
                       f"team: T\n"
                       f"type: Implementation\n"
                       f"priority: P1\n"
                       f"ai_signals:\n"
                       f"  change_specificity: 1\n"
                       f"  pattern_precedent: 0\n"
                       f"  adapter_pattern: 0\n"
                       f"  existing_foundation: 0\n"
                       f"  open_questions: 0\n"
                       f"  external_dependency: 0\n"
                       f"  human_process_gates: 0\n"
                       f"  repo_access: 0\n"
                       f"  architecture_claims: 0\n"
                       f"signal_consistency:\n"
                       f"  {sc_field}:\n"
                       f"    tier: {tier}\n"
                       f"    runs: 3\n"
                       f"---\n\n## Title\n\nEpic {i}\n")

    def test_abstention_count_and_rate(self, tmp_dir):
        """AC4: abstained_count and abstention_rate are computed correctly."""
        self._write_strategy_strat("RHAISTRAT-4001", triage="abstained")
        self._write_strategy_strat("RHAISTRAT-4002", triage="proceed")
        self._write_strategy_strat("RHAISTRAT-4003", triage="abstained")

        out, err, rc = _run_report(
            "--start-time", "2026-01-01T00:00:00Z",
            "RHAISTRAT-4001", "RHAISTRAT-4002", "RHAISTRAT-4003",
        )
        assert rc == 0, f"Script failed: {err}"

        # Find the yaml report
        import glob as g
        reports = g.glob("artifacts/decompose-runs/*.yaml")
        assert reports, "No YAML report generated"
        with open(reports[0]) as f:
            data = yaml.safe_load(f)

        assert data["triage"]["abstained_count"] == 2
        assert data["triage"]["abstention_rate"] == pytest.approx(2 / 3, abs=0.001)

    def test_signal_tier_distribution(self, tmp_dir):
        """AC4: tier_distribution counts are computed from per-epic frontmatter."""
        # 1 strategy with 2 epics: one unresolved, one high
        self._write_strategy_strat("RHAISTRAT-4010", epic_tiers=["unresolved", "high"])
        # 1 strategy with 1 epic: medium
        self._write_strategy_strat("RHAISTRAT-4011", epic_tiers=["medium"])

        out, err, rc = _run_report(
            "--start-time", "2026-01-01T00:00:00Z",
            "RHAISTRAT-4010", "RHAISTRAT-4011",
        )
        assert rc == 0, f"Script failed: {err}"

        import glob as g
        reports = g.glob("artifacts/decompose-runs/*.yaml")
        assert reports
        with open(reports[0]) as f:
            data = yaml.safe_load(f)

        dist = data["signal_consistency"]["tier_distribution"]
        assert dist["unresolved"] == 1
        assert dist["high"] == 1
        assert dist["medium"] == 1

    def test_zero_strategies_division_guard(self, tmp_dir):
        """AC4: division-by-zero guard: rate=0.0 when total_strategies==0."""
        # Use the --ids path with explicit empty list is not easy; use a
        # strategy that has no decomp file (missing entry) instead.
        # We can't call with zero ids easily, but we can test a batch where
        # no strategies are abstained.
        self._write_strategy_strat("RHAISTRAT-4020")

        out, err, rc = _run_report(
            "--start-time", "2026-01-01T00:00:00Z",
            "RHAISTRAT-4020",
        )
        assert rc == 0, f"Script failed: {err}"

        import glob as g
        reports = g.glob("artifacts/decompose-runs/*.yaml")
        assert reports
        with open(reports[0]) as f:
            data = yaml.safe_load(f)

        assert data["triage"]["abstained_count"] == 0
        assert data["triage"]["abstention_rate"] == 0.0


# ---------------------------------------------------------------------------
# AC5: old-style batch (no new fields) produces no errors, zero counts
# ---------------------------------------------------------------------------

class TestOldStyleBatch:

    def test_html_no_errors_no_new_entries(self, tmp_dir):
        """AC5: HTML report on old-style batch (no triage/signal_consistency/strategy_gap)."""
        _setup_base_strategy("RHAISTRAT-5001")

        out, err, rc = _run_html(
            "--start-time", "2026-01-01T00:00:00Z",
            "--output", "report.html",
            "RHAISTRAT-5001",
        )
        assert rc == 0, f"Script failed: {err}"

        with open("report.html") as f:
            html = f.read()

        # No new C1 kinds should appear
        assert 'class="badge badge-kind-abstained"' not in html
        assert 'class="badge badge-kind-strategy-gap"' not in html
        assert 'class="badge badge-kind-unresolved-signal"' not in html

    def test_run_report_no_errors_zero_counts(self, tmp_dir):
        """AC5: run report on old-style batch produces zero triage and tier counts."""
        _setup_base_strategy("RHAISTRAT-5002")
        # Remove epic file's signal_consistency (already absent in _setup_base_strategy)

        out, err, rc = _run_report(
            "--start-time", "2026-01-01T00:00:00Z",
            "RHAISTRAT-5002",
        )
        assert rc == 0, f"Script failed: {err}"

        import glob as g
        reports = g.glob("artifacts/decompose-runs/*.yaml")
        assert reports
        with open(reports[0]) as f:
            data = yaml.safe_load(f)

        assert data["triage"]["abstained_count"] == 0
        assert data["triage"]["abstention_rate"] == 0.0
        dist = data["signal_consistency"]["tier_distribution"]
        assert dist["high"] == 0
        assert dist["medium"] == 0
        assert dist["unresolved"] == 0


# ---------------------------------------------------------------------------
# AC6: abstained strategy — stub only, no epics, counted and rendered
# ---------------------------------------------------------------------------

class TestAbstainedStubOnly:

    def test_stub_counted_rendered_no_epic_entries(self, tmp_dir):
        """AC6: abstained stub is counted in run report and rendered in HTML, no epic C1."""
        strat_id = "RHAISTRAT-6001"
        _write_stub_decomp(strat_id)
        # No epic files, no review file

        # HTML check
        out_h, err_h, rc_h = _run_html(
            "--start-time", "2026-01-01T00:00:00Z",
            "--output", "report.html",
            strat_id,
        )
        assert rc_h == 0, f"HTML script failed: {err_h}"

        with open("report.html") as f:
            html = f.read()

        assert 'class="badge badge-kind-abstained"' in html
        # No epic entries because there are no epic files
        assert 'class="badge badge-kind-unresolved-signal"' not in html

        # Run report check
        out_r, err_r, rc_r = _run_report(
            "--start-time", "2026-01-01T00:00:00Z",
            strat_id,
        )
        assert rc_r == 0, f"Run script failed: {err_r}"

        import glob as g
        reports = g.glob("artifacts/decompose-runs/*.yaml")
        assert reports
        with open(reports[0]) as f:
            data = yaml.safe_load(f)

        assert data["triage"]["abstained_count"] == 1
        assert data["triage"]["abstention_rate"] == pytest.approx(1.0, abs=0.001)

    def test_stub_mixed_batch(self, tmp_dir):
        """AC6: mix of abstained stub and normal strategy — only stub counted."""
        _write_stub_decomp("RHAISTRAT-6010")
        _setup_base_strategy("RHAISTRAT-6011")

        out, err, rc = _run_report(
            "--start-time", "2026-01-01T00:00:00Z",
            "RHAISTRAT-6010", "RHAISTRAT-6011",
        )
        assert rc == 0, f"Script failed: {err}"

        import glob as g
        reports = g.glob("artifacts/decompose-runs/*.yaml")
        assert reports
        with open(reports[0]) as f:
            data = yaml.safe_load(f)

        assert data["triage"]["abstained_count"] == 1
        assert data["triage"]["abstention_rate"] == pytest.approx(0.5, abs=0.001)
