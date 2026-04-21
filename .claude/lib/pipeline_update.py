#!/usr/bin/env python3
"""Pipeline state management for crew-daemon.
Usage:
  python3 pipeline_update.py advance <pipeline_file> <phase_file> <signal_dir>
  python3 pipeline_update.py abort   <pipeline_file>
"""
import sys, json, os

AGENT_INITIAL_PHASE = {
    'planner': 'REQUIREMENTS',
    'designer': 'DESIGN',
    'frontend': 'IMPLEMENTATION',
    'backend': 'DESIGN',
}


def atomic_write(path, data):
    tmp = path + '.tmp'
    with open(tmp, 'w') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    os.replace(tmp, path)


def advance(pipeline_file, phase_file, signal_dir):
    with open(pipeline_file) as f:
        p = json.load(f)

    p['currentIndex'] = p.get('currentIndex', 0) + 1
    agents = p.get('agents', [])

    if p['currentIndex'] >= len(agents):
        p['status'] = 'DONE'
        with open(phase_file, 'w') as f:
            f.write('DONE')
        atomic_write(pipeline_file, p)
        print("PIPELINE_DONE")
    else:
        next_agent = agents[p['currentIndex']]
        initial_phase = AGENT_INITIAL_PHASE.get(next_agent, 'IN_PROGRESS')
        with open(phase_file, 'w') as f:
            f.write(initial_phase)
        os.makedirs(signal_dir, exist_ok=True)
        open(os.path.join(signal_dir, f"{next_agent}.ready"), 'w').close()
        with open(os.path.join(os.path.dirname(pipeline_file), 'active_agent.txt'), 'w') as f:
            f.write(next_agent)
        atomic_write(pipeline_file, p)
        print(f"NEXT_AGENT:{next_agent}")


def abort(pipeline_file):
    with open(pipeline_file) as f:
        p = json.load(f)
    p['status'] = 'FAILED'
    atomic_write(pipeline_file, p)
    print("PIPELINE_FAILED")


if __name__ == '__main__':
    action = sys.argv[1]
    if action == 'advance':
        advance(sys.argv[2], sys.argv[3], sys.argv[4])
    elif action == 'abort':
        abort(sys.argv[2])
    else:
        sys.exit(f"Unknown action: {action}")
