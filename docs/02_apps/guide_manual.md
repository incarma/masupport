# django_ma Manual App 운영·개발 지침서

> 기준일: 2026-04-29  
> 대상 앱: `manual`  
> 목적: 앞으로 전체 코드를 다시 공유하지 않아도 `manual app` 관련 보안 점검, 성능 개선, 리팩토링, 패치 설계가 가능하도록 파일 구조, 주요 함수 위치, 권한 지침, SSOT 규약, 회귀 위험 포인트를 정리합니다.

---

## 0. 문서 목적과 사용 원칙

이 문서는 `django_ma` 프로젝트의 **업무 매뉴얼(manual app)** 기능을 대상으로 합니다.

향후 다음 작업을 진행할 때 이 문서를 기준점으로 사용합니다.

- 취약점 보완 설계
- 성능 개선 및 코드 중복 제거
- 기능 변화 0 리팩토링
- 템플릿/JS/CSS 패치
- 첨부파일 다운로드/이미지 표시 정책 점검
- superuser 전용 편집 기능 권한 점검
- Quill HTML sanitize 정책 점검
- 운영 배포 전 회귀 점검

이 문서는 코드 자체를 대체하지 않습니다. 다만, 코드 전체가 다시 제공되지 않아도 구조와 규약을 기준으로 피드백할 수 있도록 정리합니다.

---

## 1. Manual App 기능 개요

`manual app`은 업무 매뉴얼 문서를 목록/상세 형태로 제공하고, `superuser`가 웹 UI에서 매뉴얼, 섹션, 블록, 이미지, 첨부파일을 관리할 수 있게 하는 기능입니다.

| 영역 | 설명 |
|---|---|
| 매뉴얼 목록 | 사용자 권한에 따라 노출 가능한 매뉴얼 목록 표시 |
| 매뉴얼 상세 | 섹션 카드와 블록 콘텐츠 표시 |
| 매뉴얼 생성/수정/삭제 | `superuser` 전용 AJAX/폼 기반 관리 |
| 섹션 관리 | 섹션 추가, 제목 수정, 삭제, 정렬 |
| 블록 관리 | 블록 추가, 수정, 삭제, 같은 섹션 내 정렬, 섹션 간 이동 |
| 이미지 표시 | 직접 `.url` 노출 대신 보호 view 경유 |
| 첨부파일 업로드/삭제/다운로드 | 업로드 검증 + 권한 검증 + `FileResponse` 제공 |
| Quill HTML 편집 | 서버 저장 전 sanitize 적용 |
| 파일 정리 명령 | 누락 이미지/첨부파일 참조 점검 및 선택적 정리 |
| sanitize 백필 명령 | 과거 저장 HTML 정리 |

---

## 2. Manual App 전체 파일 구조

```text
django_ma/
├─ manual/
│  ├─ apps.py
│  ├─ constants.py
│  ├─ forms.py
│  ├─ models.py
│  ├─ urls.py
│  │
│  ├─ views/
│  │  ├─ __init__.py
│  │  ├─ pages.py
│  │  ├─ manual.py
│  │  ├─ section.py
│  │  ├─ block.py
│  │  └─ attachment.py
│  │
│  ├─ utils/
│  │  ├─ __init__.py
│  │  ├─ http.py
│  │  ├─ parsing.py
│  │  ├─ permissions.py
│  │  ├─ rules.py
│  │  ├─ sanitize.py
│  │  ├─ serializers.py
│  │  └─ uploads.py
│  │
│  ├─ management/
│  │  └─ commands/
│  │     ├─ sanitize_manual_blocks.py
│  │     └─ cleanup_manual_files.py
│  │
│  └─ templates/
│     └─ manual/
│        ├─ manual_list.html
│        ├─ manual_detail.html
│        ├─ rules_home.html
│        └─ _partials/
│           ├─ create_manual_modal.html
│           ├─ manual_detail_boot.html
│           ├─ manual_detail_superuser_assets.html
│           └─ manual_list_scripts.html
│
├─ static/
│  ├─ css/
│  │  ├─ base.css
│  │  ├─ fixes.css
│  │  └─ apps/
│  │     └─ manual.css
│  │
│  └─ js/
│     └─ manual/
│        ├─ _shared.js
│        ├─ create_manual_modal.js
│        ├─ manual_list_boot.js
│        ├─ manual_list_edit.js
│        ├─ manual_detail_section_sort.js
│        ├─ manual_detail_subnav.js
│        └─ manual_detail_block/
│           ├─ index.js
│           ├─ quill.js
│           ├─ section_subnav.js
│           └─ sort_blocks.js
│
├─ templates/
│  └─ base.html
│
└─ web_ma/
   ├─ settings.py
   ├─ urls.py
   ├─ views.py
   └─ middleware.py
```

참고로 별도 공유된 `django_ma/management/commands/cleanup_missing_manual_images.py`도 존재합니다. 현재 기준에서는 `manual/management/commands/cleanup_manual_files.py`가 더 확장된 정리 명령으로 보이며, 중복 여부는 향후 성능/정리 점검 대상입니다.

---

## 3. Manual App SSOT 원칙

| 목적 | SSOT 파일/함수 |
|---|---|
| URL export | `manual/views/__init__.py` |
| URL 라우팅 | `manual/urls.py` |
| 접근 권한 정책 | `manual/utils/permissions.py` |
| 매뉴얼 접근 필터 | `filter_manuals_for_user()` |
| 상세 접근 차단 | `manual_accessible_or_denied()` |
| superuser AJAX 권한 | `ensure_superuser_or_403()` |
| JSON 응답 포맷 | `manual/utils/http.py`의 `ok()`, `fail()` |
| JSON body 파싱 | `json_body()` |
| 문자열/숫자 파싱 | `manual/utils/parsing.py` |
| 기본 섹션 생성 | `ensure_default_section()` |
| 공개 범위 매핑 | `access_to_flags()` |
| HTML sanitize | `manual/utils/sanitize.py`의 `sanitize_quill_html()` |
| 업로드 확장자/MIME/크기 정책 | `manual/constants.py`, `manual/utils/uploads.py` |
| block/attachment 직렬화 | `manual/utils/serializers.py` |
| 첨부 다운로드 URL | `attachment_to_dict()` |
| 이미지 보호 URL | `block_to_dict()` |
| Manual JS 공용 fetch/CSRF/error | `static/js/manual/_shared.js` |
| 목록 편집 JS | `static/js/manual/manual_list_edit.js` |
| 상세 블록 orchestration | `static/js/manual/manual_detail_block/index.js` |
| Quill manager | `manual_detail_block/quill.js` |
| 섹션/목차 sync | `manual_detail_block/section_subnav.js`, `manual_detail_subnav.js` |
| 블록 정렬/이동 | `manual_detail_block/sort_blocks.js` |
| 앱 전용 CSS | `static/css/apps/manual.css` |
| 전역 CSS 토큰 | `static/css/base.css` |
| 전역 최소 fix | `static/css/fixes.css` |

---

## 4. 권한 정책 지침

### 4.1 사용자 등급 기준

