# 보안 패치 로그 — STEP 6
> 날짜: 2026-05-06
> 커밋: bebec5c

## 수정 파일 목록
| 파일 | 변경 내용 | 상태 |
|------|---------|------|
| `board/views/worktasks.py` | audit 임포트 추가 + `worktask_att_download` 3개 분기(404/403/성공) + 파일 오류 분기에 `log_action` 삽입 | ✅ 완료 |
| `web_ma/settings.py` | `FORCE_PASSWORD_CHANGE_ENABLED` 위 운영 배포 주의 주석 추가 + SCOPE_* 빈값 동작 주석 추가 | ✅ 완료 |
| `docs/harness/DEPLOY_CHECKLIST.md` | 배포 전 체크리스트에 FORCE_PASSWORD_CHANGE 확인 항목 2건 추가 | ✅ 완료 |

---

## S-E-02 worktask_att_download audit log

### 추가된 log_action 호출 위치 (worktasks.py 패치 후 기준)

| 분기 | 위치 | action | success | reason |
|------|------|--------|---------|--------|
| DB에 없는 att (404) | `WorkTaskAttachment.DoesNotExist` except 블록 | `TASK_ATTACHMENT_DOWNLOAD` | False (meta) | not_found |
| 소유자 불일치 (403) | `att.task.owner_id != request.user.pk` 분기 직후 | `TASK_ATTACHMENT_DOWNLOAD` | False (meta) | permission_denied |
| 파일 열기 실패 (500) | `att.file.open("rb")` except 블록 내 | `TASK_ATTACHMENT_DOWNLOAD` | False (meta) | file_open_failed |
| 정상 다운로드 | `FileResponse` 반환 직전 | `TASK_ATTACHMENT_DOWNLOAD` | True (meta) | — |

모든 `log_action` 호출은 `try/except Exception`으로 감싸져 로그 실패가 다운로드 응답을 차단하지 않도록 처리.

### ACTION 상수 신규 추가 여부
- `TASK_ATTACHMENT_DOWNLOAD = "board.task_attachment.download"` — `audit/constants.py` line 30에 **이미 존재** → 추가 불필요

### get_object_or_404 → objects.get 변경 사유
404 케이스에서 `get_object_or_404`는 Http404를 즉시 raise하므로 audit log 삽입이 불가.
`WorkTaskAttachment.objects.get()` + `except DoesNotExist`로 교체하여 log_action 기록 후 수동 raise Http404 처리.
소유자 격리 로직(`att.task.owner_id != request.user.pk`) 및 FileResponse 반환 로직은 변경 없음.

---

## S-F-04 FORCE_PASSWORD_CHANGE 설정 검토

### should_enforce() SCOPE_* 비었을 때 동작
`accounts/policies/password_policy.py`의 `_decide_with_settings()` 확인 결과:
```python
# allow 리스트가 전부 비어있으면 "아직 점진 적용 전"으로 보고 allow=False(안전)
if not allow_b and not allow_p and not allow_c:
    return ScopeDecision(allow=False, deny=False)
```
→ 모든 SCOPE_* 설정이 빈 집합이면 `allow=False` → `should_enforce()` `False` 반환 → **강제 적용 없음**.

`FORCE_PASSWORD_CHANGE_ENABLED=True`로 설정하더라도 SCOPE_* 중 하나 이상에 실제 값이 없으면 아무 사용자도 강제 변경 대상이 되지 않는다.

### 추가된 주석 위치 (settings.py)

| 위치 | 주석 내용 |
|------|---------|
| `FORCE_PASSWORD_CHANGE_ENABLED` 직전 | `⚠️ 운영 배포 시 .env.prod에 FORCE_PASSWORD_CHANGE_ENABLED=True 필수` + SCOPE 주의 안내 |
| `FORCE_PASSWORD_CHANGE_SCOPE_CHANNELS` 직후 | `should_enforce()` SCOPE_* 빈값 동작 명시 |

### DEPLOY_CHECKLIST 추가 항목
```
- [ ] `.env.prod`에 `FORCE_PASSWORD_CHANGE_ENABLED=True` 확인 → [S-F-04]
- [ ] `FORCE_PASSWORD_CHANGE_SCOPE_BRANCHES`, `SCOPE_PARTS`, `SCOPE_CHANNELS` 중 하나 이상 설정 확인 → [S-F-04]
```

---

## python manage.py check 결과
```
System check identified no issues (0 silenced).
```

## security_lint.sh 결과
패치 대상 위반(S-E-02/S-E-05) 해소. 잔존 위반 2건은 이번 패치 범위 외:
- **S-B-04**: `CustomUser.objects.filter()` 직접 사용 — 구조적 리팩토링 필요, 별도 작업
- **S-S-05**: `ACCOUNTS_GRADE_UPDATE` 정의만 되고 미사용 — row별 grade 변경 감사 미구현, 별도 작업

## 회귀 점검 결과

| 항목 | 결과 |
|------|------|
| worktask_att_download FileResponse 반환 동작 변경 없는가 | ✅ 이상 없음 — FileResponse 생성/반환 코드 동일 |
| get_user_task() 소유자 격리 유지되는가 | ✅ 이상 없음 — `att.task.owner_id != request.user.pk` 검증 로직 그대로 유지 |
| audit log 실패 시 다운로드가 차단되지 않는가 | ✅ 이상 없음 — 모든 log_action 호출 try/except Exception으로 감싸짐 |
| settings.py 의 실제 동작 설정값 변경 없는가 | ✅ 이상 없음 — 주석 추가만, 설정값(False/빈집합) 변경 없음 |
| DEPLOY_CHECKLIST 에 중복 항목 없는가 | ✅ 이상 없음 — 기존 항목과 겹치지 않는 신규 2건만 추가 |
| 권한 스코프 변경 여부 | ✅ 이상 없음 |
| URL namespace 깨짐 여부 | ✅ 이상 없음 |
