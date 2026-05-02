# dash 앱 개발 가이드

> **목적**: 외부 LLM이 전체 코드 없이 dash 앱을 정확하게 디벨롭할 수 있는 수준의 참조 문서.
> **기준 커밋**: develop 브랜치 (2026-05-03)

---

## 1. 앱 책임 요약

보험 GA 조직의 **매출 현황/예측 대시보드(Sales)**, **유지율 대시보드(Retention)**, **모집/목표 대시보드(미완)** 세 영역을 담당한다. 엑셀 업로드로 SalesRecord·RetentionRecord를 적재하고, Celery Beat이 매시 집계(SalesDailyAgg)와 LightGBM 예측(SalesForecast)을 갱신하며, Chart.js가 브라우저에서 렌더링한다.

---

## 2. 디렉터리 구조

```
dash/
├── models.py                       # 7개 모델 (Sales/Retention 도메인)
├── urls.py                         # 11개 URL 패턴 (namespace="dash")
├── views.py                        # 얇은 shim — viewmods에서 re-import만 수행
├── tasks.py                        # Celery 태스크 re-export (task_runtime에서 가져옴)
├── task_runtime.py                 # ⚠️ Celery 태스크 실구현 + 집계/예측 공개 함수
├── admin.py                        # 비어있음
├── apps.py                         # DashConfig
├── tests.py
├── ml/
│   └── forecast.py                 # ⚠️ LightGBM 학습/저장/로드/예측 SSOT
├── services/
│   ├── agg.py                      # ⚠️ SalesDailyAgg 생성 서비스 SSOT
│   └── retention.py                # ⚠️ RetentionRecord 파싱/upsert/집계 SSOT
├── viewmods/
│   ├── __init__.py
│   ├── pages.py                    # 페이지 뷰 5개
│   ├── api_upload.py               # 매출 엑셀 업로드 API
│   ├── api_forecast.py             # 예측 데이터 조회 API
│   ├── api_retention.py            # 유지율 조회 API
│   ├── api_retention_upload.py     # 유지율 엑셀 업로드 API
│   ├── constants.py                # ⚠️ 보험사 목록, 필수 컬럼, FORECAST_MODEL_VER SSOT
│   └── utils/
│       ├── json.py                 # json_ok / json_error 헬퍼
│       ├── excel.py                # 엑셀 파싱 변환 유틸 (날짜, 금액, 사번 등)
│       ├── charts.py               # 누적합/라벨/Y축 계산 유틸
│       └── sales_filters.py        # SalesRecord QS 필터 유틸 + head 권한 강제
├── templates/dash/
│   ├── dash_sales.html             # 매출 대시보드 (1245줄, 서버 렌더 + Chart.js)
│   ├── dash_retention.html         # 유지율 대시보드 (content_wrapper 블록, 223줄)
│   ├── dash_recruit.html           # 모집 대시보드 (미완 — 제작중 placeholder)
│   └── dash_goals.html             # 목표 대시보드 (미완 — 제작중 placeholder)
└── migrations/                     # 6개 마이그레이션
```

---

## 3. 모델 구조

### 3.1 SalesRecord

- **역할**: 매출 엑셀 원천 레코드 (`policy_no`가 PK)
- **`policy_no`**: `CharField(primary_key=True, max_length=60)` — 증권번호
- **Snapshot 필드**: `part_snapshot`, `branch_snapshot`, `name_snapshot`, `emp_id_snapshot` — 업로드 시점 조직·인적 정보 보존, `user` FK가 NULL이어도 집계 가능하도록 설계
- **`user`**: `ForeignKey(CustomUser, null=True, blank=True)` — 사번 매칭 성공 시 연결, 실패 시 NULL
- **`life_nl`**: `CharField(choices=[('손보','손보'),('생보','생보'),('자동차','자동차')])` — 상품 분류
- **`ym`**: `CharField(max_length=7)` — YYYY-MM (월도, db_index)
- **`receipt_date`**: `DateField(null=True)` — 영수일자 (집계 기준)
- **`receipt_amount`**: `BigIntegerField(null=True)` — 영수금
- **주요 인덱스**: `(ym, insurer)`, `(ym, life_nl)`, `(ym, user)`, `(ym, vehicle_no)`
- **upsert 방식**: `update_or_create(policy_no=...)` — 재업로드 시 덮어쓰기
- **db_table**: `"dash_sales_record"`

### 3.2 SalesDailyAgg

