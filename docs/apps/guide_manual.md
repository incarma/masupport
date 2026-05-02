# manual 앱 개발 가이드

> 외부 LLM이 전체 코드 없이 이 앱을 정확하게 디벨롭할 수 있도록 작성된 문서다.
> 실제 파일명 · 함수명 · id명을 그대로 사용한다.

---

## 1. 앱 책임 요약

`manual`은 **Quill 기반 WYSIWYG 업무 매뉴얼 지식 관리 시스템**이다.  
`Manual → ManualSection → ManualBlock` 3단 계층 구조로 콘텐츠를 관리하며, 섹션·블록 단위 드래그 정렬, 이미지/첨부파일 업로드, SortableJS 기반 섹션 간 블록 이동을 지원한다.  
편집(생성·수정·삭제·정렬)은 `superuser`만 가능하고, 조회 권한은 `admin_only` · `is_published` 플래그로 grade별로 제한된다.

---

## 2. 디렉터리 구조

```
manual/
├── __init__.py
├── admin.py                          # 비어있음 (Admin 미등록)
├── apps.py                           # ManualConfig; verbose_name="업무 매뉴얼"
├── constants.py                      # 업로드 크기·확장자·MIME 상수 (SSOT)
├── forms.py                          # ManualForm (폼 기반 생성/수정, superuser only)
├── models.py                         # Manual, ManualSection, ManualBlock, ManualBlockAttachment
├── urls.py                           # 25개 URL (app_name="manual")
├── tests.py                          # (stub)
├── management/commands/
│   ├── cleanup_manual_files.py       # 오프라인 파일 정리 명령
│   ├── cleanup_missing_manual_images.py  # 미싱 이미지 DB 정리 명령
│   └── sanitize_manual_blocks.py    # 기존 블록 HTML 재살균 명령
├── migrations/                       # 0001_initial ~ 0009 (총 9개)
├── templates/manual/
│   ├── manual_list.html              # 매뉴얼 목록 (편집 모드 포함)
│   ├── manual_detail.html            # 매뉴얼 상세 (섹션·블록 편집 UI)
│   ├── rules_home.html               # 영업기준안 placeholder
│   └── _partials/
│       ├── create_manual_modal.html          # 매뉴얼 생성 모달
│       ├── manual_detail_boot.html           # superuser 전용 URL dataset 주입
│       ├── manual_detail_superuser_assets.html  # Quill·Sortable·블록편집 모달
│       └── manual_list_scripts.html          # 목록 JS 로드 순서
├── templatetags/
│   └── manual_sanitize.py            # sanitize_manual_html 필터 (mark_safe 래퍼)
├── utils/
│   ├── __init__.py
│   ├── http.py                       # json_body(), ok(), fail() 헬퍼
│   ├── parsing.py                    # to_str(), is_digits()
│   ├── permissions.py                # 접근 권한 SSOT (filter_manuals_for_user, manual_accessible_or_denied)
│   ├── rules.py                      # 도메인 규칙 (ensure_default_section, access_to_flags)
│   ├── sanitize.py                   # sanitize_quill_html() bleach 기반 HTML 살균
│   ├── serializers.py                # attachment_to_dict(), block_to_dict() JSON 직렬화
│   └── uploads.py                    # validate_manual_attachment(), validate_manual_image()
└── views/
    ├── __init__.py                   # 모든 뷰 re-export (urls.py 호환)
    ├── pages.py                      # HTML 페이지 뷰 (manual_list, manual_detail, ...)
    ├── manual.py                     # Manual AJAX 뷰
    ├── section.py                    # ManualSection AJAX 뷰
    ├── block.py                      # ManualBlock AJAX 뷰
    └── attachment.py                 # 첨부·이미지 AJAX + 다운로드 뷰

static/css/apps/manual.css           # manual 앱 전용 CSS (스코프: #manual-detail 등)
static/js/manual/
    ├── _shared.js                    # ManualShared 전역 객체 (AJAX 헬퍼, 공통 유틸)
    ├── create_manual_modal.js        # 매뉴얼 생성 모달 핸들러
    ├── manual_list_edit.js           # 목록 편집 모드 (type="module")
    ├── manual_detail_subnav.js       # sticky TOC navbar 및 스크롤 인터섹션
    ├── manual_detail_section_sort.js # 섹션 드래그 정렬 (SortableJS)
    └── manual_detail_block/
        ├── index.js                  # 블록 편집 전체 진입점 (type="module")
        ├── quill.js                  # Quill 에디터 + 첨부 업로드 관리
        ├── section_subnav.js         # 섹션 DOM 생성·제목편집·삭제·서브네비 갱신
        └── sort_blocks.js            # 블록 정렬 및 섹션 간 이동 (SortableJS)
```

---

## 3. 모델 구조

### Manual

