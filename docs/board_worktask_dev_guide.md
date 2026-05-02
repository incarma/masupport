# 📘 WorkTask 개발 지침서 (FINAL v2.0 / 2026-05-03)

---

## 🔥 0. 이번 버전 핵심 변경사항 (중요)

### 1. 용어 변경 (전역 적용)

* ❌ 영업가족 → ✅ 지점
* DB 필드(`family_branches`)는 유지 (하위 호환)

---

### 2. 상태(status) 인라인 수정 지원

* 목록에서 직접 수정 가능
* `inline_update`에서 허용 필드 추가 필요

---

### 3. CSP 대응 (🔥 필수)

* inline style 완전 제거
* JS에서 `.style = ...` 사용 금지
* CSS class 기반만 허용

---

### 4. 지점 선택 구조 안정화

* superuser 기준 `CustomUser.branch` distinct 사용
* 공백/중복 제거 필수

---

### 5. 상세 페이지 구조 변경

* 메모 → 카드 제거
* 지점/대상 → 하나의 카드에서 좌우 배치
* 순서: **지점 | 대상**

---

# 1. 모델 구조 (SSOT)

```python
family_branches = models.JSONField(
    default=list,
    blank=True,
    verbose_name="지점",
)
```

---

# 2. 지점 옵션 정책 (🔥 중요)

## 기준 함수

```python
def _get_worktask_branch_options(request)
```

## 정책

| 사용자       | 반환값                |
| --------- | ------------------ |
| superuser | 전체 branch distinct |
| 일반 사용자    | 본인 branch          |

---

## 필수 조건

```python
.annotate(branch_name=Trim("branch"))
.exclude(branch_name="")
.distinct()
```

👉 공백 제거 안 하면 중복 발생

---

# 3. 데이터 흐름

## create

```python
data["family_branches"] = _clean_family_branches(...)
```

## update (🔥 중요)

```python
if "family_branches" in data:
    data["family_branches"] = _clean_family_branches(...)
```

👉 없으면 기존 데이터 유지

---

# 4. POST 계약 (프론트 ↔ 백엔드)

## 프론트

```html
<input name="family_branches" value="강남지점">
<input name="family_branches" value="서초지점">
```

## 백엔드

```python
request.POST.getlist("family_branches")
```

---

# 5. _extract_post_data 필수 항목

```python
"family_branches": request.POST.getlist("family_branches"),
```

---

# 6. Inline Update 정책

## 허용 필드

```python
ALLOWED_FIELDS = {
    "category",
    "priority",
    "start_date",
    "due_date",
    "status",   # ← 반드시 포함
}
```

## status 처리

```python
elif field == "status":
    status_map = dict(WorkTask.STATUS_CHOICES)
```

---

## ❌ 오류 원인

```
수정 불가 필드: status
```

👉 ALLOWED_FIELDS 누락

---

# 7. 서비스 레이어 규칙

## 정규화

```python
def _clean_family_branches(values):
```

기능:

* 공백 제거
* 중복 제거
* 순서 유지

---

# 8. 템플릿 규칙

## ❌ 금지

```html
style="..."
```

```html
id="branch-{{ branch|slugify }}"
```

---

## ✅ 허용

```html
class="board-section-title-primary"
```

---

# 9. CSS 규칙 (CSP 대응)

## 필수 클래스

```css
.board-section-title-primary {
  color: #003f7d;
}

.worktask-cell-edit {
  cursor: pointer;
}
```

---

## ❌ 금지

```js
element.style.cursor = "pointer"
```

---

# 10. UI 구조

## 목록

```
분류 / 업무명 / 지점 / 대상 / 우선순위 / 상태 / 삭제
```

---

## 상세

### 상단

```
[분류 배지] [상태 배지] [우선순위 배지]
```

---

### 메모

```
업무명 아래 바로 출력
(카드 없음)
```

---

### 카드

```
[ 지점 | 대상 ]
```

---

# 11. 상태/우선순위 스타일 통일

## 동일 구조

```css
.worktask-badge,
.worktask-priority-badge {
  border-radius: 999px;
}
```

---

## 색상

| 항목 | 색상     |
| -- | ------ |
| 상  | red    |
| 중  | orange |
| 하  | blue   |

---

# 12. 분류 표시 정책

## 목록

👉 텍스트 ONLY

```html
<span class="worktask-category-text">임대차</span>
```

---

## 상세

👉 배지

---

# 13. JSON script 규칙

## ❌ 금지

```json
{ "label": "...", "label": "..." }
```

---

# 14. 권한 정책

* superuser only
* owner isolation 유지

---

# 15. 절대 금지

```python
WorkTask.objects.get(pk=pk)
```

```django
{{ file.url }}
```

---

# 16. 체크리스트 (운영 전)

* [ ] status inline 정상 작동
* [ ] CSP 오류 없음
* [ ] 지점 목록 정상 출력
* [ ] 템플릿 style 제거 완료
* [ ] 상세 페이지 구조 정상

---

# 17. 설계 방향

현재:

```
JSON 기반 (빠름)
```

향후:

```
Branch FK 구조 확장 가능
```

---

# 🎯 결론

현재 상태:

✔ 상태 inline 수정 정상
✔ CSP 오류 제거
✔ 지점 구조 안정화
✔ UI 통일 완료
✔ 상세 UX 개선 완료
