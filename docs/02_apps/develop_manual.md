# django_ma Manual App 보안 취약점 및 성능 개선 체크리스트

> 기준일: 2026-04-29  
> 범위: `manual` app 전체 및 manual이 직접 의존하는 공통 infra/frontend 일부  
> 목적: 실제 패치 전, 보안 보완사항과 성능·구조 개선 필요사항을 분리해 우선순위별로 점검하기 위한 체크리스트입니다.  
> 주의: 본 문서는 **패치 제안서가 아니라 점검 목록**입니다. 실제 수정은 별도 diff 패치로 진행합니다.

---

## 1. 기준 코드 범위

### 1.1 Backend

- `manual/apps.py`
- `manual/constants.py`
- `manual/forms.py`
- `manual/models.py`
- `manual/urls.py`
- `manual/views/__init__.py`
- `manual/views/pages.py`
- `manual/views/manual.py`
- `manual/views/section.py`
- `manual/views/block.py`
- `manual/views/attachment.py`
- `manual/utils/__init__.py`
- `manual/utils/http.py`
- `manual/utils/parsing.py`
- `manual/utils/permissions.py`
- `manual/utils/rules.py`
- `manual/utils/sanitize.py`
- `manual/utils/serializers.py`
- `manual/utils/uploads.py`
- `manual/management/commands/sanitize_manual_blocks.py`
- `manual/management/commands/cleanup_manual_files.py`
- `management/commands/cleanup_missing_manual_images.py`

### 1.2 Templates

- `manual/templates/manual/manual_list.html`
- `manual/templates/manual/manual_detail.html`
- `manual/templates/manual/rules_home.html`
- `manual/templates/manual/_partials/create_manual_modal.html`
- `manual/templates/manual/_partials/manual_detail_boot.html`
- `manual/templates/manual/_partials/manual_detail_superuser_assets.html`
- `manual/templates/manual/_partials/manual_list_scripts.html`

### 1.3 Frontend

- `static/js/manual/_shared.js`
- `static/js/manual/create_manual_modal.js`
- `static/js/manual/manual_list_boot.js`
- `static/js/manual/manual_list_edit.js`
- `static/js/manual/manual_detail_subnav.js`
- `static/js/manual/manual_detail_section_sort.js`
- `static/js/manual/manual_detail_block/index.js`
- `static/js/manual/manual_detail_block/quill.js`
- `static/js/manual/manual_detail_block/section_subnav.js`
- `static/js/manual/manual_detail_block/sort_blocks.js`
- `static/css/apps/manual.css`

### 1.4 공통 의존부

- `templates/base.html`
- `static/css/base.css`
- `static/css/fixes.css`
- `web_ma/settings.py`
- `web_ma/urls.py`
- `web_ma/views.py`
- `web_ma/middleware.py`

---

# 2. 보안상의 취약점 보완 체크리스트

## 2.1 즉시 조치급 High Risk

### 2.1.1 동적 DOM 생성 시 HTML 삽입 경로 점검

- [ ] `manual_detail_block/index.js`의 `buildBlockElement()`에서 서버 응답 `b.content`를 `innerHTML`로 삽입하는 경로 점검
- [ ] `section_subnav.js`의 `buildSectionElement()`에서 `titleHtml`을 template literal로 직접 삽입하는 경로 점검
- [ ] `manual_list_edit.js`에서 제목 수정 후 DOM 반영 시 `textContent` 기반인지 확인
- [ ] 동적 생성 HTML 중 사용자 입력값은 모두 `textContent` 또는 escape helper를 사용하도록 기준 통일
- [ ] 서버단 sanitize가 있더라도 프런트 동적 삽입 경로는 별도 XSS 방어 대상으로 관리

#### 관측 포인트

- 섹션 제목에 `<img onerror=alert(1)>` 같은 문자열 저장 시 화면에서 실행되지 않아야 함
- 블록 본문에 과거 저장된 악성 HTML이 백필 전 상태여도 상세 페이지에서 실행되지 않아야 함
- 신규 생성 섹션/블록 DOM과 서버 렌더 DOM의 escape 정책이 일치해야 함

---