```python
# manual/models.py
class Manual(models.Model):
    title       = CharField(max_length=80)
    content     = TextField(blank=True)          # 레거시 필드, 현재 Quill 블록 체계로 대체됨
    admin_only  = BooleanField(default=False)    # True: superuser/head만 접근
    is_published = BooleanField(default=True)   # False: superuser만 접근
    sort_order  = PositiveIntegerField(default=0, db_index=True)
    author      = ForeignKey(User, null=True, blank=True, on_delete=SET_NULL, related_name="manuals")
    created_at  = DateTimeField(auto_now_add=True)
    updated_at  = DateTimeField(auto_now=True)

    class Meta:
        ordering = ["sort_order", "-updated_at"]
        indexes = [...]  # (sort_order,), (is_published, admin_only)
```

### ManualSection

```python
class ManualSection(models.Model):
    manual      = ForeignKey(Manual, on_delete=CASCADE, related_name="sections")
    title       = CharField(max_length=120, blank=True, default="")
    sort_order  = PositiveIntegerField(default=0, db_index=True)
    created_at  = DateTimeField(auto_now_add=True)
    updated_at  = DateTimeField(auto_now=True)

    class Meta:
        ordering = ["sort_order", "created_at"]
        indexes = [Index(fields=["manual", "sort_order"])]
```

### ManualBlock

```python
class ManualBlock(models.Model):
    manual      = ForeignKey(Manual, on_delete=CASCADE, related_name="blocks")
    section     = ForeignKey(ManualSection, null=True, blank=True, on_delete=CASCADE, related_name="blocks")
    title       = CharField(max_length=120, blank=True, default="")
    content     = TextField(blank=True)          # Quill Delta → HTML. save() 시 sanitize 자동 실행
    image       = ImageField(upload_to="manual/blocks/", null=True, blank=True)
    sort_order  = PositiveIntegerField(default=0)
    created_at  = DateTimeField(auto_now_add=True)
    updated_at  = DateTimeField(auto_now=True)

    class Meta:
        ordering = ["sort_order", "created_at"]
        indexes = [Index(fields=["manual", "sort_order"]), Index(fields=["section", "sort_order"])]

    def save(self, *args, **kwargs):
        self.content = sanitize_quill_html(self.content)   # ⚠️ 자동 살균
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        # image 파일 자동 삭제
        if self.image:
            self.image.delete(save=False)
        super().delete(*args, **kwargs)
```

### ManualBlockAttachment

```python
class ManualBlockAttachment(models.Model):
    block        = ForeignKey(ManualBlock, on_delete=CASCADE, related_name="attachments")
    file         = FileField(upload_to="manual/attachments/", validators=[validate_attachment_size])
    original_name = CharField(max_length=255, blank=True, default="")
    size         = PositiveIntegerField(default=0)
    created_at   = DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]
        indexes = [Index(fields=["block", "created_at"])]

    def save(self, *args, **kwargs):
        # size, original_name 자동 채움
        ...
    def delete(self, *args, **kwargs):
        # 파일 자동 삭제
        if self.file:
            self.file.delete(save=False)
        super().delete(*args, **kwargs)
```

### 모델 간 관계 요약

```
Manual (1)
  └── ManualSection (N)  [manual.sections.all()]
        └── ManualBlock (N)  [section.blocks.all()]
              └── ManualBlockAttachment (N)  [block.attachments.all()]

Manual (1) ──── ManualBlock (N)  [manual.blocks.all()]
                (ManualBlock.manual = ForeignKey. section과 별개로 manual도 직접 참조)
```

⚠️ `ManualBlock.section`은 null 허용이다. 섹션 삭제 시 해당 블록들도 CASCADE 삭제된다.  
⚠️ `ManualBlock.manual` 과 `ManualBlock.section.manual`이 항상 동일해야 한다. 이를 어기는 블록 이동은 `manual_block_move_ajax`에서 서버가 방어한다.

### 운영 정책

- `ManualBlock.save()` 는 `sanitize_quill_html(self.content)`를 **자동 실행**한다.  
  → 뷰에서 별도 sanitize 없이 `block.content = html; block.save()`만 해도 안전하다.
- `Manual` 의 `is_published=False` + `admin_only=False` 조합 → superuser만 접근.  
  `admin_only=True` + `is_published=True` 조합 → superuser/head만 접근.
- 매뉴얼에 섹션이 0개가 되면 `ensure_default_section(manual)`이 자동으로 기본 섹션을 생성한다.

---

## 4. URL 네임스페이스 + 엔드포인트

**네임스페이스:** `manual`  
**prefix:** `/manual/` (web_ma/urls.py에서 include)

### HTML 페이지

| URL name | route | 메서드 | 반환 | 권한 |
|---|---|---|---|---|
| `manual_list` | `` (빈 경로) | GET | HTML | not_inactive_required |
| `manual_detail` | `<int:pk>/` | GET | HTML | not_inactive_required + 정책 체크 |
| `manual_create` | `new/` | GET, POST | HTML | superuser only |
| `manual_edit` | `<int:pk>/edit/` | GET, POST | HTML | superuser only |
| `rules_home` | `rules/` | GET | HTML | 제한 없음 (placeholder) |

### AJAX — Manual