- **역할**: scope × category × 일자별 매출 집계 (Celery가 생성, 예측/차트에서 소비)
- **복합 키**: `unique_together = [("ym", "day", "scope_type", "scope_key", "category")]`
- **`scope_type`**: `"all"` / `"part"` / `"branch"`
- **`scope_key`**: `"*"` (all) 또는 부서명 / 지점명
- **`category`**: `"long"` / `"car"` / `"long_nonlife"` / `"long_life"`
- **`day`**: `PositiveSmallIntegerField` (1~31)
- **`amount`**: 해당 일자 매출합 / **`cumsum`**: 월 1일~해당 일 누적합

### 3.3 SalesForecast

- **역할**: LightGBM 월말 예측값 (분위수 p10/p50/p90)
- **복합 키**: `unique_together = [("ym", "asof_day", "scope_type", "scope_key", "category", "model_ver")]`
- **`asof_day`**: 예측 기준일 (1~말일)
- **`model_ver`**: `CharField(default="lgbm_v1")` — 버전 SSOT는 `viewmods/constants.py:FORECAST_MODEL_VER`
- **`pred_total_p10/p50/p90`**: 월말 총액 분위수 예측 (`BigIntegerField(null=True)`)
- **`actual_to_date`**: 기준일까지 실적 누적 (검증용)
- **관계**: `SalesForecastDaily` 1:N (`related_name="days"`)

### 3.4 SalesForecastDaily

- **역할**: SalesForecast의 일별 분위수 분해값
- **`forecast`**: `ForeignKey(SalesForecast, CASCADE, related_name="days")`
- **`day`**: `PositiveSmallIntegerField`
- **`pred_amount_p10/p50/p90`**: 해당 일 예측 / **`pred_cumsum_p10/p50/p90`**: 누적 예측

### 3.5 RetentionRecord

- **역할**: 유지율 엑셀 원천 레코드
- **복합 PK**: `UniqueConstraint(policy_no, round_no)` — 증권번호 + 대상회차
- **`round_no`**: `PositiveSmallIntegerField` — 대상회차 (2, 3, 4, 7 등)
- **`life_nl`**: `"생보"` / `"손보"`
- **`recruit_amount`**: `BigIntegerField` — 최초(모집)인정실적 (유지율 분모)
- **`status`**: `choices=[("정상","정상"),("유예","유예"),("해지","해지"),("실효","실효")]`
- **유지 판정**: `status in ("정상", "유예")` → 유지 / `("해지", "실효")` → 미유지
- **`user`**: `ForeignKey(CustomUser, null=True)` — 사번 매칭 실패 시 NULL
- **주요 인덱스**: `(ym, round_no)`, `(ym, life_nl, round_no)`, `(ym, insurer, round_no)`, `(ym, emp_id_snapshot)`, `(ym, round_no, status)`

### 3.6 RetentionAgg

- **역할**: scope × life_nl × round_no × insurer 조합별 유지율 집계
- **복합 키**: `UniqueConstraint(ym, life_nl, round_no, scope_type, scope_key, insurer)`
- **`rate`**: `DecimalField(max_digits=5, decimal_places=2)` — 유지율(%)
- **`insurer`**: `CharField(blank=True, default="")` — `""` = 전체, 보험사명 = 개별
- **유지율 수식**: `paid_amount / total_amount × 100` (금액 기반)

### 3.7 RetentionUploadLog

- **역할**: 유지율 업로드 이력
- **복합 키**: `UniqueConstraint(ym, life_nl)` — 월도×손생 당 1건 (`update_or_create`)
- **필드**: `ym`, `life_nl`, `file_name`, `row_count`, `upserted`, `skipped`, `uploaded_by`(FK SET_NULL)

---

## 4. URL 네임스페이스 + 엔드포인트 전체 목록

**namespace**: `dash`

| name | route | 메서드 | 반환 | 비고 |
|------|-------|--------|------|------|
| `dash_home` | `/dash/` | GET | redirect → `dash_sales` | |
| `dash_sales` | `/dash/sales/` | GET | HTML | 매출 대시보드 |
| `dash_sales_upload` | `/dash/sales/upload/` | POST | JSON | 모달용 alias |
| `dash_recruit` | `/dash/recruit/` | GET | HTML | 미완 |
| `dash_retention` | `/dash/retention/` | GET | HTML | 유지율 대시보드 |
| `dash_goals` | `/dash/goals/` | GET | HTML | 미완, superuser 전용 |
| `dash_upload_sales_excel` | `/dash/api/upload/` | POST | JSON | 매출 업로드 API |
| `dash_forecast_api` | `/dash/api/forecast/` | GET | JSON | 예측 조회 |
| `dash_sales_forecast` | `/dash/sales/forecast/` | GET | JSON | `dash_forecast_api` alias |
| `dash_retention_api` | `/dash/api/retention/` | GET | JSON | 유지율 조회 |
| `dash_retention_upload` | `/dash/api/retention/upload/` | POST | JSON | 유지율 업로드 |