| 등급 | 의미 |
|---|---|
| `superuser` | 전체 관리 권한 |
| `head` | 관리자성 사용자. 매뉴얼 admin 전용 문서 접근 가능 |
| `leader` | 일반 운영 사용자. admin 전용 문서 접근 불가 |
| `basic` | 일반 사용자 |
| `inactive` | 비활성 사용자. 기본적으로 접근 제한 대상 |

과거 `main_admin`, `sub_admin`은 legacy 등급이며, 앞으로는 각각 `head`, `leader`로 전환하는 기준을 따릅니다. Manual app의 신규 코드나 패치에서는 legacy 등급 호환을 확장하지 않는 것이 원칙입니다.

### 4.2 매뉴얼 노출 정책

Manual 모델의 접근 제어 필드는 다음 두 가지입니다.

| 필드 | 의미 |
|---|---|
| `admin_only=True` | `superuser`, `head`만 접근 가능 |
| `is_published=False` | `superuser`만 접근 가능. 코드 주석상 직원전용/비공개 개념 |

`manual/utils/permissions.py`의 `filter_manuals_for_user(qs, user)`가 목록 노출 정책의 SSOT입니다.

```text
if grade != "superuser":
    is_published=True만 표시

if grade not in ("superuser", "head"):
    admin_only=False만 표시
```

| 사용자 | 일반 문서 | 관리자 전용 | 비공개/직원전용 |
|---|---:|---:|---:|
| superuser | 가능 | 가능 | 가능 |
| head | 가능 | 가능 | 불가 |
| leader | 가능 | 불가 | 불가 |
| basic | 가능 | 불가 | 불가 |
| inactive | 원칙적으로 접근 불가 | 원칙적으로 접근 불가 | 원칙적으로 접근 불가 |

### 4.3 상세 접근 정책

`manual_accessible_or_denied(request, manual)`이 상세 접근 차단의 SSOT입니다.

```text
manual.admin_only=True:
    superuser/head만 접근

manual.is_published=False:
    superuser만 접근
```

접근 불가 시 `no_permission_popup.html`을 렌더링합니다.

### 4.4 쓰기 권한 정책

Manual app의 AJAX 쓰기 API는 모두 `superuser` 전용입니다.

```python
@require_POST
@login_required
def some_ajax(request):
    denied = ensure_superuser_or_403(request)
    if denied:
        return denied
```

적용 대상:

- `manual_create_ajax`
- `manual_update_title_ajax`
- `manual_bulk_update_ajax`
- `manual_reorder_ajax`
- `manual_delete_ajax`
- `manual_section_add_ajax`
- `manual_section_title_update_ajax`
- `manual_section_delete_ajax`
- `manual_section_reorder_ajax`
- `manual_block_add_ajax`
- `manual_block_update_ajax`
- `manual_block_delete_ajax`
- `manual_block_reorder_ajax`
- `manual_block_move_ajax`
- `manual_block_attachment_upload_ajax`
- `manual_block_attachment_delete_ajax`

---

## 5. URL 구조와 view export 지침

### 5.1 URL SSOT

`manual/urls.py`가 URL SSOT입니다.

```text
manual/
├─ ""                                  manual_list
├─ "new/"                              manual_create
├─ "rules/"                            rules_home
├─ "<int:pk>/"                         manual_detail
├─ "<int:pk>/edit/"                    manual_edit
├─ "create-ajax/"                      manual_create_ajax
├─ "ajax/reorder/"                     manual_reorder_ajax
├─ "ajax/bulk-update/"                 manual_bulk_update_ajax
├─ "ajax/delete/"                      manual_delete_ajax
├─ "ajax/title-update/"                manual_update_title_ajax
├─ "ajax/section-add/"                 manual_section_add_ajax
├─ "ajax/section-title/update/"        manual_section_title_update_ajax
├─ "ajax/section/delete/"              manual_section_delete_ajax
├─ "ajax/section-reorder/"             manual_section_reorder_ajax
├─ "ajax/block-add/"                   manual_block_add_ajax
├─ "ajax/block/move/"                  manual_block_move_ajax
├─ "ajax/block-update/"                manual_block_update_ajax
├─ "ajax/block/delete/"                manual_block_delete_ajax
├─ "ajax/block-reorder/"               manual_block_reorder_ajax
├─ "ajax/block-attachment/upload/"     manual_block_attachment_upload_ajax
├─ "ajax/block-attachment/delete/"     manual_block_attachment_delete_ajax
├─ "attachments/<int:attachment_id>/download/" manual_attachment_download
└─ "blocks/<int:block_id>/image/"              manual_block_image
```

### 5.2 `manual.views` export SSOT

`manual/views/__init__.py`는 `manual.views` 패키지의 공식 export 목록입니다.

주의사항:

- 기존 `manual/views.py` 모놀리식 파일은 제거된 구조를 전제로 합니다.
- `manual/urls.py`는 반드시 `from . import views` 패턴을 유지합니다.
- view callable을 추가하면 `manual/views/__init__.py`의 import 및 `__all__`에도 반영합니다.
- 외부 import 호환을 위해 `from manual.views import manual_list`가 깨지지 않아야 합니다.

---

## 6. 모델 구조와 데이터 정합성

### 6.1 `Manual`

역할: 매뉴얼 문서 루트.

주요 필드:

| 필드 | 설명 |
|---|---|
| `title` | 매뉴얼 제목 |
| `content` | 구형/폼 기반 content. 현재 상세 블록 구조에서는 보조적 의미 |
| `admin_only` | 관리자 전용 여부 |
| `is_published` | 공개 여부 |
| `sort_order` | 목록 정렬 |
| `author` | 작성자 |
| `created_at`, `updated_at` | 생성/수정 시각 |

정렬/인덱스:

```python
ordering = ["sort_order", "-updated_at"]
indexes = [
    Index(["sort_order"]),
    Index(["-updated_at"]),
]
```

### 6.2 `ManualSection`

역할: 매뉴얼 상세의 섹션 카드.

| 필드 | 설명 |
|---|---|
| `manual` | 소속 Manual |
| `title` | 섹션 제목 |
| `sort_order` | 섹션 정렬 |
| `created_at`, `updated_at` | 생성/수정 시각 |

인덱스:

```python
Index(["manual", "sort_order"])
```

### 6.3 `ManualBlock`

역할: 섹션 안의 콘텐츠 블록.

| 필드 | 설명 |
|---|---|
| `manual` | 기존 호환용 FK |
| `section` | 소속 섹션. nullable 유지 |
| `title` | 블록 제목. 현재 UI에서는 주로 사용하지 않음 |
| `content` | Quill HTML |
| `image` | 블록 이미지 |
| `sort_order` | 블록 정렬 |
| `created_at`, `updated_at` | 생성/수정 시각 |

중요 동작:

- `save()`에서 `sanitize_quill_html(self.content)` 적용
- `delete()`에서 이미지 파일도 삭제
- attachments는 `on_delete=CASCADE`와 attachment 모델 delete 정책에 의존

주의:

- `manual`과 `section.manual`이 중복 근거가 될 수 있습니다.
- 현재는 기존 호환 유지를 위해 두 필드를 함께 둡니다.
- 리팩토링 시 데이터 정합성 검증이 필요합니다.

### 6.4 `ManualBlockAttachment`

역할: 블록 첨부파일.

