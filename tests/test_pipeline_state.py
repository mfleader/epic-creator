#!/usr/bin/env python3
"""Unit tests for pipeline_state.py phase-transition logic."""
import os
import sys
from pathlib import Path
from unittest.mock import call, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from pipeline_state import (
    PHASES,
    _reset_revised_flag,
    advance,
)


# ── Fixtures and helpers ───────────────────────────────────────────────────────


@pytest.fixture
def tmp_dir(tmp_path):
    """Run each test from a fresh temp directory; isolates all file I/O."""
    orig = os.getcwd()
    os.chdir(tmp_path)
    yield tmp_path
    os.chdir(orig)


def _write_ids(relpath, ids):
    Path(relpath).parent.mkdir(parents=True, exist_ok=True)
    Path(relpath).write_text("\n".join(ids) + "\n" if ids else "")


def _touch(relpath):
    Path(relpath).parent.mkdir(parents=True, exist_ok=True)
    Path(relpath).touch()


def _make_rfm(path_to_data):
    """Return a stub read_frontmatter that serves data from a dict by path."""
    def _rfm(path):
        return path_to_data.get(path, ({}, ""))
    return _rfm


# ── Phase list sanity ──────────────────────────────────────────────────────────


def test_phases_list_contains_full_main_sequence():
    expected = [
        "BATCH_START", "FETCH", "TRIAGE", "DECOMPOSE", "REVIEW_DECOMP",
        "REVISE_DECOMP", "RE_REVIEW_CHECK", "RE_REVIEW", "REVISE_CHECK",
        "RE_REVISE", "BATCH_DONE", "ERROR_COLLECT", "REPORT", "DONE",
    ]
    for phase in expected:
        assert phase in PHASES


# ── BATCH_START ────────────────────────────────────────────────────────────────


class TestBatchStart:
    def test_transitions_to_fetch(self, tmp_dir):
        state = {"phase": "BATCH_START", "batch": 0}
        nxt, summary = advance(state, dry_run=True)
        assert nxt == "FETCH"
        assert "BATCH_START" in summary and "FETCH" in summary

    def test_batch_counter_incremented_in_summary(self, tmp_dir):
        state = {"phase": "BATCH_START", "batch": 2}
        _, summary = advance(state, dry_run=True)
        assert "batch=3" in summary


# ── FETCH ──────────────────────────────────────────────────────────────────────


class TestFetch:
    def test_transitions_to_triage(self, tmp_dir):
        nxt, _ = advance({"phase": "FETCH"}, dry_run=True)
        assert nxt == "TRIAGE"


# ── TRIAGE ─────────────────────────────────────────────────────────────────────