**JSON 응답 형식 (전체 통일)**: `{ "ok": true|false, "message": "...", "data": {...} }`

---

## 5. 권한 정책

| 뷰/API | 허용 등급 | 강제 위치 |
|--------|----------|----------|
| `redirect_to_sales`, `dash_sales`, `dash_recruit`, `dash_retention` | `superuser`, `head` | `@grade_required` (pages.py:32~628) |
| `dash_goals` | `superuser` 전용 | `@grade_required` (pages.py:652) |
| `dash_forecast_api`, `retention_api` | `superuser`, `head` | `@grade_required` (api_forecast.py:97, api_retention.py:29) |
| `upload_sales_excel` | `superuser` 전용 | `@grade_required` (api_upload.py:35) |
| `upload_retention_excel` | `superuser` 전용 | `@grade_required` (api_retention_upload.py:25) |

### head(지점장) 권한 자동 스코프 강제

`head` 등급 사용자는 자신의 `branch`(영업가족) 데이터만 조회할 수 있다. 강제 위치:

- **매출 페이지**: `viewmods/utils/sales_filters.py`의 `apply_head_scope_to_salesrecord_qs()` — QS 필터
- **예측 API**: `api_forecast.py:128~136` — `scope_type="branch"`, `scope_key=request.user.branch`로 강제
- **유지율 API**: `api_retention.py` — `scope_type="branch"`, `scope_key=request.user.branch`로 강제

> ⚠️ head 사용자가 `scope=all`이나 타 지점 `scope_key`를 요청해도 서버에서 자신 지점으로 덮어쓴다. 프론트에서 필터 UI를 숨기는 것만으로는 충분하지 않다.

---

## 6. 서비스/유틸 레이어 SSOT 목록

### dash/services/agg.py ⚠️

SalesDailyAgg 생성 로직의 SSOT. 뷰나 태스크에서 직접 `SalesDailyAgg` upsert 금지.

| 공개 함수 | 역할 |
|-----------|------|
| `build_daily_agg_for_month(ym, scope_type, scope_key)` | ym+scope 조합의 일별 집계를 SalesDailyAgg에 저장 |

**카테고리 분류 기준** (`_qs_category()` 내):
- `long`: `life_nl != '자동차'` AND `pay_method != '일시납'`
- `car`: `life_nl = '자동차'`
- `long_nonlife`: `life_nl = '손보'` AND `pay_method != '일시납'`
- `long_life`: `life_nl = '생보'` AND `pay_method != '일시납'`

**스코프 필터 로직** (`_scope_filter()`):
- `scope_type="part"` → `Q(user__part=key) | Q(part_snapshot=key)` (삭제 사용자 포함)
- `scope_type="branch"` → `Q(user__branch=key) | Q(branch_snapshot=key)`

### dash/services/retention.py ⚠️

RetentionRecord 파싱·저장·집계 SSOT. 뷰에서 RetentionRecord ORM 직접 조작 금지.

| 공개 함수 | 역할 |
|-----------|------|
| `parse_retention_excel(df, life_nl)` | DataFrame → (records[], parse_errors[]) |
| `bulk_upsert_retention_records(records)` | RetentionRecord update_or_create 배치 |
| `rebuild_retention_agg(ym, life_nl)` | 모든 scope×회차×보험사 조합 RetentionAgg 재계산 |
| `_detect_life_nl(df)` | 보험사명 샘플링으로 생보/손보 자동 분류 |

### dash/ml/forecast.py ⚠️

LightGBM 예측 모델 학습·저장·로드·예측의 SSOT. task_runtime 외에서 직접 호출 금지.

| 공개 함수 | 역할 |
|-----------|------|
| `build_train_df(scope_type, scope_key, category)` | 학습 데이터 DataFrame 생성 (최근 24개월) |
| `save_models(models, tag)` | joblib → `{DASH_MODEL_DIR}/lgbm_v1__{tag}.joblib` 저장 |
| `load_models(tag)` | joblib에서 모델 로드 (없으면 None) |
| `predict_month_total(models, features)` | p10/p50/p90 예측값 반환 |
| `upsert_forecast(ym, asof_day, scope_type, scope_key, category, pred, model_ver)` | SalesForecast + SalesForecastDaily 저장 |

**모델 저장 경로**: `settings.DASH_MODEL_DIR` (기본: `var/dash_models/`, settings.py:708에서 `BASE_DIR / "var" / "dash_models"`)  
**모델 파일명 패턴**: `lgbm_v1__{scope_type}__{scope_key}__{category}.joblib`

### dash/task_runtime.py ⚠️