### 2.1.2 Quill HTML sanitize 정책의 운영 보장성 점검

- [ ] `manual/utils/sanitize.py`에서 `bleach`가 설치되어 있지 않을 때 fallback sanitizer로만 동작하는 구조 점검
- [ ] 운영 `requirements.txt`에 `bleach` 의존성이 명시되어 있는지 확인
- [ ] `CSSSanitizer` 미사용 또는 import 실패 시 style 속성 허용 정책이 의도대로 동작하는지 확인
- [ ] `sanitize_manual_blocks` command를 운영 적용 전 dry-run으로 실행해 변경 대상 확인
- [ ] 과거 저장된 `ManualBlock.content`에 대해 sanitize 백필 적용 여부 확인
- [ ] `Manual.content` 필드도 HTML 사용 가능성이 있다면 sanitize 적용 대상인지 별도 판단

#### 관측 포인트

- `python manage.py sanitize_manual_blocks`
- `python manage.py sanitize_manual_blocks --apply`
- `ManualBlock.content` 내 `script`, `iframe`, `javascript:`, `onerror` 잔존 여부
- 운영 dependency freeze 결과

---

### 2.1.3 업로드 파일 검증의 MIME 신뢰도 보강 필요

- [ ] `validate_manual_attachment()`가 브라우저 제공 `content_type`만 신뢰하고 있는지 확인
- [ ] 확장자와 MIME이 불일치하는 파일 업로드 테스트
- [ ] 이미지 업로드는 `ImageField` 검증 외에 실제 이미지 파싱 검증이 수행되는지 확인
- [ ] `.hwp`, `.hwpx`, Office 문서 등 고위험 첨부는 허용 범위가 업무상 반드시 필요한지 재검토
- [ ] 첨부파일 저장명과 원본명 분리 정책 확인
- [ ] 첨부파일 다운로드 시 `Content-Disposition`의 파일명 인코딩 정책 점검

#### 관측 포인트

- `.jpg` 확장자를 가진 HTML/JS 파일 업로드 시 차단 여부
- MIME이 비어 있는 클라이언트에서 허용되는지 여부
- 업로드 파일이 브라우저에서 inline 실행될 가능성 여부
- `manual_attachment_download`가 항상 `as_attachment=True`인지 확인

---

### 2.1.4 이미지 inline 응답의 Content-Type 및 sniffing 방어 점검

- [ ] `manual_block_image()`의 `FileResponse(..., as_attachment=False)` 응답 Content-Type 확인
- [ ] 이미지 URL이 HTML/SVG/스크립트성 파일로 악용될 수 없는지 확인
- [ ] `X-Content-Type-Options: nosniff`가 모든 이미지 응답에도 적용되는지 확인
- [ ] SVG 업로드가 허용되지 않는 현재 정책이 유지되는지 확인
- [ ] 이미지 응답 캐시가 사용자 권한 변경 이후에도 노출되지 않는지 확인

#### 관측 포인트

- `/manual/blocks/<block_id>/image/` 응답 헤더
- `Content-Type`, `X-Content-Type-Options`, `Cache-Control`
- 비권한 사용자 접근 시 403/권한 팝업 응답 여부

---

### 2.1.5 Manual 접근권한 서버 검증 일관성 점검

- [ ] `manual_list`, `manual_detail`, `manual_attachment_download`, `manual_block_image`가 모두 `manual_accessible_or_denied()` 정책을 공유하는지 확인
- [ ] AJAX 쓰기 API는 `ensure_superuser_or_403()`로 superuser만 허용하는지 확인
- [ ] `rules_home()`에 인증/비활성 차단 데코레이터가 필요한지 판단
- [ ] base navbar에서 메뉴가 숨겨지는 것과 실제 서버 접근권한이 일치하는지 확인
- [ ] `head`, `leader`, `basic`, `inactive`의 manual 접근 정책을 문서화

#### 관측 포인트

- 비로그인 접근
- inactive 접근
- basic이 admin_only 매뉴얼 직접 URL 접근
- head가 직원전용 비공개 매뉴얼 직접 URL 접근
- leader/basic이 첨부 다운로드 URL 직접 접근

---