class TestTriage:
    def test_transitions_to_decompose_dry_run(self, tmp_dir):
        nxt, _ = advance({"phase": "TRIAGE"}, dry_run=True)
        assert nxt == "DECOMPOSE"

    def test_transitions_to_decompose_with_all_proceed(self, tmp_dir):
        ids = ["RHAISTRAT-1", "RHAISTRAT-2"]
        _write_ids("tmp/pipeline-active-ids.txt", ids)
        stubs = {
            f"artifacts/epic-tasks/{sid}-decomposition.md": (
                {"triage": "proceed", "epic_count": 0}, ""
            )
            for sid in ids
        }
        for path, (data, _) in stubs.items():
            _touch(path)
        rfm = _make_rfm(stubs)
        state = {"phase": "TRIAGE"}
        nxt, _ = advance(state, dry_run=False, read_frontmatter=rfm)
        assert nxt == "DECOMPOSE"

    def test_removes_abstained_ids_from_active_list(self, tmp_dir):
        _write_ids("tmp/pipeline-active-ids.txt",
                   ["RHAISTRAT-1", "RHAISTRAT-2", "RHAISTRAT-3"])
        stubs = {
            "artifacts/epic-tasks/RHAISTRAT-1-decomposition.md":
                ({"triage": "abstained", "epic_count": 0}, ""),
            "artifacts/epic-tasks/RHAISTRAT-2-decomposition.md":
                ({"triage": "proceed", "epic_count": 0}, ""),
            "artifacts/epic-tasks/RHAISTRAT-3-decomposition.md":
                ({"triage": "abstained", "epic_count": 0}, ""),
        }
        for path in stubs:
            _touch(path)
        rfm = _make_rfm(stubs)
        state = {"phase": "TRIAGE"}
        advance(state, dry_run=False, read_frontmatter=rfm)

        from pathlib import Path
        remaining = Path("tmp/pipeline-active-ids.txt").read_text().split()
        assert remaining == ["RHAISTRAT-2"]

    def test_stores_abstained_count_in_state(self, tmp_dir):
        _write_ids("tmp/pipeline-active-ids.txt",
                   ["RHAISTRAT-1", "RHAISTRAT-2", "RHAISTRAT-3", "RHAISTRAT-4"])
        stubs = {
            "artifacts/epic-tasks/RHAISTRAT-1-decomposition.md":
                ({"triage": "abstained", "epic_count": 0}, ""),
            "artifacts/epic-tasks/RHAISTRAT-2-decomposition.md":
                ({"triage": "proceed", "epic_count": 0}, ""),
            "artifacts/epic-tasks/RHAISTRAT-3-decomposition.md":
                ({"triage": "proceed", "epic_count": 0}, ""),
            "artifacts/epic-tasks/RHAISTRAT-4-decomposition.md":
                ({"triage": "proceed", "epic_count": 0}, ""),
        }
        for path in stubs:
            _touch(path)
        rfm = _make_rfm(stubs)
        state = {"phase": "TRIAGE"}
        advance(state, dry_run=False, read_frontmatter=rfm)
        assert state["triage_abstained_count"] == 1

    def test_stores_abstention_rate_in_state(self, tmp_dir):
        _write_ids("tmp/pipeline-active-ids.txt",
                   ["RHAISTRAT-1", "RHAISTRAT-2"])
        stubs = {
            "artifacts/epic-tasks/RHAISTRAT-1-decomposition.md":
                ({"triage": "abstained", "epic_count": 0}, ""),
            "artifacts/epic-tasks/RHAISTRAT-2-decomposition.md":
                ({"triage": "proceed", "epic_count": 0}, ""),
        }
        for path in stubs:
            _touch(path)
        rfm = _make_rfm(stubs)
        state = {"phase": "TRIAGE"}
        advance(state, dry_run=False, read_frontmatter=rfm)
        assert state["triage_abstention_rate"] == pytest.approx(0.5)

    def test_sets_distribution_shift_warning_when_rate_exceeds_20_percent(
            self, tmp_dir):
        _write_ids("tmp/pipeline-active-ids.txt",
                   ["RHAISTRAT-1", "RHAISTRAT-2", "RHAISTRAT-3", "RHAISTRAT-4",
                    "RHAISTRAT-5"])
        stubs = {
            "artifacts/epic-tasks/RHAISTRAT-1-decomposition.md":
                ({"triage": "abstained", "epic_count": 0}, ""),
            "artifacts/epic-tasks/RHAISTRAT-2-decomposition.md":
                ({"triage": "abstained", "epic_count": 0}, ""),
            "artifacts/epic-tasks/RHAISTRAT-3-decomposition.md":
                ({"triage": "proceed", "epic_count": 0}, ""),
            "artifacts/epic-tasks/RHAISTRAT-4-decomposition.md":
                ({"triage": "proceed", "epic_count": 0}, ""),
            "artifacts/epic-tasks/RHAISTRAT-5-decomposition.md":
                ({"triage": "proceed", "epic_count": 0}, ""),
        }
        for path in stubs:
            _touch(path)
        rfm = _make_rfm(stubs)
        state = {"phase": "TRIAGE"}
        advance(state, dry_run=False, read_frontmatter=rfm)
        # 2/5 = 40% > 20% threshold
        assert state.get("triage_distribution_shift_warning") is True

    def test_no_distribution_shift_warning_when_rate_at_or_below_20_percent(
            self, tmp_dir):
        _write_ids("tmp/pipeline-active-ids.txt",
                   ["RHAISTRAT-1", "RHAISTRAT-2", "RHAISTRAT-3",
                    "RHAISTRAT-4", "RHAISTRAT-5"])
        stubs = {
            "artifacts/epic-tasks/RHAISTRAT-1-decomposition.md":
                ({"triage": "abstained", "epic_count": 0}, ""),
            "artifacts/epic-tasks/RHAISTRAT-2-decomposition.md":
                ({"triage": "proceed", "epic_count": 0}, ""),
            "artifacts/epic-tasks/RHAISTRAT-3-decomposition.md":
                ({"triage": "proceed", "epic_count": 0}, ""),
            "artifacts/epic-tasks/RHAISTRAT-4-decomposition.md":
                ({"triage": "proceed", "epic_count": 0}, ""),
            "artifacts/epic-tasks/RHAISTRAT-5-decomposition.md":
                ({"triage": "proceed", "epic_count": 0}, ""),
        }
        for path in stubs:
            _touch(path)
        rfm = _make_rfm(stubs)
        state = {"phase": "TRIAGE"}
        advance(state, dry_run=False, read_frontmatter=rfm)
        # 1/5 = 20% — NOT above threshold (must be strictly greater than 20%)
        assert "triage_distribution_shift_warning" not in state

    def test_dry_run_does_not_modify_state_or_ids(self, tmp_dir):
        _write_ids("tmp/pipeline-active-ids.txt",
                   ["RHAISTRAT-1", "RHAISTRAT-2"])
        stubs = {
            "artifacts/epic-tasks/RHAISTRAT-1-decomposition.md":
                ({"triage": "abstained", "epic_count": 0}, ""),
            "artifacts/epic-tasks/RHAISTRAT-2-decomposition.md":
                ({"triage": "proceed", "epic_count": 0}, ""),
        }
        for path in stubs:
            _touch(path)
        rfm = _make_rfm(stubs)
        state = {"phase": "TRIAGE"}
        advance(state, dry_run=True, read_frontmatter=rfm)

        # State not modified
        assert "triage_abstained_count" not in state
        assert "triage_abstention_rate" not in state

        # Active IDs file not modified
        from pathlib import Path
        remaining = Path("tmp/pipeline-active-ids.txt").read_text().split()
        assert set(remaining) == {"RHAISTRAT-1", "RHAISTRAT-2"}

    def test_summary_includes_distribution_shift_warning_text(self, tmp_dir):
        _write_ids("tmp/pipeline-active-ids.txt",
                   ["RHAISTRAT-1", "RHAISTRAT-2", "RHAISTRAT-3"])
        stubs = {
            "artifacts/epic-tasks/RHAISTRAT-1-decomposition.md":
                ({"triage": "abstained", "epic_count": 0}, ""),
            "artifacts/epic-tasks/RHAISTRAT-2-decomposition.md":
                ({"triage": "abstained", "epic_count": 0}, ""),
            "artifacts/epic-tasks/RHAISTRAT-3-decomposition.md":
                ({"triage": "proceed", "epic_count": 0}, ""),
        }
        for path in stubs:
            _touch(path)
        rfm = _make_rfm(stubs)
        state = {"phase": "TRIAGE"}
        _, summary = advance(state, dry_run=False, read_frontmatter=rfm)
        assert "DISTRIBUTION_SHIFT_WARNING" in summary

    def test_abstained_strategy_excluded_from_active_ids_before_decompose(
            self, tmp_dir):
        """After TRIAGE advance, abstained IDs are removed so DECOMPOSE
        never polls them."""
        _write_ids("tmp/pipeline-active-ids.txt",
                   ["RHAISTRAT-A", "RHAISTRAT-B"])
        stubs = {
            "artifacts/epic-tasks/RHAISTRAT-A-decomposition.md":
                ({"triage": "abstained", "epic_count": 0}, ""),
            "artifacts/epic-tasks/RHAISTRAT-B-decomposition.md":
                ({"triage": "below-threshold", "epic_count": 0}, ""),
        }
        for path in stubs:
            _touch(path)
        rfm = _make_rfm(stubs)
        state = {"phase": "TRIAGE"}
        advance(state, dry_run=False, read_frontmatter=rfm)

        from pathlib import Path
        active = Path("tmp/pipeline-active-ids.txt").read_text().split()
        assert "RHAISTRAT-A" not in active
        assert "RHAISTRAT-B" in active


