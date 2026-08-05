"""F1 — 무작위 번호 추첨.

이 모듈은 **외부 의존성이 전혀 없다.** 네트워크·DB가 모두 죽어도 동작해야
하는 폴백 경로다(PRD F1-5). 여기에 import를 추가할 때는 그 점을 먼저 확인할 것.
"""

from __future__ import annotations

import random

from .models import DIGITS, GROUPS, NUM_POSITIONS, Ticket


def make_rng(seed: int | None = None) -> random.Random:
    """난수 생성기를 만든다.

    시드가 없으면 `SystemRandom`(암호학적으로 안전한 OS 엔트로피)을 쓴다.
    시드를 주면 재현 가능한 `Random`을 쓰는데, 이는 **테스트 전용**이며
    리포트에 시드 사용 사실이 표기된다(PRD F1-3).
    """
    return random.SystemRandom() if seed is None else random.Random(seed)


def draw_random(rng: random.Random | None = None) -> list[Ticket]:
    """1조부터 5조까지 각 1장, 총 5장을 무작위로 추첨한다(PRD F1-1)."""
    r = rng or make_rng()
    return [
        Ticket(group_no=g, digits=tuple(r.choice(DIGITS) for _ in range(NUM_POSITIONS)))
        for g in GROUPS
    ]