### 2.1.6 첨부파일 직접 URL 노출 금지 정책 유지 점검

- [ ] 템플릿에서 `attachment.file.url` 직접 사용 여부 검색
- [ ] serializer의 `attachment_to_dict()`가 보호 다운로드 URL만 반환하는지 확인
- [ ] Quill 본문에 삽입되는 첨부 링크가 항상 `manual_attachment_download`인지 확인
- [ ] 과거 저장된 Quill 본문에 `/media/manual/attachments/` 직접 링크가 남아 있는지 점검
- [ ] `/media/` 전역 서빙이 `web_ma/urls.py`에서 제거된 정책과 충돌하지 않는지 확인

#### 검색 명령 예시

```powershell
Get-ChildItem -Path manual,templates,static -Recurse -File |
  Select-String -Pattern ".file.url","/media/manual","manual/attachments"
```

---

### 2.1.7 Audit 로그 누락 가능 지점 점검

- [ ] 매뉴얼 생성/수정/삭제 로그 확인
- [ ] 섹션 생성/수정/삭제/정렬 로그 확인
- [ ] 블록 생성/수정/삭제/정렬/이동 로그 확인
- [ ] 첨부 업로드/삭제/다운로드 로그 확인
- [ ] 이미지 조회는 로그 대상인지 정책 결정
- [ ] cleanup/sanitize management command 수행 이력도 audit 또는 운영 로그로 남기는지 확인
- [ ] 실패 이벤트도 기록할 필요가 있는지 판단

#### 중요 이벤트

- `MANUAL_CREATE`
- `MANUAL_UPDATE`
- `MANUAL_BULK_UPDATE`
- `MANUAL_DELETE`
- `MANUAL_REORDER`
- `MANUAL_SECTION_CREATE`
- `MANUAL_SECTION_UPDATE`
- `MANUAL_SECTION_DELETE`
- `MANUAL_SECTION_REORDER`
- `MANUAL_BLOCK_CREATE`
- `MANUAL_BLOCK_UPDATE`
- `MANUAL_BLOCK_DELETE`
- `MANUAL_BLOCK_REORDER`
- `MANUAL_BLOCK_MOVE`
- `MANUAL_ATTACHMENT_UPLOAD`
- `MANUAL_ATTACHMENT_DELETE`
- `MANUAL_ATTACHMENT_DOWNLOAD`

---

## 2.2 빠른 보완 권장 Medium Risk

### 2.2.1 JSON 파싱 실패 처리 표준화

- [ ] `manual/utils/http.py`의 `json_body()`가 파싱 실패 시 `{}`를 반환하는 정책 점검
- [ ] 잘못된 JSON과 빈 JSON을 구분할 필요가 있는 API 식별
- [ ] 모든 AJAX API에서 필수 파라미터 검증이 충분한지 확인
- [ ] 비JSON 요청에 대한 사용자 메시지와 서버 로그 분리 여부 확인

---

### 2.2.2 CSRF 토큰 경로 중복 및 누락 점검

- [ ] manual list는 `manualEditCsrfForm` 기준
- [ ] manual detail block은 `manualBlockCsrfForm` 기준
- [ ] create modal은 내부 form csrf 기준
- [ ] `ManualShared.getCSRFTokenFromForm()` 실패 시 cookie fallback이 필요한지 판단
- [ ] CSRF_COOKIE_HTTPONLY=False 정책과 프런트 cookie fallback 사용 여부 정합성 확인

---

### 2.2.3 외부 링크 rel 보강 정책 점검

- [ ] `sanitize_quill_html()`의 `_force_safe_anchor_attrs()`가 모든 `<a>`에 `rel`을 보강하는지 확인
- [ ] `target="_blank"`가 아닌 링크에도 rel이 붙는 현재 정책이 의도한 것인지 확인
- [ ] `href` 프로토콜이 `http`, `https`, `mailto`로만 제한되는지 확인
- [ ] Quill link tooltip 입력값에서 `javascript:`가 제거되는지 테스트

---

### 2.2.4 권한 실패 응답 포맷 일관성 점검

