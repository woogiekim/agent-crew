# /cost — 세션 비용 요약

`~/.claude/metrics/costs.jsonl`을 읽어 비용을 요약 출력한다.

## 실행

```bash
python3 - <<'PYEOF'
import json, os
from pathlib import Path
from collections import defaultdict
from datetime import datetime, timezone

costs_file = Path.home() / ".claude" / "metrics" / "costs.jsonl"

if not costs_file.exists():
    print("기록된 비용 데이터가 없습니다.")
    print("(cost-tracker 훅이 설치되어 있어야 기록됩니다)")
    exit(0)

rows = []
with open(costs_file) as f:
    for line in f:
        line = line.strip()
        if line:
            try:
                rows.append(json.loads(line))
            except Exception:
                pass

if not rows:
    print("기록된 비용 데이터가 없습니다.")
    exit(0)

# 전체 합계
total_cost  = sum(r.get("estimated_cost_usd", 0) for r in rows)
total_in    = sum(r.get("input_tokens",  0) for r in rows)
total_out   = sum(r.get("output_tokens", 0) for r in rows)

# 모델별 집계
by_model = defaultdict(lambda: {"cost": 0.0, "input": 0, "output": 0, "count": 0})
for r in rows:
    m = r.get("model", "unknown")
    by_model[m]["cost"]   += r.get("estimated_cost_usd", 0)
    by_model[m]["input"]  += r.get("input_tokens",  0)
    by_model[m]["output"] += r.get("output_tokens", 0)
    by_model[m]["count"]  += 1

# 최근 7일
now = datetime.now(timezone.utc)
recent = [r for r in rows if (now - datetime.fromisoformat(r["timestamp"])).days < 7]
recent_cost = sum(r.get("estimated_cost_usd", 0) for r in recent)

print("=" * 48)
print("  agent-crew 비용 요약")
print("=" * 48)
print(f"  전체 누적:    ${total_cost:.4f}  ({len(rows)} 세션)")
print(f"  최근 7일:     ${recent_cost:.4f}  ({len(recent)} 세션)")
print(f"  총 토큰:      in {total_in:,}  /  out {total_out:,}")
print()
print("  모델별 분포:")
for model, d in sorted(by_model.items(), key=lambda x: -x[1]["cost"]):
    label = model.split("/")[-1][:28]
    print(f"    {label:<28}  ${d['cost']:.4f}  ({d['count']} 세션)")
print("=" * 48)
PYEOF
```

## 상세 옵션 (선택)

사용자가 `--today`, `--week`, `--model <name>` 등 필터를 요청하면 위 스크립트를 적절히 수정해서 실행한다.
