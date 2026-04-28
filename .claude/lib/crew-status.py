#!/usr/bin/env python3
"""crew-status panel renderer — futuristic SF style.
Usage: python3 crew-status.py <agent_crew_dir> <current_project> [--all]
"""
import sys, json, os, re, unicodedata
from datetime import datetime

AGENT_CREW_DIR  = sys.argv[1]
CURRENT_PROJECT = sys.argv[2]
SHOW_ALL        = '--all' in sys.argv
W  = 56   # inner content width (between outer ║ chars, excl. borders)
# irow line: ║(1) + 3spaces + │(1) + space(1) + IW + space(1) + │(1) + 2spaces + ║(1) = IW+11 = 60 → IW=49
IW = 49

R  = '\033[0m';  B  = '\033[1m';  G  = '\033[0;32m'
Y  = '\033[1;33m'; C  = '\033[0;36m'; RE = '\033[0;31m'; D  = '\033[2m'
M  = '\033[0;35m'

PHASE_LABELS = {
    'REQUIREMENTS': '요구사항 수집',
    'DESIGN':       '설계',
    'IMPLEMENTATION': '구현',
    'VERIFICATION': '검증',
    'DONE':         '완료',
    'FAILED':       '실패',
}

STATUS_ICON = {
    'IN_PROGRESS': f'{C}◉{R}',
    'PENDING':     f'{Y}◌{R}',
    'DONE':        f'{G}◆{R}',
    'FAILED':      f'{RE}◇{R}',
}

AGENT_ICON = {
    'planner':  '⎇',
    'designer': '⌂',
    'frontend': '▸',
    'backend':  '⚡',
    'resolver': '◈',
}

DAEMON_ICON = {
    'RUNNING': f'{G}◉ RUNNING{R}',
    'STOPPED': f'{RE}○ STOPPED{R}',
    'STALE':   f'{Y}◌ STALE  {R}',
}


# ── Unicode helpers ──────────────────────────────────────────────
def dw(s):
    return sum(2 if unicodedata.east_asian_width(c) in ('W', 'F') else 1 for c in s)

def strip_ansi(s):
    return re.sub(r'\033\[[0-9;]*m', '', s)

def vis(s):
    return dw(strip_ansi(s))

def pad(text, width):
    return text + ' ' * max(width - vis(text), 0)

def trunc(text, max_w):
    w, result = 0, []
    for ch in strip_ansi(text):
        cw = 2 if unicodedata.east_asian_width(ch) in ('W', 'F') else 1
        if w + cw > max_w - 1:
            result.append('…'); break
        result.append(ch); w += cw
    return ''.join(result)


# ── Outer box (╭─╮ / │ / ╰─╯) ───────────────────────────────────
def otop():     print('╭' + '─' * (W + 2) + '╮')
def obottom():  print('╰' + '─' * (W + 2) + '╯')
def odivider(): print('├' + '─' * (W + 2) + '┤')
def othin():    print('│' + ' ' * (W + 2) + '│')

def orow(content=''):
    print(f'│ {pad(content, W)} │')

def orow_lr(left, right):
    gap = max(W - vis(left) - vis(right), 1)
    print(f'│ {left}{" " * gap}{right} │')


# ── Inner card (╭─╮ / │ / ╰─╯) ──────────────────────────────────
def itop(label_left='', label_right=''):
    # ╭─ label_left ───── label_right ─╮  (inside outer ║ │ space)
    inner = IW + 2  # chars between ╭ and ╮
    ll = vis(strip_ansi(label_left))
    lr = vis(strip_ansi(label_right))
    # "─ label_left " + filler + " label_right ─"
    used = 2 + ll + 1 + 1 + lr + 2   # ─ + space + ll + space + filler + space + lr + space + ─
    filler = max(inner - used, 2)
    line = f'╭─ {label_left} {"─" * filler} {label_right} ─╮'
    print(f'│   {pad(line, W - 2)} │')

def ibottom():
    line = '╰' + '─' * (IW + 2) + '╯'
    print(f'│   {pad(line, W - 2)} │')

def irow(content=''):
    print(f'│   │ {pad(content, IW)} │  │')

def irow_lr(left, right):
    gap = max(IW - vis(left) - vis(right), 1)
    print(f'│   │ {left}{" " * gap}{right} │  │')

def idivider():
    print(f'│   ├{"─" * (IW + 2)}┤  │')


# ── Data helpers ─────────────────────────────────────────────────
def read_f(path, default='-'):
    try:    return open(path).read().strip() or default
    except: return default

def elapsed(task_dir):
    path = os.path.join(task_dir, 'pipeline.json')
    if not os.path.exists(path):
        return ''
    secs = int(datetime.now().timestamp() - os.path.getmtime(path))
    if secs < 60:   return f'{secs}s'
    if secs < 3600: return f'{secs // 60}m {secs % 60:02d}s'
    return f'{secs // 3600}h {(secs % 3600) // 60:02d}m'

