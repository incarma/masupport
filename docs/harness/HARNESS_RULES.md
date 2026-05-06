# HARNESS_RULES — 보안 위반 규칙
> 출처: `docs/audit/security_checklist.md` 의 🔴 위반 항목 (5건)
> 생성일: 2026-05-03 | 기준 커밋: 5e7e7f1

---

## RULE-S-01. grade 변경 시 audit 로그 필수 기록

❌ 금지:
```python
# partner/views/subadmin.py:56-57, 130-131
u.grade = "leader"
u.save(update_fields=["grade"])
# log_action() 호출 없이 종료
```

✅ 올바른 방법:
```python
u.grade = "leader"
u.save(update_fields=["grade"])
log_action(request, ACTION.PARTNER_LEADER_ADD, obj=u, meta={"grade": "leader"})
```

📌 근거: grade 변경은 가장 중요한 권한 이벤트다. `audit/constants.py:70-71`에 `PARTNER_LEADER_ADD`, `PARTNER_LEADER_DELETE` 상수가 정의돼 있으나 `partner/views/subadmin.py` 어디서도 호출하지 않아 감사 추적 공백이 발생한다.

🔍 탐지:
```bash
grep -n "grade\s*=\s*" partner/views/subadmin.py
grep -n "log_action" partner/views/subadmin.py
# log_action 호출이 grade 할당 뒤에 없으면 위반
```

---

## RULE-S-02. 계정 Excel 업로드(grade 포함) 완료 시 audit 로그 필수 기록

❌ 금지:
```python
# accounts/tasks.py — process_users_excel_task 완료 분기
# log_action() 호출 없이 반환
return {"ok": True, "updated": count}
```

✅ 올바른 방법:
```python
log_action(request=None, action=ACTION.ACCOUNTS_EXCEL_UPLOAD,
           meta={"updated": count, "file": filename})
# grade 변경 건이 있으면 ACTION.ACCOUNTS_GRADE_UPDATE도 별도 기록
return {"ok": True, "updated": count}
```

📌 근거: `audit/constants.py:81,83`에 `ACCOUNTS_EXCEL_UPLOAD`, `ACCOUNTS_GRADE_UPDATE` 상수가 정의돼 있으나 `accounts/` 내에서 전혀 사용되지 않는다. 계정 일괄 업로드는 grade 변경을 포함하므로 감사 공백이 크다.

🔍 탐지:
```bash
grep -n "ACCOUNTS_EXCEL_UPLOAD\|ACCOUNTS_GRADE_UPDATE" accounts/tasks.py accounts/admin.py
# 결과가 0건이면 위반
grep -n "ACCOUNTS_EXCEL_UPLOAD\|ACCOUNTS_GRADE_UPDATE" audit/constants.py
```

---

## RULE-S-03. commission 엔드포인트에서 @csrf_exempt 사용 금지

❌ 금지:
```python
# commission/views/api_upload.py:13,54
# commission/views/approval.py:14,92
from django.views.decorators.csrf import csrf_exempt

@csrf_exempt
@grade_required("superuser")
def upload_view(request):
    ...
```

✅ 올바른 방법:
```python
# @csrf_exempt 제거 후 프론트엔드에서 토큰 포함
# multipart FormData 업로드:
formData.append("csrfmiddlewaretoken", getCSRFToken());
# 또는 헤더 방식:
headers: { "X-CSRFToken": getCSRFToken() }
```

📌 근거: `@grade_required("superuser")`가 함께 있어 로그인 우회는 불가하지만, CSRF 토큰 없이 cross-origin POST가 가능한 상태다. 파일 업로드(multipart)라도 CSRF 검증을 우회할 이유가 없다.

🔍 탐지:
```bash
grep -rn "csrf_exempt" --include="*.py" commission/
# 결과가 있으면 위반
```

---

## RULE-S-04. 미정의 ACTION 상수를 참조하는 audit 호출 금지

