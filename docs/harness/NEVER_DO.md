# NEVER_DO — 절대 하지 말 것 (위험도 높음 항목)
> 출처: security_checklist.md 🔴 위반 중 위험도 "높음" 4건
> 생성일: 2026-05-03 | 기준 커밋: 5e7e7f1

---

[ ] `partner/views/subadmin.py` 에서 `u.grade = "leader"` / `target.grade = "basic"` 저장 후 `log_action()` 미호출 금지 → `log_action(request, ACTION.PARTNER_LEADER_ADD/DELETE, obj=u)` 필수 (S-B-05)

[ ] `accounts/tasks.py` 의 `process_users_excel_task()` 완료 분기에서 `log_action()` 미호출 금지 → `log_action(None, ACTION.ACCOUNTS_EXCEL_UPLOAD, meta={...})` 추가 (S-B-06)

[ ] `commission/views/api_upload.py`, `commission/views/approval.py` 에서 `@csrf_exempt` 사용 금지 → 프론트엔드 JS에서 `X-CSRFToken` 헤더 또는 FormData `csrfmiddlewaretoken` 필드 포함으로 대체 (S-D-01)

[ ] `audit/constants.py` 에 미정의된 `ACTION.XXX` 상수를 `log_action()` 인자로 전달 금지 → 상수를 먼저 `audit/constants.py` 에 추가하거나 기존 상수 재활용 (S-E-01 / S-E-04)