| 필드 | 설명 |
|---|---|
| `block` | 소속 블록 |
| `file` | 실제 파일 |
| `original_name` | 원본 파일명 |
| `size` | 파일 크기 |
| `created_at` | 생성 시각 |

중요 동작:

- `save()`에서 `size`, `original_name` 자동 보정
- `delete()`에서 실제 파일도 삭제
- `validate_attachment_size()`로 20MB 제한

---

## 7. 페이지 view 지침

위치: `manual/views/pages.py`

### 7.1 `redirect_to_manual`

```python
@grade_required("superuser", "head", "leader", "basic")
def redirect_to_manual(request):
    return redirect("manual:manual_list")
```

### 7.2 `manual_list`

역할:

- 목록 노출 정책을 `filter_manuals_for_user()`에 위임
- inactive 사용자는 `not_inactive_required`로 차단
- 템플릿: `manual/manual_list.html`

주의:

- 목록 템플릿에서 `m.sections.all`을 사용하므로, 성능 개선 시 `prefetch_related("sections")` 검토 대상입니다.
- 기능 변화 0 리팩토링 시 출력 순서가 바뀌면 안 됩니다.

### 7.3 `manual_detail`

역할:

- 상세 접근 권한 최종 검증
- 섹션이 없으면 기본 섹션 생성
- 섹션/블록/첨부 prefetch
- 템플릿: `manual/manual_detail.html`

주의:

- GET 요청에서 `ensure_default_section()`이 DB write를 수행합니다.
- 운영/감사/트랜잭션 관점에서 향후 검토 대상이 될 수 있습니다.
- 다만 현재 UI 안정성을 위한 기준 동작으로 기억합니다.

### 7.4 `manual_create`, `manual_edit`

- `superuser` 전용 폼 기반 create/edit
- AJAX 기반 UI가 주 사용 경로지만, 관리용 fallback으로 유지
- 템플릿: `manual/manual_form.html`

### 7.5 `rules_home`

- `manual/rules_home.html` 렌더
- 현재 “영업기준안 제작중” 페이지

---

## 8. Manual AJAX view 지침

위치: `manual/views/manual.py`

### 8.1 `manual_create_ajax`

- 모달 기반 매뉴얼 생성
- `title`, `access` JSON 입력
- `access` 값은 `normal`, `admin`, `staff` 중 하나
- `access_to_flags()`로 `admin_only`, `is_published` 변환
- 생성 후 `redirect_url` 반환
- `ACTION.MANUAL_CREATE` audit 기록

### 8.2 `manual_update_title_ajax`

- 매뉴얼 제목 단건 수정
- `id`, `title` 검증
- `ACTION.MANUAL_UPDATE` audit 기록

### 8.3 `manual_bulk_update_ajax`

- 목록 편집모드에서 여러 매뉴얼 title/access 일괄 수정
- `transaction.atomic()` 사용
- item마다 `Manual` 조회 후 저장
- `ACTION.MANUAL_BULK_UPDATE` audit 기록

주의:

- 현재는 루프 내 개별 `get_object_or_404()` + `save()` 구조입니다.
- 대량 데이터가 많아질 경우 bulk update 최적화 검토 가능.
- 단, audit log 단위와 `updated_at` 갱신 정책 유지 여부를 먼저 결정해야 합니다.

### 8.4 `manual_reorder_ajax`

- 매뉴얼 목록 정렬 저장
- 중복 ID 검증
- 존재하지 않는 ID 검증
- `sort_order`를 순서대로 update
- `ACTION.MANUAL_REORDER` audit 기록

### 8.5 `manual_delete_ajax`

- 매뉴얼 삭제
- cascade로 section/block/attachment 삭제
- `ACTION.MANUAL_DELETE` audit 기록

주의:

- 파일 삭제는 `ManualBlock.delete()`와 `ManualBlockAttachment.delete()`를 거치는 전제입니다.
- Django cascade delete에서 개별 model `delete()` 호출 여부는 파일 정리 정책 점검 시 확인해야 합니다.

---

## 9. Section AJAX view 지침

위치: `manual/views/section.py`

### 9.1 `manual_section_add_ajax`

- 특정 매뉴얼에 섹션 추가
- 마지막 `sort_order` + 1로 생성
- `ACTION.MANUAL_SECTION_CREATE` 기록
- 새 섹션 id/sort_order/updated_at 반환

### 9.2 `manual_section_title_update_ajax`

- 섹션 소제목 수정
- `SECTION_TITLE_MAX_LEN` 검증
- `ACTION.MANUAL_SECTION_UPDATE` 기록

### 9.3 `manual_section_delete_ajax`

- 섹션 삭제
- 삭제 후 섹션이 0개가 되면 `ensure_default_section()`으로 기본 섹션 생성
- `ACTION.MANUAL_SECTION_DELETE` 기록
- 새 기본 섹션 생성 시 `new_section` 반환

### 9.4 `manual_section_reorder_ajax`

- 섹션 카드 순서 저장
- 요청 section_ids가 해당 manual의 실제 섹션 목록과 정확히 일치해야 함
- 중복 검증
- `transaction.atomic()` 사용
- `ACTION.MANUAL_SECTION_REORDER` 기록

정합성 규칙:

```text
set(requested_section_ids) == set(existing_section_ids_for_manual)
```

---

## 10. Block AJAX view 지침

위치: `manual/views/block.py`

### 10.1 `manual_block_add_ajax`

- 특정 manual/section에 블록 추가
- multipart 요청 처리
- 이미지가 있으면 `validate_manual_image()` 수행
- content는 `sanitize_quill_html()` 적용
- `ManualSection.objects.get(id=section_id, manual_id=manual_id)`로 소속 검증
- `sort_order`는 해당 섹션 내 count + 1
- `ACTION.MANUAL_BLOCK_CREATE` 기록
- `block_to_dict()` 반환

주의:

- `ManualBlock.save()`에서도 sanitize하므로 view와 model에서 sanitize가 중복 적용됩니다.
- 보안상 큰 문제는 아니나 성능/중복 개선 대상으로 검토 가능합니다.

### 10.2 `manual_block_update_ajax`

- 기존 블록 content/image 수정
- 이미지 새 업로드 시 MIME/확장자 검증
- `remove_image=1`이면 기존 이미지 삭제
- 새 이미지 업로드 시 기존 이미지 삭제 후 교체
- `transaction.atomic()` 사용
- `ACTION.MANUAL_BLOCK_UPDATE` 기록

주의:

- 파일 시스템은 DB 트랜잭션 rollback과 완전 동기화되지 않습니다.
- 운영 안전성 개선 시 `transaction.on_commit()` 기반 파일 삭제도 검토 가능합니다.

### 10.3 `manual_block_delete_ajax`

- 블록 삭제
- `ACTION.MANUAL_BLOCK_DELETE` 기록
- `b.delete()` 호출

### 10.4 `manual_block_reorder_ajax`

- 같은 섹션 내 블록 순서 저장
- 요청 block_ids가 해당 section의 실제 블록 목록과 정확히 일치해야 함
- 중복 검증
- `transaction.atomic()` 사용
- `ACTION.MANUAL_BLOCK_REORDER` 기록

정합성 규칙:

```text
set(requested_block_ids) == set(existing_block_ids_for_section)
```

### 10.5 `manual_block_move_ajax`

