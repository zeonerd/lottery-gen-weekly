"""알림 계층·메신저 포매터·발송 가드 테스트.

실제 발송은 하지 않는다. 네트워크 호출은 전부 가짜로 대체한다.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from weekly_num.config import Config
from weekly_num.notifier.file import FileNotifier
from weekly_num.notifier.telegram import TelegramNotifier
from weekly_num.pipeline import build_report, deliver, draw_already_passed
from weekly_num.reporter import messenger
from weekly_num.reporter.disclaimer import assert_present


@pytest.fixture
def data(draws, cfg):
    return build_report(draws, cfg, seed=3)


# --- 발송 가드 (PRD §9) -------------------------------------------
def test_guard_blocks_after_draw_date() -> None:
    target = date(2026, 8, 6)
    assert draw_already_passed(target, date(2026, 8, 5)) is False   # 수요일
    assert draw_already_passed(target, date(2026, 8, 6)) is False   # 추첨 당일
    assert draw_already_passed(target, date(2026, 8, 7)) is True    # 추첨 다음날


def test_deliver_skips_external_channel_when_draw_passed(data, tmp_path, monkeypatch) -> None:
    """맥이 잠들었다 늦게 깨어난 상황에서 지난 회차 추천이 날아가면 안 된다."""
    monkeypatch.chdir(tmp_path)
    cfg = Config()
    cfg.notify.channel = "telegram"
    monkeypatch.setattr(
        "weekly_num.pipeline.draw_already_passed", lambda *a, **k: True
    )
    results = deliver(data, cfg)
    assert results[0].channel == "file" and results[0].ok  # 파일은 항상 남는다
    assert any("발송을 중단" in r.detail for r in results[1:])


def test_deliver_always_writes_file_first(data, tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    cfg = Config()
    cfg.notify.channel = "file"
    results = deliver(data, cfg, force=True)
    assert results[0].ok
    assert (tmp_path / "reports").exists()


# --- 메신저 포매터 (F4-3, F4-4) -----------------------------------
def test_messenger_includes_disclaimer(data) -> None:
    assert_present(messenger.render_html(data))


def test_messenger_summary_also_includes_disclaimer(data) -> None:
    """전문이 잘려 파일로 빠지는 경우에도 고지문은 본문에 남아야 한다."""
    assert_present(messenger.render_html(data, full=False))


def test_messenger_escapes_html(data) -> None:
    data.warnings.append("위험 <script>alert(1)</script> & 기호")
    html = messenger.render_html(data)
    assert "<script>" not in html
    assert "&lt;script&gt;" in html


def test_render_within_limit_respects_telegram_cap(data) -> None:
    body, _ = messenger.render_within_limit(data)
    assert len(body) <= messenger.TELEGRAM_LIMIT


def test_long_report_falls_back_to_summary_plus_file(data, monkeypatch) -> None:
    monkeypatch.setattr(messenger, "TELEGRAM_LIMIT", 1500)
    body, needs_file = messenger.render_within_limit(data)
    assert needs_file is True
    assert len(body) <= 1500


# --- FileNotifier -------------------------------------------------
def test_file_notifier_writes_report(data, tmp_path) -> None:
    n = FileNotifier(tmp_path / "out")
    result = n.send(data)
    assert result.ok
    assert n.path_for(data).exists()
    assert_present(n.path_for(data).read_text(encoding="utf-8"))


# --- TelegramNotifier (네트워크 없이) ------------------------------
def test_telegram_reports_missing_credentials(data) -> None:
    result = TelegramNotifier(token="", chat_id="").send(data)
    assert result.ok is False
    assert ".env" in result.detail


def test_telegram_sends_html_and_attaches_when_long(data, monkeypatch) -> None:
    calls: list[tuple[str, dict]] = []

    def fake_post(self, method, **kwargs):
        calls.append((method, kwargs))
        return {"ok": True, "result": {}}

    monkeypatch.setattr(TelegramNotifier, "_post", fake_post)
    monkeypatch.setattr(messenger, "TELEGRAM_LIMIT", 1500)

    result = TelegramNotifier(token="t", chat_id="1").send(data)
    assert result.ok
    methods = [m for m, _ in calls]
    assert methods == ["sendMessage", "sendDocument"]
    assert calls[0][1]["data"]["parse_mode"] == "HTML"  # MarkdownV2 금지


def test_telegram_reports_api_failure(data, monkeypatch) -> None:
    def boom(self, method, **kwargs):
        raise RuntimeError("chat not found")

    monkeypatch.setattr(TelegramNotifier, "_post", boom)
    result = TelegramNotifier(token="t", chat_id="1").send(data)
    assert result.ok is False
    assert "chat not found" in result.detail
