"""등위 판정 테스트.

PRD RK14 대응. 등위는 배타적이며, 이 규칙이 깨지면 백테스트 결과가
조용히 부풀려진다. 그래서 여기 테스트를 고정해 둔다.
"""

from __future__ import annotations

from datetime import date

import pytest

from weekly_num.models import Draw, Ticket, evaluate_rank, is_bonus_win

DRAW = Draw.from_str(326, date(2026, 7, 30), 2, "502733", bonus="399616")


def t(group: int, number: str) -> Ticket:
    return Ticket(group, tuple(int(c) for c in number))


@pytest.mark.parametrize(
    "ticket, expected",
    [
        # 당첨번호 502733 의 꼬리: 3 / 33 / 733 / 2733 / 02733
        (t(2, "502733"), 1),   # 조 + 6자리
        (t(3, "502733"), 2),   # 6자리만 (조 불일치)
        (t(1, "902733"), 3),   # 뒤 5자리 (앞 1자리만 다름)
        (t(1, "992733"), 4),   # 뒤 4자리 — 뒤 5자리는 불일치이므로 3등이 아니다
        (t(1, "999733"), 5),   # 뒤 3자리
        (t(1, "999933"), 6),   # 뒤 2자리
        (t(1, "999993"), 7),   # 뒤 1자리
        (t(1, "999999"), None),  # 끝자리 9 ≠ 3
        (t(1, "999990"), None),
    ],
)
def test_rank_is_exclusive(ticket: Ticket, expected: int | None) -> None:
    assert evaluate_rank(ticket, DRAW) == expected


def test_higher_rank_wins_not_counted_twice() -> None:
    """뒤 5자리가 맞으면 그 아래 등위(4~7등)로는 세지 않는다."""
    ticket = t(1, "902733")
    rank = evaluate_rank(ticket, DRAW)
    assert rank == 3
    # 뒤 4·3·2·1자리도 모두 일치하지만 등위는 하나뿐이다.
    for tail in (4, 3, 2, 1):
        assert ticket.digits[-tail:] == DRAW.digits[-tail:]


def test_group_only_match_is_not_a_win() -> None:
    """조만 맞는 것은 당첨이 아니다."""
    assert evaluate_rank(t(2, "111110"), DRAW) is None


def test_bonus_is_group_independent() -> None:
    assert is_bonus_win(t(1, "399616"), DRAW) is True
    assert is_bonus_win(t(5, "399616"), DRAW) is True
    assert is_bonus_win(t(1, "399617"), DRAW) is False


def test_seventh_rank_probability_matches_official() -> None:
    """7등 확률이 1/10이 아니라 9/100(=1/11.1)임을 전수로 확인한다.

    공식 표기 1/11의 근거이며, R8 수치(9%/45%)의 출발점이다.
    """
    wins = sum(
        1
        for n in range(1000)
        if evaluate_rank(t(1, f"000{n:03d}"), DRAW) == 7
    )
    assert wins / 1000 == pytest.approx(0.09)
