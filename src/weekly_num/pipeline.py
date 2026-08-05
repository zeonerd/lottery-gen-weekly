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
from .notifier.base import DeliveryResult
from .notifier.file import FileNotifier
from .notifier.telegram import TelegramNotifier, load_env
from .reporter import builder, terminal
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
        active_rules=rules.active_rules(cfg.rules, cfg.strategy.tickets),
        seed=seed,
        warnings=warnings,
    )


def draw_already_passed(target_date: date, today: date | None = None) -> bool:
    """대상 회차의 추첨이 이미 지났는지 확인한다 (PRD §9).

    launchd의 `StartCalendarInterval`은 지정 시각에 맥이 잠들어 있으면
    건너뛰지 않고 **깨어난 직후** 실행한다. 그대로 두면 목요일 추첨이
    끝난 뒤에 "이번 주 추천"이 날아간다.
    """
    return (today or date.today()) > target_date


def save_report(data: builder.ReportData, directory: Path = REPORTS_DIR) -> Path:
    """마크다운 리포트를 파일로 남긴다. 알림이 실패해도 이건 남는다(PRD F4-4)."""
    notifier = FileNotifier(directory)
    result = notifier.send(data)
    if not result.ok:
        raise OSError(result.detail)
    return notifier.path_for(data)


def deliver(
    data: builder.ReportData,
    cfg: Config,
    force: bool = False,
    repo: Repository | None = None,
) -> list[DeliveryResult]:
    """설정된 채널로 리포트를 전달한다.

    파일 저장은 항상 먼저 수행한다. 외부 채널이 죽어도 리포트는 남아야 한다.

    외부 채널에는 두 개의 가드가 걸린다.

    1. 추첨이 이미 지났으면 보내지 않는다 — 늦게 도착한 추천은 쓸모가 없다.
    2. 같은 회차를 이미 보냈으면 보내지 않는다 — 맥이 꺼져 예약을 놓친 경우를
       대비해 로그인할 때마다 실행하므로(RunAtLoad), 이 가드가 없으면
       로그인할 때마다 같은 메시지가 날아간다.

    둘 다 `force=True` 로 무시할 수 있다.
    """
    results = [FileNotifier().send(data)]
    channel = cfg.notify.channel

    if channel == "file":
        return results

    if draw_already_passed(data.target_date) and not force:
        results.append(
            DeliveryResult(
                channel, False,
                f"{data.target_round}회 추첨({data.target_date})이 이미 지나 발송을 중단했습니다"
                " (--force 로 무시 가능)",
            )
        )
        return results

    if repo is not None and repo.was_delivered(data.target_round, channel) and not force:
        results.append(
            DeliveryResult(
                channel, True,
                f"{data.target_round}회는 이미 발송됨 — 중복 발송을 건너뜁니다",
            )
        )
        return results

    if channel == "telegram":
        load_env()
        result = TelegramNotifier().send(data)
        if result.ok and repo is not None:
            repo.mark_delivered(data.target_round, channel)
        results.append(result)
    return results


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