Celery 태스크 실구현 + 동기 예측 진입점. `api_forecast.py`에서 직접 import하는 공개 함수 포함.

| 공개 함수 | 역할 |
|-----------|------|
| `build_scope_forecast_now(ym, asof_day, scope_type, scope_key)` | 동기 집계+예측 (API 즉시 응답용) |
| `_build_aggs_for_scope(ym, scope_type, scope_key)` | 단일 scope 집계 (api_forecast.py에서 직접 사용) |
| `iter_scopes()` | `(scope_type, scope_key)` 전체 조합 반환 |
| `CATEGORIES` | `["long", "car", "long_nonlife", "long_life"]` (상수) |

**분산 락 패턴**: `cache.add(lock_key, 1, TTL)` — 중복 실행 방지

### dash/viewmods/constants.py ⚠️ (SSOT)

| 상수 | 값 | 용도 |
|------|-----|------|
| `FORECAST_MODEL_VER` | `"lgbm_v1"` | SalesForecast.model_ver 기준값 — 변경 시 기존 예측 전체 무효화 |
| `NONLIFE_INSURERS` | set(13개) | 손보사 판별 기준 |
| `LIFE_INSURERS` | set(20개) | 생보사 판별 기준 |
| `REQUIRED_COLS` | list | 일반 매출 엑셀 필수 컬럼 |
| `AUTO_REQUIRED_COLS` | list | 자동차 매출 엑셀 필수 컬럼 |
| `PART_MAP` | dict | 부서명 정규화 맵 (예: `"1인GA사업부"` → `"MA사업4부"`) |

### dash/viewmods/utils/excel.py ⚠️

엑셀 파싱 시 반드시 이 함수를 사용. `int()`, `float()`, `datetime.strptime()` 직접 사용 금지.

| 함수 | 역할 |
|------|------|
| `normalize_columns(df)` | 컬럼 문자열화 + 공백 제거 |
| `is_auto_excel(df)` | `"물건구분"` 컬럼 존재 → 자동차 파일 판별 |
| `to_date(v)` | 다양한 날짜 형식 → `date` |
| `to_str_emp_id(v)` | `"1234567.0"` → `"1234567"` |
| `to_int_money(v)` | 금액 문자열 → `int` (쉼표·소수점 제거) |
| `to_policy_no(v)` | 증권번호 정규화 |
| `normalize_part_snapshot(v)` | `PART_MAP` 기반 부서명 치환 |
| `life_nl_from_insurer(insurer)` | 보험사명 → `"생보"` / `"손보"` |
| `parse_ins_period(v)` | `"YYYYMMDD~YYYYMMDD"` → `(start, end)` |

### dash/viewmods/utils/charts.py

| 함수 | 역할 |
|------|------|
| `month_day_labels(ym)` | YYYY-MM → `["YYYY-MM-01", ..., "YYYY-MM-31"]` |
| `build_cumsum_aligned(qs, labels)` | receipt_date별 누적합 리스트 (labels 기준 정렬) |
| `build_cumsum_prevmonth_aligned(qs, labels)` | 전월 누적합 (말일 초과 인덱스 방지) |
| `nice_step_and_max(value)` | Y축 step/max 계산 (손보·생보 통일용) |
| `prev_ym_str(ym)` | 전월 YYYY-MM |
| `prev_year_ym_str(ym)` | 전년동월 YYYY-MM |

### dash/viewmods/utils/sales_filters.py ⚠️

| 함수 | 역할 |
|------|------|
| `apply_head_scope_to_salesrecord_qs(request, qs)` | head 등급이면 `branch_snapshot=내지점` 필터 강제 |
| `apply_common_filters_to_salesrecord_qs(qs, part, branch, q, life_nl, insurer)` | 부서/지점/검색어 QS 필터 |
| `clean_list(values)` | QS values 결과 정렬 + 중복/NaN 제거 |

---

## 7. 템플릿 구조

### 상속 관계

```
base.html
├── dash/dash_sales.html       ({% block content %})       ← 서버 렌더 + Chart.js
├── dash/dash_retention.html   ({% block content_wrapper %}) ← 와이드 레이아웃
├── dash/dash_recruit.html     ({% block content %})       ← 미완 placeholder
└── dash/dash_goals.html       ({% block content %})       ← 미완 placeholder
```

> ⚠️ `dash_retention.html`은 `{% block content_wrapper %}`를 사용한다. wide 레이아웃이 필요하기 때문이다. `dash_sales.html`은 `{% block content %}`를 사용한다.

### CSS 로드

`{% block app_css %}`에서 로드:

```html
{% block app_css %}
<link rel="stylesheet" href="{% static 'css/apps/dash.css' %}...">
{% endblock %}
```