- 블록을 한 섹션에서 다른 섹션으로 이동
- from/to 섹션이 같은 manual 소속인지 검증
- from/to block 목록의 합집합이 실제 두 섹션의 block 목록과 일치하는지 검증
- `cleaned_to`가 비어 있으면 오류
- 이동 대상 블록의 `section_id`를 to section으로 update
- 양쪽 섹션의 sort_order 재정렬
- `ACTION.MANUAL_BLOCK_MOVE` 기록

정합성 규칙:

```text
from_sec.manual_id == to_sec.manual_id
set(from_block_ids + to_block_ids) == set(existing_blocks_in_from_and_to_sections)
```

---

## 11. Attachment / FileResponse 지침

위치: `manual/views/attachment.py`

### 11.1 기본 원칙

```text
.file.url 직접 노출 금지
→ 보호 view URL만 노출
→ view에서 로그인/권한 검증
→ FileResponse로 제공
```

이 원칙은 project-wide `/media/ 직접 서빙 금지` 원칙과 일치합니다.

### 11.2 `manual_block_attachment_upload_ajax`

- `superuser` 전용 첨부 업로드
- multipart 요청
- `block_id`, `file` 검증
- `validate_manual_attachment()`로 크기/확장자/MIME 검증
- `ManualBlockAttachment.objects.create()`
- `ACTION.MANUAL_ATTACHMENT_UPLOAD` 기록
- `attachment_to_dict()` 반환

### 11.3 `manual_block_attachment_delete_ajax`

- `superuser` 전용 첨부 삭제
- JSON 요청
- `attachment_id` 검증
- `ACTION.MANUAL_ATTACHMENT_DELETE` 기록
- `a.delete()`로 DB row 및 파일 삭제

### 11.4 `manual_attachment_download`

- 로그인 사용자 대상 보호 다운로드
- 첨부 row 조회
- 첨부가 속한 manual 계산
- `manual_accessible_or_denied()`로 접근 권한 검증
- `FileResponse(..., as_attachment=True)` 반환
- RFC5987 방식의 `Content-Disposition` 지정
- `ACTION.MANUAL_ATTACHMENT_DOWNLOAD` 기록

### 11.5 `manual_block_image`

- 로그인 사용자 대상 보호 이미지 inline 제공
- block row 조회
- block이 속한 manual 접근 권한 검증
- `FileResponse(..., as_attachment=False)` 반환
- `Cache-Control: private, max_age=3600` 적용

---

## 12. Utils 지침

### 12.1 `manual/utils/http.py`

```python
json_body(request) -> dict
ok(data=None) -> JsonResponse
fail(message, status=400, **extra) -> JsonResponse
```

지침:

- Manual AJAX 응답은 `ok()` / `fail()` 포맷으로 통일합니다.
- 신규 JSON endpoint에서 raw `JsonResponse`를 직접 만들지 않습니다.
- 파싱 실패 시 `json_body()`는 `{}`를 반환합니다.

### 12.2 `manual/utils/parsing.py`

```python
to_str(v)
is_digits(v)
```

- view 입력값 검증 시 공통 사용
- 숫자형 PK 검증은 `is_digits()`로 하고, 통과 후 `int()` 변환

### 12.3 `manual/utils/permissions.py`

```python
user_grade(user)
is_superuser(user)
is_head(user)
ensure_superuser_or_403(request)
filter_manuals_for_user(qs, user)
manual_accessible_or_denied(request, manual)
```

- 권한 조건문을 view마다 중복하지 않습니다.
- 신규 Manual 접근 정책은 이 파일에 반영합니다.

### 12.4 `manual/utils/rules.py`

```python
ensure_default_section(manual)
access_to_flags(access)
```

| access | admin_only | is_published |
|---|---:|---:|
| normal | False | True |
| admin | True | True |
| staff | False | False |

주의:

- UI에서는 `staff`를 “직원 전용”으로 표시하지만, 권한 정책상 `is_published=False`는 `superuser`만 접근 가능합니다.

### 12.5 `manual/utils/sanitize.py`

핵심 함수:

```python
sanitize_quill_html(html)
```

허용 태그:

```text
p, br, strong, b, em, i, u, s,
ol, ul, li,
blockquote, pre, code,
h1, h2, h3,
span, a
```

허용 속성:

```python
{
    "a": ["href", "title", "target", "rel"],
    "span": ["class"],
    "p": ["class"],
    "li": ["class"],
}
```

허용 프로토콜:

```text
http, https, mailto
```

보안 보강:

- dangerous tag 제거
- event handler 속성 제거
- `javascript:` 제거
- anchor에 `rel="noopener noreferrer"` 보장

주의:

- bleach 미설치 fallback이 존재하지만, 운영에서는 bleach 설치를 권장합니다.
- `style` 속성은 현재 allowlist에 포함되어 있지 않습니다.

### 12.6 `manual/utils/serializers.py`

```python
attachment_to_dict(a)
block_to_dict(b)
```

지침:

- 첨부 URL은 반드시 `reverse("manual:manual_attachment_download", args=[a.id])`
- 이미지 URL은 반드시 `reverse("manual:manual_block_image", args=[b.id])`
- `.file.url`, `.image.url` 직접 사용 금지

### 12.7 `manual/utils/uploads.py`

```python
validate_manual_attachment(upfile)
validate_manual_image(upfile)
```

| 검증 | 첨부 | 이미지 |
|---|---:|---:|
| 파일 존재 | 필수 | 이미지 없으면 통과 |
| 크기 | `MAX_ATTACHMENT_SIZE` 이하 | `MAX_ATTACHMENT_SIZE` 이하 |
| 확장자 | attachment allowlist | image allowlist |
| MIME | attachment allowlist | image allowlist |

---

## 13. 템플릿 구조 지침

### 13.1 `manual/manual_list.html`

역할:

- 매뉴얼 목록 렌더
- `superuser`는 생성/편집/정렬/삭제/일괄수정 UI 표시
- 일반 사용자는 목록 클릭 → 상세 이동

중요 DOM ID/class:

| 요소 | 용도 |
|---|---|
| `#manualListGroup` | 목록 root, JS 이벤트 위임 대상 |
| `.manual-item` | 개별 매뉴얼 항목 |
| `data-id` | 매뉴얼 ID |
| `data-access` | 공개 범위 |
| `data-href` | 편집모드 종료 시 복원할 href |
| `#btnManualEditMode` | 편집모드 진입 |
| `#btnManualSaveOrder` | 저장 |
| `#btnManualDone` | 완료 |
| `#manualEditCsrfForm` | JS CSRF 토큰 |
| `#manual-list-boot` | reorder/delete/bulk URL dataset |
| `.manual-title-text` | 표시 제목 |
| `.manual-title-input` | 편집 제목 |
| `.manual-access-select` | 공개 범위 선택 |
| `.btn-manual-delete` | 삭제 버튼 |

### 13.2 `manual/manual_detail.html`

역할:

- 매뉴얼 상세 페이지
- 섹션 카드, 블록, 이미지, 본문 표시
- `superuser` 전용 편집/정렬/삭제/추가 UI 포함

중요 DOM ID/class:

