"""R8 분산 배치와 소거 Guard 테스트."""

from __future__ import annotations

import pytest

from weekly_num.analyzer import eliminator
from weekly_num.config import Config
from weekly_num.drawer import make_rng
from weekly_num.models import NUM_POSITIONS
from weekly_num.strategy import spread

TAIL = spread.TAIL_POSITION


def build(draws, cfg, seed=1):
    logs = eliminator.build_position_logs(draws, cfg)
    return spread.build_recommendation(draws, logs, cfg, make_rng(seed))


def test_tails_are_all_distinct(draws, cfg) -> None:
    """R8 — 5장의 뒤 1자리는 서로 달라야 한다."""
    rec = build(draws, cfg)
    tails = [t.digits[TAIL] for t in rec.tickets]
    assert len(set(tails)) == 5


def test_distinct_tails_imply_distinct_longer_tails(draws, cfg) -> None:
    """뒤 1자리가 다르면 뒤 2·3자리도 자동으로 달라진다 (PRD F6-4)."""
    rec = build(draws, cfg)
    for length in (1, 2, 3):
        tails = [t.number[-length:] for t in rec.tickets]
        assert len(set(tails)) == 5, f"뒤 {length}자리가 중복됨: {tails}"


def test_numbers_and_groups_are_unique(draws, cfg) -> None:
    rec = build(draws, cfg)
    assert len({t.number for t in rec.tickets}) == 5
    assert sorted(t.group_no for t in rec.tickets) == [1, 2, 3, 4, 5]


def test_tail_position_keeps_at_least_five_candidates(draws, cfg) -> None:
    """R8이 R1~R7보다 우선하므로 뒷자리 후보는 5개 이상 남아야 한다."""
    logs = eliminator.build_position_logs(draws, cfg)
    assert len(logs[TAIL].final) >= cfg.strategy.tickets


def test_guard_keeps_minimum_candidates(draws) -> None:
    """규칙을 극단적으로 세게 걸어도 후보가 최소치 아래로 내려가지 않는다."""
    cfg = Config()
    cfg.rules.recent_exclusion.n = 40   # 사실상 모든 숫자가 걸린다
    cfg.rules.hot_exclusion.top_k = 9
    logs = eliminator.build_position_logs(draws, cfg)
    for log in logs:
        minimum = eliminator.required_candidates(log.position, cfg)
        assert len(log.final) >= minimum


def test_guard_records_skipped_rules(draws) -> None:
    """건너뛴 규칙은 조용히 사라지지 않고 로그에 남는다."""
    cfg = Config()
    cfg.rules.recent_exclusion.n = 40
    logs = eliminator.build_position_logs(draws, cfg)
    skipped = [s for log in logs for s in log.steps if s.skipped]
    assert skipped, "후보가 고갈될 설정인데 건너뛴 기록이 없다"
    assert all(s.skip_reason for s in skipped)


def test_verify_rejects_duplicate_tails() -> None:
    from weekly_num.models import Ticket

    bad = [Ticket(g, (0, 0, 0, 0, 0, 7)) for g in (1, 2)]
    with pytest.raises(AssertionError, match="R8 위반"):
        spread.verify(bad)


def test_assign_tails_tops_up_when_short() -> None:
    """후보가 모자라면 보충하고 사유를 남긴다 — 중복은 절대 허용하지 않는다."""
    tails, note = spread.assign_tails([1, 2], count=5, rng=make_rng(7))
    assert len(set(tails)) == 5
    assert note is not None


def test_concentrate_mode_uses_one_number(draws) -> None:
    cfg = Config()
    cfg.strategy.mode = "concentrate"
    rec = build(draws, cfg)
    assert len({t.number for t in rec.tickets}) == 1


def test_all_positions_have_logs(draws, cfg) -> None:
    logs = eliminator.build_position_logs(draws, cfg)
    assert len(logs) == NUM_POSITIONS
    assert [log.position for log in logs] == list(range(NUM_POSITIONS))