# ── DECOMPOSE ──────────────────────────────────────────────────────────────────


class TestDecompose:
    def test_transitions_to_review_decomp(self, tmp_dir):
        with patch("pipeline_state._compute_ai_scores"):
            nxt, _ = advance({"phase": "DECOMPOSE"}, dry_run=False)
        assert nxt == "REVIEW_DECOMP"

    def test_calls_compute_ai_scores_on_active_ids(self, tmp_dir):
        with patch("pipeline_state._compute_ai_scores") as mock_cas:
            advance({"phase": "DECOMPOSE"}, dry_run=False)
        mock_cas.assert_called_once_with("tmp/pipeline-active-ids.txt")

    def test_skips_compute_ai_scores_when_dry_run(self, tmp_dir):
        with patch("pipeline_state._compute_ai_scores") as mock_cas:
            advance({"phase": "DECOMPOSE"}, dry_run=True)
        mock_cas.assert_not_called()


# ── REVIEW_DECOMP ──────────────────────────────────────────────────────────────


class TestReviewDecomp:
    def test_transitions_unconditionally_to_revise_decomp(self, tmp_dir):
        nxt, summary = advance({"phase": "REVIEW_DECOMP"}, dry_run=True)
        assert nxt == "REVISE_DECOMP"
        assert "unconditional" in summary

    def test_resets_revised_flag_for_each_active_id(self, tmp_dir):
        _write_ids("tmp/pipeline-active-ids.txt", ["RHAISTRAT-1", "RHAISTRAT-2"])
        for sid in ["RHAISTRAT-1", "RHAISTRAT-2"]:
            _touch(f"artifacts/epic-tasks/{sid}-decomposition.md")

        state = {"phase": "REVIEW_DECOMP"}
        with patch("pipeline_state._reset_revised_flag") as mock_reset:
            advance(state, dry_run=False)

        assert mock_reset.call_count == 2
        paths_reset = {c.args[0] for c in mock_reset.call_args_list}
        assert "artifacts/epic-tasks/RHAISTRAT-1-decomposition.md" in paths_reset
        assert "artifacts/epic-tasks/RHAISTRAT-2-decomposition.md" in paths_reset

    def test_skips_missing_decomp_files(self, tmp_dir):
        _write_ids("tmp/pipeline-active-ids.txt", ["RHAISTRAT-1"])
        # No decomp file created → _reset_revised_flag must NOT be called

        state = {"phase": "REVIEW_DECOMP"}
        with patch("pipeline_state._reset_revised_flag") as mock_reset:
            advance(state, dry_run=False)

        mock_reset.assert_not_called()


