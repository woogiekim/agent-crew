#!/usr/bin/env bash
# PreToolUse[Agent]: Agent 실행 전 HEAD 스냅샷 저장
mkdir -p /tmp/.agent-crew
git rev-parse HEAD 2>/dev/null > /tmp/.agent-crew/head-before || echo "" > /tmp/.agent-crew/head-before
