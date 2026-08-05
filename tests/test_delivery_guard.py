"""놓친 실행 따라잡기와 중복 발송 방지.

맥이 꺼져 있어 수요일 20:00 을 놓친 경우, 다음에 켤 때 RunAtLoad 로
따라잡는다. 그 대가로 로그인할 때마다 실행되므로 중복 발송을 막아야 한다.
"""

from __future__ import annotations

from datetime import date

import pytest

from weekly_num.config import Config
from weekly_num.notifier.base import DeliveryResult
from weekly_num.pipeline import build_report, deliver
from weekly_num.storage.repository import Repository


@pytest.fixture
def data(draws, cfg):
    return build_report(draws, cfg, seed=5)


@pytest.fixture
def repo(tmp_path):
    with Repository(tmp_path / "t.db") as r:
        yield r


@pytest.fixture
def telegram_cfg():
    cfg = Config()
    cfg.notify.channel = "telegram"
    return cfg


@pytest.fixture
def sent(monkeypatch):
    """텔레그램 발송을 가로채 호출 횟수만 센다."""
    calls: list[int] = []

    def fake_send(self, d):
        calls.append(d.target_round)
        return DeliveryResult("telegram", True, "보냄")

    monkeypatch.setattr(
        "weekly_num.notifier.telegram.TelegramNotifier.send", fake_send
    )
    return calls


def test_delivers_once_then_skips(data, repo, telegram_cfg, sent, tmp_path, monkeypatch):
    """따라잡기 실행이 반복돼도 발송은 한 번뿐이어야 한다."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("weekly_num.pipeline.draw_already_passed", lambda *a, **k: False)

    deliver(data, telegram_cfg, repo=repo)
    assert len(sent) == 1

    for _ in range(3):  # 로그인 3번 더
        results = deliver(data, telegram_cfg, repo=repo)
    assert len(sent) == 1, "중복 발송이 발생했다"
    assert any("이미 발송됨" in r.detail for r in results)


def test_file_is_written_every_time(data, repo, telegram_cfg, sent, tmp_path, monkeypatch):
    """발송을 건너뛰어도 파일은 매번 갱신된다."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("weekly_num.pipeline.draw_already_passed", lambda *a, **k: False)
    deliver(data, telegram_cfg, repo=repo)
    results = deliver(data, telegram_cfg, repo=repo)
    assert results[0].channel == "file" and results[0].ok


def test_force_overrides_duplicate_guard(data, repo, telegram_cfg, sent, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("weekly_num.pipeline.draw_already_passed", lambda *a, **k: False)
    deliver(data, telegram_cfg, repo=repo)
    deliver(data, telegram_cfg, repo=repo, force=True)
    assert len(sent) == 2


def test_draw_passed_guard_wins_over_catchup(data, repo, telegram_cfg, sent, tmp_path, monkeypatch):
    """따라잡기라도 추첨이 끝난 회차는 보내지 않는다."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("weekly_num.pipeline.draw_already_passed", lambda *a, **k: True)
    results = deliver(data, telegram_cfg, repo=repo)
    assert not sent
    assert any("이미 지나" in r.detail for r in results)


def test_failed_send_is_not_marked_delivered(data, repo, telegram_cfg, tmp_path, monkeypatch):
    """발송이 실패하면 기록하지 않는다. 다음 실행에서 다시 시도해야 한다."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("weekly_num.pipeline.draw_already_passed", lambda *a, **k: False)
    monkeypatch.setattr(
        "weekly_num.notifier.telegram.TelegramNotifier.send",
        lambda self, d: DeliveryResult("telegram", False, "네트워크 오류"),
    )
    deliver(data, telegram_cfg, repo=repo)
    assert repo.was_delivered(data.target_round, "telegram") is False


def test_different_rounds_are_tracked_separately(repo) -> None:
    repo.mark_delivered(327, "telegram")
    assert repo.was_delivered(327, "telegram") is True
    assert repo.was_delivered(328, "telegram") is False
    assert repo.was_delivered(327, "discord") is False


def test_file_channel_needs_no_guard(data, repo, tmp_path, monkeypatch) -> None:
    """파일 저장은 멱등이므로 가드 없이 매번 수행한다."""
    monkeypatch.chdir(tmp_path)
    cfg = Config()
    cfg.notify.channel = "file"
    results = deliver(data, cfg, repo=repo)
    assert len(results) == 1 and results[0].ok
