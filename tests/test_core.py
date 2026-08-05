"""추첨기·설정·수집 파서·저장소 테스트."""

from __future__ import annotations

from datetime import date

import pytest
from pydantic import ValidationError

from weekly_num.collector import fetcher
from weekly_num.config import Config, StrategyConfig
from weekly_num.drawer import draw_random, make_rng
from weekly_num.models import Draw, Ticket
from weekly_num.storage.repository import Repository


# --- drawer (F1) ---------------------------------------------------
def test_draw_random_covers_all_groups() -> None:
    tickets = draw_random(make_rng(1))
    assert [t.group_no for t in tickets] == [1, 2, 3, 4, 5]
    assert all(len(t.digits) == 6 for t in tickets)
    assert all(0 <= d <= 9 for t in tickets for d in t.digits)


def test_draw_random_is_reproducible_with_seed() -> None:
    assert [t.number for t in draw_random(make_rng(5))] == [
        t.number for t in draw_random(make_rng(5))
    ]


def test_draw_random_without_seed_uses_system_entropy() -> None:
    import random

    assert isinstance(make_rng(), random.SystemRandom)


def test_drawer_has_no_heavy_imports() -> None:
    """F1-5 — 폴백 경로이므로 네트워크·DB에 의존하면 안 된다."""
    import inspect

    from weekly_num import drawer

    src = inspect.getsource(drawer)
    for forbidden in ("httpx", "sqlite3", "repository", "fetcher"):
        assert forbidden not in src


# --- config --------------------------------------------------------
def test_tail_diversity_cannot_be_disabled() -> None:
    with pytest.raises(ValidationError, match="끌 수 없습니다"):
        StrategyConfig(tail_diversity=False)


def test_default_config_matches_owner_decisions() -> None:
    cfg = Config()
    assert cfg.analysis.window == 100      # 오너 결정
    assert cfg.strategy.tickets == 5
    assert cfg.strategy.mode == "spread"
    assert cfg.locale == "ko"


def test_shipped_config_file_is_valid() -> None:
    from pathlib import Path

    from weekly_num.config import load_config

    path = Path("config/rules.yaml")
    if path.exists():
        cfg = load_config(path)
        assert cfg.strategy.tail_diversity is True


# --- models --------------------------------------------------------
@pytest.mark.parametrize(
    "group, digits",
    [(0, (1, 2, 3, 4, 5, 6)), (6, (1, 2, 3, 4, 5, 6))],
)
def test_draw_rejects_invalid_group(group, digits) -> None:
    with pytest.raises(ValueError, match="조는"):
        Draw(1, date(2020, 5, 7), group, digits)


def test_draw_rejects_wrong_length() -> None:
    with pytest.raises(ValueError, match="6자리"):
        Draw(1, date(2020, 5, 7), 1, (1, 2, 3))


# --- collector parser (F3-4) ---------------------------------------
def _rec(**kw):
    base = {
        "psltEpsd": 326, "psltRflYmd": "20260730",
        "wnBndNo": "2", "wnRnkVl": "502733", "bnsRnkVl": "399616",
    }
    base.update(kw)
    return base


def test_parse_accepts_official_shape() -> None:
    draws, issues = fetcher.parse_records([_rec()])
    assert len(draws) == 1
    assert draws[0].round == 326
    assert draws[0].group_no == 2
    assert draws[0].number == "502733"
    assert draws[0].draw_date == date(2026, 7, 30)
    assert not issues


def test_parse_rejects_bad_number() -> None:
    draws, issues = fetcher.parse_records([_rec(wnRnkVl="50273")])
    assert not draws
    assert any("6자리 형식 위반" in i for i in issues)


def test_parse_rejects_non_thursday() -> None:
    draws, issues = fetcher.parse_records([_rec(psltRflYmd="20260731")])
    assert not draws
    assert any("목요일" in i for i in issues)


def test_parse_rejects_invalid_group() -> None:
    draws, issues = fetcher.parse_records([_rec(wnBndNo="9")])
    assert not draws
    assert any("조는" in i for i in issues)


def test_parse_reports_round_gaps() -> None:
    _, issues = fetcher.parse_records(
        [_rec(psltEpsd=1, psltRflYmd="20200507"),
         _rec(psltEpsd=3, psltRflYmd="20200521")]
    )
    assert any("회차 누락" in i for i in issues)


# --- storage -------------------------------------------------------
def test_repository_roundtrip(tmp_path) -> None:
    db = tmp_path / "t.db"
    draws = [Draw.from_str(1, date(2020, 5, 7), 1, "123456", "654321")]
    with Repository(db) as repo:
        assert repo.upsert_draws(draws) == 1
        assert repo.upsert_draws(draws) == 0  # 중복 저장 안 함
        assert repo.count() == 1
        assert repo.latest_round() == 1
        assert repo.all_draws()[0].number == "123456"


def test_repository_rejects_corrupt_row(tmp_path) -> None:
    """스키마 CHECK 제약이 마지막 방어선이다."""
    import sqlite3

    with Repository(tmp_path / "t.db") as repo:
        with pytest.raises(sqlite3.IntegrityError):
            repo.conn.execute(
                "INSERT INTO draws VALUES (1,'2020-05-07',9,1,2,3,4,5,6,NULL,'now')"
            )


def test_recommendations_roundtrip(tmp_path) -> None:
    with Repository(tmp_path / "t.db") as repo:
        tickets = [Ticket(g, (0, 0, 0, 0, 0, g)) for g in (1, 2)]
        repo.save_recommendations(327, "eliminate", "spread", tickets, "abc")
        rows = repo.recommendations_for(327)
        assert len(rows) == 2
        assert rows[0][1] == "eliminate"


def test_rerunning_replaces_instead_of_accumulating(tmp_path) -> None:
    """재실행해도 한 회차의 추천은 한 세트만 남아야 한다.

    누적되면 백테스트에서 같은 주가 여러 번 계상된다.
    """
    with Repository(tmp_path / "t.db") as repo:
        tickets = [Ticket(g, (0, 0, 0, 0, 0, g)) for g in (1, 2, 3, 4, 5)]
        for _ in range(3):
            repo.save_recommendations(327, "eliminate", "spread", tickets)
        assert len(repo.recommendations_for(327)) == 5

        repo.save_recommendations(327, "random", "spread", tickets)
        assert len(repo.recommendations_for(327)) == 10  # 전략이 다르면 공존
