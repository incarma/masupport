요청하신 기준(최근 패치 반영 + 트러블슈팅 + 구조 보강)을 모두 반영해서
**WorkTask 지침서 최종 리팩토링본(.md)**을 아래와 같이 정리해드립니다.

👉 원본 기반: 

---

# 📘 WorkTask 개발 지침서 (FINAL / 2026-05-02)

## ✅ 이번 리팩토링 반영 내용

기존 문서 대비 다음 항목이 추가/수정되었습니다.

### 🔥 핵심 반영 사항

* `family_branches(JSONField)` 구조 추가
* 마이그레이션 오류 방지 규칙 추가
* `_extract_post_data` 누락 버그 방지 규칙 추가
* update 시 JSON 필드 덮어쓰기 방지 규칙 추가
* 프론트–백엔드 hidden input 계약 명시
* branch 선택 정책(superuser 기준) 명문화
* WorkTask 목록 UI 확장 (86vw 구조)
* 카테고리 색상 label 기반 매핑 규칙 추가
* JSON script 중복 key 금지 규칙 추가
* slugify id 사용 금지 규칙 추가

---

# 📦 다운로드용 Markdown 파일

아래 내용을 그대로 `.md` 파일로 저장하시면 됩니다.

파일명 추천:

```
board_worktask_dev_guide_FINAL.md
```

---

# 📄 최종 문서 (다운로드용)

````markdown
# django_ma Board 앱 업무관리(WorkTask) 개발 지침서 (FINAL)

> 기준: 2026-05-02  
> 상태: family_branches 포함 최종 안정화 버전

---

## 0. 핵심 변경 요약

이번 버전에서 가장 중요한 구조 변화:

### 1. 영업가족 (family_branches) 추가
- JSONField 기반 리스트 저장
- UI에서 다중 선택
- backend 정규화 필수

### 2. WorkTask 구조 확장
- 대상 (related_users)
- 영업가족 (family_branches) → 신규

---

## 1. 모델 기준

### WorkTask

```python
family_branches = models.JSONField(
    default=list,
    blank=True,
    verbose_name="영업가족",
)
````

---

## 2. 마이그레이션 규칙 (🔥 중요)

### ❌ 절대 금지

```python
("board", "00XX_previous_migration")
```

### ✅ 반드시 실제 파일명 사용

```python
("board", "0025_xxxxx")
```

### 권장 절차

```bash
rm board/migrations/0026_*.py
python manage.py makemigrations board
python manage.py migrate
```

---

## 3. 데이터 흐름 (중요)

### create

```python
data["family_branches"] = _clean_family_branches(...)
```

### update (🔥 핵심)

```python
if "family_branches" in data:
    data["family_branches"] = _clean_family_branches(...)
```

👉 없으면 기존 데이터 유지

---

## 4. POST 데이터 계약

### 프론트

```html
<input type="hidden" name="family_branches" value="강남지점">
<input type="hidden" name="family_branches" value="서초지점">
```

### 백엔드

```python
request.POST.getlist("family_branches")
```

---

## 5. _extract_post_data 필수 항목

```python
"family_branches": request.POST.getlist("family_branches"),
```

👉 없으면 저장 안됨

---

## 6. 서비스 레이어 규칙

### 정규화 함수

```python
def _clean_family_branches(values):
```

기능:

* 공백 제거
* 중복 제거
* 순서 유지

---

## 7. 프론트엔드 규칙

### JS

* Set 기반 중복 제거
* id 기반 삭제 ❌
* value 기반 삭제 ✅

### 삭제 방식

```js
input.value === branch
```

---

## 8. 템플릿 규칙

### ❌ 금지

```html
id="hidden-family-branch-{{ branch|slugify }}"
```

### ✅ 권장

```html
<input name="family_branches" value="{{ branch }}">
```

---

## 9. UI 구조

### 목록 컬럼

```
분류 / 업무명 / 영업가족 / 대상 / 우선순위 ...
```

---

## 10. 레이아웃 규칙

### WorkTask 목록

```css
width: 86vw;
margin-left: calc(-43vw + 50%);
```

👉 manage_efficiency 동일 구조

---

## 11. 분류 색상 규칙 (🔥 중요)

label 기반 매핑

```css
[data-category-label="수수료/채권"] { red }
[data-category-label="리스크/유지율"] { orange }
[data-category-label="전산"] { yellow }
[data-category-label="위해촉"] { green }
[data-category-label="회의/미팅"] { sky }
[data-category-label="영업/리쿠르팅"] { navy }
[data-category-label="임대차"] { purple }
```

---

## 12. JSON script 규칙

### ❌ 금지

```json
{ "label": "...", "label": "..." }
```

### ✅ 허용

```json
{ "label": "...", "order": "..." }
```

---

## 13. 권한 정책

* superuser only
* owner isolation 유지

---

## 14. 핵심 버그 방지 체크리스트

* [ ] migration dependency 정상
* [ ] family_branches POST 포함
* [ ] update 시 덮어쓰기 방지
* [ ] JSON 중복 key 없음
* [ ] slugify 제거
* [ ] JS remove 로직 value 기반

---

## 15. 절대 금지

```python
WorkTask.objects.get(pk=pk)
```

```django
{{ att.file.url }}
```

---

## 16. 설계 방향

현재 구조:

```
JSON (빠름)
```

향후 확장:

```
FK (정규화)
```

---

## 17. 최종 원칙

1. owner 격리 유지
2. dataset 계약 유지
3. JSON 구조 안정성 확보
4. UI ↔ DB 싱크 보장

---

## END

```

---

# ✔ 결론

지금 상태는:

✔ 마이그레이션 문제 해결됨  
✔ backend 구조 정상  
✔ UI 확장 완료  
✔ 데이터 흐름 안정화  

👉 이 문서 하나로 이후 WorkTask 작업 전부 대응 가능

---

필요하시면 다음 단계로  
👉 **WorkTask → 팀 공유 / 조직 기반 권한 확장 설계**까지 이어서 정리해드리겠습니다.
```