# ── REVISE_DECOMP ──────────────────────────────────────────────────────────────


class TestReviseDecomp:
    def test_transitions_to_re_review_check(self, tmp_dir):
        with patch("pipeline_state._compute_ai_scores"):
            nxt, _ = advance({"phase": "REVISE_DECOMP"}, dry_run=False)
        assert nxt == "RE_REVIEW_CHECK"

    def test_calls_compute_ai_scores_on_active_ids(self, tmp_dir):
        with patch("pipeline_state._compute_ai_scores") as mock_cas:
            advance({"phase": "REVISE_DECOMP"}, dry_run=False)
        mock_cas.assert_called_once_with("tmp/pipeline-active-ids.txt")

    def test_skips_compute_ai_scores_when_dry_run(self, tmp_dir):
        with patch("pipeline_state._compute_ai_scores") as mock_cas:
            advance({"phase": "REVISE_DECOMP"}, dry_run=True)
        mock_cas.assert_not_called()


# ── RE_REVIEW_CHECK ────────────────────────────────────────────────────────────


class TestReReviewCheck:
    def test_to_batch_done_when_no_revised_ids(self, tmp_dir):
        _write_ids("tmp/pipeline-active-ids.txt", ["RHAISTRAT-1"])
        decomp = "artifacts/epic-tasks/RHAISTRAT-1-decomposition.md"
        _touch(decomp)

        rfm = _make_rfm({decomp: ({"revised": False}, "")})
        state = {"phase": "RE_REVIEW_CHECK", "revise_cycle": 0}
        nxt, summary = advance(state, read_frontmatter=rfm)
        assert nxt == "BATCH_DONE"
        assert "no changes" in summary

    def test_to_re_review_when_revised_ids_found(self, tmp_dir):
        _write_ids("tmp/pipeline-active-ids.txt", ["RHAISTRAT-1"])
        decomp = "artifacts/epic-tasks/RHAISTRAT-1-decomposition.md"
        _touch(decomp)

        rfm = _make_rfm({decomp: ({"revised": True}, "")})
        state = {"phase": "RE_REVIEW_CHECK", "revise_cycle": 0}
        nxt, _ = advance(state, dry_run=True, read_frontmatter=rfm)
        assert nxt == "RE_REVIEW"

    def test_uses_revise_ids_file_after_first_cycle(self, tmp_dir):
        # cycle > 0 → reads from pipeline-revise-ids.txt, not active-ids
        _write_ids("tmp/pipeline-revise-ids.txt", ["RHAISTRAT-2"])
        decomp = "artifacts/epic-tasks/RHAISTRAT-2-decomposition.md"
        _touch(decomp)

        rfm = _make_rfm({decomp: ({"revised": True}, "")})
        state = {"phase": "RE_REVIEW_CHECK", "revise_cycle": 1}
        nxt, _ = advance(state, dry_run=True, read_frontmatter=rfm)
        assert nxt == "RE_REVIEW"

    def test_to_batch_done_when_active_ids_empty(self, tmp_dir):
        _write_ids("tmp/pipeline-active-ids.txt", [])
        rfm = _make_rfm({})
        state = {"phase": "RE_REVIEW_CHECK", "revise_cycle": 0}
        nxt, _ = advance(state, read_frontmatter=rfm)
        assert nxt == "BATCH_DONE"


# ── RE_REVIEW ──────────────────────────────────────────────────────────────────


class TestReReview:
    def test_transitions_to_revise_check(self, tmp_dir):
        nxt, _ = advance({"phase": "RE_REVIEW"}, dry_run=True)
        assert nxt == "REVISE_CHECK"


# ── REVISE_CHECK ───────────────────────────────────────────────────────────────


