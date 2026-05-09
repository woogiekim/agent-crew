# crew:cost - Session Cost Summary

Read `~/.agent-crew/metrics/costs.jsonl` and summarize recorded session cost.

## Execution

```bash
python3 <<'PY'
import json
from pathlib import Path
from datetime import datetime, timedelta
from collections import defaultdict

path = Path.home() / ".agent-crew" / "metrics" / "costs.jsonl"

if not path.exists():
    print("No recorded cost data was found.")
    print("The cost-tracker hook must be installed before data can be recorded.")
    raise SystemExit(0)

rows = []
for line in path.read_text().splitlines():
    try:
        rows.append(json.loads(line))
    except Exception:
        pass

if not rows:
    print("No recorded cost data was found.")
    raise SystemExit(0)

total_cost = sum(float(r.get("cost_usd", 0)) for r in rows)
total_in = sum(int(r.get("input_tokens", 0)) for r in rows)
total_out = sum(int(r.get("output_tokens", 0)) for r in rows)

by_model = defaultdict(lambda: {"cost": 0.0, "input": 0, "output": 0, "count": 0})
for r in rows:
    model = r.get("model", "unknown")
    by_model[model]["cost"] += float(r.get("cost_usd", 0))
    by_model[model]["input"] += int(r.get("input_tokens", 0))
    by_model[model]["output"] += int(r.get("output_tokens", 0))
    by_model[model]["count"] += 1

cutoff = datetime.now() - timedelta(days=7)
recent = []
for r in rows:
    try:
        ts = datetime.fromisoformat(r.get("timestamp", "").replace("Z", "+00:00")).replace(tzinfo=None)
        if ts >= cutoff:
            recent.append(r)
    except Exception:
        pass

recent_cost = sum(float(r.get("cost_usd", 0)) for r in recent)

print("agent-crew cost summary")
print(f"Total:       ${total_cost:.4f} ({len(rows)} sessions)")
print(f"Last 7 days: ${recent_cost:.4f} ({len(recent)} sessions)")
print(f"Tokens:      input {total_in:,} / output {total_out:,}")
print()
print("By model:")
for model, data in sorted(by_model.items(), key=lambda item: item[1]["cost"], reverse=True):
    label = model[:28]
    print(f"  {label:<28} ${data['cost']:.4f} ({data['count']} sessions)")
PY
```

## Optional Filters

If the user asks for `--today`, `--week`, or `--model <name>`, adapt the script
above to apply the requested filter before printing the summary.
