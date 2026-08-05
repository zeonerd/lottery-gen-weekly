#!/usr/bin/env bash
# weekly-num 주간 자동 실행 등록 (매주 수요일 20:00)
#
# 이 스크립트는 로그인 계정에 상주 작업을 등록합니다. 무엇이 등록되는지
# 확인하고 실행하십시오. 해제는 uninstall-launchd.sh 입니다.
set -euo pipefail

LABEL="com.weekly-num.report"
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TEMPLATE="$PROJECT_DIR/scripts/$LABEL.plist"
TARGET="$HOME/Library/LaunchAgents/$LABEL.plist"

if [[ ! -x "$PROJECT_DIR/.venv/bin/weekly-num" ]]; then
  echo "❌ $PROJECT_DIR/.venv/bin/weekly-num 이 없습니다. 먼저 설치하세요:" >&2
  echo "   python3 -m venv .venv && .venv/bin/pip install -e ." >&2
  exit 1
fi

if [[ ! -f "$PROJECT_DIR/.env" ]]; then
  echo "⚠ .env 가 없습니다. 텔레그램 발송은 실패하고 파일 저장만 동작합니다." >&2
fi

mkdir -p "$PROJECT_DIR/logs" "$HOME/Library/LaunchAgents"
sed "s|__PROJECT_DIR__|$PROJECT_DIR|g" "$TEMPLATE" > "$TARGET"

# 이미 등록돼 있으면 갱신을 위해 내렸다가 올린다.
launchctl bootout "gui/$UID/$LABEL" 2>/dev/null || true
launchctl bootstrap "gui/$UID" "$TARGET"

echo "✅ 등록 완료: $TARGET"
echo "   실행 시각: 매주 수요일 20:00"
echo
echo "상태 확인 : launchctl print gui/$UID/$LABEL | head -20"
echo "즉시 실행 : launchctl kickstart -k gui/$UID/$LABEL"
echo "해제      : $PROJECT_DIR/scripts/uninstall-launchd.sh"