- [ ] AJAX API 권한 실패는 JSON `fail(..., 403)`로 반환
- [ ] 페이지/파일 접근 실패는 `no_permission_popup.html` 렌더
- [ ] fetch 호출에서 HTML 403이 들어올 경우 프런트 오류 메시지가 적절한지 확인
- [ ] manual 전용 JS와 공통 `readJsonOrThrow()`의 에러 메시지 정책 일치 여부 확인

---

### 2.2.5 삭제 동작의 자료 손실 방지

- [ ] 매뉴얼 삭제 시 연결된 섹션/블록/첨부파일이 cascade 되는 범위 확인
- [ ] `ManualBlock.delete()`에서 이미지 삭제가 정상 수행되는지 확인
- [ ] `ManualBlockAttachment.delete()`에서 파일 삭제가 정상 수행되는지 확인
- [ ] bulk 삭제나 QuerySet delete 사용 시 모델 `delete()`가 호출되지 않는 위험 여부 점검
- [ ] 삭제 전 confirm 외 서버단 soft-delete 필요성 검토

---

## 2.3 운영 안정성 보완

### 2.3.1 CSP와 Quill/Bootstrap/inline script 정합성

- [ ] `CONTENT_SECURITY_POLICY`의 `'unsafe-inline'`, `'unsafe-eval'` 필요 범위 확인
- [ ] Quill 1.3.7 로컬 vendor 사용 시 CSP 위반 여부 확인
- [ ] manual 템플릿 내 inline style/script 최소화 가능성 점검
- [ ] CSP Report-Only 운영 모드에서 위반 로그 확인
- [ ] `frame-ancestors 'none'`와 `X_FRAME_OPTIONS=DENY` 유지 확인

---

### 2.3.2 캐시 정책

- [ ] manual image 응답 `private, max_age=3600`이 권한 변경 시 문제 없는지 확인
- [ ] 첨부 다운로드는 캐시 제한이 필요한지 검토
- [ ] manual detail/list 페이지는 권한별 노출이 다르므로 중간 캐시 금지 확인
- [ ] base/nav에 개인정보 워터마크가 있으므로 페이지 캐시 금지 정책 점검

---

### 2.3.3 Management command 운영 가드

- [ ] `sanitize_manual_blocks`는 기본 dry-run 유지
- [ ] `cleanup_manual_files`는 `--apply --delete-missing-attachments --force` 3단계 가드 유지
- [ ] 실행 전 DB 백업 절차 문서화
- [ ] 실행 결과 로그 보관
- [ ] 운영 실행 주체와 승인 절차 지정

---

# 3. 성능 및 코드 개선 필요사항 체크리스트

## 3.1 즉시 검토 권장

### 3.1.1 정렬 저장 로직의 row-by-row update 개선

- [ ] `manual_reorder_ajax()`의 매뉴얼 정렬 저장이 row-by-row update인지 확인
- [ ] `manual_section_reorder_ajax()`의 섹션 정렬 저장이 row-by-row update인지 확인
- [ ] `manual_block_reorder_ajax()`의 블록 정렬 저장이 row-by-row update인지 확인
- [ ] `manual_block_move_ajax()`의 from/to 정렬 저장이 row-by-row update인지 확인
- [ ] 대량 섹션/블록에서 `bulk_update()`로 전환 가능성 검토
- [ ] 기능 변화 0 조건에서 정렬 결과와 updated_at 정책 차이 확인

#### 영향

- 섹션/블록 수가 많아질수록 DB round-trip 증가
- Drag & drop 저장 시 응답 지연 가능
- 동시 편집 시 경합 가능성 증가

---

### 3.1.2 목록 화면 N+1 쿼리 점검

- [ ] `manual_list()`에서 `Manual.objects.all()` 후 템플릿에서 `m.sections.all`을 반복하는 구조 확인
- [ ] 목록 화면 섹션 chip 표시를 위해 `prefetch_related("sections")` 필요 여부 확인
- [ ] 매뉴얼 수가 늘어났을 때 SQL query count 측정
- [ ] 정렬 기준 `sort_order`, `updated_at` 인덱스 활용 여부 확인

#### 관측 포인트

```python
from django.test.utils import CaptureQueriesContext
from django.db import connection
```

