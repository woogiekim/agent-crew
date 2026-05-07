#!/usr/bin/env bash
# Stop 훅: 세션 토큰/비용 기록 → ~/.claude/metrics/costs.jsonl

python3 - <<'PYEOF'
import sys, json, os
from datetime import datetime, timezone
from pathlib import Path

raw = sys.stdin.read(1024 * 1024)  # max 1 MB

try:
    data = json.loads(raw)
except Exception:
    sys.stdout.write(raw)
    sys.exit(0)

usage = data.get("usage") or data.get("token_usage") or {}
input_tokens  = int(usage.get("input_tokens")  or usage.get("prompt_tokens")     or 0)
output_tokens = int(usage.get("output_tokens") or usage.get("completion_tokens") or 0)

model      = str(data.get("model") or os.environ.get("CLAUDE_MODEL") or "unknown").lower()
session_id = os.environ.get("CLAUDE_SESSION_ID") or "default"

if input_tokens > 0 or output_tokens > 0:
    # $/1M tokens (보수적 추정치)
    rates = {"haiku": (0.8, 4.0), "sonnet": (3.0, 15.0), "opus": (15.0, 75.0)}
    rate_in, rate_out = next((v for k, v in rates.items() if k in model), (3.0, 15.0))
    cost = (input_tokens / 1_000_000) * rate_in + (output_tokens / 1_000_000) * rate_out

    metrics_dir = Path.home() / ".claude" / "metrics"
    metrics_dir.mkdir(parents=True, exist_ok=True)

    row = {
        "timestamp":          datetime.now(timezone.utc).isoformat(),
        "session_id":         session_id,
        "model":              model,
        "input_tokens":       input_tokens,
        "output_tokens":      output_tokens,
        "estimated_cost_usd": round(cost, 6),
    }
    with open(metrics_dir / "costs.jsonl", "a") as f:
        f.write(json.dumps(row) + "\n")

sys.stdout.write(raw)
PYEOF