| URL name | route | 메서드 | 반환 | 권한 |
|---|---|---|---|---|
| `manual_create_ajax` | `create-ajax/` | POST | JSON | superuser |
| `manual_update_title_ajax` | `ajax/title-update/` | POST | JSON | superuser |
| `manual_bulk_update_ajax` | `ajax/bulk-update/` | POST | JSON | superuser |
| `manual_reorder_ajax` | `ajax/reorder/` | POST | JSON | superuser |
| `manual_delete_ajax` | `ajax/delete/` | POST | JSON | superuser |

### AJAX — Section

| URL name | route | 메서드 | 반환 | 권한 |
|---|---|---|---|---|
| `manual_section_add_ajax` | `ajax/section-add/` | POST | JSON | superuser |
| `manual_section_title_update_ajax` | `ajax/section-title/update/` | POST | JSON | superuser |
| `manual_section_delete_ajax` | `ajax/section/delete/` | POST | JSON | superuser |
| `manual_section_reorder_ajax` | `ajax/section-reorder/` | POST | JSON | superuser |

### AJAX — Block

| URL name | route | 메서드 | 반환 | 권한 |
|---|---|---|---|---|
| `manual_block_add_ajax` | `ajax/block-add/` | POST (multipart) | JSON | superuser |
| `manual_block_update_ajax` | `ajax/block-update/` | POST (multipart) | JSON | superuser |
| `manual_block_delete_ajax` | `ajax/block/delete/` | POST | JSON | superuser |
| `manual_block_reorder_ajax` | `ajax/block-reorder/` | POST | JSON | superuser |
| `manual_block_move_ajax` | `ajax/block/move/` | POST | JSON | superuser |

### AJAX — Attachment / 파일

| URL name | route | 메서드 | 반환 | 권한 |
|---|---|---|---|---|
| `manual_block_attachment_upload_ajax` | `ajax/block-attachment/upload/` | POST (multipart) | JSON | superuser |
| `manual_block_attachment_delete_ajax` | `ajax/block-attachment/delete/` | POST | JSON | superuser |
| `manual_attachment_download` | `attachments/<int:attachment_id>/download/` | GET | FileResponse | not_inactive + 정책 |
| `manual_block_image` | `blocks/<int:block_id>/image/` | GET | FileResponse | not_inactive + 정책 |

### JSON 응답 표준 형식

```python
# 성공
{"ok": True, ...data}          # ok() 헬퍼 사용

# 실패
{"ok": False, "message": "..."}  # fail() 헬퍼 사용
```

`manual/utils/http.py` 의 `ok(data)`, `fail(message, status)` 함수가 SSOT다.

---

## 5. 권한 정책

**SSOT:** `manual/utils/permissions.py`

### 조회 권한

| 조건 | superuser | head | leader | basic | resign | inactive |
|---|---|---|---|---|---|---|
| `is_published=True`, `admin_only=False` | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ |
| `is_published=True`, `admin_only=True` | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ |
| `is_published=False`, `admin_only=False` | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ |
| `is_published=False`, `admin_only=True` | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ |

### 편집 권한

| 기능 | superuser | head | leader | basic |
|---|---|---|---|---|
| 매뉴얼 생성/수정/삭제/정렬 | ✅ | ❌ | ❌ | ❌ |
| 섹션 생성/수정/삭제/정렬 | ✅ | ❌ | ❌ | ❌ |
| 블록 생성/수정/삭제/정렬/이동 | ✅ | ❌ | ❌ | ❌ |
| 첨부 업로드/삭제 | ✅ | ❌ | ❌ | ❌ |

### 권한 강제 위치

```python
# manual/views/pages.py
@not_inactive_required
def manual_list(request):
    qs = Manual.objects.all()
    qs = filter_manuals_for_user(qs, request.user)   # ⚠️ 반드시 이 함수 경유
    ...

@not_inactive_required
def manual_detail(request, pk):
    manual = get_object_or_404(Manual, pk=pk)
    denied = manual_accessible_or_denied(request, manual)  # ⚠️ 반드시 이 함수 경유
    if denied:
        return denied
    ...

# 편집 뷰 (pages.py)
@grade_required("superuser")
def manual_create(request): ...

# AJAX 뷰 (manual.py, section.py, block.py, attachment.py)
@require_POST
@login_required
def manual_create_ajax(request):
    resp = ensure_superuser_or_403(request)   # ⚠️ AJAX 편집 권한 체크
    if resp: return resp
```

### `access` → `(admin_only, is_published)` 변환 SSOT

```python
# manual/utils/rules.py
def access_to_flags(access: str) -> tuple[bool, bool]:
    # "normal" → (False, True)   : 전체 공개
    # "admin"  → (True,  True)   : 관리자(superuser/head)만
    # "staff"  → (False, False)  : superuser만 (비공개)
```

프론트에서 `access` 라디오 값("normal"/"admin"/"staff")을 전송하면 서버에서 이 함수로 변환한다.

---

## 6. 서비스/유틸 레이어 SSOT 목록