---

### 3.1.3 상세 화면 prefetch 정렬 정확성 점검

- [ ] `manual_detail()`에서 `manual.sections.prefetch_related("blocks", "blocks__attachments")` 사용 중
- [ ] prefetch된 blocks가 모델 Meta ordering에만 의존하는지 확인
- [ ] attachments 정렬이 serializer에서 다시 `.order_by()` 호출되어 추가 쿼리가 발생하는지 확인
- [ ] `Prefetch` 객체로 blocks/attachments 정렬을 명시할 필요성 검토
- [ ] 상세 페이지 블록 수가 많을 때 query count 측정

---

### 3.1.4 serializer에서 attachments 재조회 가능성

- [ ] `block_to_dict()`의 `b.attachments.all().order_by("created_at", "id")`가 prefetch cache를 무시하는지 확인
- [ ] 블록 생성/수정 응답에서는 문제 없으나 대량 직렬화 시 N+1 가능성 확인
- [ ] serializer 정책을 “단건 응답용”과 “목록 응답용”으로 분리할지 검토

---

### 3.1.5 Quill/Sortable 중복 로드 점검

- [ ] `manual_detail_superuser_assets.html`에서 `_shared.js` 로드
- [ ] `manual_detail.html`에서 다시 `_shared.js` 로드
- [ ] `manual_detail.html`에서 SortableJS 로드
- [ ] `manual_detail_superuser_assets.html` 또는 list scripts와 중복 로드 가능성 확인
- [ ] `create_manual_modal.js`가 상세 페이지에서도 필요한지 여부 확인
- [ ] 최종 로딩 책임을 partial 단위로 정리할 필요성 검토

#### 영향

- JS 다운로드/파싱 비용 증가
- 중복 바인딩 가드는 있으나 디버깅 복잡성 증가
- 모듈 전환 상태에서 legacy script 잔존 가능성

---

## 3.2 코드 구조 개선

### 3.2.1 manual JS 내 공통 API 호출 유틸 통합

- [ ] `ManualShared.postJson/postForm`과 `common/manage/http.js`의 역할 중복 점검
- [ ] manual만의 `ok` 응답 포맷과 partner/commission의 `status: success` 포맷 차이 문서화
- [ ] JSON non-response 처리 문구 통일
- [ ] CSRF fallback 정책 통일
- [ ] 추후 공통 fetch 유틸로 병합 가능한지 검토

---

### 3.2.2 권한 정책 함수 명확화

- [ ] `ensure_superuser_or_403()`는 JSON 전용 성격인지 명명 검토
- [ ] `manual_accessible_or_denied()`는 HTML 렌더 응답을 반환하므로 AJAX와 구분 필요
- [ ] `filter_manuals_for_user()`와 `manual_accessible_or_denied()` 규칙이 항상 동일하게 유지되는지 테스트 필요
- [ ] `rules_home()` 권한 정책을 manual domain policy에 포함할지 결정

---

### 3.2.3 ManualBlock의 `manual` FK와 `section` FK 중복 구조 정리 검토

- [ ] `ManualBlock.manual`은 기존 호환을 위해 유지 중
- [ ] `section.manual`과 불일치할 수 있는 데이터 무결성 위험 확인
- [ ] 저장 시 `manual=section.manual` 강제 정책이 모든 경로에서 지켜지는지 확인
- [ ] DB constraint 또는 model clean/save 보강 필요성 검토
- [ ] 장기적으로 `manual` FK 제거 또는 read-only 동기화 정책 검토

---

### 3.2.4 default section 생성 경합 가능성

- [ ] `ensure_default_section()`이 동시 요청에서 중복 섹션을 만들 가능성 점검
- [ ] 상세 페이지 GET에서 DB write가 발생하는 현재 구조가 의도된 것인지 확인
- [ ] `manual_create_ajax()` 또는 생성 시점에 기본 섹션을 만드는 방식으로 전환 가능성 검토
- [ ] 트랜잭션/락 또는 unique 정책 필요 여부 검토

---

### 3.2.5 감사로그 메타 크기 및 민감정보 점검

