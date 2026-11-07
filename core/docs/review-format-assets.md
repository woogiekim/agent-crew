# 리뷰 출력 형식의 원본과 업데이트 보존

## 소유 경로

| 자산 | 저장소 원본 | 설치 원본과 사본 |
|---|---|---|
| 리뷰 명령 8개 | `core/user/commands/*.md` | `~/.agent-crew/user/commands/` → `commands/` → Claude `commands/` |
| Codex 진입점 8개 | `adapters/codex/skill/<name>/SKILL.md` | `~/.codex/skills/<name>/SKILL.md` |
| 방법 비교·증거 규칙 | `core/rules/review-method-comparison.md`, `review-evidence-style.md` | `system/rules/` + `user/rules/` → `rules/` → Claude 규칙 사본 |
| 사용자 리뷰 에이전트 | `~/.agent-crew/user/agents/` | Claude Markdown·Codex TOML 사본 |
| 사용자 종합 가이드 | `~/.agent-crew/user/skills/review-synthesis.md` | `skills/`와 호스트별 agent-crew 가이드 사본 |

대상 명령은 `review`, `generic-review`, `post-audit`, `mr-review-rate`,
`mr-review-note`, `review-followup`, `review-synthesis`,
`parity-check`다. 일반 리뷰의 실제 절차는 `review`에서 관리하고 `generic-review`는
그 명령에 위임한다. 특정 호스트의 외부 methodology 파일을 필수 원본으로 삼지 않는다.
사용자 설치의 `review-retrospective`에도 같은 공통 형식을 적용할 수 있지만, 해당 명령의
신규 workflow 원본과 래퍼는 별도 작업 범위로 관리한다.

## 수정과 갱신

- 명령과 Codex 래퍼의 공통 개선은 위 저장소 원본에 반영한다. 사용자 명령이 이미 존재하면
  설치 사본만 고치지 말고 `user/commands`와 원본의 차이를 먼저 확인한다.
- `seed-user-commands.sh`는 기록한 seed와 같은 사본만 갱신하고, 사용자가 편집한 명령은
  보존·보고한다. 사용자의 변경을 덮기 위해 seed manifest 해시를 임의로 고치지 않는다.
- 개인 설치의 리뷰 명령 끝에는 `user-owned-review-format` 주석을 둔다. 이는 기존 seed와
  다른 사용자 편집이므로 현재 seeder가 해당 명령을 사용자 소유로 판단해 보존한다.
  이 주석을 source seed까지 복사하면 양쪽이 같아져 pristine으로 다시 분류될 수 있으므로
  사용자 레이어에만 둔다. 실행 지시·권한을 추가하는 주석은 아니다. 명령 본문의 개선은
  저장소 seed에도 반영하고, 향후 upstream 변경은 수동 병합한다.
- 개인 설치에서 반드시 유지할 규칙은 `~/.agent-crew/user/rules/`에 둔다. discovery와
  system 사본에만 둔 수정은 갱신 시 교체·정리될 수 있다. 사용자 규칙이 같은 경로의
  system 규칙보다 우선하므로 향후 upstream 변경은 원본과 비교해 수동 병합해야 한다.
- 사용자 에이전트·가이드의 원본은 사용자 레이어에 유지한다. 같은 이름의 system
  에이전트로 복제해 소유권 충돌을 만들지 않는다. 새 머신으로 옮기려면 사용자 레이어를
  별도로 가져와야 한다. 저장소만 설치해 사용자 정의 에이전트까지 복원되는 것은 아니다.
- 원격 업데이트가 이 저장소 변경을 포함하려면 별도의 commit·push·통합이 필요하다.
  로컬 검증이나 사본 갱신을 원격 배포로 표현하지 않는다.

## 검증

```bash
python3 -m pytest tests/python/test_review_format_update_retention.py tests/python/test_review_evidence_style_rule.py tests/python/test_review_followup_command_contract.py tests/python/test_codex_command_wrapper_integrity.py -q
```

기존 seeder를 실제 호출해 신규 파일 설치, pristine 갱신, 사용자 편집 보존과 반복 실행을
검증한다. 전체 갱신 검증은 별도 임시 설치 경로를 지정해 `sync-local-install.sh`를
실행하고, 명령·규칙·Codex 래퍼·사용자 에이전트/가이드의 사본 및 drift 검사를 대조한다.
실제 사용자 설치 전체를 임시 검증 대상으로 사용하지 않는다.
