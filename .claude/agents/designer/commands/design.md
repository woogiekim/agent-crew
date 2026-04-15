# designer /design — UI/UX 명세 작성

## 실행 순서

1. `.claude/state/context/prd.md` 읽기
2. `.claude/state/handoff.md` 읽기

3. 아래 항목으로 UI/UX 명세 작성

### 명세 항목
- **화면 목록**: 필요한 모든 화면/페이지 열거
- **레이아웃**: 각 화면의 구성 요소 배치
- **컴포넌트 정의**: 재사용 컴포넌트, props, 상태
- **인터랙션 흐름**: 사용자 동선, 상태 전환
- **API 연동 포인트**: 백엔드와의 인터페이스 정의

4. `.claude/state/context/design-spec.md` 저장

5. `.claude/state/pipeline.json` 갱신 (currentIndex + 1)

6. `.claude/state/handoff.md` 갱신
   - 완성된 화면 목록
   - 컴포넌트 구조 요약
   - frontend에게 전달할 구현 우선순위

7. git commit: `docs: designer design-spec complete`

## 완료 후
자동으로 다음 에이전트의 첫 번째 단계를 실행한다.