### dash_sales.html 서버 렌더 데이터 주입 (`json_script` 태그)

| json_script id | context 변수 | 내용 |
|----------------|-------------|------|
| `part-branch-map` | `part_branch_map` | 부서→지점 목록 매핑 |
| `branch-options-all` | `branch_options_all` | 전체 지점 목록 |
| `life-nl-insurer-map` | `life_nl_insurer_map` | 손생→보험사 목록 매핑 |
| `chart-day-labels` | `chart_day_labels` | 월 1일~말일 라벨 |
| `nl-l-y-step` / `nl-l-y-max` | `nl_l_y_step` / `nl_l_y_max` | 손보·생보 Y축 통일값 |
| `chart-cumsum` | `chart_cumsum` | 손생 당월 누적합 |
| `car-chart-cumsum` | `car_chart_cumsum` | 자동차 당월 누적합 |
| `nonlife-chart-cumsum` | `nonlife_chart_cumsum` | 손보 당월 누적합 |
| `life-chart-cumsum` | `life_chart_cumsum` | 생보 당월 누적합 |
| `prev-ym` | `prev_ym` | 전월 YYYY-MM |
| `prev-chart-cumsum` 등 4개 | 전월 시리즈 | 전월 누적합 (4 category) |
| `prev-year-ym` | `prev_year_ym` | 전년동월 YYYY-MM |
| `py-chart-cumsum` 등 4개 | 전년동월 시리즈 | 전년동월 누적합 (4 category) |

---

## 8. JS 부트 패턴

### dash_sales.html / dash_sales_page.js

- **루트 id**: `dash-sales` (CSS class: `container-fluid`)
- **dataset 키** (변경 금지 계약):

| 속성 | 연결 대상 |
|------|----------|
| `data-upload-url` | `{% url 'dash:dash_sales_upload' %}` |
| `data-forecast-url` | `{% url 'dash:dash_forecast_api' %}` |
| `data-today` | `{% now 'Y-m-d' %}` |
| `data-initial-part` | `{{ filter_part\|default:''\|escapejs }}` |
| `data-initial-branch` | `{{ filter_branch\|default:''\|escapejs }}` |
| `data-initial-life-nl` | `{{ filter_life_nl\|default:''\|escapejs }}` |
| `data-initial-insurer` | `{{ filter_insurer\|default:''\|escapejs }}` |
| `data-static-version` / `data-static-ver` | `{{ STATIC_VER }}` (두 키 모두 존재) |

- **BFCache 가드**: ❌ 없음 (단순 root 존재 여부만 체크)
- **패턴**: IIFE (`(() => { ... })()`)
- **외부 의존**: `vendor/chartjs/chart.umd.min.js` (Chart.js)
- **JS 로드 순서**:
  1. `vendor/chartjs/chart.umd.min.js`
  2. `js/dash/dash_sales_page.js`
  3. `js/dash/sales_upload.js` (`type="module"`)
  4. `js/dash/product_modal.js`

**예측(Forecast) 요청 파라미터** (`buildForecastUrl()` 빌드):
```
/dash/api/forecast/?ym=YYYY-MM&asof_day=N&scope=all|part|branch&part=...&branch=...
```

### dash_retention.html / dash_retention_page.js

- **루트 id**: `dash-retention` (CSS class: `dash-retention-root`)
- **dataset 키** (변경 금지 계약):

| 속성 | 연결 대상 |
|------|----------|
| `data-user-grade` | `{{ request.user.grade }}` |
| `data-user-part` | `{{ request.user.part }}` |
| `data-user-branch` | `{{ request.user.branch }}` |
| `data-initial-year` | `{{ initial_year }}` |
| `data-initial-month` | `{{ initial_month }}` |
| `data-initial-scope-type` | `{{ initial_scope_type }}` |
| `data-initial-scope-key` | `{{ initial_scope_key }}` |
| `data-retention-api-url` | `{% url 'dash:dash_retention_api' %}` |
| `data-upload-url` | `{% url 'dash:dash_retention_upload' %}` |

- **BFCache 가드**: ✅ `root.dataset.inited === "1"` 가드 + `window.addEventListener("pageshow", e => { if (e.persisted) root.dataset.inited = ""; })` (dash_retention_page.js:11~14, 549)
- **패턴**: IIFE
- **업로드 패널**: `data-user-grade==="superuser"` 일 때만 `#drUploadPanel` 활성화 (JS에서 제어)
- **JS 로드 순서**:
  1. `vendor/chartjs/chart.umd.min.js`
  2. `js/dash/dash_retention_page.js`

---

## 9. CSS 스코프 규약

