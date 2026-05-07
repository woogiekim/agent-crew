#!/bin/bash
# context-guard.sh
# PreToolUse(Agent) 훅: 에이전트 spawn 시 프롬프트에 파일 내용이 인라인으로 포함되면 경고
#
# 감지 대상: 프롬프트가 2000자 이상이면서 마크다운 코드블록이 포함된 경우
# → 파일 내용을 인라인으로 넘기는 패턴일 가능성이 높음

INPUT=$(cat)

python3 - <<'PYEOF'
import sys, json, os

raw = sys.stdin.buffer.read() if hasattr(sys.stdin, 'buffer') else sys.stdin.read()

try:
    data = json.loads(raw)
except Exception:
    sys.stdout.write(raw.decode() if isinstance(raw, bytes) else raw)
    sys.exit(0)

tool_name = data.get("tool_name", "")
tool_input = data.get("tool_input", {})

if tool_name != "Agent":
    sys.stdout.write(raw.decode() if isinstance(raw, bytes) else raw)
    sys.exit(0)

prompt = tool_input.get("prompt", "")
prompt_len = len(prompt)

warnings = []

# 2000자 이상 프롬프트는 경고
if prompt_len > 2000:
    warnings.append(f"[context-guard] Agent 프롬프트가 {prompt_len}자입니다. 파일 내용을 인라인으로 전달하고 있지 않은지 확인하세요.")

# 코드블록 + 긴 내용 패턴 감지
import re
code_blocks = re.findall(r'```[\s\S]{500,}?```', prompt)
if code_blocks:
    warnings.append(f"[context-guard] 프롬프트에 500자 이상 코드블록 {len(code_blocks)}개 감지. 경로(path)만 전달하는 것을 권장합니다.")

if warnings:
    output = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "additionalContext": "\n".join(warnings)
        }
    }
    print(json.dumps(output, ensure_ascii=False))

sys.stdout.write(raw.decode() if isinstance(raw, bytes) else raw)
PYEOF
