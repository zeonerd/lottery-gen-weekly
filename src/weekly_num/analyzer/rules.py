"""소거 규칙 R1~R3 (Phase 1).

이 규칙들은 당첨 확률을 높이지 않는다. 높일 수 없다(PRD §0.2).
목적은 **매주 다른 번호를 읽을 수 있는 근거와 함께 고르는 것**이다.
따라서 규칙을 추가·수정할 때의 기준은 "확률이 오르는가"가 아니라
"흥미로운 서사를 만들고 번호를 다양하게 흩어 주는가"이다.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..config import RulesConfig
from ..models import Draw
from . import stats


@dataclass(slots=True)
class RuleOutcome:
    rule: str
    label: str
    removed: set[int]
    detail: str


def recent_exclusion(draws: list[Draw], position: int, n: int) -> RuleOutcome:
    """R1 — 최근 n회차에 나온 숫자를 제외한다."""
    removed = stats.recent_digits(draws, position, n)
    return RuleOutcome(
        rule="recent_exclusion",
        label=f"최근 {n}회차 내 출현 숫자 제외",
        removed=removed,
        detail=", ".join(str(d) for d in sorted(removed)) or "해당 없음",
    )


def hot_exclusion(draws: list[Draw], position: int, top_k: int) -> RuleOutcome:
    """R2 — 출현 빈도 상위 k개를 제외한다."""
    freq = stats.frequency(draws, position)
    ranked = sorted(freq.items(), key=lambda kv: (-kv[1], kv[0]))[:top_k]
    removed = {digit for digit, _ in ranked}
    detail = ", ".join(f"{d}({c}회)" for d, c in ranked) or "해당 없음"
    return RuleOutcome(
        rule="hot_exclusion",
        label=f"출현 빈도 상위 {top_k}개 제외",
        removed=removed,
        detail=detail,
    )


def cold_weights(
    draws: list[Draw], position: int, candidates: list[int], weight: float
) -> list[float]:
    """R3 — 오래 잠든 숫자에 가산점을 준다.

    소거가 아니라 **선택 가중치**다. 최종 선택은 여전히 무작위이며,
    가중치는 그 무작위의 분포만 기울인다. 가장 잠든 숫자가 반드시
    뽑히게 만들면 매주 같은 번호가 나온다.
    """
    if not candidates:
        return []
    g = stats.gaps(draws, position)
    span = max(g[c] for c in candidates) or 1
    return [1.0 + (weight - 1.0) * (g[c] / span) for c in candidates]


def active_rules(cfg: RulesConfig) -> list[str]:
    """활성화된 규칙 이름 목록 (리포트 표시용)."""
    names = []
    if cfg.recent_exclusion.enabled:
        names.append(f"R1 recent_exclusion(n={cfg.recent_exclusion.n})")
    if cfg.hot_exclusion.enabled:
        names.append(f"R2 hot_exclusion(top_k={cfg.hot_exclusion.top_k})")
    if cfg.cold_preference.enabled:
        names.append(f"R3 cold_preference(weight={cfg.cold_preference.weight})")
    names.append("R8 tail_diversity (해제 불가)")
    return names