def last_event(task_dir):
    ef = os.path.join(task_dir, 'events.jsonl')
    if not os.path.exists(ef):
        return 0, '-'
    lines = [l.strip() for l in open(ef) if l.strip()]
    if not lines: return 0, '-'
    try:   ev = json.loads(lines[-1]).get('event', '-')
    except: ev = '-'
    return len(lines), ev

def shorten_path(path):
    home = os.path.expanduser('~')
    return ('~' + path[len(home):]) if path.startswith(home) else path

def daemon_status(state_dir):
    pid_file = os.path.join(state_dir, 'orchestrator.pid')
    if not os.path.exists(pid_file):
        return DAEMON_ICON['STOPPED'], '-'
    pid = open(pid_file).read().strip()
    try:    os.kill(int(pid), 0); return DAEMON_ICON['RUNNING'], pid
    except: return DAEMON_ICON['STALE'], pid

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
        icon = AGENT_ICON.get(a, '▸')
        if i < idx:    parts.append(f'{D}✓{a}{R}')
        elif i == idx: parts.append(f'{C}{icon} {a}{R}')
        else:          parts.append(f'{D}○{a}{R}')
    return ' → '.join(parts)

def is_zombie(task_dir, threshold=600):
    ef = os.path.join(task_dir, 'events.jsonl')
    if not os.path.exists(ef): return False
    return (datetime.now().timestamp() - os.path.getmtime(ef)) > threshold

def get_tasks(project_state_dir, active_only=True):
    tasks_dir = os.path.join(project_state_dir, 'tasks')
    result = []
    if not os.path.isdir(tasks_dir): return result
    for tid in sorted(os.listdir(tasks_dir), reverse=True):
        d = os.path.join(tasks_dir, tid)
        if not os.path.isdir(d): continue
        _, status, _, _ = parse_pipeline(d)
        if active_only and status not in ('IN_PROGRESS', 'PENDING'): continue
        result.append((tid, d))
    return result

def has_active_tasks(state_dir):
    return bool(get_tasks(state_dir, active_only=True))


# ── Project collection ────────────────────────────────────────────
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


# ── Render ────────────────────────────────────────────────────────
print()
otop()
orow_lr(f'{B}{C}  agent-crew{R}  {D}projects: {len(projects)}{R}',
        f'{D}{datetime.now().strftime("%H:%M:%S")}  {R}')
odivider()

for name in projects:
    state_dir     = os.path.join(AGENT_CREW_DIR, name)
    daemon_lbl, daemon_pid = daemon_status(state_dir)
    tasks         = get_tasks(state_dir, active_only=not SHOW_ALL)
    is_current    = (name == CURRENT_PROJECT)
    prefix_icon   = f'{C}▸{R}' if is_current else ' '

    orow(f'  {prefix_icon} {B}{name}{R}')
    orow_lr(f'    {daemon_lbl}  {D}pid:{daemon_pid}{R}', '')

    if not tasks:
        orow(f'    {D}(활성 task 없음){R}')
        odivider()
        continue

    orow()
    for i, (task_id, task_dir) in enumerate(tasks):
        task, pip_status, idx, agents = parse_pipeline(task_dir)
        phase    = read_f(os.path.join(task_dir, 'phase.txt'))
        agent    = read_f(os.path.join(task_dir, 'active_agent.txt'))
        retry    = read_f(os.path.join(task_dir, 'retry_count.txt'), '0')
        branch   = read_f(os.path.join(task_dir, 'branch.txt'))
        worktree = read_f(os.path.join(task_dir, 'worktree_path.txt'))
        prog     = progress_line(agents, idx)
        st_icon  = STATUS_ICON.get(pip_status, f'{D}○{R}')
        a_icon   = AGENT_ICON.get(agent, '▸')
        zombie   = is_zombie(task_dir) and pip_status == 'IN_PROGRESS'
        ev_count, ev_last = last_event(task_dir)
        elapsed_str  = elapsed(task_dir)
        phase_label  = PHASE_LABELS.get(phase, phase)

        zombie_tag = f'  {Y}▲ ZOMBIE{R}' if zombie else ''
        retry_tag  = f'  {D}×{retry}{R}' if retry != '0' else ''

        elapsed_lbl = f'{D}{elapsed_str}{R}' if elapsed_str else ''

        # Inner card
        itop(f'{D}task {task_id}{R}{zombie_tag}{retry_tag}', elapsed_lbl)
        irow(f'{st_icon}  {trunc(task, IW - 4)}')
        idivider()
        irow_lr(
            f'{D}status{R}  {st_icon} {B}{pip_status}{R}',
            f'{D}{phase_label}{R}'
        )
        irow(f'{D}agent {R}  {C}{a_icon} {agent}{R}  {D}{trunc(branch, 22)}{R}')
        if ev_count > 0:
            irow(f'{D}events{R}  {ev_count}  {D}last: {ev_last}{R}')
        if worktree != '-':
            irow(f'{D}path  {R}  {D}{trunc(shorten_path(worktree), IW - 10)}{R}')
        irow(f'{D}{trunc(prog, IW)}{R}')
        ibottom()
        orow()

    odivider()

orow(hint)
orow(f'{D}  crew-status --live [q:종료 r:갱신]  |  --all{R}')
obottom()
print()
