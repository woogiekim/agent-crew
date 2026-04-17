#!/usr/bin/env bash
# crew-status — agent-crew 전체 상태 패널 출력
# Usage:
#   crew-status              — 모든 프로젝트 상태 1회 출력
#   crew-status --live       — 2초마다 실시간 갱신 (Ctrl+C 종료)
#   crew-status --live 5     — 5초마다 실시간 갱신

if [[ "${1:-}" == "--live" ]]; then
  INTERVAL="${2:-2}"
  while true; do
    clear
    bash "$0"
    sleep "$INTERVAL"
  done
  exit 0
fi

AGENT_CREW_DIR="${HOME}/.claude/agent-crew"
CURRENT_PROJECT=$(basename "$(git rev-parse --show-toplevel 2>/dev/null || pwd)")

python3 - "$AGENT_CREW_DIR" "$CURRENT_PROJECT" <<'PYEOF'
import sys, json, os, subprocess, unicodedata
from datetime import datetime

AGENT_CREW_DIR = sys.argv[1]
CURRENT_PROJECT = sys.argv[2]
W = 54  # 내부 너비 (테두리 제외)

# ── ANSI ────────────────────────────────────────────────────────
R  = '\033[0m'
B  = '\033[1m'
G  = '\033[0;32m'
Y  = '\033[1;33m'
C  = '\033[0;36m'
RE = '\033[0;31m'
D  = '\033[2m'

def dw(s):
    """터미널 표시 너비 계산 (한글 등 CJK = 2칸)"""
    w = 0
    for ch in s:
        ea = unicodedata.east_asian_width(ch)
        w += 2 if ea in ('W', 'F') else 1
    return w

def strip_ansi(s):
    import re
    return re.sub(r'\033\[[0-9;]*m', '', s)

def pad(text, width):
    """ANSI 코드를 제거한 표시 너비 기준으로 오른쪽을 공백으로 채움"""
    fill = width - dw(strip_ansi(text))
    return text + ' ' * max(fill, 0)

def trunc(text, max_w):
    """표시 너비 기준으로 자르고 … 추가"""
    w = 0
    result = []
    for ch in text:
        cw = 2 if unicodedata.east_asian_width(ch) in ('W', 'F') else 1
        if w + cw > max_w - 1:
            result.append('…')
            break
        result.append(ch)
        w += cw
    return ''.join(result)

def row(content):
    print(f'║ {pad(content, W)} ║')

def top():
    print('╔' + '═' * (W + 2) + '╗')

def bottom():
    print('╚' + '═' * (W + 2) + '╝')

def divider():
    print('╠' + '═' * (W + 2) + '╣')

def read_f(path, default='-'):
    try:
        return open(path).read().strip() or default
    except:
        return default

def daemon_status(state_dir):
    pid_file = os.path.join(state_dir, 'orchestrator.pid')
    if not os.path.exists(pid_file):
        return f'{RE}● STOPPED{R}', '-'
    pid = open(pid_file).read().strip()
    try:
        os.kill(int(pid), 0)
        return f'{G}● RUNNING{R}', pid
    except:
        return f'{Y}● STALE  {R}', pid

def parse_pipeline(state_dir):
    path = os.path.join(state_dir, 'pipeline.json')
    if not os.path.exists(path):
        return '-', 'PENDING', 0, []
    p = json.load(open(path))
    task = p.get('task', '') or '-'
    status = p.get('status', 'PENDING')
    idx = p.get('currentIndex', 0)
    agents = p.get('agents', [])
    return task, status, idx, agents

def progress_line(agents, idx):
    if not agents:
        return '-'
    parts = []
    for i, a in enumerate(agents):
        if i < idx:   parts.append(f'{D}✓{a}{R}')
        elif i == idx: parts.append(f'{B}▶{a}{R}')
        else:          parts.append(f'{D}○{a}{R}')
    return ' → '.join(parts)

def status_color(s):
    return {
        'DONE': G, 'FAILED': RE, 'IN_PROGRESS': C
    }.get(s, D)

def phase_color(p):
    return {
        'DONE': G, 'IMPLEMENTATION': C, 'VERIFICATION': Y, 'DESIGN': C
    }.get(p, D)

# ── 프로젝트 수집 ────────────────────────────────────────────────
projects = []
try:
    for name in sorted(os.listdir(AGENT_CREW_DIR)):
        if name in ('agents', 'hooks'):
            continue
        d = os.path.join(AGENT_CREW_DIR, name)
        if os.path.isdir(d) and os.path.exists(os.path.join(d, 'pipeline.json')):
            projects.append(name)
except:
    pass

if not projects:
    print(f'\n{D}  agent-crew: 활성 프로젝트 없음 (/setup으로 시작하세요){R}\n')
    sys.exit(0)

# ── 렌더 ────────────────────────────────────────────────────────
print()
top()
row(f'{B}{C}agent-crew{R}  projects: {len(projects)}')
divider()
row(f'{D}  updated: {datetime.now().strftime("%H:%M:%S")}{R}')

for name in projects:
    state_dir = os.path.join(AGENT_CREW_DIR, name)
    phase        = read_f(os.path.join(state_dir, 'phase.txt'))
    agent        = read_f(os.path.join(state_dir, 'active_agent.txt'))
    iterations   = read_f(os.path.join(state_dir, 'iterations.txt'), '0')
    events_count = 0
    ef = os.path.join(state_dir, 'events.jsonl')
    if os.path.exists(ef):
        with open(ef) as f:
            events_count = sum(1 for _ in f)

    task, pip_status, idx, agents = parse_pipeline(state_dir)
    daemon_lbl, daemon_pid = daemon_status(state_dir)
    prog = progress_line(agents, idx)

    sc = status_color(pip_status)
    pc = phase_color(phase)

    is_current = (name == CURRENT_PROJECT)
    prefix = f'{B}{C}▶ ' if is_current else f'{B}  '
    name_label = f'{prefix}{name}{R}'

    divider()
    row(name_label)
    row(f'  {B}Task  {R} {trunc(task, W - 8)}')
    row(f'  {B}Status{R} {sc}{pip_status}{R}  {D}phase: {pc}{phase}{R}')
    row(f'  {B}Agent {R} {agent}')
    row(f'  {prog}')
    row(f'  {B}Daemon{R} {daemon_lbl}  pid:{daemon_pid}  events:{events_count}')

divider()
row(f'{D}  crew-status --live{R}')
bottom()
print()
PYEOF
