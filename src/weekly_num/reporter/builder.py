"""리포트 데이터 조립. 포맷과 무관한 순수 계산만 한다."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from ..analyzer import stats
from ..config import Config
from ..models import Draw, Recommendation, Ticket


@dataclass(slots=True)
class DigitNote:
    position: int
    digit: int
    count: int
    low: float
    high: float
    within: bool


@dataclass(slots=True)
class PositionStat:
    position: int
    chi: float
    p_value: float
    significant: bool
    min_digit: int
    min_count: int
    max_digit: int
    max_count: int


@dataclass(slots=True)
class ReportData:
    target_round: int
    target_date: date
    total_rounds: int
    first_round: int
    last_round: int
    last_draw_date: date
    window_size: int
    window_rounds: int
    expected_per_digit: float
    normal_low: float
    normal_high: float
    random_tickets: list[Ticket]
    recommendation: Recommendation
    active_rules: list[str]
    position_stats: list[PositionStat]
    longest_gap: DigitNote | None
    group_chi: float
    group_p: float
    seed: int | None = None
    warnings: list[str] = field(default_factory=list)

    @property
    def tail_hit_pct(self) -> float:
        from ..strategy.spread import tail_hit_probability

        return 100 * tail_hit_probability(len(self.recommendation.tickets), True)


def build(
    draws: list[Draw],
    target_round: int,
    target_date: date,
    random_tickets: list[Ticket],
    recommendation: Recommendation,
    cfg: Config,
    active_rules: list[str],
    seed: int | None = None,
    warnings: list[str] | None = None,
) -> ReportData:
    win = stats.window(draws, cfg.analysis.window)
    n = len(win)
    low, high = stats.normal_range(n)

    position_stats = []
    for p in range(6):
        freq = stats.frequency(win, p)
        chi, pv = stats.chi_square(freq)
        lo = min(freq.items(), key=lambda kv: (kv[1], kv[0]))
        hi = max(freq.items(), key=lambda kv: (kv[1], -kv[0]))
        position_stats.append(
            PositionStat(
                position=p, chi=chi, p_value=pv, significant=pv < 0.05,
                min_digit=lo[0], min_count=lo[1], max_digit=hi[0], max_count=hi[1],
            )
        )

    longest: DigitNote | None = None
    for p in range(6):
        g = stats.gaps(win, p)
        freq = stats.frequency(win, p)
        digit, gap = max(g.items(), key=lambda kv: (kv[1], -kv[0]))
        if longest is None or gap > longest.count:
            longest = DigitNote(
                position=p, digit=digit, count=gap, low=low, high=high,
                within=low <= freq[digit] <= high,
            )

    gchi, gp = stats.chi_square(stats.group_frequency(win))

    return ReportData(
        target_round=target_round,
        target_date=target_date,
        total_rounds=len(draws),
        first_round=draws[0].round,
        last_round=draws[-1].round,
        last_draw_date=draws[-1].draw_date,
        window_size=cfg.analysis.window,
        window_rounds=n,
        expected_per_digit=n / 10,
        normal_low=low,
        normal_high=high,
        random_tickets=random_tickets,
        recommendation=recommendation,
        active_rules=active_rules,
        position_stats=position_stats,
        longest_gap=longest,
        group_chi=gchi,
        group_p=gp,
        seed=seed,
        warnings=list(warnings or []),
    )
