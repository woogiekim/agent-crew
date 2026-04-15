# TDD 구현 이력

## 사이클 1 — D: 플러그인 설치/배포
- RED: plugin.json 없음, /setup 없음, install.sh URL 오래됨
- GREEN: plugin.json 생성, /setup 명령어 생성, install.sh URL 갱신
- REFACTOR: CLAUDE.md에 플러그인 설치 방법 반영

## 사이클 2 — C: 오케스트레이션
- RED: /start 없음, pipeline.json 없음, 자동 인계 불가
- GREEN: /start 명령어 생성, pipeline.json 초기 파일 생성
- REFACTOR: 모든 라우터 명령어(/requirements, /design, /implement, /verify)를 pipeline.json 기반으로 업데이트

## 사이클 3 — B: 명령어 라우팅 개선
- RED: 명령어가 active_agent.txt만 읽어 pipeline 상태 무시
- GREEN: pipeline.json 우선 읽기, fallback으로 active_agent.txt 사용
- REFACTOR: 완료 후 자동 진행 지시 추가

## 사이클 4 — A: 새 에이전트 구현
- RED: planner/designer/frontend 에이전트 TODO 상태
- GREEN: 3개 에이전트 AGENT.md + commands 파일 생성
- REFACTOR: CLAUDE.md 아키텍처 섹션에 새 에이전트 반영