- [ ] `log_action` meta에 title/name이 그대로 저장되는 정책 검토
- [ ] 첨부 파일명에 개인정보가 포함될 수 있는지 확인
- [ ] block content 자체는 audit meta에 저장하지 않는 현재 정책 유지
- [ ] 대량 정렬 시 `section_ids`, `block_ids`, `ordered_ids` 길이 제한 필요성 확인

---

## 3.3 프론트엔드 성능 개선

### 3.3.1 Subnav rebuild 빈도와 DOM 비용

- [ ] `manual_detail_subnav.js`가 rebuild 시 전체 링크를 다시 생성하는 구조 확인
- [ ] `section_subnav.js`도 별도 rebuild 로직을 보유하고 있어 중복 가능성 점검
- [ ] 섹션 수가 많아질 때 rebuild 비용 측정
- [ ] `window.ManualDetailSubnav` API로 단일화 가능성 검토

---

### 3.3.2 IntersectionObserver 재생성 비용

- [ ] subnav rebuild마다 observer disconnect/recreate 수행
- [ ] 섹션 수가 많을 때 스크롤 성능 확인
- [ ] debounce/RAF는 적용되어 있으나 삭제/추가 연속 작업에서 충분한지 확인

---

### 3.3.3 이미지 미리보기 Blob URL 관리

- [ ] `manual_detail_block/index.js`에서 preview blob URL revoke 정책 확인
- [ ] 모달 hide 시 revoke 정상 수행 확인
- [ ] 새 파일 재선택 시 이전 URL revoke 정상 수행 확인

---

### 3.3.4 DOM template literal 사용 축소

- [ ] `buildBlockElement()`, `buildSectionElement()`의 큰 HTML 문자열 생성 구조 점검
- [ ] 사용자 입력이 섞이는 부분은 DOM API 기반 생성으로 전환 가능성 검토
- [ ] 보안 개선과 함께 렌더 안정성 개선 가능

---

### 3.3.5 파일 업로드 UX

- [ ] 첨부 업로드 중 버튼/입력 비활성화 여부 확인
- [ ] 이미지 업로드 클라이언트 측 확장자/용량 사전 검증 여부 확인
- [ ] 서버 검증 실패 메시지 표시 위치 확인
- [ ] 대용량 파일 업로드 중 중복 클릭 방지 확인

---

## 3.4 운영/배포 성능

### 3.4.1 정적파일 캐시 버전 정책

- [ ] `manual.css` 버전 쿼리 값 관리 방식 확인
- [ ] `create_manual_modal.js`, `manual_detail_block/index.js` 등 수동 version query 관리 부담 확인
- [ ] 운영 Whitenoise Manifest 사용 시 query version 의존도를 낮출 수 있는지 검토
- [ ] DEBUG/prod 정적파일 로딩 차이 확인

---

### 3.4.2 Quill vendor 크기와 페이지별 로딩

- [ ] Quill은 superuser 상세 페이지에서만 필요한지 확인
- [ ] 일반 사용자는 Quill/Sortable 미로딩 상태인지 확인
- [ ] manual list에서 SortableJS가 superuser에게만 로드되는지 확인
- [ ] 편집 모드 진입 시 lazy-load로 전환할 가치가 있는지 검토

---

### 3.4.3 이미지 최적화

- [ ] 업로드 이미지 원본을 그대로 제공하는 현재 구조 확인
- [ ] 썸네일 생성 여부 없음
- [ ] 큰 이미지가 상세 페이지 로딩에 미치는 영향 측정
- [ ] `loading="lazy"` 적용 가능성 검토
- [ ] 이미지 리사이즈/압축 정책 필요성 검토

---

# 4. 우선순위별 실행 가이드

## 4.1 1차: 보안 우선 점검

- [ ] dynamic innerHTML 삽입 경로 XSS 점검
- [ ] bleach 설치/운영 반영 여부 확인
- [ ] 과거 ManualBlock.content sanitize 백필 dry-run
- [ ] 첨부/이미지 MIME·확장자 우회 테스트
- [ ] `/media/manual` 직접 링크 잔존 여부 검색
- [ ] 권한별 direct URL 접근 테스트
- [ ] 첨부 다운로드 audit 로그 확인

