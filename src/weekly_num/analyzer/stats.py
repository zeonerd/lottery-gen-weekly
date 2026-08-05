"""통계 지표 계산. 순수 함수만 둔다.

`z_score`와 `normal_range`는 **리포트 표시 전용**이다. 소거 근거로 쓰지 말 것.
유의하지 않은 편차로 번호를 지우는 것은 노이즈를 신호로 착각하는 일이며
PRD 원칙 1을 위반한다.
"""

from __future__ import annotations

import math
from collections import Counter

from scipy import stats

from ..models import DIGITS, GROUPS, Draw

CHI2_DF_DIGITS = 9  # 10개 숫자 - 1
CHI2_DF_GROUPS = 4  # 5개 조 - 1


def window(draws: list[Draw], size: int) -> list[Draw]:
    """최근 `size` 회차를 반환한다. 0이면 전체."""
    return draws if size <= 0 else draws[-size:]


def frequency(draws: list[Draw], position: int) -> dict[int, int]:
    """자리 `position`(0~5)에서 각 숫자의 출현 횟수."""
    c = Counter(d.digits[position] for d in draws)
    return {digit: c.get(digit, 0) for digit in DIGITS}


def gaps(draws: list[Draw], position: int) -> dict[int, int]:
    """각 숫자가 마지막으로 나온 뒤 경과한 회차 수.

    직전 회차에 나왔으면 1. 창 안에서 한 번도 안 나왔으면 len(draws)+1.
    """
    result = {digit: len(draws) + 1 for digit in DIGITS}
    for offset, draw in enumerate(reversed(draws), start=1):
        digit = draw.digits[position]
        if result[digit] == len(draws) + 1:
            result[digit] = offset
    return result


def recent_digits(draws: list[Draw], position: int, n: int) -> set[int]:
    """최근 n회차에 자리 `position`에서 나온 숫자 집합."""
    return {d.digits[position] for d in draws[-n:]} if n > 0 else set()


def group_frequency(draws: list[Draw]) -> dict[int, int]:
    c = Counter(d.group_no for d in draws)
    return {g: c.get(g, 0) for g in GROUPS}


def chi_square(observed: dict[int, int]) -> tuple[float, float]:
    """균등분포 적합도 검정. (통계량, p-value)를 반환한다."""
    counts = list(observed.values())
    total = sum(counts)
    if total == 0:
        return 0.0, 1.0
    expected = total / len(counts)
    chi = sum((o - expected) ** 2 / expected for o in counts)
    p = float(stats.chi2.sf(chi, len(counts) - 1))
    return chi, p


def normal_range(n: int, p: float = 0.1, sigmas: float = 2.0) -> tuple[float, float]:
    """이항분포 기준 ±`sigmas`σ 정상 변동 범위.

    이 범위를 리포트에 병기하지 않으면 "숫자 7이 최다 출현"이 마치 의미 있는
    신호처럼 읽힌다(PRD §6.1.1, RK12).
    """
    mean = n * p
    sd = math.sqrt(n * p * (1 - p))
    return max(0.0, mean - sigmas * sd), mean + sigmas * sd


def z_score(count: int, n: int, p: float = 0.1) -> float:
    sd = math.sqrt(n * p * (1 - p))
    return 0.0 if sd == 0 else (count - n * p) / sd