- **파일**: `static/css/apps/dash.css`
- **매출 스코프**: `#dash-sales` 하위 — `.dash-top10-table`, `.dash-rank-tabs`, `.dash-chart-summary`, `.dash-product-name`
- **유지율 스코프**: `.dash-retention-page` / `.dash-retention-root` 하위 — `.dr-hero`, `.dr-kpi`, `.dr-panel`, `.dr-filter-grid`, `.dr-upload-card`, `.dr-drop-zone`, `.dr-table`, `.dr-val-low`, `.dr-err-banner`
- **전역 누수 방지 원칙**: 모든 dash 전용 규칙은 `#dash-sales` 또는 `.dash-retention-root` 하위로 스코핑. `base.css` 수정 금지.
- **반응형 breakpoint**: 1200px, 900px, 768px

---

## 10. 절대 수정 금지 목록

| 파일/요소 | 금지 이유 |
|-----------|----------|
| `dash/viewmods/constants.py:FORECAST_MODEL_VER` | `"lgbm_v1"` 변경 시 DB의 모든 기존 `SalesForecast.model_ver` 레코드와 불일치 — 예측 조회가 전부 빈 결과를 반환하고 매번 재학습이 트리거됨 |
| `dash/ml/forecast.py` 모델 파일명 패턴 `lgbm_v1__{tag}.joblib` | `save_models()`와 `load_models()`가 동일 패턴 사용 — 변경 시 기존 학습된 모델 파일 전부 로드 불가 |
| `SalesDailyAgg.unique_together` `(ym, day, scope_type, scope_key, category)` | 집계 upsert 키 — 변경 시 중복 레코드 누적 또는 데이터 유실 |
| `SalesForecast.unique_together` `(ym, asof_day, scope_type, scope_key, category, model_ver)` | 예측 upsert 키 — 변경 시 동일 기준 예측이 복수 저장됨 |
| `SalesRecord.policy_no` (PK) | 증권번호 PK 변경 시 재업로드 upsert 불가 — 동일 증권번호 중복 저장 발생 |
| `dash_sales.html` `id="dash-sales"` 및 json_script id 전체 | `dash_sales_page.js`가 `getElementById()`로 직접 참조 — 변경 시 차트 데이터 전부 소실 |
| `dash_retention.html` `id="dash-retention"` 및 모든 `data-*` 속성 | `dash_retention_page.js`의 유일한 설정 소스 |
| `task_runtime.py:CATEGORIES` `["long", "car", "long_nonlife", "long_life"]` | 집계·예측·API 응답 schema 전체에 사용 — 항목 추가/삭제 시 DB, API 응답, 차트 렌더링 동시 변경 필요 |
| `services/agg.py:_scope_filter()` snapshot fallback 로직 | 제거 시 `user`가 NULL인 레코드(사번 미매칭, 퇴직자)가 집계에서 누락됨 |
| `settings.DASH_MODEL_DIR` 경로 (`var/dash_models/`) | Docker 볼륨 마운트 경로와 연동 — 변경 시 배포 환경에서 모델 영속화 불가 |

---

## 11. 다른 앱과의 의존 관계

### 이 앱이 의존하는 외부 SSOT

| 의존 대상 | 위치 | 용도 |
|-----------|------|------|
| `grade_required` 데코레이터 | `accounts/decorators.py` | 모든 뷰 권한 강제 |
| `CustomUser` 모델 | `accounts/models.py` | `SalesRecord.user`, `RetentionRecord.user` FK, head 등급 체크 |
| `audit.constants.ACTION.RETENTION_EXCEL_UPLOAD` | `audit/constants.py` | 유지율 업로드 감사 로그 |
| `audit.services.log_action` | `audit/services.py` | 유지율 업로드 시 감사 로그 기록 |
| Django `cache` framework (Redis) | `django.core.cache.cache` | 예측 캐시 30분 TTL, Celery 분산 락 |
| `vendor/chartjs/chart.umd.min.js` | `static/vendor/chartjs/` | 차트 렌더링 |

### 다른 앱이 이 앱에 의존하는 관계

현재 다른 앱이 `dash` 앱 모델·서비스를 직접 import하지 않는다. `dash`는 독립 집계 도메인이다.

---

## 12. 신규 기능 추가 패턴

### 패턴 A: 새 매출 집계 카테고리 추가

1. `dash/task_runtime.py:CATEGORIES` 리스트에 새 카테고리 문자열 추가
2. `dash/services/agg.py:_qs_category()` 내 해당 카테고리 필터 Q 객체 추가
3. `dash/ml/forecast.py`의 학습·예측 루프가 `CATEGORIES`를 순회하므로 자동 적용
4. `SalesDailyAgg`, `SalesForecast` 기존 데이터는 새 카테고리 행이 없으므로 `build_sales_aggs_hourly` 다음 실행 시 자동 생성
5. API 응답 `data.series`에 새 키가 자동 포함됨 — 프론트엔드 차트 렌더링 로직에 새 카테고리 처리 추가

