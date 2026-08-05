"""리포트 테스트. 확률 고지문 누락은 반드시 실패해야 한다 (PRD §8.3)."""

from __future__ import annotations

import pytest

from weekly_num.pipeline import build_report
from weekly_num.reporter import html, markdown, terminal
from weekly_num.reporter.disclaimer import DISCLAIMER_MARKERS, assert_present


@pytest.fixture
def data(draws, cfg):
    return build_report(draws, cfg, seed=99)


@pytest.mark.parametrize("render", [markdown.render, terminal.render, html.render])
def test_disclaimer_present(data, render) -> None:
    """모든 렌더러 출력에 고지문이 들어 있어야 한다."""
    assert_present(render(data))


def test_html_is_self_contained(data) -> None:
    """외부 CSS·폰트·스크립트를 참조하지 않아야 오프라인에서 그대로 열린다."""
    text = html.render(data)
    assert "<!doctype html>" in text.lower()
    for external in ("http://", "https://", "<script"):
        assert external not in text


def test_html_escapes_untrusted_text(data) -> None:
    data.warnings.append("<img src=x onerror=alert(1)>")
    text = html.render(data)
    assert "<img src=x" not in text
    assert "&lt;img" in text


@pytest.mark.parametrize("marker", DISCLAIMER_MARKERS)
def test_each_marker_present_in_markdown(data, marker) -> None:
    assert marker in markdown.render(data)


def test_assert_present_detects_missing() -> None:
    with pytest.raises(AssertionError, match="고지문 누락"):
        assert_present("번호만 있고 고지문이 없는 리포트")


def test_markdown_shows_elimination_steps(data) -> None:
    text = markdown.render(data)
    assert "자리별 소거 과정" in text
    assert "최종 후보" in text
    assert "5장 배정" in text  # 뒷자리 R8 표기


def test_markdown_shows_normal_range(data) -> None:
    """최다/최소 출현에는 반드시 정상 변동 범위가 병기된다 (PRD RK12)."""
    text = markdown.render(data)
    assert "정상 변동 범위" in text


def test_seed_is_disclosed(data) -> None:
    """시드 고정 실행은 리포트에 표시된다 (PRD F1-3)."""
    assert "시드 고정" in markdown.render(data)
    assert "시드 고정" in terminal.render(data)


def test_report_is_deterministic_with_seed(draws, cfg) -> None:
    a = build_report(draws, cfg, seed=7)
    b = build_report(draws, cfg, seed=7)
    assert [t.number for t in a.recommendation.tickets] == [
        t.number for t in b.recommendation.tickets
    ]


def test_tail_hit_probability_is_45_percent(data) -> None:
    """5장 분산 배치의 7등 이상 적중 확률 = 5 × 9/100 = 45% (PRD F6-4)."""
    assert data.tail_hit_pct == pytest.approx(45.0)
