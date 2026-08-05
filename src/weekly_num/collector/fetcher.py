"""F3 — 동행복권 공식 JSON 엔드포인트 수집기.

HTML을 파싱하지 않는다. Phase 0에서 확인한 대로 공식 사이트가 당첨번호를
AJAX로 싣고 있어, 그 엔드포인트 하나로 전 회차를 받을 수 있다.

레거시 `gameResult.do?method=win720`은 `/errorPage`로 302 리다이렉트된다.
인터넷 예제 상당수가 그 URL을 쓰므로 되돌리지 말 것.
"""

from __future__ import annotations

import time
from datetime import date, datetime

import httpx

from ..models import Draw

LIST_URL = "https://www.dhlottery.co.kr/pt720/selectPstPt720WnList.do"
REFERER = "https://www.dhlottery.co.kr/pt720/result"
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)

HEADERS = {
    "User-Agent": USER_AGENT,
    "Referer": REFERER,
    "X-Requested-With": "XMLHttpRequest",
    "Accept": "application/json",
}

MAX_RETRIES = 3
BACKOFF_BASE = 1.5


class CollectorError(RuntimeError):
    """수집 실패. 호출자는 이를 치명적 오류로 다루지 않는다(PRD F3-3)."""


def fetch_raw(timeout: float = 20.0, retries: int = MAX_RETRIES) -> list[dict]:
    """전 회차 원시 레코드를 가져온다. 요청 1회로 끝난다."""
    last: Exception | None = None
    for attempt in range(retries):
        if attempt:
            time.sleep(BACKOFF_BASE**attempt)
        try:
            resp = httpx.get(LIST_URL, headers=HEADERS, timeout=timeout,
                             follow_redirects=True)
            if resp.status_code == 429 or "errorPage" in str(resp.url):
                # WAF 차단 신호(PRD RK13). 재시도로 악화시키지 않는다.
                raise CollectorError(f"접근이 차단되었습니다 (url={resp.url})")
            resp.raise_for_status()
            payload = resp.json()
        except CollectorError:
            raise
        except Exception as exc:  # noqa: BLE001 - 네트워크 예외 전반
            last = exc
            continue
        result = (payload.get("data") or {}).get("result")
        if not result:
            raise CollectorError(f"응답에 회차 데이터가 없습니다: {str(payload)[:200]}")
        return result
    raise CollectorError(f"{retries}회 재시도 후 실패: {last}")


def parse_records(records: list[dict]) -> tuple[list[Draw], list[str]]:
    """원시 레코드를 검증하며 `Draw`로 변환한다.

    반환값은 (유효 데이터, 거부 사유 목록). 형식이 어긋난 레코드는
    저장하지 않고 사유만 남긴다(PRD F3-4).
    """
    draws: list[Draw] = []
    rejects: list[str] = []
    for rec in records:
        try:
            round_ = int(rec["psltEpsd"])
            drawn = datetime.strptime(str(rec["psltRflYmd"]), "%Y%m%d").date()
            group_no = int(rec["wnBndNo"])
            number = str(rec["wnRnkVl"])
            bonus = str(rec["bnsRnkVl"]) if rec.get("bnsRnkVl") else None
        except (KeyError, ValueError, TypeError) as exc:
            rejects.append(f"필드 파싱 실패 ({exc}): {str(rec)[:120]}")
            continue

        if not (number.isdigit() and len(number) == 6):
            rejects.append(f"{round_}회: 6자리 형식 위반 ({number!r})")
            continue
        if bonus is not None and not (bonus.isdigit() and len(bonus) == 6):
            rejects.append(f"{round_}회: 보너스 형식 위반 ({bonus!r})")
            bonus = None
        if drawn.weekday() != 3:  # 목요일
            rejects.append(f"{round_}회: 추첨일이 목요일이 아님 ({drawn})")
            continue
        try:
            draws.append(Draw.from_str(round_, drawn, group_no, number, bonus))
        except ValueError as exc:
            rejects.append(f"{round_}회: {exc}")

    draws.sort(key=lambda d: d.round)
    rejects.extend(_continuity_warnings(draws))
    return draws, rejects


def _continuity_warnings(draws: list[Draw]) -> list[str]:
    """회차 누락을 경고로 보고한다. 데이터를 버리지는 않는다."""
    warnings = []
    for prev, cur in zip(draws, draws[1:]):
        if cur.round != prev.round + 1:
            warnings.append(f"회차 누락: {prev.round} → {cur.round}")
    return warnings


def collect() -> tuple[list[Draw], list[str]]:
    """수집 + 검증을 한 번에 수행한다."""
    return parse_records(fetch_raw())


def next_round_after(draws: list[Draw]) -> tuple[int, date]:
    """다음 대상 회차 번호와 예상 추첨일(다음 목요일)을 반환한다."""
    from datetime import timedelta

    latest = draws[-1]
    return latest.round + 1, latest.draw_date + timedelta(days=7)