| 요소 | 용도 |
|---|---|
| `#manual-detail` | 상세 root |
| `#manualDetailTop` | 상단 기준 |
| `#manualSubnav` | 섹션 목차 |
| `.jsSubnavLink` | 목차 링크 |
| `#manualDetailBoot` | superuser AJAX URL dataset |
| `#manualSections` | 섹션 root |
| `.manual-section` | 섹션 카드 |
| `data-section-id` | 섹션 ID |
| `.sec-card-actions` | 섹션 이동/삭제 |
| `.jsSectionDragHandle` | 섹션 Sortable handle |
| `.btnDeleteSection` | 섹션 삭제 |
| `[data-role="secTitleText"]` | 섹션 제목 |
| `.btnEditSectionTitle` | 섹션 제목 수정 |
| `.manualBlocks` | 블록 목록 |
| `.manual-block` | 블록 카드 |
| `data-block-id` | 블록 ID |
| `data-image-url` | 보호 이미지 URL |
| `.jsManualImg` | 이미지 뷰어 trigger |
| `.manual-block-content` | Quill content 표시 |
| `.jsBlockDragHandle` | 블록 Sortable handle |
| `.btn-edit-block` | 블록 수정 |
| `.btn-delete-block` | 블록 삭제 |
| `.btn-add-block` | 블록 추가 |
| `#btnAddManualSection` | 섹션 추가 |
| `#btnManualGoTop` | TOP 이동 |

주의:

- 본문은 `{{ b.content|safe }}`로 출력됩니다.
- 따라서 서버단 sanitize가 필수 전제입니다.

### 13.3 `_partials/create_manual_modal.html`

| 요소 | 용도 |
|---|---|
| `#createManualModal` | modal root |
| `data-create-url` | 생성 AJAX URL |
| `#createManualForm` | form |
| `#manualTitleInput` | 제목 입력 |
| `name="manualAccess"` | 공개 범위 radio |
| `#manualCreateError` | 오류 박스 |
| `#btnCreateManualConfirm` | 생성 버튼 |

### 13.4 `_partials/manual_detail_boot.html`

역할:

- 상세 페이지 JS용 URL dataset 주입
- superuser가 아니면 같은 ID/키를 유지하되 빈 값 주입

중요 dataset:

```text
data-section-title-update-url
data-section-delete-url
data-block-delete-url
data-block-reorder-url
data-block-move-url
```

### 13.5 `_partials/manual_detail_superuser_assets.html`

구성:

| 요소 | 용도 |
|---|---|
| `#manualBlockCsrfForm` | CSRF token |
| `#manualImageViewer` | 이미지 전체보기 모달 |
| `#manualViewerImg` | viewer 이미지 |
| `#manualBlockModal` | 블록 add/edit 모달 |
| `data-add-url` | 블록 추가 URL |
| `data-update-url` | 블록 수정 URL |
| `data-attach-upload-url` | 첨부 업로드 URL |
| `data-manual-id` | 현재 manual ID |
| `#manualBlockImageInput` | 이미지 파일 입력 |
| `#manualBlockImagePreviewWrap` | 이미지 미리보기 wrapper |
| `#manualBlockRemoveImageWrap` | 기존 이미지 삭제 체크 wrapper |
| `#manualQuillAttachInput` | Quill 첨부 hidden input |
| `#manualQuillEditor` | Quill editor |
| `#manualBlockError` | 오류 박스 |
| `#btnManualBlockSave` | 저장 버튼 |

리소스:

- `vendor/quill/1.3.7/quill.snow.css`
- `vendor/quill/1.3.7/quill.min.js`
- `js/manual/_shared.js`

### 13.6 `_partials/manual_list_scripts.html`

- `js/manual/_shared.js`
- `vendor/sortablejs/1.15.2/Sortable.min.js`
- `js/manual/create_manual_modal.js`
- `js/manual/manual_list_edit.js`

### 13.7 `rules_home.html`

- 영업기준안 placeholder 페이지
- inline style이 존재하므로 앱 CSS 스코프 정리 후보입니다.

---

## 14. Manual JavaScript 지침

### 14.1 공통 규칙

```text
1. 템플릿의 id/class/data-*를 SSOT로 사용한다.
2. superuser 전용 스크립트는 superuser 템플릿 블록에서만 로드한다.
3. 중복 바인딩 방지를 위해 dataset.bound 또는 documentElement dataset guard를 사용한다.
4. AJAX는 ManualShared.postJson/postForm을 우선 사용한다.
5. CSRF는 hidden form에서 읽고, same-origin + X-Requested-With를 사용한다.
6. 동적 DOM 변경 후 Subnav sync를 유지한다.
```

### 14.2 `_shared.js`

전역 객체:

```javascript
window.ManualShared
```

제공 함수:

| 함수 | 용도 |
|---|---|
| `ready()` | DOM ready helper |
| `toStr()` | 문자열 정규화 |
| `isDigits()` | 숫자 문자열 검증 |
| `getCSRFTokenFromForm()` | form 내 CSRF 획득 |
| `setBtnLoading()` | 버튼 로딩 상태 |
| `showErrorBox()` | 오류 박스 표시 |
| `clearErrorBox()` | 오류 박스 초기화 |
| `safeReadJson()` | JSON/non-JSON 응답 방어 |
| `postJson()` | JSON POST |
| `postForm()` | FormData POST |
| `formatBytes()` | 파일 크기 표시 |

### 14.3 `create_manual_modal.js`

- 생성 모달 submit 처리
- title/access 검증
- JSON POST
- 성공 시 `redirect_url` 이동 또는 reload

중요 guard:

```javascript
if (!modal || modal.dataset.bound) return;
modal.dataset.bound = "true";
```

### 14.4 `manual_list_boot.js`

- `#manualListBoot` dataset을 `window.ManualListBoot`로 복사
- 현재 템플릿은 `#manual-list-boot`를 사용하며, `manual_list_edit.js`는 두 ID를 모두 fallback 처리합니다.
- `manual_list_boot.js`는 현재 구조에서 필수는 아닐 수 있으며 중복/legacy 검토 대상입니다.

### 14.5 `manual_list_edit.js`

- 목록 편집모드
- SortableJS 정렬
- 삭제
- 제목/access 일괄 수정
- 저장 시 bulk update + reorder 순차 호출

중요 동작:

- 편집모드 진입 시 href를 `javascript:void(0)`으로 바꾸고 원본 href를 `data-href`에 저장
- 완료 시 href 복원
- 저장 시 변경된 title/access만 `bulkUpdateUrl`로 전송한 뒤 전체 `ordered_ids`를 `reorderUrl`로 전송

### 14.6 `manual_detail_subnav.js`

- 섹션 목차 rebuild-safe 관리
- 동적 섹션 추가/삭제/제목 변경에 대응
- IntersectionObserver 기반 active 표시
- smooth scroll
- TOP 버튼 처리
- `window.ManualDetailSubnav` API 제공

전역 API:

```javascript
window.ManualDetailSubnav = {
  rebuild,
  rebuildNow,
  updateLinkText,
  removeLink,
}
```

### 14.7 `manual_detail_section_sort.js`

- 섹션 카드 Sortable 정렬
- `manual_section_reorder_ajax` 호출
- 실패 시 이전 순서 복원
- 성공/실패 시 Subnav 순서 sync

### 14.8 `manual_detail_block/index.js`

