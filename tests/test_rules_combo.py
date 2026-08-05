"""규칙 R4~R7 테스트."""

from __future__ import annotations

import pytest

from weekly_num.analyzer import eliminator, rules
from weekly_num.config import Config
from weekly_num.drawer import make_rng
from weekly_num.strategy import spread


# --- R4 인접값 제외 -------------------------------------------------
def test_adjacent_exclusion_removes_neighbours(draws) -> None:
    last = draws[-1].digits[0]
    out = rules.adjacent_exclusion(draws, 0)
    assert out.removed == {(last - 1) % 10, (last + 1) % 10}


def test_adjacent_exclusion_wraps_around(draws) -> None:
    """0의 이웃은 9와 1이다 (자리값은 순환한다)."""
    from datetime import date

    from weekly_num.models import Draw

    d = [Draw(1, date(2020, 5, 7), 1, (0, 0, 0, 0, 0, 0))]
    assert rules.adjacent_exclusion(d, 0).removed == {9, 1}


def test_r4_participates_in_elimination(draws) -> None:
    cfg = Config()
    cfg.rules.adjacent_exclusion.enabled = True
    logs = eliminator.build_position_logs(draws, cfg)
    applied = {s.rule for log in logs for s in log.steps if not s.skipped}
    assert "adjacent_exclusion" in applied


# --- R5 홀짝 균형 ---------------------------------------------------
@pytest.mark.parametrize(
    "digits, ok",
    [
        ((1, 3, 5, 7, 9, 1), False),  # 홀 6개 — 극단
        ((0, 2, 4, 6, 8, 0), False),  # 짝 6개 — 극단
        ((1, 2, 3, 4, 5, 6), True),
        ((1, 2, 2, 4, 6, 8), True),   # 홀 1개 — 경계 통과
    ],
)
def test_parity_balance(digits, ok) -> None:
    assert (rules.check_parity(digits, 1, 5) is None) is ok


# --- R6 자리합 범위 -------------------------------------------------
def test_sum_bounds_are_within_observed_range(draws) -> None:
    low, high = rules.sum_bounds(draws, 10, 90)
    sums = [sum(d.digits) for d in draws]
    assert min(sums) <= low < high <= max(sums)


def test_check_sum_rejects_extremes(draws) -> None:
    low, high = rules.sum_bounds(draws, 10, 90)
    assert rules.check_sum((0, 0, 0, 0, 0, 0), low, high) is not None
    assert rules.check_sum((9, 9, 9, 9, 9, 9), low, high) is not None


def test_generated_tickets_satisfy_combo_rules(draws) -> None:
    """실제 생성된 5장이 R5·R6을 만족한다."""
    cfg = Config()
    logs = eliminator.build_position_logs(draws, cfg)
    rec = spread.build_recommendation(draws, logs, cfg, make_rng(4))
    bounds = rules.sum_bounds(draws, cfg.rules.sum_range.low_pct,
                              cfg.rules.sum_range.high_pct)
    for t in rec.tickets:
        assert rules.check_parity(t.digits, 1, 5) is None, t
        assert rules.check_sum(t.digits, *bounds) is None, t


def test_impossible_constraints_still_produce_tickets(draws) -> None:
    """제약을 만족할 수 없어도 리포트는 나와야 한다. 대신 사유를 남긴다."""
    cfg = Config()
    cfg.rules.parity_balance.min_odd = 6
    cfg.rules.parity_balance.max_odd = 6
    cfg.rules.sum_range.low_pct = 49  # 홀수 6개와 동시 만족이 사실상 불가능
    logs = eliminator.build_position_logs(draws, cfg)
    rec = spread.build_recommendation(draws, logs, cfg, make_rng(4))
    assert len(rec.tickets) == 5
    assert any("재시도" in n for n in rec.notes)
    spread.verify(rec.tickets)  # R8은 여전히 지켜진다


# --- R7 조 순환 -----------------------------------------------------
def test_group_rotation_is_reported_as_void_for_five_tickets() -> None:
    """5장이 5개 조를 다 덮으면 조를 고를 여지가 없다. 그 사실을 숨기지 않는다."""
    note = rules.group_rotation_note(5)
    assert "무효" in note


def test_active_rules_lists_r8_always() -> None:
    cfg = Config()
    names = rules.active_rules(cfg.rules, 5)
    assert any("R8" in n for n in names)
