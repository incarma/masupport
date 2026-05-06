# board/task.py 이름 혼동 정리 로그 — STEP 9
> 날짜: 2026-05-06
> 브랜치: develop
> 관련 체크리스트 항목: Q-F-05

---

## 현황 파악 결과

| task 파일 | 관리 task | 등록명 | autodiscover 방식 |
|----------|---------|--------|-----------------|
| `board/task.py` (구) | `generate_monthly_worktasks` | `board.tasks.generate_monthly_worktasks` | ❌ autodiscover 미등록 — `board.task` (단수)는 탐색 경로 외 |
| `board/task.py` (구) | `notify_due_worktasks` | `board.tasks.notify_due_worktasks` | ❌ autodiscover 미등록 |
| `board/tasks/industry_info.py` | `collect_board_industry_news` | `board.tasks.industry_info.collect_board_industry_news` | ✅ `autodiscover_tasks()` → `board.tasks` 패키지 |
| `board/tasks/industry_info.py` | `cleanup_old_industry_articles` | `board.tasks.industry_info.cleanup_old_industry_articles` | ✅ 동일 |
| `board/tasks/holidays.py` | `sync_kr_holidays_for_year_task` | `board.tasks.holidays.sync_kr_holidays_for_year` | ✅ 동일 |
| `board/tasks/holidays.py` | `sync_kr_holidays_window_task` | `board.tasks.holidays.sync_kr_holidays_window` | ✅ 동일 |

**근본 원인**: `board/task.py` (단수)와 `board/tasks/` (복수 패키지)가 공존.  
`app.autodiscover_tasks()`는 `board.tasks` (복수 패키지)만 임포트하므로 `board.task`(단수)는 영구 미탐색 상태였음.  
beat_schedule에 등록된 `generate_monthly_worktasks`, `notify_due_worktasks` 두 태스크가 Celery에 실제로 등록되지 않던 잠재 버그.

---

## 선택된 방법과 근거

**방법 A** 선택 — `board/task.py` → `board/tasks/worktask_tasks.py` 이동

| 판단 기준 | 결과 |
|----------|------|
| `board.task` import 파일 수 | 0건 (안전) |
| autodiscover 누락 버그 존재 | ✅ (방법 B로는 해소 불가) |
| `@shared_task(name=)` 변경 여부 | 절대 변경 없음 |
| 이동 후 패키지 구조 일관성 | `board/tasks/` 하위 단일화 완성 |

---

## 수정 내용

### 1. `board/tasks/worktask_tasks.py` 신규 생성
- `board/task.py`의 `generate_monthly_worktasks`, `notify_due_worktasks` 이동
- `@shared_task(name=)` 등록명 **절대 변경 없음**
  - `"board.tasks.generate_monthly_worktasks"` 유지
  - `"board.tasks.notify_due_worktasks"` 유지

### 2. `board/tasks/__init__.py` 수정
- 패키지 역할 주석 추가 (파일별 관리 태스크 명시)
- `from .worktask_tasks import generate_monthly_worktasks, notify_due_worktasks` 추가
- `__all__`에 두 함수 추가

### 3. `board/task.py` deprecation 래퍼로 교체
```python
# board/task.py — DEPRECATED
from board.tasks.worktask_tasks import (  # noqa: F401
    generate_monthly_worktasks,
    notify_due_worktasks,
)
```
하위 호환성 유지 (혹여 외부에서 직접 임포트하는 경우 대비)

### 4. `web_ma/celery.py` 주석 수정
- 잘못된 주석 `board/tasks.py: generate_monthly_worktasks`  
  → `board/tasks/worktask_tasks.py: generate_monthly_worktasks` 로 수정 (동일 패턴으로 notify도)

---

## python manage.py check 결과

```
System check identified no issues (0 silenced).
```

---

## celery_check.sh 결과

```
beat_schedule 등록 task (9건) — 전부 @shared_task(name=) 일치 확인
  [generate-monthly-worktasks] -> board.tasks.generate_monthly_worktasks
    등록 위치: board/tasks/worktask_tasks.py:37  ✅
  [notify-due-worktasks] -> board.tasks.notify_due_worktasks
    등록 위치: board/tasks/worktask_tasks.py:76  ✅
  ...

[OK] Celery task 이름 점검 통과 (불일치 0건)
```

---

## 회귀 점검 결과

| 항목 | 결과 |
|------|------|
| beat_schedule "task" 값 변경 여부 | ✅ 변경 없음 |
| @shared_task(name=) 등록명 변경 여부 | ✅ 변경 없음 |
| celery_check.sh 불일치 건수 | ✅ 0건 |
| board/task.py import 파일 정상 동작 | ✅ (0건 → deprecation 래퍼가 re-export 보장) |
| 권한 스코프 변경 여부 | ✅ 없음 (Celery 태스크 파일만 수정) |
| URL reverse / 네임스페이스 깨짐 여부 | ✅ 없음 |
| 템플릿 dataset / DOM id 변경 여부 | ✅ 없음 |
| 첨부 다운로드 정책 위반 여부 | ✅ 없음 |
| JSON 응답 형식 앱 규약 준수 여부 | ✅ 없음 (태스크 파일 변경만) |
| 운영 환경 영향 여부 | ✅ 없음 |

---

## 최종 파일 구조

```
board/
  task.py              ← DEPRECATED: deprecation re-export 래퍼
  tasks/
    __init__.py        ← industry_info + holidays + worktask_tasks 통합 re-export
    industry_info.py   ← 업계정보 태스크 (변경 없음)
    holidays.py        ← 공휴일 태스크 (변경 없음)
    worktask_tasks.py  ← WorkTask 반복생성/알림 태스크 (board/task.py에서 이동)
```