### `manual/utils/permissions.py` ⚠️

| 함수 | 역할 |
|---|---|
| `user_grade(user) → str` | `user.grade` 안전 추출 |
| `is_superuser(user) → bool` | `grade == "superuser"` 판정 |
| `is_head(user) → bool` | `grade == "head"` 판정 |
| `ensure_superuser_or_403(request) → Optional[JsonResponse]` | AJAX 뷰의 superuser 권한 게이트 |
| `filter_manuals_for_user(qs, user) → QuerySet` | **목록 노출 정책 SSOT** — 반드시 이것만 경유 |
| `manual_accessible_or_denied(request, manual) → Optional[HttpResponse]` | **상세 접근 정책 SSOT** — 반드시 이것만 경유 |

⚠️ `Manual.objects.filter(is_published=True)` 를 직접 작성하면 `admin_only` 필터가 빠진다. 반드시 `filter_manuals_for_user(qs, user)`를 경유한다.

### `manual/utils/sanitize.py` ⚠️

| 함수 | 역할 |
|---|---|
| `sanitize_quill_html(html: str) → str` | bleach 기반 Quill HTML 살균. `ManualBlock.save()` 에서 자동 호출 |

⚠️ Quill 에디터에서 온 HTML을 DB에 저장하기 전에 반드시 이 함수를 거쳐야 한다.  
`ManualBlock.save()`가 자동 호출하므로 뷰에서 별도 호출이 중복되지 않도록 주의한다.

**허용 태그:** `p`, `br`, `div`, `span`, `strong`, `b`, `em`, `i`, `u`, `s`, `ul`, `ol`, `li`, `blockquote`, `pre`, `code`, `h1`~`h6`, `table`, `thead`, `tbody`, `tr`, `th`, `td`, `a`  
**허용 속성:** `href`, `title`, `target`, `rel` (a); `class`, `colspan`, `rowspan`  
**자동 추가:** `target="_blank"` 링크에 `rel="noopener noreferrer"` 강제

### `manual/utils/rules.py`

| 함수 | 역할 |
|---|---|
| `ensure_default_section(manual) → ManualSection` | 섹션 0개 상태를 방지, 없으면 기본 섹션 생성 |
| `access_to_flags(access: str) → tuple[bool, bool]` | "normal"/"admin"/"staff" → (admin_only, is_published) 변환 |

### `manual/utils/serializers.py` ⚠️

| 함수 | 역할 |
|---|---|
| `attachment_to_dict(a: ManualBlockAttachment) → dict` | 첨부파일 JSON 직렬화 — 업로드 응답에 사용 |
| `block_to_dict(b: ManualBlock) → dict` | 블록 전체 JSON 직렬화 — 블록 수정 응답에 사용 |

⚠️ 첨부파일 응답 구조는 `attachment_to_dict()`가 SSOT다. 프론트의 `quill.js` 가 이 구조를 기대한다.  
`{"id", "name", "url", "download_url", "size"}` 키를 임의로 변경하면 Quill 첨부 링크 삽입이 깨진다.

### `manual/utils/uploads.py` ⚠️

| 함수 | 역할 |
|---|---|
| `validate_manual_attachment(upfile) → str` | 첨부파일 확장자/MIME 검증. 오류 메시지 반환, 정상이면 `""` |
| `validate_manual_image(upfile) → str` | 이미지 파일 검증 |

⚠️ 첨부 업로드 시 반드시 `validate_manual_attachment()` → 오류 있으면 `fail()` 반환해야 한다.

### `manual/utils/http.py`

| 함수 | 역할 |
|---|---|
| `json_body(request) → dict` | `request.body` 안전 JSON 파싱 |
| `ok(data=None) → JsonResponse` | 성공 응답 `{"ok": True, ...data}` |
| `fail(message, status=400) → JsonResponse` | 실패 응답 `{"ok": False, "message": ...}` |

### `manual/constants.py` ⚠️

| 상수 | 값 | 용도 |
|---|---|---|
| `MAX_ATTACHMENT_SIZE` | `20 * 1024 * 1024` (20MB) | 첨부파일 최대 크기 |
| `MANUAL_ALLOWED_ATTACHMENT_EXTENSIONS` | `.pdf`, `.docx`, `.xlsx` 등 15개 | 허용 확장자 set |
| `MANUAL_ALLOWED_ATTACHMENT_MIME_TYPES` | 대응 MIME 16개 | 허용 Content-Type set |
| `MANUAL_ALLOWED_IMAGE_EXTENSIONS` | `.jpg`, `.jpeg`, `.png`, `.gif`, `.webp` | 이미지 허용 확장자 |
| `MANUAL_ALLOWED_IMAGE_MIME_TYPES` | 이미지 MIME 4개 | 이미지 허용 Content-Type |
| `MANUAL_TITLE_MAX_LEN` | `80` | Manual.title 최대 길이 |
| `SECTION_TITLE_MAX_LEN` | `120` | ManualSection.title 최대 길이 |
| `BLOCK_TITLE_MAX_LEN` | `120` | ManualBlock.title 최대 길이 |