### 패턴 B: 새 Scope 집계 추가 (예: 새 scope_type="team")

1. `dash/task_runtime.py:iter_scopes()` 반환값에 `("team", team_key)` 조합 추가
2. `dash/services/agg.py:_scope_filter()` 내 `scope_type="team"` 분기 추가
3. `SalesDailyAgg.scope_type` choices 업데이트 + migration 생성
4. API 파라미터·응답 schema 업데이트

### 패턴 C: 유지율 새 회차 추가

1. `services/retention.py:rebuild_retention_agg()` 내 `round_no` 목록 업데이트 (하드코딩된 경우)
2. `dash_retention_page.js:renderKpis()` 및 테이블 렌더 함수에 새 회차 컬럼 추가
3. 기존 업로드 재처리 필요 시 `rebuild_retention_agg(ym, life_nl)` 호출

### 패턴 D: 새 대시보드 페이지 추가 (미완 → 완성)

1. `dash/viewmods/pages.py`에 뷰 함수 추가 (`@grade_required("superuser", "head")`)
2. `dash/templates/dash/dash_<name>.html` 작성 (`{% extends 'base.html' %}`, `{% block app_css %}`)
3. `dash/urls.py`에 URL 추가
4. `static/js/dash/<name>_page.js` 작성 (IIFE 패턴, `#dash-<name>` 루트 ID, dataset으로 URL 주입)
5. `static/css/apps/dash.css`에 `#dash-<name>` 하위 스코핑으로 스타일 추가

### 패턴 E: 예측 모델 버전 업그레이드

1. `dash/ml/forecast.py` 내 모델 학습 로직 수정
2. `dash/viewmods/constants.py:FORECAST_MODEL_VER` 값 변경 (예: `"lgbm_v2"`)
3. `var/dash_models/` 내 기존 `lgbm_v1__*` 파일은 자동으로 사용되지 않음 (삭제 가능)
4. 다음 `build_sales_forecasts_daily` 실행 시 전체 재학습 + 새 버전으로 저장

---

## 13. LLM 함정 포인트

### ① `SalesRecord.user`가 NULL이어도 집계에서 누락되지 않는다

**함정**: `user`가 NULL인 레코드는 집계 대상이 아니라고 가정한다.  
**실제 설계**: `_scope_filter()`가 `Q(user__part=key) | Q(part_snapshot=key)` 형태로 OR 조건을 사용한다. 사번 매칭이 실패한 신규 설계사나 퇴직자도 snapshot 컬럼으로 집계에 포함된다.

### ② `dash_retention.html`은 `{% block content %}`를 쓰지 않는다

**함정**: 다른 dash 페이지처럼 `{% block content %}`를 사용한다고 가정한다.  
**실제 설계**: `{% block content_wrapper %}`를 사용한다 — 와이드 테이블 레이아웃을 위해 `container` 래핑을 직접 제어한다.

### ③ `tasks.py`는 빈 re-export이고 실구현은 `task_runtime.py`에 있다

**함정**: `tasks.py`에 태스크 로직을 구현하려 한다.  
**실제 설계**: `tasks.py`는 `from dash.task_runtime import ...`만 수행한다. 모든 구현은 `task_runtime.py`에 있다. Celery beat의 `"task": "dash.tasks.build_sales_aggs_hourly"` 등록명은 `task_runtime.py`의 `@shared_task(name=...)` 값과 일치해야 한다.

### ④ `api_forecast.py`는 `_build_aggs_for_scope` underscore 함수를 직접 import한다

**함정**: underscore prefix 함수는 내부 전용이므로 외부에서 import하면 안 된다고 가정한다.  
**실제 설계**: `api_forecast.py:14`에서 `from dash.task_runtime import _build_aggs_for_scope`를 명시적으로 import한다. API 즉시 응답(동기 집계)을 위해 의도적으로 공개한 내부 함수다.

### ⑤ `FORECAST_MODEL_VER`는 `constants.py`에 있고 `ml/forecast.py`의 기본값과 다를 수 있다

**함정**: `ml/forecast.py`의 함수 기본값 `model_ver="lgbm_v1"`을 SSOT로 생각한다.  
**실제 설계**: SSOT는 `dash/viewmods/constants.py:FORECAST_MODEL_VER = "lgbm_v1"` (line 34)이다. `api_forecast.py`가 이 값을 import하여 DB 조회에 사용한다. 버전 업그레이드는 이 파일만 수정한다.

### ⑥ 예측 API는 데이터가 없으면 즉시 계산하여 응답한다

