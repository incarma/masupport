# manual 앱 최종 기준 문서 (SSOT)

본 문서는 django_ma manual 앱의 **최종 운영 기준 문서**입니다.

---

## 1. 핵심 정의
manual 앱은 내부 운영용 구조화된 매뉴얼 CMS입니다.
- Manual → Section → Block 구조
- 권한 기반 접근 제어
- 드래그 기반 정렬 및 편집

---

## 2. JSON 응답 규약 (SSOT)

모든 AJAX 응답은 아래 형식을 따릅니다.

### 성공
```json
{ "ok": true }
```

### 실패
```json
{ "ok": false, "message": "에러 메시지" }
```

---

## 3. 보안 규칙

### 3.1 XSS 방어
- Quill HTML 저장 시 sanitize 필수
- script / iframe / 이벤트 속성 제거

### 3.2 파일 업로드
- 확장자 화이트리스트
- MIME 검증
- size 제한
- 파일명 랜덤화

### 3.3 다운로드 정책
- 직접 URL 접근 금지
- View에서 권한 검증 후 FileResponse

### 3.4 권한 검증
- ensure_superuser_or_403 사용
- 모든 AJAX endpoint 필수 적용

---

## 4. JS 아키텍처

### 4.1 구조
- _shared.js → 공통 유틸
- list / detail → 모듈 분리

### 4.2 Boot 규약
- dataset 기반 URL 주입
- camelCase로 접근

### 4.3 BFCache 대응
- dataset.bound 사용
- 중복 이벤트 방지

---

## 5. 트랜잭션 정책

다음 작업은 반드시 atomic 처리

- manual reorder
- section reorder
- block move

---

## 6. 성능 정책

- prefetch_related 사용
- N+1 방지

---

## 7. 운영 체크리스트

- 권한 검증 완료 여부
- 업로드 정책 적용 여부
- 로그 기록 여부
- JS 중복 바인딩 방지 여부

---

## 8. 결론

manual 앱은 단순 기능이 아닌  
**운영형 CMS 구조**로 관리해야 합니다.