⚠️ 허용 확장자/MIME 변경 시 이 파일만 수정하고, `uploads.py`가 이 상수를 참조한다.

### `manual/templatetags/manual_sanitize.py` ⚠️

| 필터 | 역할 |
|---|---|
| `sanitize_manual_html` | 템플릿에서 `{{ block.content\|sanitize_manual_html }}` 로 안전하게 렌더링 |

⚠️ `{{ block.content }}` 를 필터 없이 사용하면 XSS 위험이다.  
반드시 `{% load manual_sanitize %}` + `{{ block.content|sanitize_manual_html }}` 패턴을 사용한다.

---

## 7. 템플릿 구조

### 상속 관계

```
base.html
├── manual/manual_list.html
│   └── ({% include %}) _partials/create_manual_modal.html
│   └── ({% include %}) _partials/manual_list_scripts.html
└── manual/manual_detail.html
    ├── ({% include %}) _partials/create_manual_modal.html  (superuser only)
    ├── ({% include %}) _partials/manual_detail_boot.html   (superuser only)
    └── ({% include %}) _partials/manual_detail_superuser_assets.html  (superuser only)
```

⚠️ `_partials/` 하위 파일들은 직접 렌더링하지 않는다. 반드시 `{% include %}` 로만 사용한다.

### CSS 로드

두 메인 템플릿 모두 `{% block app_css %}` 블록에서 `manual.css`를 로드한다:

```html
{% block app_css %}
<link rel="stylesheet" href="{% static 'css/apps/manual.css' %}?v={% now 'U' %}">
{% endblock %}
```

### Vendor 라이브러리 로드 위치

`_partials/manual_detail_superuser_assets.html` 에서만 로드 (superuser일 때만 include):

```html
<!-- Quill 1.3.7 -->
<link href=".../quill.snow.css">
<script src=".../quill.min.js"></script>

<!-- SortableJS 1.15.2 -->
<script src="{% static 'js/vendor/sortablejs/1.15.2/Sortable.min.js' %}"></script>
```

SortableJS는 목록 편집 모드에서도 필요하므로 `manual_list_scripts.html`에도 별도 로드된다.

---

## 8. JS 부트 패턴

### `manual_list.html` — 목록 페이지

**루트 엘리먼트:** `#manualListGroup` (list-group 컨테이너)  
**부트 엘리먼트:** `#manual-list-boot`  

**`#manual-list-boot` dataset 계약 (변경 금지):**

| key | 연결 URL name |
|---|---|
| `data-reorder-url` | `manual:manual_reorder_ajax` |
| `data-delete-url` | `manual:manual_delete_ajax` |
| `data-bulk-update-url` | `manual:manual_bulk_update_ajax` |

**각 `.manual-item` 엘리먼트 dataset:**

| key | 설명 |
|---|---|
| `data-id` | Manual PK |
| `data-access` | `"normal"` / `"admin"` / `"staff"` |
| `data-href` | 상세 페이지 URL (편집 모드에서 링크 비활성화 시 저장용) |

**BFCache 가드:** `manual_list_edit.js` 는 `type="module"` 이므로 모듈 자체가 재실행되지 않는다.

---

### `manual_detail.html` — 상세 페이지

**루트 엘리먼트:** `#manual-detail` (wide layout wrapper)  
**BFCache 가드:** `document.documentElement.dataset.manualDetailBound` 플래그 (`index.js`에서 설정)

**`#manualSections` dataset:**

| key | 연결 URL name |
|---|---|
| `data-manual-id` | Manual PK |
| `data-section-add-url` | `manual:manual_section_add_ajax` |
| `data-section-reorder-url` | `manual:manual_section_reorder_ajax` |

**`#manualDetailBoot` dataset (superuser only, `_partials/manual_detail_boot.html`):**

| key | 연결 URL name |
|---|---|
| `data-section-title-update-url` | `manual:manual_section_title_update_ajax` |
| `data-section-delete-url` | `manual:manual_section_delete_ajax` |
| `data-block-delete-url` | `manual:manual_block_delete_ajax` |
| `data-block-reorder-url` | `manual:manual_block_reorder_ajax` |
| `data-block-move-url` | `manual:manual_block_move_ajax` |

**`#manualBlockModal` dataset (superuser only):**

| key | 연결 URL name |
|---|---|
| `data-add-url` | `manual:manual_block_add_ajax` |
| `data-update-url` | `manual:manual_block_update_ajax` |
| `data-attach-upload-url` | `manual:manual_block_attachment_upload_ajax` |
| `data-manual-id` | Manual PK |

**각 `.manual-section` dataset:**

| key | 설명 |
|---|---|
| `data-section-id` | ManualSection PK |

**각 `.manual-block` dataset:**

| key | 설명 |
|---|---|
| `data-block-id` | ManualBlock PK |
| `data-image-url` | `{% url 'manual:manual_block_image' block.id %}` 또는 `""` |

