"""도메인 모델과 등위 판정.

등위 판정(`evaluate_rank`)이 이 모듈의 핵심이다. PRD §2.2에서 확인했듯
연금복권720+의 등위는 **배타적**이므로 반드시 최상위부터 검사하고
첫 일치에서 중단해야 한다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

NUM_POSITIONS = 6
DIGITS: tuple[int, ...] = tuple(range(10))
GROUPS: tuple[int, ...] = (1, 2, 3, 4, 5)

#: 자리 이름 (동행복권 표기와 동일)
POSITION_NAMES = ("십만", "만", "천", "백", "십", "일")

#: 등위별 당첨금 (원). 연금식은 총 수령액 기준(세전).
RANK_PRIZE = {
    1: 700_0000 * 12 * 20,  # 월 700만원 × 20년
    2: 100_0000 * 12 * 10,  # 월 100만원 × 10년
    3: 1_000_000,
    4: 100_000,
    5: 50_000,
    6: 5_000,
    7: 1_000,
}

RANK_LABEL = {
    1: "1등 (조+6자리)",
    2: "2등 (6자리)",
    3: "3등 (뒤 5자리)",
    4: "4등 (뒤 4자리)",
    5: "5등 (뒤 3자리)",
    6: "6등 (뒤 2자리)",
    7: "7등 (뒤 1자리)",
}

TICKET_PRICE = 1_000


@dataclass(frozen=True, slots=True)
class Draw:
    """한 회차의 추첨 결과."""

    round: int
    draw_date: date
    group_no: int
    digits: tuple[int, ...]
    bonus: str | None = None

    def __post_init__(self) -> None:
        if self.group_no not in GROUPS:
            raise ValueError(f"조는 1~5여야 합니다: {self.group_no}")
        if len(self.digits) != NUM_POSITIONS:
            raise ValueError(f"번호는 6자리여야 합니다: {self.digits}")
        if any(d not in DIGITS for d in self.digits):
            raise ValueError(f"각 자리는 0~9여야 합니다: {self.digits}")

    @property
    def number(self) -> str:
        return "".join(str(d) for d in self.digits)

    @classmethod
    def from_str(cls, round_: int, draw_date: date, group_no: int, number: str,
                 bonus: str | None = None) -> Draw:
        return cls(round_, draw_date, group_no, tuple(int(c) for c in number), bonus)


@dataclass(frozen=True, slots=True)
class Ticket:
    """구매(추천) 한 장."""

    group_no: int
    digits: tuple[int, ...]

    @property
    def number(self) -> str:
        return "".join(str(d) for d in self.digits)

    def __str__(self) -> str:
        return f"{self.group_no}조 - {self.number}"


def evaluate_rank(ticket: Ticket, draw: Draw) -> int | None:
    """티켓의 당첨 등위를 반환한다. 미당첨이면 None.

    등위는 배타적이다(PRD §2.2). 상위 등위에 해당하면 하위 등위로는 세지 않는다.
    그래서 위에서부터 검사하고 **첫 일치에서 즉시 반환**한다.

    이 순서를 바꾸거나 각 등위를 독립적으로 세면 한 장이 여러 등위에
    중복 계상되어 백테스트 결과가 부풀려진다(PRD RK14).
    """
    if ticket.digits == draw.digits:
        return 1 if ticket.group_no == draw.group_no else 2
    for tail, rank in ((5, 3), (4, 4), (3, 5), (2, 6), (1, 7)):
        if ticket.digits[-tail:] == draw.digits[-tail:]:
            return rank
    return None


def is_bonus_win(ticket: Ticket, draw: Draw) -> bool:
    """보너스 당첨 여부. 조와 무관하게 6자리가 보너스 번호와 일치하면 당첨."""
    return draw.bonus is not None and ticket.number == draw.bonus


@dataclass(slots=True)
class EliminationStep:
    """소거 과정의 한 단계. 리포트에 그대로 표시된다."""

    rule: str
    label: str
    removed: tuple[int, ...] = ()
    detail: str = ""
    skipped: bool = False
    skip_reason: str = ""


@dataclass(slots=True)
class PositionLog:
    """한 자리(0~5)의 후보 소거 이력."""

    position: int
    initial: tuple[int, ...]
    steps: list[EliminationStep] = field(default_factory=list)
    final: tuple[int, ...] = ()

    @property
    def name(self) -> str:
        return POSITION_NAMES[self.position]

    @property
    def ordinal(self) -> int:
        return self.position + 1


@dataclass(slots=True)
class Recommendation:
    """분석 기반 추천 결과 일체."""

    tickets: list[Ticket]
    position_logs: list[PositionLog]
    notes: list[str] = field(default_factory=list)