class TestReviseCheck:
    def _setup(self, tmp_dir, ids, review_data):
        _write_ids("tmp/pipeline-revise-ids.txt", ids)
        path_data = {}
        for sid in ids:
            review = f"artifacts/epic-reviews/{sid}-decomp-review.md"
            _touch(review)
            path_data[review] = (review_data, "")
        return _make_rfm(path_data)

    def test_to_re_revise_when_failing_review_cycle_zero(self, tmp_dir):
        rfm = self._setup(tmp_dir, ["RHAISTRAT-1"], {"pass": False})
        state = {"phase": "REVISE_CHECK", "revise_cycle": 0}
        nxt, summary = advance(state, dry_run=True, read_frontmatter=rfm)
        assert nxt == "RE_REVISE"
        assert "cycle=1/2" in summary

    def test_to_re_revise_when_failing_review_cycle_one(self, tmp_dir):
        rfm = self._setup(tmp_dir, ["RHAISTRAT-1"], {"pass": False})
        state = {"phase": "REVISE_CHECK", "revise_cycle": 1}
        nxt, summary = advance(state, dry_run=True, read_frontmatter=rfm)
        assert nxt == "RE_REVISE"
        assert "cycle=2/2" in summary

    def test_cycle_cap_at_two_goes_to_batch_done(self, tmp_dir):
        """After 2 revise cycles with still-failing review → BATCH_DONE."""
        rfm = self._setup(tmp_dir, ["RHAISTRAT-1"], {"pass": False})
        state = {"phase": "REVISE_CHECK", "revise_cycle": 2}
        nxt, summary = advance(state, dry_run=True, read_frontmatter=rfm)
        assert nxt == "BATCH_DONE"
        assert "cycle cap" in summary

    def test_to_batch_done_when_review_passes(self, tmp_dir):
        rfm = self._setup(tmp_dir, ["RHAISTRAT-1"], {"pass": True})
        state = {"phase": "REVISE_CHECK", "revise_cycle": 0}
        nxt, _ = advance(state, dry_run=True, read_frontmatter=rfm)
        assert nxt == "BATCH_DONE"

    def test_to_batch_done_when_no_revise_ids(self, tmp_dir):
        _write_ids("tmp/pipeline-revise-ids.txt", [])
        rfm = _make_rfm({})
        state = {"phase": "REVISE_CHECK", "revise_cycle": 0}
        nxt, _ = advance(state, dry_run=True, read_frontmatter=rfm)
        assert nxt == "BATCH_DONE"

    def test_resets_revised_flag_for_failing_ids_when_not_dry_run(self, tmp_dir):
        """REVISE_CHECK resets the revised flag on each failing ID's decomp file."""
        _write_ids("tmp/pipeline-revise-ids.txt", ["RHAISTRAT-1"])
        review = "artifacts/epic-reviews/RHAISTRAT-1-decomp-review.md"
        decomp = "artifacts/epic-tasks/RHAISTRAT-1-decomposition.md"
        _touch(review)
        _touch(decomp)

        rfm = _make_rfm({review: ({"pass": False}, "")})
        state = {"phase": "REVISE_CHECK", "revise_cycle": 0}

        with patch("pipeline_state._reset_revised_flag") as mock_reset:
            advance(state, dry_run=False, read_frontmatter=rfm)

        mock_reset.assert_called_once_with(decomp, read_frontmatter=rfm)


# ── RE_REVISE ──────────────────────────────────────────────────────────────────


class TestReRevise:
    def test_transitions_to_re_review_check(self, tmp_dir):
        with patch("pipeline_state._compute_ai_scores"):
            nxt, _ = advance({"phase": "RE_REVISE"}, dry_run=False)
        assert nxt == "RE_REVIEW_CHECK"

    def test_calls_compute_ai_scores_on_revise_ids(self, tmp_dir):
        with patch("pipeline_state._compute_ai_scores") as mock_cas:
            advance({"phase": "RE_REVISE"}, dry_run=False)
        mock_cas.assert_called_once_with("tmp/pipeline-revise-ids.txt")

    def test_skips_compute_ai_scores_when_dry_run(self, tmp_dir):
        with patch("pipeline_state._compute_ai_scores") as mock_cas:
            advance({"phase": "RE_REVISE"}, dry_run=True)
        mock_cas.assert_not_called()


# ── BATCH_DONE ─────────────────────────────────────────────────────────────────