**서브내비 링크:** `.jsSubnavLink[data-target="sec-{section.id}"]` — 섹션 `id="sec-{section.id}"`로 스크롤

---

### JS 모듈 로드 순서 (`_partials/manual_detail_superuser_assets.html`)

1. `_shared.js` — `window.ManualShared` 전역 객체
2. Quill CDN
3. SortableJS
4. `create_manual_modal.js` — 매뉴얼 생성 모달
5. `manual_detail_block/index.js` (type="module") — 블록 편집 전체
6. `manual_detail_section_sort.js` — 섹션 정렬
7. `manual_detail_subnav.js` — sticky TOC

### `window.ManualShared` API (SSOT)

```javascript
// static/js/manual/_shared.js
window.ManualShared = {
  toStr(v),                                  // String(v ?? "").trim()
  isDigits(v),                               // /^\d+$/.test()
  ready(fn),                                 // DOMContentLoaded 안전 실행
  getCSRFTokenFromForm(formEl),              // formEl 내 csrfmiddlewaretoken 값
  setBtnLoading(btn, isLoading, loadingText, defaultText),
  showErrorBox(errBox, msg, fallbackAlert),
  clearErrorBox(errBox),
  safeReadJson(res),                         // fetch Response → JSON (에러 안전)
  postJson(url, bodyObj, csrfToken),         // JSON POST fetch wrapper
  postForm(url, formData, csrfToken),        // FormData POST fetch wrapper
  formatBytes(bytes),                        // "1.2 MB" 포맷
}
```

⚠️ 모든 JS 파일에서 AJAX는 `ManualShared.postJson()` / `postForm()` 만 사용한다. 직접 `fetch()` 작성 금지.

---

## 9. CSS 스코프 규약

**파일:** `static/css/apps/manual.css`

### 스코프 루트 선택자

| 선택자 | 용도 |
|---|---|
| `#manual-detail` | 상세 페이지 와이드 레이아웃 |
| `.manual-list-container` | 목록 max-width 800px 컨테이너 |
| `.manual-subnav` | sticky TOC navbar |
| `.manual-fab` | floating action button (우하단 고정) |
| `.manual-section` | 섹션 카드 |
| `.manual-block-grid` | 블록 이미지+텍스트 그리드 |

### CSS 변수

```css
/* manual.css 상단 */
:root {
  --manual-wide-width: 72vw;
  --manual-wide-max: 1200px;
}
```

### 전역 누수 방지 원칙

- `manual.css`의 모든 규칙은 `#manual-detail`, `.manual-*`, `.manual-list-container` 등 manual 전용 선택자 하위에서만 동작한다.
- `base.css` 수정 금지. 전역 스타일에 manual 전용 규칙을 추가하면 다른 앱 레이아웃이 깨진다.
- `manual_detail_superuser_assets.html`에 Quill snow 테마 CSS가 로드된다. `.ql-editor`, `.ql-toolbar` 스타일을 `base.css`에 추가하면 안 된다.

### 주요 CSS 클래스 (변경 시 JS와 동시 변경 필요)

| 클래스 | JS 의존 여부 |
|---|---|
| `.manual-item` | `manual_list_edit.js` 에서 querySelectorAll |
| `.manual-drag-handle` | SortableJS `handle` 옵션 |
| `.manual-editing` | 편집 모드 토글 클래스 |
| `.jsSectionDragHandle` | 섹션 정렬 SortableJS handle |
| `.jsBlockDragHandle` | 블록 정렬 SortableJS handle |
| `.jsSubnavLink` | 서브내비 클릭 스크롤 대상 |
| `.btn-edit-block`, `.btn-delete-block`, `.btn-add-block` | 블록 액션 위임 |
| `.manualBlocks` | 섹션 내 블록 컨테이너 (SortableJS 그룹) |
| `.manual-section` | 섹션 카드 (SortableJS draggable) |

---

## 10. 절대 수정 금지 목록

| 파일 | 금지 이유 |
|---|---|
| `manual/utils/permissions.py` `filter_manuals_for_user()` | 목록 노출 정책 변경 시 권한 없는 사용자(head 미만)에게 admin_only 매뉴얼 노출 위험 |
| `manual/utils/permissions.py` `manual_accessible_or_denied()` | 상세 접근 정책 변경 시 비공개 매뉴얼 무단 열람 위험 |
| `manual/utils/sanitize.py` `sanitize_quill_html()` allowlist | ALLOWED_TAGS에 `<script>`, `<iframe>` 추가 시 XSS 위험. allowlist는 최소한으로 유지 |
| `manual/templatetags/manual_sanitize.py` | 이 필터를 통하지 않고 `{{ block.content }}` 렌더링하면 저장된 HTML이 그대로 출력되어 XSS |
| `manual/utils/serializers.py` `attachment_to_dict()` 반환 키 | `quill.js`의 `insertAttachmentLink()`가 `{id, name, url, download_url, size}` 키를 기대. 변경 시 Quill 첨부 링크 삽입 기능 전체 파손 |
| `manual/constants.py` `MAX_ATTACHMENT_SIZE` | 20MB 초과 파일 허용 시 서버 디스크·메모리 위험 |
| `static/js/manual/_shared.js` `ManualShared` API | 모든 JS 모듈이 의존. 함수 시그니처 변경 시 연쇄 파손 |
| `.manual-section[data-section-id]`, `.manual-block[data-block-id]` | JS의 위임 이벤트와 SortableJS가 이 선택자로 PK를 읽음. 제거 시 정렬·삭제·이동 전체 파손 |
| `ManualBlock.save()` sanitize 호출 | 제거 시 Quill HTML이 sanitize 없이 DB에 저장됨. 추후 템플릿 렌더 시 XSS |

