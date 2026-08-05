"""F6 — 분산 배치 전략 (R8).

이 프로젝트에서 수학적 근거를 가진 유일한 전략이다. 당첨 확률은 바꾸지 못하지만
**분산은 실제로 바꾼다**.

5장의 뒤 1자리를 서로 다르게 두면:

    뒷자리가 모두 같을 때 → 7등 적중 9%,  적중 시 5장 동시 (5,000원)
    뒷자리가 모두 다를 때 → 7등 적중 45%, 적중 시 1장   (1,000원)

기대값은 450원으로 동일하고, "매주 뭐라도 회수할 확률"만 9% → 45%로 바뀐다.
7등 확률이 1/10이 아니라 1/11인 것은 등위가 배타적이기 때문이다(PRD §2.2).

뒤 1자리만 서로 다르게 하면 뒤 2자리·3자리도 자동으로 달라지므로,
이 단일 제약으로 6등·5등 커버리지까지 동시에 최대화된다.
"""

from __future__ import annotations

import random

from ..analyzer import rules
from ..config import Config
from ..models import (
    DIGITS,
    GROUPS,
    NUM_POSITIONS,
    Draw,
    PositionLog,
    Recommendation,
    Ticket,
)

TAIL_POSITION = NUM_POSITIONS - 1


#: 자리별 (후보, 가중치). 한 회차에 대해 한 번만 만들고 재사용한다.
PickTable = list[tuple[list[int], list[float] | None]]


def build_pick_table(
    draws: list[Draw], position_logs: list[PositionLog], cfg: Config
) -> PickTable:
    """자리별 후보와 R3 가중치를 미리 계산한다.

    가중치 계산은 잠복 기간 스캔이라 회차 수에 비례한다. 티켓마다 다시
    계산하면 한 번 호출에 30회씩 반복되고, 백테스트에서는 그 비용이
    수만 배로 불어난다. 회차당 한 번만 만든다.
    """
    table: PickTable = []
    for p, log in enumerate(position_logs):
        candidates = list(log.final)
        weights = (
            rules.cold_weights(draws, p, candidates, cfg.rules.cold_preference.weight)
            if cfg.rules.cold_preference.enabled
            else None
        )
        table.append((candidates, weights))
    return table


def _pick(table: PickTable, position: int, rng: random.Random) -> int:
    candidates, weights = table[position]
    if weights:
        return rng.choices(candidates, weights=weights, k=1)[0]
    return rng.choice(candidates)


def assign_tails(
    tail_candidates: list[int], count: int, rng: random.Random
) -> tuple[list[int], str | None]:
    """5장에 서로 다른 뒷자리를 배정한다(R8).

    소거 Guard가 후보 수를 보장하지만, 방어적으로 부족한 경우를 처리한다.
    부족하면 남은 숫자로 채우고 사유를 반환한다 — R8은 소거 규칙보다
    우선하므로, 여기서 중복 뒷자리를 허용하는 일은 없어야 한다.
    """
    note = None
    pool = list(tail_candidates)
    if len(pool) < count:
        filler = [d for d in DIGITS if d not in pool]
        need = count - len(pool)
        pool += rng.sample(filler, k=min(need, len(filler)))
        note = (
            f"6번째 자리: R8 충족을 위해 소거를 해제해 후보를 {len(pool)}개로 보충"
        )
    return rng.sample(pool, k=count), note


MAX_RESAMPLE = 50


def _violations(
    digits: tuple[int, ...], cfg: Config, bounds: tuple[int, int] | None
) -> list[str]:
    """조합 수준 규칙(R5 홀짝, R6 자리합) 위반 사유를 모은다."""
    reasons = []
    if cfg.rules.parity_balance.enabled:
        r = rules.check_parity(
            digits, cfg.rules.parity_balance.min_odd, cfg.rules.parity_balance.max_odd
        )
        if r:
            reasons.append(f"R5 {r}")
    if cfg.rules.sum_range.enabled and bounds:
        r = rules.check_sum(digits, *bounds)
        if r:
            reasons.append(f"R6 {r}")
    return reasons