class TestBatchDone:
    def test_to_batch_start_when_not_last_batch(self, tmp_dir):
        _write_ids("tmp/pipeline-active-ids.txt", ["RHAISTRAT-1"])
        rfm = _make_rfm({})
        state = {"phase": "BATCH_DONE", "batch": 1, "total_batches": 3,
                 "retry_cycle": 0}
        nxt, _ = advance(state, dry_run=True, read_frontmatter=rfm)
        assert nxt == "BATCH_START"

    def test_to_report_when_last_batch_no_errors(self, tmp_dir):
        _write_ids("tmp/pipeline-active-ids.txt", ["RHAISTRAT-1"])
        _write_ids("tmp/pipeline-all-ids.txt", ["RHAISTRAT-1"])
        decomp = "artifacts/epic-tasks/RHAISTRAT-1-decomposition.md"
        _touch(decomp)

        rfm = _make_rfm({})
        state = {"phase": "BATCH_DONE", "batch": 1, "total_batches": 1,
                 "retry_cycle": 0}
        nxt, _ = advance(state, read_frontmatter=rfm)
        assert nxt == "REPORT"

    def test_to_error_collect_when_decomp_missing(self, tmp_dir):
        _write_ids("tmp/pipeline-active-ids.txt", ["RHAISTRAT-1"])
        _write_ids("tmp/pipeline-all-ids.txt", ["RHAISTRAT-1"])
        # No decomp file → triggers ERROR_COLLECT

        rfm = _make_rfm({})
        state = {"phase": "BATCH_DONE", "batch": 1, "total_batches": 1,
                 "retry_cycle": 0}
        nxt, _ = advance(state, read_frontmatter=rfm)
        assert nxt == "ERROR_COLLECT"

    def test_to_error_collect_when_review_has_error_flag(self, tmp_dir):
        _write_ids("tmp/pipeline-active-ids.txt", ["RHAISTRAT-1"])
        _write_ids("tmp/pipeline-all-ids.txt", ["RHAISTRAT-1"])
        decomp = "artifacts/epic-tasks/RHAISTRAT-1-decomposition.md"
        review = "artifacts/epic-reviews/RHAISTRAT-1-decomp-review.md"
        _touch(decomp)
        _touch(review)

        rfm = _make_rfm({review: ({"error": "agent crashed"}, "")})
        state = {"phase": "BATCH_DONE", "batch": 1, "total_batches": 1,
                 "retry_cycle": 0}
        nxt, _ = advance(state, read_frontmatter=rfm)
        assert nxt == "ERROR_COLLECT"

    def test_skips_error_check_when_retry_cycle_nonzero(self, tmp_dir):
        _write_ids("tmp/pipeline-active-ids.txt", ["RHAISTRAT-1"])
        # Missing decomp would normally trigger ERROR_COLLECT, but retry_cycle=1
        # skips the error check and goes straight to REPORT

        rfm = _make_rfm({})
        state = {"phase": "BATCH_DONE", "batch": 1, "total_batches": 1,
                 "retry_cycle": 1}
        nxt, _ = advance(state, read_frontmatter=rfm)
        assert nxt == "REPORT"


# ── ERROR_COLLECT ──────────────────────────────────────────────────────────────


class TestErrorCollect:
    def test_transitions_to_batch_start(self, tmp_dir):
        _write_ids("tmp/pipeline-retry-ids.txt", ["RHAISTRAT-1"])
        state = {"phase": "ERROR_COLLECT", "total_batches": 2}
        nxt, summary = advance(state, dry_run=True)
        assert nxt == "BATCH_START"
        assert "ERROR_COLLECT" in summary


# ── REPORT ─────────────────────────────────────────────────────────────────────


class TestReport:
    def test_transitions_to_done(self, tmp_dir):
        nxt, _ = advance({"phase": "REPORT"}, dry_run=True)
        assert nxt == "DONE"


# ── _compute_ai_scores called at exactly three transitions ─────────────────────


class TestComputeAiScoresCoverage:
    def test_scoring_phases_call_it_exactly_three_times(self, tmp_dir):
        """_compute_ai_scores fires at DECOMPOSE, REVISE_DECOMP, RE_REVISE only."""
        with patch("pipeline_state._compute_ai_scores") as mock_cas:
            advance({"phase": "DECOMPOSE"}, dry_run=False)
            advance({"phase": "REVISE_DECOMP"}, dry_run=False)
            advance({"phase": "RE_REVISE"}, dry_run=False)
        assert mock_cas.call_count == 3

    def test_non_scoring_phases_do_not_call_it(self, tmp_dir):
        """None of the other phases invoke _compute_ai_scores."""
        _write_ids("tmp/pipeline-active-ids.txt", [])
        _write_ids("tmp/pipeline-revise-ids.txt", [])
        _write_ids("tmp/pipeline-all-ids.txt", [])
        _write_ids("tmp/pipeline-retry-ids.txt", [])
        rfm = _make_rfm({})

        with patch("pipeline_state._compute_ai_scores") as mock_cas:
            advance({"phase": "BATCH_START", "batch": 0}, dry_run=True,
                    read_frontmatter=rfm)
            advance({"phase": "FETCH"}, dry_run=True, read_frontmatter=rfm)
            advance({"phase": "TRIAGE"}, dry_run=True, read_frontmatter=rfm)
            advance({"phase": "REVIEW_DECOMP"}, dry_run=True,
                    read_frontmatter=rfm)
            advance({"phase": "RE_REVIEW_CHECK", "revise_cycle": 0},
                    dry_run=True, read_frontmatter=rfm)
            advance({"phase": "RE_REVIEW"}, dry_run=True, read_frontmatter=rfm)
            advance({"phase": "REVISE_CHECK", "revise_cycle": 0},
                    dry_run=True, read_frontmatter=rfm)
            advance({"phase": "BATCH_DONE", "batch": 1, "total_batches": 1,
                     "retry_cycle": 1}, dry_run=True, read_frontmatter=rfm)
            advance({"phase": "ERROR_COLLECT", "total_batches": 0},
                    dry_run=True, read_frontmatter=rfm)
            advance({"phase": "REPORT"}, dry_run=True, read_frontmatter=rfm)

        mock_cas.assert_not_called()

    def test_decompose_uses_active_ids_file(self, tmp_dir):
        with patch("pipeline_state._compute_ai_scores") as mock_cas:
            advance({"phase": "DECOMPOSE"}, dry_run=False)
        assert mock_cas.call_args == call("tmp/pipeline-active-ids.txt")

    def test_revise_decomp_uses_active_ids_file(self, tmp_dir):
        with patch("pipeline_state._compute_ai_scores") as mock_cas:
            advance({"phase": "REVISE_DECOMP"}, dry_run=False)
        assert mock_cas.call_args == call("tmp/pipeline-active-ids.txt")

    def test_re_revise_uses_revise_ids_file(self, tmp_dir):
        with patch("pipeline_state._compute_ai_scores") as mock_cas:
            advance({"phase": "RE_REVISE"}, dry_run=False)
        assert mock_cas.call_args == call("tmp/pipeline-revise-ids.txt")


