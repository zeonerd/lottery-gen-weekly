"""수집 → 분석 → 추천 → 리포트를 잇는 조립 계층.

CLI와 알림 계층이 공통으로 쓴다. 여기서만 부수효과(네트워크·DB)를 다루고,
`analyzer`/`strategy`/`drawer`는 순수하게 유지한다.
"""

from __future__ import annotations

import hashlib
import json
from datetime import date, timedelta
from pathlib import Path

from .analyzer import eliminator, rules, stats
from .collector import fetcher
from .config import Config
from .drawer import draw_random, make_rng
from .models import Draw
from .reporter import builder, markdown, terminal
from .storage.repository import Repository
from .strategy import spread

REPORTS_DIR = Path("reports")


def sync(repo: Repository) -> tuple[int, list[str]]:
    """공식 엔드포인트에서 회차를 받아 신규분만 저장한다.

    실패는 치명적이지 않다(PRD F3-3). 경고를 반환하고 호출자가 기존 DB로 진행한다.
    """
    try:
        draws, issues = fetcher.collect()
    except fetcher.CollectorError as exc:
        return 0, [f"데이터 수집 실패 — 기존 DB로 진행합니다: {exc}"]
    saved = repo.upsert_draws(draws)
    return saved, issues


def next_target(draws: list[Draw]) -> tuple[int, date]:
    latest = draws[-1]
    return latest.round + 1, latest.draw_date + timedelta(days=7)


def _rules_hash(cfg: Config) -> str:
    payload = json.dumps(cfg.rules.model_dump(), sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()[:12]


def build_report(
    draws: list[Draw],
    cfg: Config,
    seed: int | None = None,
    warnings: list[str] | None = None,
) -> builder.ReportData:
    """전체 파이프라인을 실행해 리포트 데이터를 만든다."""
    if not draws:
        raise ValueError("분석할 회차 데이터가 없습니다. 먼저 `weekly-num sync`를 실행하세요.")

    rng = make_rng(seed)
    target_round, target_date = next_target(draws)
    win = stats.window(draws, cfg.analysis.window)

    logs = eliminator.build_position_logs(win, cfg)
    recommendation = spread.build_recommendation(win, logs, cfg, rng)
    random_tickets = draw_random(rng)

    return builder.build(
        draws=draws,
        target_round=target_round,
        target_date=target_date,
        random_tickets=random_tickets,
        recommendation=recommendation,
        cfg=cfg,
        active_rules=rules.active_rules(cfg.rules),
        seed=seed,
        warnings=warnings,
    )


def save_report(data: builder.ReportData, directory: Path = REPORTS_DIR) -> Path:
    """마크다운 리포트를 파일로 남긴다. 알림이 실패해도 이건 남는다(PRD F4-4)."""
    directory.mkdir(parents=True, exist_ok=True)
    iso = data.target_date.isocalendar()
    path = directory / f"{iso.year}-W{iso.week:02d}-{data.target_round}회.md"
    text = markdown.render(data)
    path.write_text(text, encoding="utf-8")
    return path


def persist_recommendation(
    repo: Repository, data: builder.ReportData, cfg: Config
) -> None:
    """추천 이력을 저장한다. 이후 당첨 여부 대조(F5)에 쓰인다."""
    h = _rules_hash(cfg)
    repo.save_recommendations(
        data.target_round, "random", cfg.strategy.mode, data.random_tickets, h
    )
    repo.save_recommendations(
        data.target_round, "eliminate", cfg.strategy.mode,
        data.recommendation.tickets, h,
    )


def render_terminal(data: builder.ReportData, verbose: bool = True) -> str:
    return terminal.render(data, verbose=verbose)
