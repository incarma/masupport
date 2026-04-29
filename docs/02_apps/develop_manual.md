# django_ma 성능 및 구조 개선 체크리스트

## 1. DB / Query

-   [ ] manual_detail prefetch 최적화
-   [ ] sort_order 인덱스 검토
-   [ ] audit 조회 성능 확인

## 2. JS 중복

-   [ ] subnav rebuild 중복 제거
-   [ ] 이벤트 바인딩 중복 제거
-   [ ] Sortable 동적 적용 검증

## 3. Static / Vendor

-   [ ] 페이지별 JS 로딩 최소화
-   [ ] vendor unused 제거
-   [ ] cache 전략 정리

## 4. Audit 성능

-   [ ] meta 크기 제한
-   [ ] 로그 보관 정책 수립

## 5. View / Service

-   [ ] 공통 유틸 통합
-   [ ] 파일 다운로드 로직 공용화

## 6. Frontend 공통화

-   [ ] ManualShared vs common util 통합
-   [ ] 업로드/preview 유틸 공용화

## 7. 운영

-   [ ] Docker 이미지 최적화
-   [ ] static/vendor 포함 여부 정책
-   [ ] backup 대상 정리

## 우선순위

-   즉시: JS 중복, Sortable, audit meta
-   단기: queryset, vendor
-   장기: audit lifecycle, 서비스 레이어 통합

작성일: 2026-04-27