# ── _reset_revised_flag behavior ───────────────────────────────────────────────


class TestResetRevisedFlag:
    def test_removes_revised_key_when_present(self, tmp_dir):
        """_reset_revised_flag deletes 'revised', not just sets it to False."""
        decomp = "artifacts/epic-tasks/RHAISTRAT-1-decomposition.md"
        Path(decomp).parent.mkdir(parents=True, exist_ok=True)
        Path(decomp).write_text(
            "---\nrevised: false\nepic_count: 2\n---\nbody text\n"
        )

        from artifact_utils import read_frontmatter
        _reset_revised_flag(decomp, read_frontmatter=read_frontmatter)

        data, body = read_frontmatter(decomp)
        assert "revised" not in data
        assert data.get("epic_count") == 2
        assert body.strip() == "body text"

    def test_no_op_when_revised_key_absent(self, tmp_dir):
        """_reset_revised_flag is safe when file has no 'revised' key."""
        decomp = "artifacts/epic-tasks/RHAISTRAT-1-decomposition.md"
        Path(decomp).parent.mkdir(parents=True, exist_ok=True)
        Path(decomp).write_text("---\nepic_count: 1\n---\nbody\n")

        from artifact_utils import read_frontmatter
        _reset_revised_flag(decomp, read_frontmatter=read_frontmatter)

        data, _ = read_frontmatter(decomp)
        assert "revised" not in data

    def test_called_in_review_decomp_transition(self, tmp_dir):
        """REVIEW_DECOMP calls _reset_revised_flag for each existing decomp."""
        _write_ids("tmp/pipeline-active-ids.txt", ["RHAISTRAT-1"])
        _touch("artifacts/epic-tasks/RHAISTRAT-1-decomposition.md")

        state = {"phase": "REVIEW_DECOMP"}
        with patch("pipeline_state._reset_revised_flag") as mock_reset:
            advance(state, dry_run=False)

        mock_reset.assert_called_once()
        assert "RHAISTRAT-1-decomposition.md" in mock_reset.call_args.args[0]

    def test_called_in_revise_check_for_failing_ids(self, tmp_dir):
        """REVISE_CHECK calls _reset_revised_flag for failing IDs (non-dry-run)."""
        _write_ids("tmp/pipeline-revise-ids.txt", ["RHAISTRAT-1"])
        review = "artifacts/epic-reviews/RHAISTRAT-1-decomp-review.md"
        decomp = "artifacts/epic-tasks/RHAISTRAT-1-decomposition.md"
        _touch(review)
        _touch(decomp)

        rfm = _make_rfm({review: ({"pass": False}, "")})
        state = {"phase": "REVISE_CHECK", "revise_cycle": 0}

        with patch("pipeline_state._reset_revised_flag") as mock_reset:
            advance(state, dry_run=False, read_frontmatter=rfm)

        mock_reset.assert_called_once_with(decomp, read_frontmatter=rfm)

    def test_not_called_in_revise_check_for_passing_ids(self, tmp_dir):
        """REVISE_CHECK does not call _reset_revised_flag when review passes."""
        _write_ids("tmp/pipeline-revise-ids.txt", ["RHAISTRAT-1"])
        review = "artifacts/epic-reviews/RHAISTRAT-1-decomp-review.md"
        _touch(review)

        rfm = _make_rfm({review: ({"pass": True}, "")})
        state = {"phase": "REVISE_CHECK", "revise_cycle": 0}

        with patch("pipeline_state._reset_revised_flag") as mock_reset:
            advance(state, dry_run=False, read_frontmatter=rfm)

        mock_reset.assert_not_called()


# ── Triage poller ──────────────────────────────────────────────────────────────


