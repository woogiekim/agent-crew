#!/usr/bin/env python3
"""crew-status panel renderer.
Usage: python3 crew-status.py <agent_crew_dir> <current_project> [--all]
"""
import sys, json, os, re, unicodedata
from datetime import datetime

AGENT_CREW_DIR = sys.argv[1]
CURRENT_PROJECT = sys.argv[2]
SHOW_ALL = '--all' in sys.argv
W = 54

R  = '\033[0m';  B  = '\033[1m';  G  = '\033[0;32m'
Y  = '\033[1;33m'; C  = '\033[0;36m'; RE = '\033[0;31m'; D  = '\033[2m'


def dw(s):
    return sum(2 if unicodedata.east_asian_width(c) in ('W', 'F') else 1 for c in s)

def strip_ansi(s):
    return re.sub(r'\033\[[0-9;]*m', '', s)

def pad(text, width):
    return text + ' ' * max(width - dw(strip_ansi(text)), 0)

def trunc(text, max_w):
    w, result = 0, []
    for ch in text:
        cw = 2 if unicodedata.east_asian_width(ch) in ('W', 'F') else 1
        if w + cw > max_w - 1:
            result.append('…'); break
        result.append(ch); w += cw
    return ''.join(result)

def row(content):     print(f'║ {pad(content, W)} ║')
def top():            print('╔' + '═' * (W + 2) + '╗')
def bottom():         print('╚' + '═' * (W + 2) + '╝')
def divider():        print('╠' + '═' * (W + 2) + '╣')

def read_f(path, default='-'):
    try:    return open(path).read().strip() or default
    except: return default

def daemon_status(state_dir):
    pid_file = os.path.join(state_dir, 'orchestrator.pid')
    if not os.path.exists(pid_file):
        return f'{RE}● STOPPED{R}', '-'
    pid = open(pid_file).read().strip()
    try:    os.kill(int(pid), 0); return f'{G}● RUNNING{R}', pid
    except: return f'{Y}● STALE  {R}', pid

def parse_pipeline(state_dir):
    path = os.path.join(state_dir, 'pipeline.json')
    if not os.path.exists(path):
        return '-', 'PENDING', 0, []
    p = json.load(open(path))
    return p.get('task') or '-', p.get('status', 'PENDING'), p.get('currentIndex', 0), p.get('agents', [])

def progress_line(agents, idx):
    if not agents: return '-'
    parts = []
    for i, a in enumerate(agents):
        if i < idx:    parts.append(f'{D}✓{a}{R}')
        elif i == idx: parts.append(f'{B}▶{a}{R}')
        else:          parts.append(f'{D}○{a}{R}')
    return ' → '.join(parts)

def status_color(s): return {'DONE': G, 'FAILED': RE, 'IN_PROGRESS': C}.get(s, D)
def phase_color(p):  return {'DONE': G, 'IMPLEMENTATION': C, 'VERIFICATION': Y, 'DESIGN': C}.get(p, D)


def is_active(state_dir):
    """Return True if project has an active (IN_PROGRESS) pipeline."""
    path = os.path.join(state_dir, 'pipeline.json')
    try:
        p = json.load(open(path))
        return p.get('status') == 'IN_PROGRESS' and bool(p.get('task', '').strip())
    except:
        return False


all_projects = []
try:
    for name in sorted(os.listdir(AGENT_CREW_DIR)):
        if name in ('agents', 'hooks', 'lib'): continue
        d = os.path.join(AGENT_CREW_DIR, name)
        if os.path.isdir(d) and os.path.exists(os.path.join(d, 'pipeline.json')):
            all_projects.append(name)
except: pass

projects = all_projects if SHOW_ALL else [n for n in all_projects if is_active(os.path.join(AGENT_CREW_DIR, n))]

if not projects:
    if SHOW_ALL:
        print(f'\n{D}  agent-crew: 프로젝트 없음 (/setup으로 시작하세요){R}\n')
    else:
        print(f'\n{D}  agent-crew: 활성 파이프라인 없음{R}  {D}(전체 보기: crew-status --all){R}\n')
    sys.exit(0)

hint = f'{D}  전체 {len(all_projects)}개 중 {len(projects)}개 표시  crew-status --all{R}' if not SHOW_ALL else f'{D}  전체 {len(projects)}개 표시{R}'

print()
top()
row(f'{B}{C}agent-crew{R}  active: {len(projects)}')
divider()
row(f'{D}  updated: {datetime.now().strftime("%H:%M:%S")}{R}')

for name in projects:
    state_dir = os.path.join(AGENT_CREW_DIR, name)
    phase  = read_f(os.path.join(state_dir, 'phase.txt'))
    agent  = read_f(os.path.join(state_dir, 'active_agent.txt'))
    ef = os.path.join(state_dir, 'events.jsonl')
    events_count = sum(1 for _ in open(ef)) if os.path.exists(ef) else 0

    task, pip_status, idx, agents = parse_pipeline(state_dir)
    daemon_lbl, daemon_pid = daemon_status(state_dir)
    prog = progress_line(agents, idx)
    sc, pc = status_color(pip_status), phase_color(phase)
    prefix = f'{B}{C}▶ ' if name == CURRENT_PROJECT else f'{B}  '

    divider()
    row(f'{prefix}{name}{R}')
    row(f'  {B}Task  {R} {trunc(task, W - 8)}')
    row(f'  {B}Status{R} {sc}{pip_status}{R}  {D}phase: {pc}{phase}{R}')
    row(f'  {B}Agent {R} {agent}')
    row(f'  {prog}')
    row(f'  {B}Daemon{R} {daemon_lbl}  pid:{daemon_pid}  events:{events_count}')

divider()
row(hint)
row(f'{D}  crew-status --live  |  crew-status --all{R}')
bottom()
print()
