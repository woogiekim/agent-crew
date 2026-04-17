# /status — agent-crew 상태 패널 출력

다음 명령을 실행하여 현재 파이프라인과 데몬 상태를 출력한다:

```bash
crew-status
```

실시간 모니터링이 필요하면 별도 터미널에서:
```bash
crew-status --live        # 2초마다 갱신
crew-status --live 5      # 5초마다 갱신
```