**함정**: SalesForecast 없으면 404 또는 빈 응답을 반환할 것이라 생각한다.  
**실제 설계**: `api_forecast.py:_bootstrap_requested_scope_if_missing()`이 SalesDailyAgg나 SalesForecast가 없으면 동기적으로 집계+예측을 실행한 후 응답한다. 최초 조회 시 응답이 수십 초 걸릴 수 있다.

### ⑦ 매출 대시보드 TOP10 데이터는 JS가 아니라 서버에서 렌더링된다

**함정**: TOP10 테이블도 JS가 API를 호출하여 렌더링한다고 가정한다.  
**실제 설계**: `dash_sales.html`은 서버 사이드 렌더링 템플릿이다. TOP10 데이터는 `dash_sales(request)` 뷰에서 컨텍스트로 주입되어 Django 템플릿이 직접 `<tr>` 태그를 생성한다. 예측 차트만 JS의 `fetchForecastOnce()`로 비동기 로드한다.

### ⑧ head 스코프 강제는 클라이언트 파라미터를 무시하고 서버에서 덮어쓴다

**함정**: head 사용자가 `scope=all`을 요청하면 전체 데이터를 볼 수 있다고 생각한다.  
**실제 설계**: `api_forecast.py:128~136`에서 `request.user.grade == "head"`이면 전달받은 `scope`, `scope_key`를 무시하고 `scope_type="branch"`, `scope_key=request.user.branch`로 강제 설정한다.

---

## 14. 회귀 위험 체크리스트

### Celery 태스크

- [ ] `task_runtime.py`에 새 `@shared_task` 추가 시 `tasks.py`에서 re-export했는가?
- [ ] `beat_schedule`의 `"task"` 값이 `@shared_task(name=...)` 등록명과 정확히 일치하는가?
- [ ] `build_sales_forecasts_for_yms.delay(yms)` 호출 시 yms가 `List[str]` (YYYY-MM) 형식인가?
- [ ] 분산 락 TTL이 태스크 최대 실행 시간보다 충분히 긴가?

### 매출 집계/예측

- [ ] `SalesDailyAgg` 생성 후 `SalesForecast` 생성 순서인가? (집계 선행 필수)
- [ ] 새 scope 추가 시 `iter_scopes()`와 `_scope_filter()` 두 곳 모두 수정했는가?
- [ ] `FORECAST_MODEL_VER` 변경 시 기존 `SalesForecast` 레코드와 신규 레코드가 혼재하지 않는가?
- [ ] `var/dash_models/` 디렉터리가 Docker 볼륨에 마운트되어 있는가? (컨테이너 재시작 시 모델 파일 유실 방지)

### 매출 엑셀 업로드

- [ ] 자동차 파일과 일반 파일 판별이 `is_auto_excel(df)` (`"물건구분"` 컬럼 존재 여부)를 사용하는가?
- [ ] `to_str_emp_id()` 없이 사번을 처리하면 `"1234567.0"` 형태로 저장되어 User 매칭 실패 발생
- [ ] `normalize_part_snapshot()` 없이 부서명을 저장하면 `PART_MAP` 치환이 누락됨

### 유지율 집계

- [ ] `rebuild_retention_agg(ym, life_nl)` 호출 시 scope 목록에 head 사용자 지점이 포함되는가?
- [ ] 유지 판정 로직: `status in ("정상", "유예")`만 유지로 계산하는가?
- [ ] `RetentionUploadLog` upsert 후 `audit.log_action(ACTION.RETENTION_EXCEL_UPLOAD)` 호출했는가?

### 캐시 무효화

- [ ] 유지율 API 응답은 30분 캐시 (`dash:retention:api:{ym}:{life_nl}:{scope_type}:{scope_key}:{q}`) — 업로드 후 캐시가 즉시 갱신되지 않을 수 있다 ⚠️
- [ ] 매출 `life_nl_insurer_map` 캐시 키 `dash:lifeinsmap:{ym}:{part}:{branch}`가 새 업로드 후에도 구버전을 반환하지 않는가?

### 템플릿/JS

- [ ] `#dash-sales` json_script 태그 id 변경 시 `dash_sales_page.js`의 `getElementById()` 참조도 함께 수정했는가?
- [ ] `dash_sales_page.js`에 BFCache 가드가 없으므로, 브라우저 뒤로가기 시 차트 초기화가 중복 실행될 수 있다 ⚠️
- [ ] `sales_upload.js`는 `type="module"` — `window.CommissionCommon` 같은 전역 네임스페이스에 의존하지 않는가?
- [ ] vendor Chart.js가 `dash_sales_page.js`보다 먼저 로드되는가?