- 상세 블록 관리의 orchestration
- Quill manager 연결
- Section/Subnav manager 연결
- Sortable 연결
- 이미지 viewer
- 블록 add/edit/delete
- modal state 관리

중요 state:

```javascript
const state = {
  mode: "add",
  editingBlockId: null,
  currentSectionId: null,
  _previewBlobUrl: null,
};
```

### 14.9 `manual_detail_block/quill.js`

- Quill editor 생성/관리
- 첨부 업로드 후 링크 삽입
- getHtml/setHtml/reset 제공

중요 정책:

- 첨부는 `edit` 모드의 저장된 블록에서만 가능
- 새 블록은 먼저 저장 후 수정에서 첨부 가능
- 첨부 업로드 결과의 `att.url`을 링크로 삽입

### 14.10 `manual_detail_block/section_subnav.js`

- 섹션 추가/삭제/제목 수정
- Subnav rebuild
- 새 섹션 DOM builder 제공

주의:

- `buildSectionElement()`는 innerHTML로 동적 DOM을 생성합니다.
- 현재 title은 `toStr()`만 거칩니다.
- 서버에서 title 길이 검증은 하지만, 동적 DOM 삽입 시 HTML escape 여부는 향후 점검 대상입니다.

### 14.11 `manual_detail_block/sort_blocks.js`

- 각 `.manualBlocks`에 Sortable 적용
- 같은 섹션 내 reorder 저장
- 섹션 간 이동 저장
- 실패 시 같은 섹션 reorder는 DOM 복원, 섹션 간 이동 실패는 reload

주의:

- 초기 로드된 `.manualBlocks`에만 Sortable을 적용합니다.
- 새로 추가된 섹션의 `.manualBlocks`에도 Sortable을 적용해야 하는지는 향후 기능 점검 포인트입니다.

---

## 15. CSS 지침

### 15.1 전역 CSS와 앱 CSS 분리

| 파일 | 역할 |
|---|---|
| `static/css/base.css` | 전역 토큰/기본 UI |
| `static/css/fixes.css` | 전역 최소 fix |
| `static/css/apps/manual.css` | manual 전용 스타일 |

`base.html`은 core CSS를 먼저 로드하고, 각 앱은 `app_css` block에서 앱별 CSS를 로드합니다.

```django
{% block app_css %}
  <link rel="stylesheet" href="{% static 'css/apps/manual.css' %}?v=...">
{% endblock %}
```

### 15.2 `manual.css` 주요 범위

| 영역 | 선택자 예 |
|---|---|
| wide layout | `#manual-detail` |
| badges | `.manual-badge-admin`, `.manual-badge-staff` |
| list | `.manual-list-container`, `.manual-title-row` |
| detail section | `#manual-detail .manual-section`, `.sec-card-actions` |
| block grid | `.manual-block-grid`, `.manual-block-media` |
| FAB | `.manual-fab` |
| subnav | `.manual-subnav` |
| editor modal | `.manual-block-modal`, `.manual-quill-editor` |
| drag helpers | `.jsSectionDragHandle`, `.manual-sort-ghost` |

주의:

- `manual.css`에 `.navbar .dropdown-menu` 규칙이 있어 앱 CSS가 전역 navbar에 영향을 줍니다.
- 향후 no-leak 관점에서 점검 대상입니다.

---

## 16. Audit Logging 지침

Manual app은 주요 행위에 대해 `audit.services.log_action()`을 사용합니다.

| 행위 | ACTION |
|---|---|
| 매뉴얼 생성 | `ACTION.MANUAL_CREATE` |
| 매뉴얼 수정 | `ACTION.MANUAL_UPDATE` |
| 매뉴얼 일괄 수정 | `ACTION.MANUAL_BULK_UPDATE` |
| 매뉴얼 정렬 | `ACTION.MANUAL_REORDER` |
| 매뉴얼 삭제 | `ACTION.MANUAL_DELETE` |
| 섹션 생성 | `ACTION.MANUAL_SECTION_CREATE` |
| 섹션 수정 | `ACTION.MANUAL_SECTION_UPDATE` |
| 섹션 삭제 | `ACTION.MANUAL_SECTION_DELETE` |
| 섹션 정렬 | `ACTION.MANUAL_SECTION_REORDER` |
| 블록 생성 | `ACTION.MANUAL_BLOCK_CREATE` |
| 블록 수정 | `ACTION.MANUAL_BLOCK_UPDATE` |
| 블록 삭제 | `ACTION.MANUAL_BLOCK_DELETE` |
| 블록 정렬 | `ACTION.MANUAL_BLOCK_REORDER` |
| 블록 이동 | `ACTION.MANUAL_BLOCK_MOVE` |
| 첨부 업로드 | `ACTION.MANUAL_ATTACHMENT_UPLOAD` |
| 첨부 삭제 | `ACTION.MANUAL_ATTACHMENT_DELETE` |
| 첨부 다운로드 | `ACTION.MANUAL_ATTACHMENT_DOWNLOAD` |

지침:

- 중요 쓰기 작업에는 audit log를 남깁니다.
- 첨부 다운로드도 audit 대상입니다.
- 로그 meta에는 민감정보를 과도하게 넣지 않습니다.
- 파일명/크기/block_id/manual_id 정도는 운영 추적에 유효합니다.

---

## 17. Management Command 지침

### 17.1 `sanitize_manual_blocks.py`

역할:

- 과거 저장된 `ManualBlock.content`에 `sanitize_quill_html()` 백필
- 기본은 dry-run
- `--apply` 지정 시 DB 반영
- `--batch-size` 지원
- `bulk_update()`로 content만 갱신
- `updated_at`은 갱신하지 않는 의도적 정책

사용 예:

```bash
python manage.py sanitize_manual_blocks
python manage.py sanitize_manual_blocks --apply
python manage.py sanitize_manual_blocks --apply --batch-size 200
```

### 17.2 `cleanup_manual_files.py`

역할:

- ManualBlock.image 누락 파일 참조 점검
- ManualBlockAttachment.file 누락 파일 참조 점검
- 기본 dry-run
- `--apply` 시 누락 이미지 참조 제거
- `--delete-missing-attachments --force` 조합 시 누락 첨부 row 삭제 가능
- 누락 첨부 삭제 시 audit log 기록

사용 예:

```bash
python manage.py cleanup_manual_files
python manage.py cleanup_manual_files --apply
python manage.py cleanup_manual_files --apply --delete-missing-attachments --force
```

### 17.3 `cleanup_missing_manual_images.py`

- 존재하지 않는 이미지 파일을 참조하는 `ManualBlock.image` 값 정리
- 기본 dry-run
- `--apply` 시 image 필드 제거
- `cleanup_manual_files.py`와 역할이 중복되므로 향후 정리/모듈화 후보입니다.

---

## 18. 공통 인프라 의존 지침

### 18.1 `web_ma/urls.py`

중요 원칙:

```text
/media/ 직접 서빙 금지
파일 접근은 반드시 앱별 보호 view에서 권한 검증 후 FileResponse로 제공
DEBUG에서도 동일 원칙 유지
```

Manual app은 다음 보호 view를 사용합니다.

```text
manual:manual_attachment_download
manual:manual_block_image
```

