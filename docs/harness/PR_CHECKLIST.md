# PR 머지 전 체크리스트

> 매 PR 머지 시 해당 섹션을 점검한다.
> 규칙 원문: [HARNESS_RULES.md](HARNESS_RULES.md) | [security_checklist.md](../audit/security_checklist.md) | [quality_checklist.md](../audit/quality_checklist.md)

---

### 공통 (모든 PR)

- [ ] 권한 스코프가 변경되지 않았는가 (`grade_required` 데코레이터 유지, 새 뷰에 추가) → [RULE-S-01](HARNESS_RULES.md)
- [ ] URL namespace가 깨지지 않았는가 (`{% url 'app:view' %}` 역추적 + `urls.py` 이름 확인)
- [ ] 템플릿 `data-*` 속성이 변경되지 않았는가 (JS가 읽는 `dataset` 키 변경 시 JS도 함께 수정)
- [ ] 감사 로그가 필요한 행위가 누락되지 않았는가 (grade 변경·엑셀 업로드·결재는 필수) → [RULE-S-01](HARNESS_RULES.md) / [RULE-S-02](HARNESS_RULES.md)
- [ ] JSON 응답 형식이 해당 앱 규약과 일치하는가 (`board/commission/dash` → `ok`, `partner` → `status`)

---

### 파일 업로드 포함 PR

- [ ] `save_attachments()` 또는 registry SSOT 경유하는가 (직접 `Attachment.objects.create` 금지) → [S-A-06](../audit/security_checklist.md)
- [ ] `_norm_emp_id()` 사번 정규화 적용하는가 (accounts 업로드 한정) → [RULE-S-02](HARNESS_RULES.md)
- [ ] `bulk_create` / `update_or_create` 사용하는가 (row-by-row `save()` 금지) → [Q-D-01](../audit/quality_checklist.md)
- [ ] `transaction.atomic()` 으로 전체 업로드 로직을 감싸는가 → [Q-D-02](../audit/quality_checklist.md)
- [ ] 완료 분기에 `log_action()` 호출이 있는가 → [RULE-S-02](HARNESS_RULES.md)

---

### JS 변경 포함 PR

- [ ] AJAX URL이 `dataset`에서 읽는가 (JS 내 URL 문자열 하드코딩 금지) → [Q-B-04](../audit/quality_checklist.md)
- [ ] BFCache 가드(`root.dataset.inited === "1"`) 가 있는가 → [Q-B-05](../audit/quality_checklist.md)
- [ ] CSRF는 `common/manage/csrf.js`의 `getCSRFToken()`을 사용하는가 (파일 내 재구현 금지) → [RULE-Q-01](HARNESS_RULES.md)

---

### CSS 변경 포함 PR

- [ ] 모든 CSS 규칙이 앱 스코프 루트 선택자 하위에서만 적용되는가 (`.board-scope`, `#app-root` 등) → [RULE-Q-02](HARNESS_RULES.md)
- [ ] `base.css` / `fixes.css` 수정이 없는가 (앱 전용 규칙은 `static/css/apps/<앱명>.css`에만) → [Q-C-04](../audit/quality_checklist.md)
