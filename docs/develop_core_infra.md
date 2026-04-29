# django_ma CORE INFRA 점검 체크리스트

## 1. 보안 취약점 체크리스트

### 즉시 조치급

-   csrf_failure 로그 쿠키 마스킹 필요
-   X-Forwarded-For 신뢰 범위 검증 필요
-   업로드 결과 파일 접근 권한 검증 필요
-   RequestLog 전수 저장 정책 재검토
-   CSP unsafe-inline / unsafe-eval 제거 검토

### 빠른 보완 권장

-   Dockerfile collectstatic 실패 무시 제거
-   Docker base image 버전 고정
-   docker-compose 운영 bind mount 제거 검토
-   latest 태그 제거 (redis/nginx)
-   audit meta key 기반 마스킹 강화
-   landing/login fetch JSON 방어 추가
-   excel_upload XSS 방어 강화

### 운영 안정성 보완

-   RequestLog/AuditLog retention 정책
-   healthcheck 로그 제외
-   Celery idempotency 검증
-   업로드 temp/result 파일 cleanup
-   CustomUser is_superuser 충돌 점검

------------------------------------------------------------------------

## 2. 성능 개선 체크리스트

### 즉시 점검

-   RequestLog DB write 부하
-   path index 효율
-   AuditLog meta 크기 제한
-   Excel upload row-by-row 처리 성능
-   search API icontains 성능

### 빠른 개선

-   signals DB 조회 최소화
-   SubAdminTemp sync 최적화
-   DataTables 자동 초기화 범위 제한
-   file_upload 전체 HTML 교체 방식 검토
-   base_ui.js 역할 정리
-   landing 애니메이션 코드 중복 제거

### 구조 개선

-   admin.py 서비스 분리
-   login view 책임 분리
-   RequestLog async/batch 검토
-   fetch JSON 처리 공통화
-   submit lock 공통 유틸화
-   settings 문서화