---

## 11. 다른 앱과의 의존 관계

### 이 앱이 의존하는 외부 SSOT

| 대상 | 파일 | 용도 |
|---|---|---|
| `accounts.decorators.grade_required` | `manual/views/pages.py` | superuser 전용 편집 뷰 접근 제어 |
| `accounts.decorators.not_inactive_required` | `manual/views/pages.py` | inactive grade 차단 |
| `audit.constants.ACTION` | `manual/views/*.py` | 감사 로그 액션 코드 (MANUAL_CREATE, MANUAL_BLOCK_CREATE 등) |
| `audit.services.log_action` | `manual/views/*.py` | 모든 CRUD에 감사 로그 기록 |
| `AUTH_USER_MODEL` (accounts.CustomUser) | `manual/models.py` `Manual.author` | 작성자 FK |

### 다른 앱이 이 앱에 의존하는 관계

현재 `manual` 앱을 import하는 다른 앱은 없다. 의존 방향이 단방향이다.

### 공용 컴포넌트 사용

`templates/components/search_user_modal.html` — 현재 manual에서 사용하지 않음.

---

## 12. 신규 기능 추가 패턴

### 신규 AJAX 뷰 추가 (예: 블록 복제)

1. `manual/views/block.py`에 뷰 함수 작성:
   - `ensure_superuser_or_403(request)` 호출 (편집 권한)
   - `json_body(request)` 로 payload 파싱
   - 성공이면 `ok({...})`, 실패면 `fail("...", 400)` 반환
   - `log_action(request, ACTION.MANUAL_BLOCK_CREATE, ...)` 호출
2. `manual/views/__init__.py`에 re-export 추가
3. `manual/urls.py`에 `path("ajax/block-clone/", views.manual_block_clone_ajax, name="manual_block_clone_ajax")` 추가
4. 해당 URL을 전달해야 하는 템플릿 dataset에 추가 (`_partials/manual_detail_boot.html` 또는 `manual_detail_superuser_assets.html`)
5. JS에서 `ManualShared.postJson(url, {block_id: id}, csrfToken)` 로 호출

### 신규 매뉴얼 Access 타입 추가 (예: "leader_only")

1. `manual/utils/rules.py` `access_to_flags()`에 새 케이스 추가
2. `manual/utils/permissions.py` `filter_manuals_for_user()`에 새 필터 조건 추가
3. `manual/utils/permissions.py` `manual_accessible_or_denied()`에 접근 체크 추가
4. 모델에 새 필드 추가 + `makemigrations` + `migrate`
5. 프론트 radio 버튼 (`create_manual_modal.html`, 목록 편집 모드) 추가
6. `manual_list.html`의 배지 패턴 추가 (`.manual-badge-*`)

### 신규 블록 타입 추가 (예: 영상 임베드)

1. `ManualBlock` 모델에 필드 추가 + 마이그레이션
2. `block_to_dict()` 에 새 필드 포함
3. `manual_block_add_ajax` / `manual_block_update_ajax` 뷰에 파싱 로직 추가
4. Quill toolbar 커스터마이징 (`quill.js` `createQuillManager()`)
5. 템플릿에서 렌더링 처리 (`manual_detail.html`)

---

## 13. LLM 함정 포인트

### `Manual.content` vs `ManualBlock.content`

`Manual.content` 는 **레거시 필드**다. 현재 실제 콘텐츠는 `Manual → ManualSection → ManualBlock.content`(Quill HTML) 체계로 관리된다.  
`manual.content`를 신규 기능에서 사용하면 안 된다.

### `ManualBlock.save()`의 sanitize 자동 실행 — 이중 호출 주의

```python
# ❌ 이중 sanitize
block.content = sanitize_quill_html(html)   # 뷰에서 직접 호출
block.save()                                # save()에서 또 sanitize → 문제없지만 불필요

# ✅ save()가 자동으로 sanitize하므로 뷰에서 별도 호출 불필요
block.content = html
block.save()
```

### `filter_manuals_for_user()` 없이 목록 조회 금지

```python
# ❌ 금지: admin_only 필터 누락
qs = Manual.objects.filter(is_published=True)

# ❌ 금지: 권한 체크 없이 전체 반환
qs = Manual.objects.all()

# ✅ 올바른 방법
from manual.utils.permissions import filter_manuals_for_user
qs = filter_manuals_for_user(Manual.objects.all(), request.user)
```

