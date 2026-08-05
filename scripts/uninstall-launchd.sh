#!/usr/bin/env bash
# weekly-num 주간 자동 실행 해제
set -euo pipefail

LABEL="com.weekly-num.report"
TARGET="$HOME/Library/LaunchAgents/$LABEL.plist"

launchctl bootout "gui/$UID/$LABEL" 2>/dev/null || true
rm -f "$TARGET"
echo "✅ 해제 완료 ($LABEL)"
