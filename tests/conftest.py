from __future__ import annotations

import random
from datetime import date, timedelta

import pytest

from weekly_num.config import Config
from weekly_num.models import Draw

FIRST_DRAW = date(2020, 5, 7)  # 1회차 (실측)


def make_draws(count: int = 120, seed: int = 42) -> list[Draw]:
    """검증용 합성 회차. 실제 추첨과 같은 균등분포로 만든다."""
    rng = random.Random(seed)
    return [
        Draw(
            round=i,
            draw_date=FIRST_DRAW + timedelta(weeks=i - 1),
            group_no=rng.randint(1, 5),
            digits=tuple(rng.randint(0, 9) for _ in range(6)),
            bonus="".join(str(rng.randint(0, 9)) for _ in range(6)),
        )
        for i in range(1, count + 1)
    ]


@pytest.fixture
def draws() -> list[Draw]:
    return make_draws()


@pytest.fixture
def cfg() -> Config:
    return Config()
