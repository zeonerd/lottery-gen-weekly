"""CLI 진입점."""

from __future__ import annotations

from pathlib import Path

import typer

from .config import load_config
from .drawer import draw_random, make_rng
from .models import evaluate_rank, RANK_LABEL
from .notifier.base import DeliveryResult
from .notifier.file import FileNotifier
from .notifier.telegram import TelegramNotifier, load_env
from .pipeline import (
    build_report,
    deliver,
    persist_recommendation,
    render_terminal,
    sync,
)
from .storage.repository import DEFAULT_DB_PATH, Repository

app = typer.Typer(
    add_completion=False,
    help="연금복권720+ 주간 번호 추천 (개인용). 당첨 확률을 높이지 않습니다.",
)

DbOpt = typer.Option(DEFAULT_DB_PATH, "--db", help="SQLite 파일 경로")
SeedOpt = typer.Option(None, "--seed", help="재현용 시드 (테스트 전용)")


@app.command()
def draw(seed: int | None = SeedOpt) -> None:
    """1~5조 무작위 번호를 추첨합니다 (분석 없음, 항상 동작)."""
    typer.echo("[무작위 추첨]")
    for t in draw_random(make_rng(seed)):
        typer.echo(f"{t.group_no}조 - {t.number}")


@app.command("sync")
def sync_cmd(db: Path = DbOpt) -> None:
    """동행복권 공식 엔드포인트에서 회차 데이터를 받아 저장합니다."""
    with Repository(db) as repo:
        saved, issues = sync(repo)
        typer.echo(f"신규 저장: {saved}건 / 보유 총 {repo.count()}회차")
        latest = repo.latest_round()
        if latest:
            typer.echo(f"최신 회차: {latest}회")
        for msg in issues:
            typer.echo(f"  ⚠ {msg}", err=True)


@app.command()
def analyze(
    db: Path = DbOpt,
    seed: int | None = SeedOpt,
    verbose: bool = typer.Option(True, help="소거 과정을 모두 표시"),
) -> None:
    """과거 회차를 분석해 소거 과정과 추천 번호를 보여줍니다."""
    cfg = load_config()
    with Repository(db) as repo:
        draws = repo.all_draws()
    data = build_report(draws, cfg, seed=seed)
    typer.echo(render_terminal(data, verbose=verbose))


@app.command()
def report(
    db: Path = DbOpt,
    seed: int | None = SeedOpt,
    no_sync: bool = typer.Option(False, "--no-sync", help="수집을 건너뜁니다"),
    send: bool = typer.Option(False, "--send", help="설정된 알림 채널로 발송합니다"),
    html: bool = typer.Option(False, "--html", help="HTML 리포트도 함께 저장합니다"),
    force: bool = typer.Option(False, "--force", help="추첨이 지났어도 발송합니다"),
    quiet: bool = typer.Option(False, "--quiet", help="터미널 출력을 생략합니다"),
) -> None:
    """주간 리포트를 생성합니다 (수집 → 분석 → 리포트 → 저장/발송)."""
    cfg = load_config()
    warnings: list[str] = []
    with Repository(db) as repo:
        if not no_sync:
            _, issues = sync(repo)
            warnings.extend(issues)
        draws = repo.all_draws()
        data = build_report(draws, cfg, seed=seed, warnings=warnings)
        if not quiet:
            typer.echo(render_terminal(data))

        if send:
            results = deliver(data, cfg, force=force, repo=repo)
        else:
            results = [FileNotifier().send(data)]
        persist_recommendation(repo, data, cfg)

        if html:
            from .reporter.html import render as render_html

            path = FileNotifier().path_for(data).with_suffix(".html")
            path.write_text(render_html(data), encoding="utf-8")
            results.append(DeliveryResult("html", True, str(path)))

        typer.echo("")
        for r in results:
            mark = "✅" if r.ok else "⚠"
            typer.echo(f"{mark} {r.channel}: {r.detail}", err=not r.ok)


@app.command("notify-test")
def notify_test() -> None:
    """텔레그램 자격증명을 점검합니다 (읽기 전용 — 메시지를 보내지 않습니다)."""
    load_env()
    result = TelegramNotifier().verify()
    mark = "✅" if result.ok else "❌"
    typer.echo(f"{mark} {result.channel}: {result.detail}")
    if not result.ok:
        raise typer.Exit(1)


@app.command()
def backtest(
    db: Path = DbOpt,
    weeks: int = typer.Option(200, help="대상 회차 수"),
    trials: int = typer.Option(100, help="회차당 시행 수 (몬테카를로)"),
    seed: int | None = typer.Option(20260805, "--seed", help="재현용 시드"),
) -> None:
    """전략별 성적을 무작위 기준선과 나란히 비교합니다."""
    from . import backtest as bt

    cfg = load_config()
    with Repository(db) as repo:
        draws = repo.all_draws()
    if len(draws) < cfg.analysis.window + 10:
        typer.echo("회차 데이터가 부족합니다. 먼저 `weekly-num sync`를 실행하세요.", err=True)
        raise typer.Exit(1)
    results = bt.run(draws, cfg, weeks=weeks, trials=trials, seed=seed)
    typer.echo(bt.render(results, cfg))


@app.command()
def check(round_: int = typer.Argument(..., metavar="ROUND"), db: Path = DbOpt) -> None:
    """지정 회차의 추천 번호가 실제로 당첨됐는지 대조합니다."""
    with Repository(db) as repo:
        target = next((d for d in repo.all_draws() if d.round == round_), None)
        if target is None:
            typer.echo(f"{round_}회 추첨 결과가 없습니다.", err=True)
            raise typer.Exit(1)
        recs = repo.recommendations_for(round_)
        if not recs:
            typer.echo(f"{round_}회 대상 추천 이력이 없습니다.")
            raise typer.Exit(0)

        typer.echo(f"[{round_}회 결과] {target.group_no}조 - {target.number}")
        for _id, strategy, ticket in recs:
            rank = evaluate_rank(ticket, target)
            label = RANK_LABEL[rank] if rank else "미당첨"
            typer.echo(f"  {strategy:9s} {ticket} → {label}")


if __name__ == "__main__":
    app()