### `attachment_to_dict()` 반환 키 변경 금지

`quill.js` 의 `insertAttachmentLink()` 는 업로드 응답에서 `{name, download_url, size}` 키를 읽어 Quill에 링크를 삽입한다.  
이 키를 변경하면 첨부파일 업로드 후 에디터에 링크가 삽입되지 않는다.

### `ensure_superuser_or_403()` 반환값 처리 패턴

```python
# ❌ 반환값 무시
@require_POST
@login_required
def manual_block_add_ajax(request):
    ensure_superuser_or_403(request)   # 반환값을 버림 → 권한 없어도 통과
    ...

# ✅ 올바른 패턴
def manual_block_add_ajax(request):
    resp = ensure_superuser_or_403(request)
    if resp:
        return resp   # 403 JsonResponse 반환
    ...
```

### `_partials/` 파일 직접 URL 접근 불가

`_partials/*.html`은 `{% include %}` 전용이다. `path()`를 붙여 직접 접근 가능하게 만들면 안 된다.

### 섹션 삭제 후 `ensure_default_section()` 호출 필수

```python
# manual/views/section.py manual_section_delete_ajax()
manual.sections.filter(id=section_id).delete()
if not manual.sections.exists():
    ensure_default_section(manual)   # ⚠️ 이 호출이 없으면 빈 매뉴얼 상태
```

섹션 삭제 로직을 수정할 때 이 호출을 빠뜨리면, 매뉴얼 상세 페이지에서 섹션이 0개인 상태가 되어 블록 추가 UI가 동작하지 않는다.

### `manual_block_move_ajax` — 트랜잭션 필수

블록 이동은 두 섹션의 sort_order를 동시에 갱신한다. 트랜잭션 없이 구현하면 부분 실패 시 데이터가 불일치 상태가 된다.  
`from django.db import transaction` + `with transaction.atomic():` 블록 안에서 처리해야 한다.

### Quill 에디터 — 첨부 업로드는 edit 모드에서만

`quill.js` 의 attach 버튼은 `state.mode === "edit"` 일 때만 활성화된다.  
블록을 **새로 추가(add 모드)** 할 때는 첨부 업로드 버튼이 비활성화되며, 저장 후 edit 모드로 재진입해야 첨부를 추가할 수 있다.  
이 UX 제약을 변경하려면 서버에 blockId가 없는 상태에서 첨부를 임시 저장하는 별도 메커니즘이 필요하다. 단순히 버튼을 활성화해도 서버에서 `block_id` 없이는 `ManualBlockAttachment`를 생성할 수 없다.

---

## 14. 회귀 위험 체크리스트

manual 앱 수정 시 반드시 확인해야 하는 포인트:

- [ ] **`filter_manuals_for_user()` 변경** → head/leader/basic 사용자가 볼 수 없는 매뉴얼이 목록에 노출되지 않는지 확인
- [ ] **`manual_accessible_or_denied()` 변경** → 비공개(`is_published=False`) 매뉴얼의 상세 페이지가 superuser 외 접근 차단 유지 여부
- [ ] **`sanitize_quill_html()` allowlist 변경** → 추가된 태그/속성이 XSS에 안전한지 검토. `<script>`, `on*` 이벤트 속성 금지
- [ ] **`attachment_to_dict()` 키 변경** → `quill.js` 의 `insertAttachmentLink()` 가 기대하는 키(`name`, `download_url`, `size`) 유지 여부
- [ ] **모델 필드 추가** → `block_to_dict()` 반환값에 새 필드 포함 필요 여부
- [ ] **섹션 삭제 로직 변경** → `ensure_default_section()` 호출 유지 여부 (섹션 0개 방지)
- [ ] **URL 추가** → `manual/views/__init__.py` re-export 추가 여부 (없으면 `NoReverseMatch`)
- [ ] **dataset 키 변경** → 대응하는 JS 파일에서 해당 `dataset.*` 참조 동시 변경 여부
- [ ] **JS 클래스명 변경** → SortableJS `handle`, `draggable` 옵션과 CSS `.manual-*` 클래스가 동기화되어 있는지
- [ ] **감사 로그 누락** → 새 편집 기능에 `log_action(request, ACTION.MANUAL_*, ...)` 호출 여부
- [ ] **이미지 URL 노출 금지** → `block.image.url` 직접 노출 대신 `{% url 'manual:manual_block_image' block.id %}` 경유 여부
- [ ] **첨부 URL 노출 금지** → `att.file.url` 직접 노출 대신 `{% url 'manual:manual_attachment_download' att.id %}` 경유 여부
- [ ] **Quill HTML 렌더링** → 템플릿에서 `{{ block.content|sanitize_manual_html }}` 필터 적용 여부 (`{% load manual_sanitize %}` 포함)
- [ ] **블록 이동(move) 트랜잭션** → 두 섹션 sort_order 동시 갱신 시 `transaction.atomic()` 유지 여부