### 18.2 `templates/base.html`

Manual 관련 의존:

- 인증 사용자 navbar에서 매뉴얼 메뉴 노출
- `user.is_active`일 때 manual 메뉴 표시
- `manual:manual_list`
- `manual:rules_home`
- `app_css` block에서 `manual.css` 로드
- `content_wrapper` block으로 manual list/detail이 wrapper 재정의 가능
- `privacy-watermark` 전역 표시

주의:

- base.html의 navbar 권한과 manual view 권한은 별도입니다.
- 메뉴에서 보이지 않아도 URL 직접 접근은 view 권한에서 최종 차단해야 합니다.

### 18.3 `web_ma/settings.py`

Manual app과 관련 있는 설정:

| 설정 | 관련성 |
|---|---|
| `INSTALLED_APPS` | `"manual"` 포함 |
| `MEDIA_ROOT`, `MEDIA_URL` | 파일 저장 경로 |
| `STATICFILES_STORAGE` | 운영 정적파일 manifest |
| `CONTENT_SECURITY_POLICY` | Quill/inline style/script 영향 |
| `LOGGING` | manual logger가 별도로 없으므로 root/django.request 의존 |
| `SECURE_*` | 운영 보안 헤더/쿠키 |
| `DATA_UPLOAD_MAX_NUMBER_FIELDS` | 대량 폼 제출 방어 |

### 18.4 `web_ma/middleware.py`

관련 미들웨어:

| 미들웨어 | 관련성 |
|---|---|
| `SecurityHeadersMiddleware` | CSP/Referrer/Permissions/COOP/X-Frame 보강 |
| `ForceCSRFCookieOnLoginMiddleware` | 로그인 CSRF 쿠키 안정화 |
| `CleanupLegacyCSRFCookieMiddleware` | 운영 CSRF 중복 쿠키 정리 |
| `audit.middleware.RequestLogMiddleware` | 요청 로그 |

---

## 19. 업로드/다운로드 보안 지침

### 19.1 업로드 제한

기준 상수:

```python
MAX_ATTACHMENT_SIZE = 20 * 1024 * 1024
MANUAL_ALLOWED_ATTACHMENT_EXTENSIONS = {...}
MANUAL_ALLOWED_ATTACHMENT_MIME_TYPES = {...}
MANUAL_ALLOWED_IMAGE_EXTENSIONS = {...}
MANUAL_ALLOWED_IMAGE_MIME_TYPES = {...}
```

지침:

- 신규 첨부/이미지 업로드 view는 반드시 `validate_manual_attachment()` 또는 `validate_manual_image()` 사용
- 클라이언트 accept 속성만 믿지 않음
- 모델 validator만 믿지 않음
- 서버단 검증이 최종

### 19.2 다운로드 제한

지침:

- 템플릿/serializer/JS에서 `a.file.url` 사용 금지
- `manual_attachment_download`에서 권한 검증 후 제공
- `manual_block_image`에서 권한 검증 후 제공
- `FileResponse` 사용
- 다운로드 행위는 audit log 대상

### 19.3 파일명 처리

현재 다운로드는 다음 로직을 사용합니다.

```python
filename = a.original_name or os.path.basename(a.file.name)
quoted = quote(filename)
response["Content-Disposition"] = f"attachment; filename*=UTF-8''{quoted}"
```

지침:

- 한글 파일명 깨짐 방지를 위해 RFC5987 방식을 유지합니다.
- board app의 `open_fileresponse_from_fieldfile` 방식과 통일 가능성은 향후 리팩토링 후보입니다.

---

## 20. HTML Sanitization 지침

Manual app은 `ManualBlock.content`를 `safe`로 렌더링합니다.

따라서 서버단 sanitize가 필수입니다.

현재 sanitize 적용 지점:

| 위치 | 적용 방식 |
|---|---|
| `manual_block_add_ajax` | view에서 sanitize |
| `manual_block_update_ajax` | view에서 sanitize |
| `ManualBlock.save()` | model save에서 sanitize |
| `sanitize_manual_blocks` | 과거 데이터 백필 |

지침:

- Quill HTML 저장 전 sanitize는 서버에서 수행합니다.
- 클라이언트 Quill은 보안 경계가 아닙니다.
- `|safe` 사용은 sanitize 완료 데이터라는 전제에서만 허용합니다.
- sanitize 정책 변경 시 `sanitize_manual_blocks` 백필 실행 여부를 검토합니다.

---

## 21. 성능·정합성 관점에서 기억할 구조

아직 구체적인 개선안은 별도 단계에서 다룹니다. 다만 향후 성능 점검 시 반드시 확인할 구조는 다음과 같습니다.

### 21.1 Query 관련

| 위치 | 확인 포인트 |
|---|---|
| `manual_list` | `m.sections.all` 사용으로 목록에서 N+1 가능성 |
| `manual_detail` | `prefetch_related("blocks", "blocks__attachments")` 적용됨 |
| `block_to_dict` | attachments `.all().order_by()` 호출 |
| reorder views | 루프 update 구조 |
| bulk update | 루프 get/save 구조 |

### 21.2 파일 정리 관련

| 위치 | 확인 포인트 |
|---|---|
| `ManualBlock.delete()` | 이미지 삭제 |
| `ManualBlockAttachment.delete()` | 첨부 파일 삭제 |
| cascade delete | model delete 호출 여부와 실제 파일 삭제 보장 |
| cleanup commands | 중복 command 존재 가능성 |

### 21.3 JS 관련

| 위치 | 확인 포인트 |
|---|---|
| `_shared.js` | 중복 로드 guard 있음 |
| `manual_detail.html` | `_shared.js`, create modal script 중복 로드 가능 |
| `sort_blocks.js` | 신규 섹션 추가 후 Sortable 재적용 여부 |
| `section_subnav.js` | innerHTML 기반 동적 DOM 생성 |
| `manual_list_boot.js` | 현재 DOM ID와 불일치 가능성 있는 legacy wrapper |
| `manual_detail_subnav.js` | IntersectionObserver rebuild 비용 |

### 21.4 CSS 관련

| 위치 | 확인 포인트 |
|---|---|
| `manual.css` | `.navbar .dropdown-menu` 전역 영향 |
| `rules_home.html` | inline style |
| manual wide layout | `72vw` / max 1200px 기준 |
| FAB z-index | modal/navbar와 충돌 여부 |

---

## 22. 회귀 위험 Top 체크리스트

### 22.1 권한/보안

- [ ] `superuser` 외 사용자가 AJAX 쓰기 API를 호출할 수 없는가?
- [ ] `head`는 `admin_only=True` 문서 접근 가능, `is_published=False` 문서 접근 불가인가?
- [ ] `leader/basic`은 일반 문서만 접근 가능한가?
- [ ] inactive 사용자는 manual list/detail 접근이 차단되는가?
- [ ] 첨부 다운로드는 권한 검증 후에만 가능한가?
- [ ] 이미지 표시도 보호 view를 거치는가?
- [ ] `.file.url`, `.image.url` 직접 노출이 없는가?
- [ ] `{{ b.content|safe }}`의 전제인 sanitize가 유지되는가?
- [ ] Quill 첨부 링크가 보호 다운로드 URL을 사용하는가?

### 22.2 URL/템플릿

