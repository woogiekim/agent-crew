---
name: generic-review
description: Use when the user invokes $generic-review for a read-only code review over a branch, diff, path, module, commit, or range.
---

# generic-review

이 래퍼는 일반 코드 리뷰 렌즈의 호환 진입점이며 다음 공통 명령에 위임한다.

```text
~/.agent-crew/commands/generic-review.md
```

## Execution

1. 위 명령 파일 전체를 읽고 `$generic-review` 뒤의 원문을 리뷰 범위로 전달한다.
2. 실제 대상은 사용자 요청·계약·현재 저장소에서 정한다. 명령의 출처로 대상을 추정하지 않는다.
3. 공통 명령이 참조하는 `~/.agent-crew/rules/review-method-comparison.md`를 읽고,
   방법 선택이 있는 항목에 실제 방법명·이해득실·소제목·빈 줄·대안별 장단점을 적용한다.
4. 독립 검토와 읽기 전용 경계를 유지한다. 실행하지 않은 리뷰·검증은 완료로 보고하지 않는다.
5. 수정·커밋·push·게시·배포는 수행하지 않고 필요한 후속 작업만 제안한다.
