"""백테스트 테스트.

핵심은 두 가지다. 미래 정보가 새어 들어가지 않을 것, 그리고 관측된
적중률이 이론값과 맞을 것.
"""

from __future__ import annotations

import pytest

from weekly_num import backtest as bt
from weekly_num.config import Config
from weekly_num.models import Draw, Ticket
from weekly_num.strategy import spread

from conftest import make_draws


@pytest.fixture(scope="module")
def results():
    cfg = Config()
    cfg.analysis.window = 50
    return bt.run(make_draws(200), cfg, weeks=100, trials=60, seed=7)


def test_all_strategies_are_simulated(results) -> None:
    assert set(results) == set(bt.THEORY)
    assert all(r.trials > 0 for r in results.values())


@pytest.mark.parametrize("name", ["random", "random_spread", "eliminate", "concentrate"])
def test_hit_rate_matches_theory(results, name) -> None:
    """관측 적중률이 이론값의 신뢰구간 안에 들어와야 한다.

    벗어나면 당첨 판정이나 배치 로직에 문제가 있다는 뜻이다.
    """
    r = results[name]
    lo, hi = bt.hit_rate_ci(r, r.weeks)
    assert lo <= bt.THEORY[name] <= hi, (
        f"{name}: 관측 {r.hit_rate:.4f}, 이론 {bt.THEORY[name]:.4f}, 구간 [{lo:.4f}, {hi:.4f}]"
    )


def test_spread_beats_random_on_frequency(results) -> None:
    """R8은 적중 빈도를 올린다 — 산술적 사실이므로 표본에서도 보여야 한다."""
    assert results["random_spread"].hit_rate > results["random"].hit_rate


def test_concentrate_has_lower_frequency_but_higher_variance(results) -> None:
    conc, sprd = results["concentrate"], results["random_spread"]
    assert conc.hit_rate < sprd.hit_rate
    assert conc.sd_weekly_low > 0


def test_elimination_rules_add_no_significant_edge(results) -> None:
    """소거 규칙의 기여는 유의하지 않아야 한다. 유의하게 나오면 그게 이상한 것."""
    p = bt.two_proportion_test(
        results["random_spread"], results["eliminate"], results["eliminate"].weeks
    )
    assert p > 0.05, f"소거 규칙이 유의한 효과를 보였다 (p={p:.4f}) — 표본 잡음이거나 버그다"


def test_roi_is_negative_for_every_strategy(results) -> None:
    """어떤 전략도 돈을 벌지 못한다. 양수가 나오면 판정 로직을 의심할 것."""
    for name, r in results.items():
        assert r.roi_low < 0, f"{name}: 회수율 {r.roi_low:.2%}"


def test_no_lookahead(monkeypatch) -> None:
    """대상 회차 이후의 데이터가 분석에 들어가지 않는지 확인한다."""
    draws = make_draws(120)
    cfg = Config()
    cfg.analysis.window = 30
    seen: list[int] = []

    original = spread.build_pick_table

    def spy(hist, logs, c):
        seen.append(max(d.round for d in hist))
        return original(hist, logs, c)

    monkeypatch.setattr(spread, "build_pick_table", spy)
    bt.run(draws, cfg, weeks=10, trials=1, seed=1)

    # 각 대상 회차 t 에 대해 사용된 최신 이력은 t-1 이어야 한다.
    targets = list(range(len(draws) - 10 + 1, len(draws) + 1))
    assert seen == [t - 1 for t in targets]


def test_render_reports_theory_alongside_observed(results) -> None:
    cfg = Config()
    text = bt.render(results, cfg)
    assert "이론값" in text
    assert "신뢰구간" in text
    assert "유의하지 않" in text or "유의" in text


def test_render_states_non_significance_is_normal(results) -> None:
    """'우위 없음'이 정상 결과임을 리포트가 말해야 한다 (PRD 원칙 3)."""
    text = bt.render(results, Config())
    assert "정상이며 버그가 아닙니다" in text


def test_score_counts_rank_once() -> None:
    """한 장이 여러 등위에 중복 계상되지 않는다 (RK14)."""
    from datetime import date

    actual = Draw.from_str(1, date(2020, 5, 7), 2, "502733")
    r = bt.StrategyResult("t")
    bt._score(r, [Ticket(1, tuple(int(c) for c in "902733"))], actual)
    assert sum(r.ranks.values()) == 1
    assert r.ranks[3] == 1
