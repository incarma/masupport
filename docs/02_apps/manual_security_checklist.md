# manual 보안 점검 체크리스트 (django_ma)

## 1. 즉시 조치급 (High Risk)

- [ ] Quill HTML 저장/출력 XSS 방어 적용
  - content sanitize (allowlist)
  - script/iframe/on* 이벤트/javascript: 차단

- [ ] 첨부파일 직접 URL 노출 제거
  - .file.url 사용 금지
  - 다운로드 view + 권한검증 + FileResponse

- [ ] 이미지 URL 노출 정책 재검토
  - b.image.url 직접 노출 최소화
  - 필요 시 서명 URL 또는 view 경유

- [ ] /media 직접 서빙 정책 제거
  - 객체 단위 권한 검증 필수

- [ ] AJAX 쓰기 API 객체 소속 검증
  - block_id / section_id / attachment_id 검증

- [ ] 감사 로그 적용
  - 생성/삭제/수정/정렬/이동 전체 대상

---

## 2. 빠른 보완 권장 (Medium Risk)

- [ ] 업로드 서버단 검증 강화
  - 용량 제한
  - 확장자 whitelist
  - MIME 검증

- [ ] 파일명 보안 정책
  - original_name = 표시용
  - 저장 파일명 = 랜덤

- [ ] CDN 보안 강화
  - SRI 적용 또는 로컬 번들화

- [ ] 권한 정책 SSOT 정합성 점검

- [ ] JSON 응답 일관성 유지
  - safeReadJson 전역 적용

- [ ] 정렬 API 입력 검증
  - 중복 / 누락 / 범위 체크

---

## 3. 운영 안정성 보완 (Low ~ Medium)

- [ ] 트랜잭션 보장
  - reorder / move / delete

- [ ] 동시 수정 충돌 방지
  - optimistic lock 검토

- [ ] N+1 성능 개선
  - prefetch_related 적용

- [ ] 소프트 삭제 정책 검토

- [ ] 로그 체계 정리
  - ERROR / AUDIT 분리

- [ ] 이벤트 중복 바인딩 방어 유지

- [ ] 정적파일 캐시 정책 관리

---

## 한 줄 핵심
👉 "파일은 무조건 view 경유 + 권한검증, HTML은 sanitize, API는 객체 단위 검증"
