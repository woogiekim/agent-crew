# frontend /implement — UI 구현

## 실행 순서

1. `.claude/state/context/design-spec.md` 읽기
2. `.claude/state/handoff.md` 읽기

3. 컴포넌트 단위로 순차 구현
   - 공통 컴포넌트 → 페이지 컴포넌트 → 인터랙션 순서로 진행
   - API 연동 포인트는 인터페이스만 정의, 실제 연동은 backend 완료 후

4. 구현 완료 시 `.claude/state/pipeline.json`의 phase를 verify로 표시

5. git commit: `feat: frontend implement [화면명]`

## 완료 후
자동으로 frontend /verify 단계로 진행한다.
