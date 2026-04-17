# django_ma Partner App 운영 지침서 (partner.md)

## 1. 목적
Partner 앱은 조직관리(편제/요율/지점효율/권한)를 담당하며,
운영 안정성, 권한 일관성, 데이터 무결성을 최우선으로 한다.

---

## 2. 핵심 아키텍처

### 2.1 Boot 패턴 (SSOT)
- 모든 페이지는 root dataset 기반
- JS는 dataset만 참조
- 서버 → 템플릿 → dataset → JS 흐름 유지

---

### 2.2 권한 체계
| 등급 | 범위 |
|------|------|
| superuser | 전체 |
| head | 본인 지점 |
| leader | 팀 기반 |

※ 모든 조회/수정은 반드시 서버에서 재검증

---

### 2.3 데이터 도메인
- Structure (편제)
- Rate (요율)
- Efficiency (지점효율)

---

## 3. API 규약

### 3.1 JSON 응답
- 성공: { status: "success" }
- 실패: { status: "error", message }

### 3.2 공통 규칙
- 모든 API는 login_required 필수
- 쓰기 API는 transaction.atomic 필수

---

## 4. 파일 처리 정책

### 금지
- file.url 직접 노출 ❌

### 필수
- 다운로드 view → 권한검증 → FileResponse

---

## 5. 엑셀 업로드 규칙
- 컬럼 기반 파싱
- bulk 처리 (row-by-row 금지)
- fail row 별도 관리

---

## 6. 프론트엔드 규칙

### 6.1 이벤트
- dataset 기반 초기화
- 중복 바인딩 방지

### 6.2 테이블
- inputTable: fixed + scroll
- mainTable: ellipsis

---

## 7. 보안 원칙

### 필수 체크
- 권한 스코프 검증
- branch 제한
- 대상자 검증

---

## 8. 감사 로그

### 대상
- 권한 변경
- 업로드
- 삭제

---

## 9. 운영 체크리스트

### 배포 전
- python manage.py check
- 권한 테스트

### 운영 중
- 로그 확인
- 업로드 검증

---

## 10. 금지 사항
- 권한 우회 로직
- 직접 URL 파일 접근
- 공용 유틸 중복 생성