def _compose(
    table: PickTable,
    cfg: Config,
    rng: random.Random,
    tail: int | None,
    bounds: tuple[int, int] | None,
) -> tuple[tuple[int, ...], str | None]:
    """R5·R6을 만족하는 한 장을 만든다. 실패하면 마지막 시도를 쓰고 사유를 남긴다.

    무한 재시도는 하지 않는다. 소거로 후보가 좁아진 상태에서는 어떤 조합으로도
    제약을 만족하지 못할 수 있는데, 그때 멈추면 리포트 자체가 안 나온다.
    """
    positions = range(NUM_POSITIONS - 1) if tail is not None else range(NUM_POSITIONS)
    digits: tuple[int, ...] = ()
    reasons: list[str] = []
    for _ in range(MAX_RESAMPLE):
        picked = tuple(_pick(table, p, rng) for p in positions)
        digits = picked + (tail,) if tail is not None else picked
        reasons = _violations(digits, cfg, bounds)
        if not reasons:
            return digits, None
    return digits, (
        f"{MAX_RESAMPLE}회 재시도 후에도 조합 제약 미충족 ({', '.join(reasons)}) "
        "— 제약을 완화해 채택했습니다"
    )


def build_recommendation(
    draws: list[Draw],
    position_logs: list[PositionLog],
    cfg: Config,
    rng: random.Random,
    table: PickTable | None = None,
    bounds: tuple[int, int] | None = None,
) -> Recommendation:
    """소거 결과로부터 최종 5장을 구성한다.

    `table`과 `bounds`는 회차당 한 번만 계산하면 되는 값이다. 백테스트처럼
    같은 회차로 여러 번 뽑을 때 밖에서 만들어 넘기면 재계산을 피할 수 있다.
    """
    count = cfg.strategy.tickets
    notes: list[str] = []
    if table is None:
        table = build_pick_table(draws, position_logs, cfg)
    if bounds is None and cfg.rules.sum_range.enabled:
        bounds = rules.sum_bounds(
            draws, cfg.rules.sum_range.low_pct, cfg.rules.sum_range.high_pct
        )

    if cfg.strategy.mode == "concentrate":
        digits, note = _compose(table, cfg, rng, None, bounds)
        if note:
            notes.append(note)
        tickets = [Ticket(g, digits) for g in GROUPS[:count]]
        notes.append("집중(concentrate) 모드: 5장 모두 동일 번호 — 기본값이 아닙니다.")
        return Recommendation(tickets=tickets, position_logs=position_logs, notes=notes)

    tails, note = assign_tails(list(position_logs[TAIL_POSITION].final), count, rng)
    if note:
        notes.append(note)

    tickets: list[Ticket] = []
    for group_no, tail in zip(GROUPS[:count], tails):
        digits, warn = _compose(table, cfg, rng, tail, bounds)
        if warn:
            notes.append(f"{group_no}조: {warn}")
        tickets.append(Ticket(group_no=group_no, digits=digits))

    verify(tickets)
    return Recommendation(tickets=tickets, position_logs=position_logs, notes=notes)


def verify(tickets: list[Ticket]) -> None:
    """분산 제약 최종 검증(PRD F6-5-1, F6-5-2).

    조용히 깨지면 안 되는 불변식이라 예외를 던진다.
    """
    tails = [t.digits[TAIL_POSITION] for t in tickets]
    if len(set(tails)) != len(tails):
        raise AssertionError(f"R8 위반: 뒷자리가 중복됩니다 {tails}")
    numbers = [t.number for t in tickets]
    if len(set(numbers)) != len(numbers):
        raise AssertionError(f"번호 중복: {numbers}")


def tail_hit_probability(ticket_count: int, distinct_tails: bool) -> float:
    """7등 이상 적중 확률. 리포트 표시용.

    7등 = 뒤 1자리 일치 AND 뒤 2자리 불일치 = 9/100 (등위 배타성, PRD §2.2).
    """
    return 0.09 * ticket_count if distinct_tails else 0.09