- [ ] `manual/views/__init__.py` export 목록이 URL과 일치하는가?
- [ ] `manual/urls.py` name이 JS dataset과 일치하는가?
- [ ] `#manualDetailBoot` ID가 유지되는가?
- [ ] `#manualSections`, `.manual-section`, `.manualBlocks`, `.manual-block` 구조가 유지되는가?
- [ ] `#manual-list-boot` dataset이 유지되는가?
- [ ] `createManualModal` 관련 ID가 유지되는가?

### 22.3 JS

- [ ] `_shared.js`가 superuser 화면에서 먼저 로드되는가?
- [ ] SortableJS가 필요한 페이지에서만 로드되는가?
- [ ] 목록 편집모드에서 링크 이동 차단/복원이 정상인가?
- [ ] 섹션 추가/삭제/제목 변경 후 Subnav가 즉시 갱신되는가?
- [ ] 블록 추가/수정 후 DOM이 정상 갱신되는가?
- [ ] 첨부 업로드 후 Quill 링크가 삽입되는가?
- [ ] 이미지 미리보기 blob URL이 modal 종료 시 revoke되는가?
- [ ] BFCache/pageshow 중복 바인딩이 발생하지 않는가?

### 22.4 CSS/UI

- [ ] `manual.css`가 manual 페이지에서만 로드되는가?
- [ ] base.css/fixes.css와 충돌하지 않는가?
- [ ] 모바일에서 목록/상세/subnav가 깨지지 않는가?
- [ ] navbar dropdown이 subnav에 가려지지 않는가?
- [ ] modal z-index와 FAB z-index 충돌이 없는가?

### 22.5 운영

- [ ] `python manage.py check` 통과
- [ ] 정적파일 경로가 Manifest 환경에서 깨지지 않는가?
- [ ] Quill/Sortable vendor 파일이 static에 존재하는가?
- [ ] 첨부 업로드/다운로드 시 한글 파일명이 정상인가?
- [ ] audit log가 기록되는가?
- [ ] 오류 발생 시 서버 로그에 traceback이 남는가?

---

## 23. 최소 검증 시나리오

### 23.1 공통

```bash
python manage.py check
```

### 23.2 권한별 화면 진입

| 계정 | 확인 |
|---|---|
| superuser | 목록/상세/생성/편집/삭제 UI 노출 |
| head | admin 전용 문서 접근 가능, 편집 UI 미노출 |
| leader | 일반 문서만 접근 |
| basic | 일반 문서만 접근 |
| inactive | 접근 차단 |

### 23.3 매뉴얼 목록

- [ ] 목록 표시
- [ ] 새 매뉴얼 생성 모달 열림
- [ ] 제목 누락 시 오류 표시
- [ ] 생성 성공 시 상세로 redirect
- [ ] 편집모드 진입
- [ ] 제목/access 변경 후 저장
- [ ] 드래그 정렬 후 저장
- [ ] 삭제 동작

### 23.4 매뉴얼 상세

- [ ] 섹션 목차 표시
- [ ] 목차 클릭 시 해당 섹션으로 scroll
- [ ] 섹션 추가
- [ ] 섹션 제목 수정
- [ ] 섹션 삭제
- [ ] 섹션 정렬
- [ ] 블록 추가
- [ ] 블록 수정
- [ ] 블록 삭제
- [ ] 블록 정렬
- [ ] 블록 섹션 간 이동
- [ ] 이미지 클릭 viewer
- [ ] TOP 버튼

### 23.5 첨부/이미지

- [ ] 허용 이미지 업로드 가능
- [ ] 허용되지 않는 확장자 차단
- [ ] 허용되지 않는 MIME 차단
- [ ] 20MB 초과 차단
- [ ] 첨부 업로드 후 Quill 링크 삽입
- [ ] 링크 클릭 시 다운로드 view 경유
- [ ] 권한 없는 사용자가 첨부 URL 직접 접근 시 차단
- [ ] 이미지 URL 직접 접근도 권한 검증

### 23.6 운영 유사

- [ ] `collectstatic` 후 Quill/Sortable/static 경로 정상
- [ ] Manifest storage에서 `?v=`와 static path 충돌 없음
- [ ] CSP 적용 상태에서 Quill editor 정상 작동
- [ ] audit log 저장
- [ ] 500 발생 시 `django_error.log` 기록

---

## 24. 향후 패치 응답 표준

### 24.1 버그 원인 분석 요청

해결책 제시 금지가 있으면 다음만 제공합니다.

1. 현상 요약
2. 원인 후보 Top N
3. 프로젝트 규약 관점 근거
4. 원인 확정에 필요한 관측 포인트

코드 패치나 명령은 제시하지 않습니다.

### 24.2 코드 수정/패치 요청

반드시 다음을 포함합니다.

1. 변경 목적
2. 수정 파일 목록 + 영향도
3. diff patch
4. 로컬 검증 체크리스트
5. 운영 배포 시 주의사항

### 24.3 리팩토링 요청

반드시 다음을 포함합니다.

1. 기능 변화 0 보장 포인트
2. 삭제/통합 대상 근거
3. 대체 SSOT 위치
4. 회귀 위험
5. diff patch

### 24.4 설계 요청

반드시 다음을 포함합니다.

1. 기존 구조와 SSOT
2. 변경 대상 범위
3. URL/API 계약
4. 템플릿 dataset 계약
5. 권한/감사 로그
6. 마이그레이션/백필/롤백
7. MVP → 확장 단계

---

## 25. Manual App 금지 패턴

- [ ] 첨부파일을 `.file.url`로 직접 노출
- [ ] 블록 이미지를 `.image.url`로 직접 노출
- [ ] 권한 검증 없이 `FileResponse` 반환
- [ ] superuser AJAX에 `ensure_superuser_or_403()` 누락
- [ ] JSON 응답 포맷을 제각각 생성
- [ ] `manual.views.__init__` export 누락
- [ ] 템플릿 ID/class/data-* 변경 후 JS 미점검
- [ ] Quill HTML을 sanitize 없이 `|safe` 출력
- [ ] CDN 리소스 재도입
- [ ] 앱 전용 CSS를 `base.css`에 추가
- [ ] manual.css에서 불필요한 전역 선택자 확대
- [ ] legacy 등급 `main_admin/sub_admin` 신규 확장
- [ ] 운영 설정/CSP/Whitenoise를 임시로 완화해 해결

---

## 26. 기준 결론

현재 Manual app은 다음 기준 구조를 가집니다.

```text
Model:
  Manual → ManualSection → ManualBlock → ManualBlockAttachment

View:
  pages/manual/section/block/attachment 모듈 분리
  views/__init__.py re-export SSOT

Permission:
  목록: filter_manuals_for_user()
  상세: manual_accessible_or_denied()
  쓰기: ensure_superuser_or_403()

Security:
  content sanitize
  protected FileResponse
  upload extension/MIME/size 검증
  audit logging

Frontend:
  ManualShared 공용 유틸
  dataset boot
  superuser-only assets
  SortableJS
  Quill local vendor
  Subnav rebuild-safe 구조

CSS:
  base.css / fixes.css / apps/manual.css 분리
```

향후 취약점 보완과 성능 개선은 이 문서를 기준으로 수행합니다.
