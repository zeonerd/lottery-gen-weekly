"""소거 파이프라인.

핵심은 Guard다. 규칙을 순서대로 쌓다 보면 후보가 0개가 되거나 특정 숫자로
수렴한다. 후보가 최소치 미만으로 떨어뜨리는 규칙은 **적용하지 않고 건너뛰며,
건너뛴 사실을 로그에 남긴다**(PRD F2-4).

6번째 자리는 R8(분산 배치)이 5개 이상의 후보를 요구하므로 최소치가 다르다.
R8은 R1~R7보다 우선한다(PRD F6-5-3).
"""

from __future__ import annotations

from ..config import Config
from ..models import DIGITS, NUM_POSITIONS, Draw, EliminationStep, PositionLog
from . import rules

TAIL_POSITION = NUM_POSITIONS - 1  # 5 (뒤 1자리)


def required_candidates(position: int, cfg: Config) -> int:
    """해당 자리에 필요한 최소 후보 수."""
    if position == TAIL_POSITION and cfg.strategy.mode == "spread":
        # 5장에 서로 다른 뒷자리를 배정해야 하므로 티켓 수만큼 필요하다.
        return max(cfg.analysis.min_candidates, cfg.strategy.tickets)
    return cfg.analysis.min_candidates


def eliminate_position(draws: list[Draw], position: int, cfg: Config) -> PositionLog:
    """한 자리에 규칙을 순차 적용해 후보를 좁힌다."""
    minimum = required_candidates(position, cfg)
    candidates = set(DIGITS)
    log = PositionLog(position=position, initial=DIGITS)

    outcomes: list[rules.RuleOutcome] = []
    if cfg.rules.recent_exclusion.enabled:
        outcomes.append(
            rules.recent_exclusion(draws, position, cfg.rules.recent_exclusion.n)
        )
    if cfg.rules.hot_exclusion.enabled:
        outcomes.append(
            rules.hot_exclusion(draws, position, cfg.rules.hot_exclusion.top_k)
        )

    for outcome in outcomes:
        surviving = candidates - outcome.removed
        if len(surviving) < minimum:
            reason = f"적용 시 후보 {len(surviving)}개 → 최소 {minimum}개 미만이라 건너뜀"
            if position == TAIL_POSITION and cfg.strategy.mode == "spread":
                reason += " (R8 분산 배치가 우선)"
            log.steps.append(
                EliminationStep(
                    rule=outcome.rule,
                    label=outcome.label,
                    skipped=True,
                    skip_reason=reason,
                )
            )
            continue
        actually_removed = tuple(sorted(candidates & outcome.removed))
        candidates = surviving
        log.steps.append(
            EliminationStep(
                rule=outcome.rule,
                label=outcome.label,
                removed=actually_removed,
                detail=outcome.detail,
            )
        )

    log.final = tuple(sorted(candidates))
    return log


def build_position_logs(draws: list[Draw], cfg: Config) -> list[PositionLog]:
    """6개 자리 전부에 대해 소거를 수행한다."""
    return [eliminate_position(draws, p, cfg) for p in range(NUM_POSITIONS)]