## 4.2 2차: 기능 안정성 점검

- [ ] 매뉴얼 생성/수정/삭제
- [ ] 목록 편집모드 저장/완료/삭제
- [ ] 섹션 추가/제목수정/삭제/정렬
- [ ] 블록 추가/수정/삭제/정렬/이동
- [ ] 이미지 업로드/삭제/원본보기
- [ ] 첨부 업로드/본문 링크 삽입/다운로드
- [ ] superuser/head/leader/basic/inactive 접근 차이

## 4.3 3차: 성능/구조 개선 검토

- [ ] manual_list N+1 제거
- [ ] detail prefetch 정렬 최적화
- [ ] 정렬 저장 bulk_update 검토
- [ ] JS 중복 로드 정리
- [ ] Subnav rebuild 단일화
- [ ] ManualBlock manual/section 중복 FK 정리 로드맵

---

# 5. 최소 검증 시나리오

## 5.1 로컬 기본 검증

```bash
python manage.py check
python manage.py test manual
```

수동 검증:

- [ ] superuser로 매뉴얼 목록 진입
- [ ] 새 매뉴얼 생성
- [ ] 목록 편집모드에서 제목/공개범위/정렬 저장
- [ ] 상세에서 구역 추가/소제목 수정/구역 삭제
- [ ] 블록 추가/수정/삭제
- [ ] 이미지 업로드/삭제/원본 보기
- [ ] 첨부 업로드/다운로드
- [ ] head/basic 계정으로 권한 노출 확인
- [ ] inactive 계정 접근 차단 확인

## 5.2 보안 검증

- [ ] 제목 입력값 XSS 문자열 테스트
- [ ] 섹션 제목 XSS 문자열 테스트
- [ ] 블록 본문 XSS HTML 테스트
- [ ] `javascript:` 링크 테스트
- [ ] 허용되지 않은 확장자 업로드 테스트
- [ ] MIME 위장 파일 업로드 테스트
- [ ] 첨부 다운로드 direct URL 권한 테스트
- [ ] 비공개 매뉴얼 direct URL 접근 테스트
- [ ] audit 로그 기록 확인

## 5.3 운영 유사 검증

- [ ] `DEBUG=False` 유사 환경에서 정적파일 로딩 확인
- [ ] Quill/Sortable/vendor 경로 200 확인
- [ ] CSP Report-Only 위반 로그 확인
- [ ] 이미지/첨부 응답 헤더 확인
- [ ] 로그 파일에 500 traceback 기록 확인
- [ ] sanitize/cleanup command dry-run 로그 확인

---

# 6. 패치 진행 시 주의사항

- 기능 변화 0 원칙을 기본값으로 둔다.
- URL name, DOM id, data-* key는 JS 의존성이 있으므로 임의 변경하지 않는다.
- 첨부파일은 절대 `.file.url` 직접 노출로 회귀하지 않는다.
- 권한 완화로 문제를 해결하지 않는다.
- sanitize 정책 변경 시 과거 데이터 백필 계획을 함께 세운다.
- 정렬/이동 로직은 서버 검증을 절대 제거하지 않는다.
- 공통 유틸과 manual 전용 유틸의 역할을 명확히 분리한다.
- 패치는 반드시 diff 형태로 적용하고, 검증 시나리오를 함께 기록한다.

---

# 7. 최종 요약

## 보안 핵심

- 가장 먼저 볼 지점은 **동적 innerHTML 삽입 경로**, **sanitize 운영 보장성**, **업로드 MIME 검증**, **첨부 직접 URL 잔존 여부**, **권한별 direct URL 접근**입니다.

## 성능 핵심

- 가장 먼저 볼 지점은 **manual_list N+1**, **정렬 저장 row-by-row update**, **상세 prefetch 정렬/serializer 재조회**, **Quill/Sortable 중복 로드**, **Subnav rebuild 중복**입니다.

## 운영 핵심

- management command는 반드시 dry-run → 백업 → apply 순서로 운영합니다.
- audit 로그와 파일 응답 권한 검증은 manual app의 운영 신뢰성 핵심입니다.