class TestTriagePoller:
    def test_pending_when_stub_absent(self, tmp_dir):
        from check_decompose_progress import check_id
        assert check_id("triage", "RHAISTRAT-1") == "pending"

    def test_pending_when_stub_has_no_triage_field(self, tmp_dir):
        from check_decompose_progress import check_id
        stub = "artifacts/epic-tasks/RHAISTRAT-1-decomposition.md"
        from pathlib import Path
        Path(stub).parent.mkdir(parents=True, exist_ok=True)
        Path(stub).write_text("---\nepic_count: 0\n---\n")
        assert check_id("triage", "RHAISTRAT-1") == "pending"

    def test_completed_when_triage_is_proceed(self, tmp_dir):
        from check_decompose_progress import check_id
        stub = "artifacts/epic-tasks/RHAISTRAT-1-decomposition.md"
        from pathlib import Path
        Path(stub).parent.mkdir(parents=True, exist_ok=True)
        Path(stub).write_text(
            "---\ntriage: proceed\nepic_count: 0\n---\n")
        assert check_id("triage", "RHAISTRAT-1") == "completed"

    def test_completed_when_triage_is_abstained(self, tmp_dir):
        from check_decompose_progress import check_id
        stub = "artifacts/epic-tasks/RHAISTRAT-1-decomposition.md"
        from pathlib import Path
        Path(stub).parent.mkdir(parents=True, exist_ok=True)
        Path(stub).write_text(
            "---\ntriage: abstained\nepic_count: 0\n---\n")
        assert check_id("triage", "RHAISTRAT-1") == "completed"

    def test_completed_when_triage_is_below_threshold(self, tmp_dir):
        from check_decompose_progress import check_id
        stub = "artifacts/epic-tasks/RHAISTRAT-1-decomposition.md"
        from pathlib import Path
        Path(stub).parent.mkdir(parents=True, exist_ok=True)
        Path(stub).write_text(
            "---\ntriage: below-threshold\nepic_count: 0\n---\n")
        assert check_id("triage", "RHAISTRAT-1") == "completed"

    def test_decompose_poller_returns_pending_for_stub_with_epic_count_zero(
            self, tmp_dir):
        """Triage stubs have epic_count: 0; the decompose poller must not
        count them as completed."""
        from check_decompose_progress import check_id
        stub = "artifacts/epic-tasks/RHAISTRAT-1-decomposition.md"
        from pathlib import Path
        Path(stub).parent.mkdir(parents=True, exist_ok=True)
        Path(stub).write_text(
            "---\ntriage: proceed\nepic_count: 0\n---\n")
        assert check_id("decompose", "RHAISTRAT-1") == "pending"


# ── Poller quirk: any non-None revised counts as completed ────────────────────


class TestPollerQuirk:
    def test_revised_false_counts_as_completed(self, tmp_dir):
        """revised: False is non-None, so the poller treats it as completed."""
        from check_decompose_progress import check_id

        decomp = "artifacts/epic-tasks/RHAISTRAT-1-decomposition.md"
        Path(decomp).parent.mkdir(parents=True, exist_ok=True)
        Path(decomp).write_text("---\nrevised: false\nepic_count: 1\n---\n")

        assert check_id("revise_decomp", "RHAISTRAT-1") == "completed"

    def test_revised_absent_means_pending(self, tmp_dir):
        """Absent revised key means the agent has not finished yet."""
        from check_decompose_progress import check_id

        decomp = "artifacts/epic-tasks/RHAISTRAT-1-decomposition.md"
        Path(decomp).parent.mkdir(parents=True, exist_ok=True)
        Path(decomp).write_text("---\nepic_count: 1\n---\n")

        assert check_id("revise_decomp", "RHAISTRAT-1") == "pending"

    def test_revised_true_counts_as_completed(self, tmp_dir):
        """revised: True also counts as completed (changes were made)."""
        from check_decompose_progress import check_id

        decomp = "artifacts/epic-tasks/RHAISTRAT-1-decomposition.md"
        Path(decomp).parent.mkdir(parents=True, exist_ok=True)
        Path(decomp).write_text("---\nrevised: true\nepic_count: 1\n---\n")

        assert check_id("revise_decomp", "RHAISTRAT-1") == "completed"

    def test_flag_delete_restores_pending_state(self, tmp_dir):
        """
        Setting revised: False instead of deleting it leaves poller at
        'completed', so the revise agent is never re-launched. Deleting
        the key makes the poller return 'pending' again.
        """
        from check_decompose_progress import check_id
        from artifact_utils import read_frontmatter

        decomp = "artifacts/epic-tasks/RHAISTRAT-1-decomposition.md"
        Path(decomp).parent.mkdir(parents=True, exist_ok=True)
        Path(decomp).write_text("---\nrevised: false\nepic_count: 1\n---\n")

        # Before reset: False is non-None → completed
        assert check_id("revise_decomp", "RHAISTRAT-1") == "completed"

        # After reset: key gone → pending
        _reset_revised_flag(decomp, read_frontmatter=read_frontmatter)
        assert check_id("revise_decomp", "RHAISTRAT-1") == "pending"