❌ 금지:
```python
# commission/views/approval.py:119,131,142,177,213,226
log_action(request, ACTION.COMMISSION_EXCEL_UPLOAD, ...)
# → AttributeError: type object 'ACTION' has no attribute 'COMMISSION_EXCEL_UPLOAD'
# try/except 내부라 조용히 실패 → 감사 기록 전혀 없음
```

✅ 올바른 방법:
```python
# 방법 1: audit/constants.py에 상수 추가
# COMMISSION_EXCEL_UPLOAD = "commission.excel.upload"

# 방법 2: 기존 상수 재활용
log_action(request, ACTION.COMMISSION_UPLOAD_APPROVAL, ...)
```

📌 근거: `audit/constants.py`에 `COMMISSION_EXCEL_UPLOAD`가 없어 런타임 `AttributeError`가 발생한다. try/except로 감싸져 있어 조용히 실패하므로 결재/효율성 업로드 audit 로그가 전혀 기록되지 않는다.

🔍 탐지:
```bash
grep -n "COMMISSION_EXCEL_UPLOAD" audit/constants.py
# 결과가 0건이면 위반 (상수 미정의)
grep -n "COMMISSION_EXCEL_UPLOAD" commission/views/approval.py
# 참조 위치 확인
```

## S-B-04 제외 판정 (2026-05-06 기준)

아래 파일들은 "사용자 검색" 목적이 아닌 내부 조회로 판정하여 lint 제외 패턴에 등록:

| 파일 | 용도 | 판정 |
|------|------|------|
| `board/views/worktasks.py` | `_get_worktask_branch_options()`: 지점 목록 집계, `_extract_post_data()`: pk→인스턴스 변환 | ✅ 정당 |
| `partner/views/grades.py` | 권한 스코프 내 조직 grade 관리 | ✅ 정당 |
| `partner/views/rate.py`, `ratetable.py` | 요율 관리 대상 조회 | ✅ 정당 |
| `partner/views/structure.py` | 조직도 관리 대상 조회 | ✅ 정당 |
| `commission/upload_handlers/efficiency.py` | 업로드 행 사번 매핑 | ✅ 정당 |
| `commission/upload_utils/_db.py` | bulk 처리 사번 존재 검증 | ✅ 정당 |
| `dash/viewmods/` | 대시보드 집계용 필터 | ✅ 정당 |

재검토 시점: 신규 사용자 검색 기능 추가 시 또는 분기별 audit

---

## RULE-S-05. 정의된 grade 변경 audit 상수는 반드시 실제 호출에 연결

❌ 금지:
```python
# audit/constants.py:70-71,83 — 상수는 정의됨
PARTNER_LEADER_ADD    = "partner.leader.add"
PARTNER_LEADER_DELETE = "partner.leader.delete"
ACCOUNTS_GRADE_UPDATE = "accounts.user.grade.update"

# 그러나 어느 파일에서도 log_action()에 이 상수를 전달하지 않음
```

✅ 올바른 방법:
```python
# partner/views/subadmin.py — ajax_add_sub_admin() 성공 분기
log_action(request, ACTION.PARTNER_LEADER_ADD,
           obj=u, meta={"from": old_grade, "to": "leader"})

# partner/views/subadmin.py — ajax_delete_subadmin() 성공 분기
log_action(request, ACTION.PARTNER_LEADER_DELETE,
           obj=target, meta={"from": "leader", "to": "basic"})
```

📌 근거: 권한 등급 변경은 보안상 가장 민감한 이벤트다. 상수가 정의만 돼 있고 호출이 없으면 감사 시스템이 작동하지 않는 것과 동일하다.

🔍 탐지:
```bash
grep -rn "PARTNER_LEADER_ADD\|PARTNER_LEADER_DELETE\|ACCOUNTS_GRADE_UPDATE" \
  --include="*.py" . | grep -v "audit/constants.py"
# 결과가 0건이면 위반 (상수가 실제로 사용되지 않음)
```
