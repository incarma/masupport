# 배포 전/후 체크리스트

> 규칙 원문: [HARNESS_RULES.md](HARNESS_RULES.md) | [security_checklist.md](../audit/security_checklist.md) | [quality_checklist.md](../audit/quality_checklist.md)

---

### 배포 전

- [ ] `python manage.py check` 오류 없음 (시스템 설정·모델 유효성 확인)
- [ ] `python manage.py collectstatic --noinput` 실행 완료 (정적 파일 최신화) → [Q-G-03](../audit/quality_checklist.md)
- [ ] 신규 migration이 있으면 `migrate` 실행 계획 확인 (운영 DB 영향 범위 검토)
- [ ] Celery `beat_schedule` 신규 task가 있으면 `@shared_task(name=)` 값과 일치하는가 → [Q-D-04](../audit/quality_checklist.md)
- [ ] `.env.prod`에 민감 정보(`SECRET_KEY`, DB 비밀번호 등) 하드코딩 없음 확인 → [S-F-01](../audit/security_checklist.md)

---

### 배포 후 검증 (3종 계정 필수)

- [ ] `superuser` 계정: 관리 기능 3개 이상 정상 동작 확인 (grade 변경·업로드·결재 포함)
- [ ] `head` 계정: 자신의 지점/파트 스코프 외 데이터 접근 차단 확인
- [ ] `basic` 계정: 관리자 전용 메뉴·엔드포인트 접근 시 403/redirect 정상 동작 확인
- [ ] 신규 다운로드 기능: 권한 검증 통과 후 `FileResponse` 반환 및 파일명 정상 확인 → [S-A-02](../audit/security_checklist.md)
- [ ] 신규 업로드 기능: 서버 로그에 traceback 없음 확인 (`logs/error.log` 점검)

---

### 이상 발생 시 롤백 기준

- [ ] 500 오류 발생 시 즉시 롤백 (원인 파악 전 운영 서버 복구 우선)
- [ ] 보안 위반 발견 시 즉시 롤백 (`@csrf_exempt` 노출·권한 우회·audit 공백 등) → [RULE-S-03](HARNESS_RULES.md)
