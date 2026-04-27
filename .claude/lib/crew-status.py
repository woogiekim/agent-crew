#!/usr/bin/env python3
"""crew-status panel renderer — multi-task hierarchy view.
Usage: python3 crew-status.py <agent_crew_dir> <current_project> [--all]
"""
import sys, json, os, re, unicodedata
from datetime import datetime

AGENT_CREW_DIR = sys.argv[1]
CURRENT_PROJECT = sys.argv[2]
SHOW_ALL = '--all' in sys.argv
W = 56

R  = '\033[0m';  B  = '\033[1m';  G  = '\033[0;32m'
Y  = '\033[1;33m'; C  = '\033[0;36m'; RE = '\033[0;31m'; D  = '\033[2m'

PHASE_LABELS = {
    'REQUIREMENTS': '요구사항 수집',
    'DESIGN': '설계',
    'IMPLEMENTATION': '구현',
    'VERIFICATION': '검증',
    'DONE': '완료',
    'FAILED': '실패',
}


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

def row(content):
    print(f'║ {pad(content, W)} ║')

def row_lr(left, right):
    lw = dw(strip_ansi(left))
    rw = dw(strip_ansi(right))
    gap = max(W - lw - rw, 1)
    print(f'║ {left}{" " * gap}{right} ║')

def top():      print('╔' + '═' * (W + 2) + '╗')
def bottom():   print('╚' + '═' * (W + 2) + '╝')
def divider():  print('╠' + '═' * (W + 2) + '╣')
def thin():     print('╟' + '─' * (W + 2) + '╢')

def read_f(path, default='-'):
    try:    return open(path).read().strip() or default
    except: return default

def elapsed(task_dir):
    path = os.path.join(task_dir, 'pipeline.json')
    if not os.path.exists(path):
        return ''
    secs = int(datetime.now().timestamp() - os.path.getmtime(path))
    if secs < 60:
        return f'{secs}s'
    if secs < 3600:
        return f'{secs // 60}m {secs % 60:02d}s'
    return f'{secs // 3600}h {(secs % 3600) // 60:02d}m'

def last_event(task_dir):
    ef = os.path.join(task_dir, 'events.jsonl')
    if not os.path.exists(ef):
        return 0, '-'
    lines = [l.strip() for l in open(ef) if l.strip()]
    if not lines:
        return 0, '-'
    try:
        ev = json.loads(lines[-1]).get('event', '-')
    except:
        ev = '-'
    return len(lines), ev

def shorten_path(path):
    home = os.path.expanduser('~')
    return ('~' + path[len(home):]) if path.startswith(home) else path

def daemon_status(state_dir):
    pid_file = os.path.join(state_dir, 'orchestrator.pid')
    if not os.path.exists(pid_file):
        return f'{RE}● STOPPED{R}', '-'
    pid = open(pid_file).read().strip()
    try:    os.kill(int(pid), 0); return f'{G}● RUNNING{R}', pid
    except: return f'{Y}● STALE  {R}', pid

def parse_pipeline(task_dir):
    path = os.path.join(task_dir, 'pipeline.json')
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

def is_zombie(task_dir, threshold=600):
    ef = os.path.join(task_dir, 'events.jsonl')
    if not os.path.exists(ef):
        return False
    return (datetime.now().timestamp() - os.path.getmtime(ef)) > threshold

def get_tasks(project_state_dir, active_only=True):
    tasks_dir = os.path.join(project_state_dir, 'tasks')
    result = []
    if not os.path.isdir(tasks_dir):
        return result
    for tid in sorted(os.listdir(tasks_dir), reverse=True):
        d = os.path.join(tasks_dir, tid)
        if not os.path.isdir(d):
            continue
        _, status, _, _ = parse_pipeline(d)
        if active_only and status not in ('IN_PROGRESS', 'PENDING'):
            continue
        result.append((tid, d))
    return result

def has_active_tasks(state_dir):
    return bool(get_tasks(state_dir, active_only=True))


