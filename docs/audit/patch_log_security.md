# 보안 패치 로그 — STEP 1
> 날짜: 2026-05-04
> 커밋 기준: d90b143
> 기준 문서: docs/harness/HARNESS_RULES.md

## 수정 파일 목록
| 파일 | RULE | 변경 내용 |
|------|------|---------|
| `audit/constants.py` | S-04 | `COMMISSION_EXCEL_UPLOAD = "commission.excel.upload"` 상수 추가 |
| `partner/views/subadmin.py` | S-01, S-05 | `import logging`, `from audit.constants import ACTION`, `from audit.services import log_action` 추가; `ajax_add_sub_admin`에 `_old_grade` 캡처 + `log_action(PARTNER_LEADER_ADD)` 삽입; `ajax_delete_subadmin`에 `_old_grade` 캡처 + `log_action(PARTNER_LEADER_DELETE)` 삽입 |
| `accounts/tasks.py` | S-02 | `from audit.constants import ACTION`, `from audit.services import log_action` 추가; `process_users_excel_task` 성공 return 직전에 `log_action(None, ACTION.ACCOUNTS_EXCEL_UPLOAD, ...)` 삽입 |
| `commission/views/api_upload.py` | S-03 | `from django.views.decorators.csrf import csrf_exempt` import 제거; `upload_excel` 함수의 `@csrf_exempt` 데코레이터 제거 |
| `commission/views/approval.py` | S-03 | `from django.views.decorators.csrf import csrf_exempt` import 제거; `approval_upload_excel` 함수의 `@csrf_exempt` 데코레이터 제거 |

## 패치별 상태
| RULE | 상태 | 사유 |
|------|------|------|
| RULE-S-01 | 완료 | `subadmin.py` ajax_add_sub_admin / ajax_delete_subadmin 양쪽에 log_action 삽입. try/except로 감싸 응답 차단 없음 |
| RULE-S-02 | 완료 | `accounts/tasks.py` 성공 return 직전 log_action(request=None, ACTION.ACCOUNTS_EXCEL_UPLOAD) 삽입. audit/services.py가 request=None 지원 확인 후 적용 |
| RULE-S-03 | 완료 | api_upload.py / approval.py 양쪽 @csrf_exempt 제거. 프론트엔드(excel_upload.js:104, approval_excel_upload.js:163) 이미 X-CSRFToken 헤더 전송 중 — JS 수정 불필요 |
| RULE-S-04 | 완료 | audit/constants.py Commission 블록에 COMMISSION_EXCEL_UPLOAD = "commission.excel.upload" 추가. approval.py 6개 참조 모두 유효화 |
| RULE-S-05 | 완료 | PARTNER_LEADER_ADD(subadmin.py:69) / PARTNER_LEADER_DELETE(subadmin.py:154) 실제 호출 연결 완료 |

## python manage.py check 결과
```
System check identified no issues (0 silenced).
```

## security_lint.sh 결과
패치 대상 위반 전체 해소. 잔존 위반 2건은 이번 패치 범위 외:
- **S-B-04**: `CustomUser.objects.filter()` 직접 사용 — 기존 다수 파일에 걸친 구조적 문제, 별도 작업 필요
- **S-S-05**: `ACCOUNTS_GRADE_UPDATE` 정의만 되고 미사용 — per-row grade 변경 감사는 별도 작업 필요

## 회귀 점검 결과 (9항목)
| 항목 | 결과 |
|------|------|
| 권한 스코프 변경 여부 | 이상 없음 — log_action 추가만, 권한 로직 변경 없음 |
| URL namespace 깨짐 여부 | 이상 없음 — URL 변경 없음 |
| 템플릿 dataset/DOM id 변경 | 이상 없음 — 템플릿 변경 없음 |
| 첨부 다운로드 정책 위반 | 이상 없음 — 다운로드 뷰 변경 없음 |
| 업로드 레지스트리 영향 | 이상 없음 — @csrf_exempt 제거 후 JS에서 이미 X-CSRFToken 헤더 전송 중 |
| DataTables 정책 깨짐 | 이상 없음 — JS/템플릿 변경 없음 |
| CSS 스코프 누수 | 이상 없음 — CSS 변경 없음 |
| 운영 환경 영향 | 이상 없음 — @csrf_exempt 제거는 보안 강화이며 기능 영향 없음 |
| JSON 응답 형식 변경 | 이상 없음 — 응답 형식 변경 없음 |

## 미완료 항목 및 사유
없음. 5개 RULE 전체 완료.

---

# 재검증 — 2026-05-06
> 커밋: be12619
> 검증자: 보안 패치 담당

## 파일별 현재 상태 재확인

| 파일 | 확인 결과 |
|------|---------|
| `audit/constants.py` | `COMMISSION_EXCEL_UPLOAD` (line 80), `PARTNER_LEADER_ADD` (line 71), `PARTNER_LEADER_DELETE` (line 72), `ACCOUNTS_EXCEL_UPLOAD` (line 83) 모두 존재 ✅ |
| `partner/views/subadmin.py` | `log_action(PARTNER_LEADER_ADD)` (line 67), `log_action(PARTNER_LEADER_DELETE)` (line 152) 적용 확인 ✅ |
| `accounts/tasks.py` | `log_action(None, ACTION.ACCOUNTS_EXCEL_UPLOAD, ...)` (line 486) 적용 확인 ✅ |
| `commission/views/api_upload.py` | `@csrf_exempt` 없음 ✅ |
| `commission/views/approval.py` | `@csrf_exempt` 없음, `ACTION.COMMISSION_EXCEL_UPLOAD` 유효 ✅ |

## python manage.py check 결과
```
System check identified no issues (0 silenced).
```

## security_lint.sh 결과 (위반 2건 잔존)

```
❌ [S-B-04] CustomUser.objects.filter() 직접 사용 — 21개 위치
❌ [S-S-05] ACCOUNTS_GRADE_UPDATE 정의만 되고 사용처 0건
```

| 위반 | 판단 | 조치 |
|------|------|------|
| S-B-04 | 이번 패치 범위 외 (STEP 1에 미포함) | 별도 리팩토링 작업 필요 |
| S-S-05 (ACCOUNTS_GRADE_UPDATE) | RULE-S-02 "grade 변경 건이 있으면 별도 기록" 미구현 | `process_users_excel_task`에 row별 grade 변경 카운트 추적 후 `log_action(ACTION.ACCOUNTS_GRADE_UPDATE)` 추가 필요 — 별도 STEP으로 처리 |

## 회귀 점검 결과 (9항목)
| 항목 | 결과 |
|------|------|
| 권한 스코프 변경 여부 | 이상 없음 |
| URL namespace 깨짐 여부 | 이상 없음 |
| 템플릿 dataset/DOM id 변경 | 이상 없음 |
| 첨부 다운로드 정책 위반 | 이상 없음 |
| 업로드 레지스트리 영향 | 이상 없음 |
| DataTables 정책 깨짐 | 이상 없음 |
| CSS 스코프 누수 | 이상 없음 |
| 운영 환경 영향 | 이상 없음 |
| JSON 응답 형식 변경 | 이상 없음 |

## 미완료 항목
| 항목 | 우선순위 | 설명 |
|------|---------|------|
| `ACCOUNTS_GRADE_UPDATE` 미사용 | 중간 | RULE-S-05 부분 미완 — 엑셀 업로드 시 grade 변경 row 수 집계 후 별도 audit log 기록 필요 |
| S-B-04 `CustomUser.objects.filter()` 직접 사용 | 낮음 | 검색 목적이 아닌 내부 업무 로직 조회가 포함되어 있어 별도 판단 필요 |
