"""텔레그램 알림 (PRD F4-4).

SDK를 쓰지 않는다. 필요한 API가 `sendMessage`와 `sendDocument` 둘뿐이고
둘 다 POST 한 번이다. 봇 프레임워크는 폴링·핸들러·비동기 루프를 끌고
오는데 우리는 **수신을 하지 않는다.**
"""

from __future__ import annotations

import os
from pathlib import Path

import httpx

from ..reporter.builder import ReportData
from ..reporter.markdown import render as render_markdown
from ..reporter.messenger import render_within_limit
from .base import DeliveryResult

API = "https://api.telegram.org"
TIMEOUT = 20.0
RETRIES = 3
BACKOFF = 1.5


class TelegramNotifier:
    name = "telegram"

    def __init__(self, token: str | None = None, chat_id: str | None = None) -> None:
        self.token = token or os.environ.get("TELEGRAM_BOT_TOKEN", "")
        self.chat_id = chat_id or os.environ.get("TELEGRAM_CHAT_ID", "")

    @property
    def configured(self) -> bool:
        return bool(self.token and self.chat_id)

    def _post(self, method: str, **kwargs) -> dict:
        url = f"{API}/bot{self.token}/{method}"
        last: Exception | None = None
        for attempt in range(RETRIES):
            if attempt:
                import time

                time.sleep(BACKOFF**attempt)
            try:
                resp = httpx.post(url, timeout=TIMEOUT, **kwargs)
                payload = resp.json()
            except Exception as exc:  # noqa: BLE001 - 네트워크 예외 전반
                last = exc
                continue
            if payload.get("ok"):
                return payload
            # 4xx 계열 논리 오류는 재시도해도 같은 결과다.
            if 400 <= resp.status_code < 500:
                raise RuntimeError(payload.get("description", f"HTTP {resp.status_code}"))
            last = RuntimeError(payload.get("description", "unknown"))
        raise RuntimeError(f"{RETRIES}회 재시도 후 실패: {last}")

    def send(self, data: ReportData) -> DeliveryResult:
        if not self.configured:
            return DeliveryResult(
                self.name, False,
                "TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID 미설정 — .env 를 확인하세요",
            )
        body, needs_file = render_within_limit(data)
        try:
            self._post(
                "sendMessage",
                data={
                    "chat_id": self.chat_id,
                    "text": body,
                    "parse_mode": "HTML",
                    "disable_web_page_preview": "true",
                },
            )
            if needs_file:
                self._send_document(data)
        except RuntimeError as exc:
            return DeliveryResult(self.name, False, str(exc))
        detail = "본문 전송" + (" + 전문 파일 첨부" if needs_file else "")
        return DeliveryResult(self.name, True, detail)

    def _send_document(self, data: ReportData) -> None:
        """본문이 4,096자를 넘으면 전문을 마크다운 파일로 첨부한다."""
        iso = data.target_date.isocalendar()
        filename = f"{iso.year}-W{iso.week:02d}-{data.target_round}회.md"
        content = render_markdown(data).encode("utf-8")
        self._post(
            "sendDocument",
            data={"chat_id": self.chat_id, "caption": "전체 리포트"},
            files={"document": (filename, content, "text/markdown")},
        )

    def verify(self) -> DeliveryResult:
        """읽기 전용 자격증명 점검. 메시지를 보내지 않는다."""
        if not self.configured:
            return DeliveryResult(self.name, False, "토큰/chat_id 미설정")
        try:
            me = self._post_get("getMe")
            chat = self._post_get("getChat", chat_id=self.chat_id)
        except RuntimeError as exc:
            return DeliveryResult(self.name, False, str(exc))
        who = chat.get("first_name") or chat.get("title") or "?"
        return DeliveryResult(
            self.name, True, f"@{me.get('username')} → {who} ({chat.get('type')})"
        )

    def _post_get(self, method: str, **params) -> dict:
        url = f"{API}/bot{self.token}/{method}"
        try:
            payload = httpx.get(url, params=params, timeout=TIMEOUT).json()
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(str(exc)) from exc
        if not payload.get("ok"):
            raise RuntimeError(payload.get("description", "unknown"))
        return payload["result"]


def load_env(path: Path | str = ".env") -> None:
    """`.env`를 환경변수로 읽어 들인다. 없으면 조용히 넘어간다."""
    p = Path(path)
    if not p.exists():
        return
    from dotenv import dotenv_values

    for k, v in dotenv_values(p).items():
        if v is not None and k not in os.environ:
            os.environ[k] = v