# ── 프로젝트 목록 수집 ──────────────────────────────────────────
all_projects = []
try:
    for name in sorted(os.listdir(AGENT_CREW_DIR)):
        if name in ('agents', 'hooks', 'lib'): continue
        d = os.path.join(AGENT_CREW_DIR, name)
        if os.path.isdir(d) and os.path.isdir(os.path.join(d, 'tasks')):
            all_projects.append(name)
except: pass

projects = (all_projects if SHOW_ALL
            else [n for n in all_projects if has_active_tasks(os.path.join(AGENT_CREW_DIR, n))])

if not projects:
    if SHOW_ALL:
        print(f'\n{D}  agent-crew: 프로젝트 없음 (/setup으로 시작하세요){R}\n')
    else:
        print(f'\n{D}  agent-crew: 활성 파이프라인 없음{R}  {D}(전체 보기: crew-status --all){R}\n')
    sys.exit(0)

hint = (f'{D}  전체 {len(all_projects)}개 중 {len(projects)}개 표시  crew-status --all{R}'
        if not SHOW_ALL else f'{D}  전체 {len(projects)}개 표시{R}')

print()
top()
row(f'{B}{C}agent-crew{R}  projects: {len(projects)}')
divider()
row(f'{D}  updated: {datetime.now().strftime("%H:%M:%S")}{R}')

for name in projects:
    state_dir = os.path.join(AGENT_CREW_DIR, name)
    daemon_lbl, daemon_pid = daemon_status(state_dir)
    tasks = get_tasks(state_dir, active_only=not SHOW_ALL)
    prefix = f'{B}{C}▶ ' if name == CURRENT_PROJECT else f'{B}  '

    divider()
    row(f'{prefix}{name}{R}  {daemon_lbl}  {D}pid:{daemon_pid}{R}')

    if not tasks:
        row(f'  {D}(활성 task 없음){R}')
        continue

    for i, (task_id, task_dir) in enumerate(tasks):
        task, pip_status, idx, agents = parse_pipeline(task_dir)
        phase    = read_f(os.path.join(task_dir, 'phase.txt'))
        agent    = read_f(os.path.join(task_dir, 'active_agent.txt'))
        retry    = read_f(os.path.join(task_dir, 'retry_count.txt'), '0')
        branch   = read_f(os.path.join(task_dir, 'branch.txt'))
        worktree = read_f(os.path.join(task_dir, 'worktree_path.txt'))
        prog     = progress_line(agents, idx)
        sc, pc   = status_color(pip_status), phase_color(phase)
        zombie   = is_zombie(task_dir) and pip_status == 'IN_PROGRESS'
        ev_count, ev_last = last_event(task_dir)
        elapsed_str  = elapsed(task_dir)
        phase_label  = PHASE_LABELS.get(phase, phase)

        if i > 0: thin()

        zombie_tag = f'  {Y}⚠ ZOMBIE{R}' if zombie else ''
        retry_tag  = f'  {D}retry:{retry}{R}' if retry != '0' else ''
        left  = f'  {D}task {task_id}{R}{zombie_tag}{retry_tag}'
        right = f'{D}{elapsed_str}{R}' if elapsed_str else ''
        if right:
            row_lr(left, right)
        else:
            row(left)

        row(f'    {B}Task  {R} {trunc(task, W - 10)}')
        row(f'    {B}Status{R} {sc}{pip_status}{R}  {D}{pc}{phase_label}{R}')
        row(f'    {B}Agent {R} {agent}  {D}branch: {trunc(branch, 20)}{R}')
        if ev_count > 0:
            row(f'    {B}Events{R} {D}{ev_count}  last: {ev_last}{R}')
        if worktree != '-':
            row(f'    {B}Path  {R} {D}{trunc(shorten_path(worktree), W - 12)}{R}')
        row(f'    {prog}')

divider()
row(hint)
row(f'{D}  crew-status --live [q:종료 r:갱신]  |  --all{R}')
bottom()
print()
