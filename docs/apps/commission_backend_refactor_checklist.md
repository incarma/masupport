# django_ma commission 앱 백엔드 리팩토링 지침서

> 목적: `django_ma/commission` 앱 백엔드 코드를 **성능 변화 0 / 기능 변화 0** 범위에서 정리한다.  
> 범위: `commission/views`, `commission/services`, `commission/upload_handlers`, `commission/upload_utils`, `commission/services/rate_example_normalizers` 및 관련 shim/public API.  
> 금지: 이 지침서는 실제 패치가 아니라, 향후 패치 작업자가 추가 코드 제공 없이 안전하게 리팩토링을 진행하기 위한 작업 기준서다.

---

## 0. 리팩토링 대원칙 체크리스트

### 0-1. 반드시 보존할 것

- [ ] 기존 URL name, route, namespace `commission`을 변경하지 않는다.
- [ ] 기존 템플릿의 `data-*`, DOM id, JS 호출 계약을 변경하지 않는다.
- [ ] JSON 응답 형식은 `{ "ok": true|false, "message": "...", "data": {...} }` 규약을 유지한다.
- [ ] `commission.views.utils_json._json_ok`, `_json_error`, `_set_attachment_filename`을 commission JSON/다운로드 응답 SSOT로 유지한다.
- [ ] 파일 다운로드는 반드시 권한 검증 후 `HttpResponse` 또는 `FileResponse` attachment로 제공한다.
- [ ] `.file.url`, `/media/` 직접 노출 방식은 절대 도입하지 않는다.
- [ ] `CustomUser.pk`가 사번 문자열이라는 전제를 침범하지 않는다.
- [ ] 엑셀/CSV/PDF 업로드 파싱에서 사번 정규화는 `commission.upload_utils._norm_emp_id` 계열 규약을 따른다.
- [ ] 업로드 타입 문자열은 변경하지 않는다. 특히 `registry.py`의 `upload_type`은 DB/프론트/업로드 라우팅의 유일키다.
- [ ] `replace` / `append` 동작 의미를 변경하지 않는다.
- [ ] `RateExample` 정규화 결과 저장 정책을 변경하지 않는다.
- [ ] 손해보험 수정률 parser의 raw 백분율 저장 정책을 변경하지 않는다.
- [ ] 손해보험 지급률 `fire_pay.py`의 `/ 0.97` 보정 정책을 변경하지 않는다.
- [ ] 생명보험 환산율 parser의 Excel percent format `×100` 보정 정책을 유지한다.
- [ ] 처브/카디프 등 PDF raw `% × 12` 저장 정책을 유지한다.
- [ ] `사용안함` sentinel 값은 계산 옵션 체인 보장을 위해 유지한다.
- [ ] `DepositUploadLog` 갱신은 `commission.upload_handlers.deposit._update_upload_log`를 SSOT로 유지한다.
- [ ] `Collect` 도메인 비즈니스 로직은 `commission.services.collect`를 SSOT로 유지한다.
- [ ] `RateExample` 계산 로직은 `commission.services.rate_example_calculator`를 SSOT로 유지한다.
- [ ] 정상 동작 중인 legacy shim은 제거하지 않는다. 제거가 필요하면 별도 호환성 검증 후 별도 작업으로 분리한다.

### 0-2. 이번 리팩토링에서 허용되는 것

- [ ] 중복 helper를 공통 모듈로 이동한다.
- [ ] 파일명/폴더 구조를 더 명확하게 바꾸되, 기존 import surface는 shim으로 유지한다.
- [ ] parser 내부 반복 패턴을 공통 helper로 추출한다.
- [ ] 주석을 실제 동작 기준으로 보완한다.
- [ ] 타입 힌트와 dataclass를 추가한다.
- [ ] logging 메시지를 표준화한다.
- [ ] `__all__` export surface를 명확히 한다.
- [ ] 빈 stub 파일은 삭제하지 않고 목적 주석을 보완한다.
- [ ] 테스트/검증 시나리오를 추가한다.

### 0-3. 이번 리팩토링에서 금지되는 것

- [ ] DB 모델 필드명, migration, unique constraint를 변경하지 않는다.
- [ ] 업로드/다운로드 URL을 변경하지 않는다.
- [ ] 프론트 요구 파라미터명을 변경하지 않는다.
- [ ] `RateExampleConversionRow` 필드 의미를 변경하지 않는다.
- [ ] 환산율/수정률 계산 산식을 “정리” 명목으로 수정하지 않는다.
- [ ] 파서별 보험사명 canonical 값(`DB`, `KB`, `한화`, `푸본현대`, `AIG` 등)을 변경하지 않는다.
- [ ] PDF parser 라이브러리 fallback 순서를 무단 변경하지 않는다.
- [ ] 예외를 `except: pass`로 삼키지 않는다.
- [ ] `@csrf_exempt`를 새로 추가하지 않는다.
- [ ] 업로드 실패 token 권한 정책을 완화하지 않는다.
- [ ] audit 로그 호출 위치를 제거하지 않는다.
- [ ] 파일 직접 URL 노출, storage path 노출, temp file 방치 가능성을 만들지 않는다.

---

## 1. 현재 commission 앱 백엔드 기준 구조

```text
commission/
├── admin.py
├── apps.py
├── tests.py
├── views/
│   ├── __init__.py
│   ├── _excel_export.py
│   ├── _files.py
│   ├── _ym.py
│   ├── api_deposit.py
│   ├── api_deposit_impl.py
│   ├── api_rate_example.py
│   ├── api_rate_example_calculate.py
│   ├── api_rate_example_conversion.py
│   ├── api_rate_example_options.py
│   ├── api_upload.py
│   ├── approval.py
│   ├── collect_notice_export.py
│   ├── constants.py
│   ├── downloads.py
│   ├── pages.py
│   ├── utils_excel.py
│   ├── utils_fail_excel.py
│   └── utils_json.py
├── services/
│   ├── __init__.py
│   ├── collect.py
│   ├── collect_notice_excel.py
│   ├── rate_example.py
│   ├── rate_example_calculator.py
│   ├── rate_example_conversion_edit.py
│   ├── rate_example_normalizer.py
│   ├── rate_example_options.py
│   ├── rate_example_pay_normalizer.py
│   └── rate_example_normalizers/
│       ├── fire_*.py
│       └── life_*.py
├── upload_handlers/
│   ├── __init__.py
│   ├── approval.py
│   ├── collect.py
│   ├── deposit.py
│   ├── efficiency.py
│   └── registry.py
└── upload_utils/
    ├── __init__.py
    ├── _convert.py
    ├── _db.py
    ├── _detect.py
    ├── _readers.py
    └── upload_utils.py
```

---

## 2. 목표 폴더 구조 제안

> 원칙: 폴더 구조는 바꾸되, 기존 import 경로는 shim으로 살린다.  
> 1차 패치에서는 파일 이동보다 **신규 공통 helper 추가 + 기존 파일 내부 import 교체**를 우선한다.

### 2-1. 1차 리팩토링 후 권장 구조

```text
commission/
├── views/
│   ├── _excel_export.py
│   ├── _files.py
│   ├── _ym.py
│   ├── utils_json.py
│   ├── utils_fail_excel.py
│   ├── utils_excel.py              # legacy shim 유지
│   ├── downloads.py
│   ├── api_upload.py
│   ├── approval.py
│   ├── collect_notice_export.py
│   └── ...
├── services/
│   ├── collect.py
│   ├── deposit.py                  # 신규 후보: Deposit 조회 서비스
│   ├── collect_notice_excel.py
│   ├── rate_example.py
│   ├── rate_example_calculator.py
│   ├── rate_example_conversion_edit.py
│   ├── rate_example_normalizer.py
│   ├── rate_example_options.py
│   ├── rate_example_pay_normalizer.py
│   └── rate_example_normalizers/
│       ├── _common/
│       │   ├── text.py             # 신규 후보
│       │   ├── decimal.py          # 신규 후보
│       │   ├── excel.py            # 신규 후보
│       │   ├── pdf.py              # 신규 후보
│       │   └── rows.py             # 신규 후보
│       ├── fire/
│       │   ├── aig.py              # 장기 후보. 1차에서는 기존 fire_aig.py 유지 가능
│       │   └── ...
│       └── life/
│           ├── abl.py              # 장기 후보. 1차에서는 기존 life_abl.py 유지 가능
│           └── ...
├── upload_handlers/
│   ├── registry.py
│   ├── deposit.py
│   ├── collect.py
│   ├── approval.py
│   └── efficiency.py
└── upload_utils/
    ├── _convert.py
    ├── _detect.py
    ├── _readers.py
    ├── _db.py
    └── upload_utils.py             # legacy shim 유지
```

### 2-2. 파일명 변경은 2차 과제로 분리

- [ ] 1차: `life_*.py`, `fire_*.py` 파일명 유지.
- [ ] 1차: 공통 helper만 추가하고 import 교체.
- [ ] 2차: `rate_example_normalizers/life/*.py`, `fire/*.py` 하위 폴더로 이동 검토.
- [ ] 2차 이동 시 반드시 기존 경로에 shim을 둔다.

예시:

```python
# commission/services/rate_example_normalizers/life_abl.py
# legacy shim
from commission.services.rate_example_normalizers.life.abl import *  # noqa
```

- [ ] `rate_example_normalizer.py` dispatcher가 기존 import와 신규 import 중 어느 것을 쓰는지 명확히 한다.
- [ ] 이동 패치는 보험사 1~2개 단위로 쪼갠다.

---

## 3. 리팩토링 우선순위

### P0. 회귀 방지 기반 작업

- [ ] 현재 동작을 문서화한다.
- [ ] 업로드 타입 목록과 보험사 parser 목록을 고정한다.
- [ ] 핵심 API 응답 샘플을 저장한다.
- [ ] 테스트용 샘플 파일이 없다면 최소한 “업로드 결과 row count” 검증 스크립트를 만든다.
- [ ] `python manage.py check`를 기준선으로 둔다.
- [ ] `bash scripts/harness/security_lint.sh` 결과를 기준선으로 둔다.
- [ ] `bash scripts/harness/quality_lint.sh` 결과를 기준선으로 둔다.

### P1. views 계층 중복 제거

- [ ] `api_deposit_impl.py`의 로컬 JSON helper가 있다면 `utils_json._json_error`로 통일한다.
- [ ] Excel response 생성은 `_excel_export.py`만 사용하게 통일한다.
- [ ] 업로드 temp file 저장/삭제는 `_files.save_temp_upload`, `_files.safe_delete`만 사용한다.
- [ ] year/month/ym 파싱은 `_ym.resolve_ym`만 사용한다.
- [ ] 실패 엑셀 token 생성은 `utils_fail_excel.store_fail_rows_as_excel`만 사용한다.
- [ ] 다운로드 filename은 `_set_attachment_filename`만 사용한다.

### P2. upload_handlers/upload_utils 정리

- [ ] `upload_handlers.registry.UploadSpec`을 업로드 라우팅의 유일한 SSOT로 유지한다.
- [ ] `views/constants.SUPPORTED_UPLOAD_TYPES`는 registry 기반 빌더를 유지한다.
- [ ] upload handler 내부에서 컬럼 탐지/숫자 변환을 직접 재구현한 부분을 `upload_utils`로 통일 가능한지 검토한다.
- [ ] 다만 handler별 raw matrix 특수 로직은 성급히 공통화하지 않는다.
- [ ] `_update_upload_log` wrapper는 legacy 호환용으로 유지한다.
- [ ] `upload_utils/upload_utils.py` legacy shim은 유지한다.

### P3. RateExample normalizer 공통화

- [ ] parser별 `_clean_text`, `_to_decimal_percent`, `_merged_value`, `_append_unique`, `_coverage_type` 중 공통화 가능한 것만 추출한다.
- [ ] parser별 보정 정책이 다른 함수는 이름만 같아도 공통화하지 않는다.
- [ ] 특히 `%`, `×100`, `×12`, `/0.97`, raw 그대로 저장 정책을 절대 섞지 않는다.
- [ ] PDF 텍스트 추출 fallback은 보험사별로 다르므로 1차에서는 공통화하지 않는다.
- [ ] Excel 병합셀 전파 helper는 공통화 후보이나, “가로 병합 무시/세로 병합 전파”처럼 보험사별 의미 차이가 있으면 별도 helper명을 둔다.
- [ ] row 생성 boilerplate는 공통 factory 후보이나, insurer/coverage/year 정책이 명확히 같은 그룹만 묶는다.

### P4. Deposit 조회 서비스 분리

- [ ] `commission/services/deposit.py` 신규 추가를 검토한다.
- [ ] `api_deposit_impl.py`의 ORM 조회/권한 범위/serializer를 서비스 함수로 이동한다.
- [ ] View는 request parsing, permission check, JSON response만 담당하게 만든다.
- [ ] 기존 API 응답 key를 1개도 바꾸지 않는다.

### P5. 주석/문서 정비

- [ ] “수정률/환산율/지급률” 용어를 파일별 역할에 맞게 통일한다.
- [ ] 보험사별 parser 상단 docstring에 “저장값 단위”를 반드시 명시한다.
- [ ] raw 컬럼 위치는 1-based/0-based 여부를 명확히 적는다.
- [ ] “왜 공통화하지 않았는지”가 중요한 특수 로직에는 보존 주석을 단다.
- [ ] legacy shim에는 제거 금지 이유와 대체 import 경로를 명시한다.

---

## 4. views 계층 리팩토링 체크리스트

### 4-1. `views/utils_json.py`

현재 역할:

- `_json_error(message, status=400, **extra)`
- `_json_ok(message=None, **extra)`
- `_set_attachment_filename(resp, filename)`

작업 기준:

- [ ] commission 앱의 모든 JSON 실패 응답은 `_json_error`를 사용한다.
- [ ] commission 앱의 모든 JSON 성공 응답은 `_json_ok`를 사용한다.
- [ ] 새 helper명을 만들지 않는다.
- [ ] 파일 다운로드 응답에는 `_set_attachment_filename`을 사용한다.
- [ ] 한글 파일명 대응을 직접 재구현하지 않는다.
- [ ] `_set_attachment_filename`의 `filename` + `filename*` 동시 세팅 정책을 유지한다.

검토 대상:

- [ ] `api_deposit_impl.py`
- [ ] `api_upload.py`
- [ ] `approval.py`
- [ ] `downloads.py`
- [ ] `collect_notice_export.py`
- [ ] `api_rate_example*.py`

금지 예:

```python
return JsonResponse({"success": True})
return JsonResponse({"status": "success"})
```

허용 예:

```python
return _json_ok("조회되었습니다.", data=data)
return _json_error("권한이 없습니다.", status=403)
```

---

### 4-2. `views/_excel_export.py`

현재 역할:

- `rows_to_xlsx_bytes(rows, sheet_name)`
- `xlsx_bytes_response(content, filename)`
- `rows_to_excel_response(rows, sheet_name, filename)`
- `XLSX_MIME`

작업 기준:

- [ ] rows → DataFrame → xlsx bytes 반복 구현을 제거한다.
- [ ] pandas/openpyxl 엔진 정책을 유지한다.
- [ ] rows가 비어 있으면 호출부에서 404 처리하는 기존 패턴을 유지한다.
- [ ] `xlsx_bytes_response`는 cache bytes 다운로드에도 재사용한다.
- [ ] `Content-Disposition` 직접 세팅을 새로 만들지 않는다.

검토 대상:

- [ ] `downloads.py`
- [ ] `utils_fail_excel.py`
- [ ] `collect_notice_export.py`
- [ ] 향후 환수내역/안내자료 다운로드 기능

주의:

- [ ] `collect_notice_excel.py`은 openpyxl 스타일 workbook을 직접 생성하므로 `_excel_export.py`로 억지 통합하지 않는다.
- [ ] 단순 table export와 서식 workbook export를 구분한다.

---

### 4-3. `views/_files.py`

현재 역할:

- `TempUpload`
- `save_temp_upload(excel_file)`
- `safe_delete(temp)`

작업 기준:

- [ ] 업로드 임시 저장은 `save_temp_upload`로 통일한다.
- [ ] 처리 후 삭제는 `finally: safe_delete(temp)` 패턴으로 통일한다.
- [ ] 삭제 실패는 logger.exception으로 기록하고 사용자 기능을 막지 않는다.
- [ ] `FileSystemStorage()` 직접 생성 반복을 줄인다.
- [ ] 파일 경로를 사용자 응답에 노출하지 않는다.

권장 패턴:

```python
temp = save_temp_upload(excel_file)
try:
    result = handler(temp.file_path, temp.original_name, ...)
finally:
    safe_delete(temp)
```

---

### 4-4. `views/_ym.py`

현재 역할:

- `split_ym`
- `validate_ym`
- `resolve_ym`

작업 기준:

- [ ] `YYYY-MM`, `YYYYMM`, `year/month` 파싱 로직을 재구현하지 않는다.
- [ ] `approval.py`, `downloads.py`, collect 계열에서 월도 형식이 다른 경우 명시적으로 분리한다.
- [ ] approval/efficiency는 `YYYY-MM` 기준이다.
- [ ] collect 원장은 `YYYYMM` 기준이므로 혼용하지 않는다.

---

### 4-5. `views/downloads.py`

현재 역할:

- 실패 업로드 token 다운로드
- 수수료 미결 다운로드
- 지점효율 초과 다운로드

작업 기준:

- [ ] token 다운로드는 `cache.get(f"commission:upload_fail:{token}")` 계약을 유지한다.
- [ ] `owner_id`가 있으면 업로드 실행자 본인만 허용한다.
- [ ] legacy token(`owner_id` 없음)은 superuser만 허용한다.
- [ ] 다운로드 권한을 완화하지 않는다.
- [ ] 최신 `ym` fallback 동작을 변경하지 않는다.
- [ ] rows key, sheet name, filename을 변경하지 않는다.

---

### 4-6. `views/collect_notice_export.py`

현재 역할:

- 환수내역 안내자료 xlsx/pdf 생성 API
- FormData 수신
- service 호출 후 attachment 반환

작업 기준:

- [ ] View는 request validation과 response 생성만 담당한다.
- [ ] Excel/PDF 생성 로직은 `services.collect_notice_excel`에 둔다.
- [ ] output은 `xlsx`, `pdf`만 허용한다.
- [ ] manual_rows는 JSON list만 허용한다.
- [ ] `file_yms` 수와 `notice_files` 수 일치 검증을 유지한다.
- [ ] PDF는 `b"%PDF"` magic byte 검증을 유지한다.
- [ ] LibreOffice RuntimeError는 503으로 반환한다.
- [ ] 생성 결과 bytes를 서버 파일 URL로 노출하지 않는다.

---

## 5. upload_handlers 리팩토링 체크리스트

### 5-1. `upload_handlers/registry.py`

현재 역할:

- `UploadSpec(upload_type, mode, fn, msg_tpl)`
- `_REGISTRY`
- `get_upload_spec(upload_type)`
- `supported_upload_types()`

작업 기준:

- [ ] 업로드 타입 추가/삭제/이름 변경은 registry에서만 한다.
- [ ] `views/api_upload.py`는 registry만 신뢰한다.
- [ ] `views/constants.SUPPORTED_UPLOAD_TYPES`는 registry 기반 자동 생성 정책을 유지한다.
- [ ] fallback set은 “서버 부팅 안전망”으로만 둔다.
- [ ] `upload_type` 문자열을 리팩토링 명목으로 영문화하지 않는다.
- [ ] `mode="df"`와 `mode="file"` 의미를 변경하지 않는다.
- [ ] raw matrix handler를 `df` mode로 바꾸지 않는다.
- [ ] `환수관리`는 `collect_handler.handle_upload_collect`로 유지한다.

---

### 5-2. `upload_handlers/deposit.py`

보존 정책:

- [ ] Deposit 업로드 도메인의 실질 SSOT다.
- [ ] `_update_upload_log`는 `DepositUploadLog` 갱신 SSOT다.
- [ ] `row_count` / `rows_count`, `file_name` / `filename` 모델 필드 차이 방어를 유지한다.
- [ ] 보증보험/기타채권은 대상 user_id 기존 rows 삭제 후 bulk_create하는 현재 방식을 유지한다.
- [ ] 통산손보/통산생보는 raw matrix A열에서 emp7 추출 후 `DepositSummary` 갱신하는 정책을 유지한다.
- [ ] 최종지급액/환수지급예상/채권지표/응당생보/응당손보 필드 매핑을 변경하지 않는다.

리팩토링 후보:

- [ ] 공통 user existence lookup helper 통일
- [ ] 공통 amount/date conversion helper 사용 확대
- [ ] `_update_summary` 류 내부 helper의 docstring 보완
- [ ] handler별 return dict 형식 통일

금지:

- [ ] `DepositSummary`를 row-by-row unnecessary save로 바꾸지 않는다.
- [ ] 기존 bulk 처리 성능을 저하시키지 않는다.
- [ ] 사번 정규화를 변경하지 않는다.

---

### 5-3. `upload_handlers/approval.py`

보존 정책:

- [ ] raw matrix 기준 B=이름, C=사번, N=실지급액, O=결재값을 유지한다.
- [ ] 조건 `actual_pay > 0`, `approval_flag == "N"`을 유지한다.
- [ ] 유자격 조건 `regist in {"손생등록", "생보등록", "손보등록"}`을 유지한다.
- [ ] 동일 사번 실지급액 합산 정책을 유지한다.
- [ ] part 파라미터가 있으면 해당 part 사용자만 저장한다.
- [ ] `ApprovalPending.objects.bulk_create(update_conflicts=True)` 유지.
- [ ] `_handle_upload_commission_approval` alias 유지.

리팩토링 후보:

- [ ] `_safe_cell`을 upload_utils 공통 “empty-like cell” helper로 추출 가능.
- [ ] return dict 구조를 typed dataclass로 내부 정리 후 dict 반환 가능.
- [ ] logger 추가 가능.

주의:

- [ ] `_safe_cell`의 `"nan"`, `"none"` 공란 처리 정책을 유지한다.
- [ ] `missing_sample[:10]` 정책을 유지한다.

---

### 5-4. `upload_handlers/efficiency.py`

보존 정책:

- [ ] 상단 0~5행에서 `구분`/`금액` 또는 `지급액` 헤더 탐지한다.
- [ ] 사번은 E열 고정이다.
- [ ] `구분 == "지급"`인 금액만 합산한다.
- [ ] part 파라미터가 있으면 해당 part 사용자만 저장한다.
- [ ] `EfficiencyPayExcess.objects.bulk_create(update_conflicts=True)` 유지.
- [ ] `_handle_upload_efficiency_pay_excess` alias 유지.

리팩토링 후보:

- [ ] `_find_header_row_and_col_indices`에 타입 힌트와 docstring 보강.
- [ ] `_safe_text` helper 공통화.
- [ ] empty raw matrix 방어 추가 검토. 단, 기존 예외 흐름이 사용자에게 필요한 경우 변경 금지.

---

### 5-5. `upload_handlers/collect.py`

보존 정책:

- [ ] `COL_MAP` 고정 컬럼 매핑 유지.
- [ ] 필수 컬럼 `사번`, `월도`, `최종지급액` 유지.
- [ ] `emp_id`, `ym` 정규화 실패 row skip 유지.
- [ ] `PART_ALIAS {"1인GA사업부": "MA사업4부"}` 유지.
- [ ] `CollectRecord.bulk_create(update_conflicts=True)` 유지.
- [ ] `unique_fields=["emp_id", "ym"]` 유지.
- [ ] `CollectUploadLog`는 ym별 `update_or_create(row_count)` 처리 유지.
- [ ] `file_name`, `uploaded_by`는 뷰 after-hook 대상이라는 주석을 유지한다.
- [ ] Audit은 handler가 아니라 View 계층에서 수행한다.

리팩토링 후보:

- [ ] 필수 컬럼 검증 helper 분리.
- [ ] decimal/date/text 변환 공통화.
- [ ] skip reason 집계 추가는 기능 변화가 될 수 있으므로 별도 과제로 분리.

---

## 6. upload_utils 리팩토링 체크리스트

### 6-1. `upload_utils/__init__.py`

작업 기준:

- [ ] 외부 import는 `commission.upload_utils`로 통일한다.
- [ ] 하위 모듈 직접 import는 내부 구현에서만 허용한다.
- [ ] `__all__`은 실제 re-export 심볼과 일치시킨다.
- [ ] legacy import 경로를 제거하지 않는다.

---

### 6-2. `_convert.py`

보존 정책:

- [ ] `DEC2 = Decimal("0.00")` 유지.
- [ ] `_to_int`, `_to_decimal`, `_safe_decimal_q2`, `_to_date`, `_to_div`, `_norm_emp_id`, `_extract_emp7_from_a` 동작 유지.
- [ ] pandas `isna` 방어 유지.
- [ ] `_norm_emp_id("1234567.0") -> "1234567"` 정책 유지.
- [ ] `_extract_emp7_from_a`의 `s[-8:-1]` 정책 유지.

리팩토링 후보:

- [ ] 공통 empty-like 값 `("", "nan", "none", "-")` 상수화.
- [ ] docstring에 저장 대상 필드 설명 추가.
- [ ] `Decimal` quantize 정책을 함수명에 명확히 표현.

금지:

- [ ] 사번 앞자리 0 제거/보정 같은 신규 정책 도입 금지.
- [ ] `_extract_emp7_from_a` 추출 위치 변경 금지.

---

### 6-3. `_detect.py`

보존 정책:

- [ ] 컬럼 alias와 ban group 정책 유지.
- [ ] 사번/등록번호 탐지 우선순위 유지.
- [ ] `_find_exact_or_space_removed` 공백 제거 매칭 유지.

리팩토링 후보:

- [ ] alias 세트를 상단 상수로 정리.
- [ ] 탐지 실패 시 logger.debug 추가.
- [ ] 함수별 “사용 도메인” 주석 보완.

---

### 6-4. `_readers.py`

보존 정책:

- [ ] xlsx/openpyxl, xls/xlrd, OLE2/xls 안내 메시지 유지.
- [ ] CSV/TSV/HTML table fallback 유지.
- [ ] `_read_excel_safely`, `_read_excel_raw_matrix` public API 유지.
- [ ] encoding best-effort 정책 유지.

리팩토링 후보:

- [ ] reader별 예외 메시지를 상수화.
- [ ] HTML/text fallback 경로에 logger.debug 추가.
- [ ] read matrix/DataFrame 차이를 docstring으로 명확화.

---

### 6-5. `_db.py`

보존 정책:

- [ ] `_bulk_existing_user_ids`는 `CustomUser.pk` 문자열 기준으로 bulk 조회한다.
- [ ] `_update_upload_log`는 deprecated wrapper로 유지한다.
- [ ] wrapper는 `commission.upload_handlers.deposit._update_upload_log`로 위임한다.

리팩토링 후보:

- [ ] deprecated 주석 강화.
- [ ] 신규 코드에서는 `_db._update_upload_log` import 금지 안내 추가.

---

## 7. services 계층 리팩토링 체크리스트

### 7-1. `services/collect.py`

보존 정책:

- [ ] Collect 도메인 비즈니스 로직 SSOT다.
- [ ] 뷰에서 Collect ORM 직접 조작 금지.
- [ ] `YYYYMM` 월도 유틸 유지.
- [ ] 권한 스코프 유지:
  - [ ] superuser: 필터 기반 조회
  - [ ] head: 본인 branch
  - [ ] leader: 팀/branch 기반
- [ ] 최신 피드백 Subquery 정책 유지.
- [ ] DepositSummary bulk map 정책 유지.
- [ ] feedback 수정/삭제는 `transaction.atomic` + `select_for_update` + `author_id` 검증 유지.
- [ ] dropdown feedback은 이력 누적형 구조 유지.

리팩토링 후보:

- [ ] 반환 payload serializer 함수 분리.
- [ ] 권한 스코프 함수 docstring 보완.
- [ ] feedback_type choices 주석 보완.
- [ ] `ym_to_date`, `date_to_ym`, `offset_ym` 테스트 추가.

---

### 7-2. `services/collect_notice_excel.py`

보존 정책:

- [ ] HTTP response를 만들지 않는다.
- [ ] View에는 bytes/filename/row_count 결과만 반환한다.
- [ ] `NoticeSourceFile`, `NoticeWorkbookResult`, `NoticePdfResult` dataclass 유지.
- [ ] `HEADERS`, `COLUMN_WIDTHS`, `SHEET_NAME`, `FONT_NAME` 등 결과 엑셀 구조 상수 유지.
- [ ] 개인정보 마스킹 정책 유지.
- [ ] manual_rows 검증/정규화 유지.
- [ ] LibreOffice headless 변환 유지.
- [ ] PDF magic 검증 유지.
- [ ] LibreOffice 없으면 RuntimeError 유지.

리팩토링 후보:

- [ ] workbook style 적용 함수 그룹화.
- [ ] row normalization과 masking 함수 분리.
- [ ] PDF 변환 함수에 작업 디렉토리 cleanup 보장 주석 추가.

금지:

- [ ] 생성 파일을 MEDIA URL로 노출하지 않는다.
- [ ] PDF 변환 실패를 빈 PDF로 대체하지 않는다.

---

### 7-3. `services/rate_example.py`

보존 정책:

- [ ] RateExampleService가 파일 검증/생성/삭제 SSOT다.
- [ ] `ALLOWED_EXTENSIONS`, `ALLOWED_MIME_TYPES`, `MAX_FILE_SIZE` 정책 유지.
- [ ] `create()`는 `transaction.atomic()` 유지.
- [ ] CAT_PAY는 insurer/product_kind 초기화 및 replace 강제 정책 유지.
- [ ] `delete()`는 물리 파일 삭제 후 DB 삭제 정책 유지.
- [ ] 파일 삭제 예외는 logger.exception 처리 유지.
- [ ] `list_all()`의 `uploaded_by select_related` 유지.

리팩토링 후보:

- [ ] validation error 메시지 상수화.
- [ ] create input dataclass 도입.
- [ ] delete 파일 처리 helper 추출.

---

### 7-4. `services/rate_example_normalizer.py`

보존 정책:

- [ ] RateExample 정규화 오케스트레이터다.
- [ ] `pay` 카테고리는 `rate_example_pay_normalizer`로 위임한다.
- [ ] openpyxl custom property 오류 시 `docProps/custom.xml` 제거 재시도 정책 유지.
- [ ] PDF/XLSX 분기 유지.
- [ ] life/fire conv 대상 보험사별 parser dispatch 유지.
- [ ] replace면 기존 row 삭제 후 bulk_create.
- [ ] append면 기존 row 삭제 없이 추가.
- [ ] FieldFile.path 또는 FieldFile.open 기반 내부 접근만 사용한다.
- [ ] 파일 URL 직접 접근 금지.

리팩토링 후보:

- [ ] dispatcher mapping을 상수 dict로 정리.
- [ ] insurer/product_kind별 분기 주석 보완.
- [ ] parser import를 지연 import로 정리해 순환 위험 낮추기.
- [ ] bulk_create batch_size 명시 검토.

금지:

- [ ] parser가 DB 저장까지 직접 하게 만들지 않는다.
- [ ] replace/append 의미 변경 금지.

---

### 7-5. `services/rate_example_calculator.py`

보존 정책:

- [ ] Decimal 기반 계산 유지.
- [ ] 사용자 노출 가능한 오류는 `RateExampleCalcError`로만 낸다.
- [ ] `CalcInput` dataclass 유지.
- [ ] RateExampleConversionRow와 RateExamplePayRow 조합 정책 유지.
- [ ] IBK 지급률 상품군 전용 계산 유지.
- [ ] DB생명 예외 산식 유지.
- [ ] 손해보험은 수정률 year1을 배율로 직접 사용한다.
- [ ] `EXCLUDED_CALC_INSURERS` 현재 빈 set 정책 유지.

리팩토링 후보:

- [ ] 생보/손보 계산 분기 함수 명확화.
- [ ] 보험사별 특수 산식 dict화 검토.
- [ ] 에러 메시지 상수화.

금지:

- [ ] 보험료/환산율/지급률 산식을 임의 조정하지 않는다.
- [ ] Decimal을 float로 바꾸지 않는다.

---

### 7-6. `services/rate_example_conversion_edit.py`

보존 정책:

- [ ] 환산율/수정률 직접수정 서비스 SSOT다.
- [ ] View는 HTTP/JSON만 담당한다.
- [ ] ORM 변경/검증/트랜잭션은 서비스에서 처리한다.
- [ ] row id가 보험사 scope에 속하는지 재검증한다.
- [ ] 신규 row는 최신 RateExample source_file에 연결한다.
- [ ] Decimal parsing 정책 유지.
- [ ] fire는 strategy/year2~4 비움 정책 유지.
- [ ] 삭제/수정/신규 생성은 `transaction.atomic()` 유지.

리팩토링 후보:

- [ ] 입력 payload dataclass 도입.
- [ ] validation 함수명 명확화.
- [ ] fire/life 차이 주석 보강.

---

### 7-7. `services/rate_example_options.py`

보존 정책:

- [ ] 계산 입력 옵션 조회 서비스 SSOT다.
- [ ] `RateExampleOptionQuery` dataclass 유지.
- [ ] insurer_type life/fire 정규화 유지.
- [ ] insurer canonical map 유지.
- [ ] kind 값 `insurers/products/plan_types/pay_periods` 유지.
- [ ] IBK products는 `RateExamplePayRow.coverage_type("[IBK]...")` 기준 제공 유지.
- [ ] IBK는 plan/pay_period 없음 정책 유지.

리팩토링 후보:

- [ ] canonical map 상수명 명확화.
- [ ] 빈 plan_type 제거 정책과 `사용안함` sentinel 관계 주석 보완.

---

### 7-8. `services/rate_example_pay_normalizer.py`

보존 정책:

- [ ] 생보 지급률 xlsx 20개 생보사 고정 컬럼 매핑 유지.
- [ ] `TARGET_SHEET = "① 5천만, 3천만↑"` 유지.
- [ ] 지급률 저장값 = raw / 0.97 유지.
- [ ] `PAY_QUANT = 0.0001` 유지.
- [ ] IBK는 `coverage_type="[IBK]{상품명}"` 별도 정책 유지.
- [ ] fire 지급률은 `build_fire_pay_rows`로 위임한다.
- [ ] normalize_mode replace면 pay rows 전체 삭제 후 bulk_create 유지.

리팩토링 후보:

- [ ] insurer column map 상수 정리.
- [ ] 생보/손보 지급률 저장 정책 주석 강화.
- [ ] /0.97 보정 주석을 계산 화면과 연결해 설명.

---

## 8. RateExample normalizer 공통화 설계

### 8-1. 공통 helper 후보

#### `_common/text.py`

추출 후보:

```python
def clean_spaces(value: object) -> str: ...
def clean_lines(value: object, *, sep: str = " ") -> str: ...
def compact_key(value: object) -> str: ...
def is_empty_like(value: object) -> bool: ...
```

적용 후보:

- `life_abl.py`
- `life_db.py`
- `life_met.py`
- `life_dongyang.py`
- `life_kb.py`
- `fire_aig.py`
- `fire_meritz.py`

주의:

- [ ] 상품명 줄바꿈을 “공백으로 결합”하는 parser와 “붙여서 결합”하는 parser를 구분한다.
- [ ] 미래에셋은 줄별 trim 후 붙이는 정책이 있으므로 단순 clean_spaces로 대체 금지.
- [ ] 삼성은 줄바꿈을 공백으로 결합한다.
- [ ] 라이나 PDF는 상품명 continuation을 공백 없이 결합한다.

#### `_common/decimal.py`

추출 후보:

```python
def decimal_from_text(value: object) -> Decimal | None: ...
def decimal_percent_cell(cell) -> Decimal | None: ...
def decimal_raw_percent(value: object) -> Decimal | None: ...
def decimal_x12_percent(value: object) -> Decimal | None: ...
```

주의:

- [ ] 이름에 저장 정책을 반드시 포함한다.
- [ ] `decimal_percent_cell`: Excel percent format이면 ×100.
- [ ] `decimal_raw_percent`: 문자열 `%` 제거 후 그대로.
- [ ] `decimal_x12_percent`: raw % ×12.
- [ ] 손보 수정률 raw 그대로 저장 함수와 지급률 `/0.97` 함수는 분리한다.

#### `_common/excel.py`

추출 후보:

```python
def build_merged_value_map(ws) -> dict[tuple[int, int], object]: ...
def cell_value_with_merged(ws, merged_map, row, col): ...
def find_header_row(ws, predicates, max_scan_row=30): ...
```

주의:

- [ ] 삼성처럼 “가로 병합은 좌측만 인정, 세로 병합은 전파”하는 정책은 별도 함수가 필요하다.
- [ ] KDB/라이나/농협처럼 병합값을 모든 점유 셀에 전파하는 정책과 섞지 않는다.
- [ ] worksheet 자체를 unmerge하거나 값을 직접 써넣지 않는다.

#### `_common/rows.py`

추출 후보:

```python
def append_unique(rows, seen, row, key_fields=None): ...
def make_conversion_row(...): ...
```

주의:

- [ ] row factory는 보험사별 insurer, coverage, year 정책이 너무 다르면 공통화하지 않는다.
- [ ] `source_sheet`, `source_row_no` 보존 정책을 변경하지 않는다.

#### `_common/pdf.py`

1차에서는 보류 권장:

- [ ] PDF parser는 보험사별 라이브러리와 추출 방식이 다르다.
- [ ] `pypdf`, `PyPDF2`, `PyMuPDF`, `pdfplumber` fallback 순서가 보험사별로 다르다.
- [ ] 1차 리팩토링에서는 공통화보다 주석 보완이 안전하다.

---

### 8-2. 공통화 금지 대상

- [ ] AIG PDF regex row parser
- [ ] 하나손보/하나생명 좌표 기반 PDF parser
- [ ] 흥국 PDF word coordinate parser
- [ ] 처브 PPP/FA/P/CP 조건 parser
- [ ] 카디프 x12 + plan sentinel parser
- [ ] 농협생명 block/pair parser
- [ ] 한화 product_kind별 parser
- [ ] 삼성 병합 정책
- [ ] 현대 상품명 continuation merge
- [ ] 손보 지급률 `/0.97` parser

---

## 9. 생명보험 parser별 회귀 방지 체크리스트

### 9-1. ABL

- [ ] 필수 시트 2개 누락 시 예외 유지.
- [ ] 저축성 보종 `연금` 고정 유지.
- [ ] 보장성 상품명 `종신` 포함 시 `종신/CI` 유지.
- [ ] 상품명/구분 carry-down 유지.
- [ ] 저축성 year4 None 유지.

### 9-2. 동양

- [ ] 대상 시트 `주계약` only 유지.
- [ ] 1~14행 제외 유지.
- [ ] 대표상품명 B열 carry-down 유지.
- [ ] 구분은 C열 첫 `_` 뒤 텍스트 유지.
- [ ] J열 year1, L열 year2~4 동일 저장 유지.
- [ ] Excel percent format ×100 유지.

### 9-3. 메트라이프

- [ ] 대상 시트 `주계약 CSC` 유지.
- [ ] 데이터 시작 11행 유지.
- [ ] 구분은 F열 우선, 없으면 G열 유지.
- [ ] K~N year1~4 유지.
- [ ] coverage 우선순위 변액 > 경영 > 종신 > 연금 > 기타 유지.

### 9-4. 카디프

- [ ] `□ 특약` 이후 제외 유지.
- [ ] raw `% × 12` 저장 유지.
- [ ] `사용안함` sentinel 유지.
- [ ] 일시납 단일 환산율 table 대응 유지.
- [ ] `example.file.open("rb")` 기반 temp PDF 작성 유지.

### 9-5. 처브

- [ ] 특약 섹션 감지 시 해당 페이지부터 중단 유지.
- [ ] 1종/2종 row 복제 유지.
- [ ] PPP → 납기 정규화 유지.
- [ ] FA/P/CP → 구분 정규화 유지.
- [ ] raw `% × 12` 저장 유지.

### 9-6. DB생명

- [ ] 특약/방카교차 시트 제외 유지.
- [ ] 각 시트 첫 번째 테이블만 사용 유지.
- [ ] 특약/의무부가 table 시작 시 중단 유지.
- [ ] 상품명 A1 `□` 제거 유지.
- [ ] F열 헤더가 `계`이면 year4 제외 유지.
- [ ] 구분 carry-down 유지.

### 9-7. 푸본현대

- [ ] `■` 상품 블록 title 사용 유지.
- [ ] 특약/패키지 제외 유지.
- [ ] `주계약/특약 동일`은 포함 유지.
- [ ] 초년도 year1, 차년도 year2~4 동일 저장 유지.
- [ ] pdfplumber → PyMuPDF → pypdf fallback 유지.

### 9-8. 하나생명

- [ ] PDF 첫 페이지만 정규화 유지.
- [ ] table detector 우선, 좌표 fallback 유지.
- [ ] 상품명 + 심사유형 괄호 결합 유지.
- [ ] 구분=상품유형 유지.
- [ ] 납기=납입기간 유지.
- [ ] year4=year3 유지.

### 9-9. 한화

- [ ] product_kind 세 종류 유지.
- [ ] 숨김 시트 제외 유지.
- [ ] 첫 `주계약` table만 사용 유지.
- [ ] 독립특약/종속특약 이후 제외 유지.
- [ ] 일반보장은 `전기납` 포함 가능 유지.
- [ ] CEO정기만 raw 구분 사용 유지.
- [ ] 연금보험에서 `바로` 포함 시트 제외 유지.

### 9-10. 흥국

- [ ] 대상 PDF 두 번째 페이지 only 유지.
- [ ] target keyword 확인 유지.
- [ ] 상품코드/비고 제외 유지.
- [ ] word 좌표 기반 rate header 매칭 유지.
- [ ] 납기 headers `20년↑`, `15년↑`, `10년↑`, `5년↑` 유지.
- [ ] rate를 year1~4 동일 저장 유지.

### 9-11. IM

- [ ] 첫 번째 시트명 `(총괄)환산성적표` 검증 유지.
- [ ] E열 `주계약` 행만 정규화 유지.
- [ ] L열 `미판매` 제외 유지.
- [ ] J열 납기 Excel 표시값 보정 유지.
- [ ] 전략상품 I/Ⅱ 등을 전략상품1~4로 정규화 유지.

### 9-12. KB생명

- [ ] 일반상품/건강보험 분리 유지.
- [ ] 일반상품 D/E가 K보다 우선 유지.
- [ ] D/E 모두 `-`이면 구분 공란 유지.
- [ ] 건강보험 B열 `특약` 등장 시 하단 전체 제외 유지.
- [ ] 건강보험 C열 괄호 밖 상품명, 괄호 안 구분 분리 유지.
- [ ] percent format ×100 유지.

### 9-13. KDB

- [ ] 대상 시트 `GA 주계약` only 유지.
- [ ] 1~3행 제외 유지.
- [ ] C/H 병합셀 전파 유지.
- [ ] plan_type 공란 유지.
- [ ] H + I 괄호 결합 유지.
- [ ] K열 변경후 year1~4 동일 저장 유지.
- [ ] 중복 기준 상품명+구분+납기 유지.

### 9-14. 교보

- [ ] 대상 시트 `주계약(종속특약포함)` only 유지.
- [ ] 5개 병렬 테이블 유지.
- [ ] 판매중지/특약 상품과 하위 공란 행 제외 유지.
- [ ] 단독 괄호 subtype 직전 상품명 합성 유지.
- [ ] percent format ×100 유지.

### 9-15. 라이나

- [ ] Excel/PDF parser 모두 유지.
- [ ] Excel 구분 병합 영역 첫 컬럼 상품명, 마지막 컬럼 납기 유지.
- [ ] 납기 `년납` 포함 행만 정규화 유지.
- [ ] PDF 상품명 continuation 병합 유지.
- [ ] PDF 노이즈/특약/헤더 제외 유지.
- [ ] year1~4 동일 저장 유지.

### 9-16. 미래에셋

- [ ] 대상 시트 `보장성`, `보장성_*`, `저축성` 유지.
- [ ] 병합 셀 전파 유지.
- [ ] 줄바꿈 상품명 붙여 한 줄 정규화 유지.
- [ ] 별도 구분 없는 상품 `사용안함` 유지.
- [ ] 저축성 환산성적→year1~2, 유지성적→year3~4 유지.

### 9-17. 농협생명

- [ ] 대상 시트 `GA` 유지.
- [ ] 월납 block R9~R51 유지.
- [ ] 저축·연금 block R56~R69 유지.
- [ ] 특약/일시납 block 제외 유지.
- [ ] `-` 값은 해당 납기-rate row 제외 유지.
- [ ] percent format ×100 유지.
- [ ] 납기 header row + 다음 rate row 구조 유지.
- [ ] 실손의료비보험 단일 환산율 `전기납` 대응 유지.

### 9-18. 삼성

- [ ] 대상 시트 `보장성`, `건강상해`, `건강상해(`, `연금저축` 유지.
- [ ] 가로 병합은 좌측 셀만 인정 유지.
- [ ] 세로 병합은 행 전체 전파 유지.
- [ ] plan_type 공란은 `사용안함` 유지.
- [ ] 건강상해(...)는 상품명에 `보험` 포함 행만 사용 유지.
- [ ] 판매중지 행과 바로 위 row 제외 유지.

### 9-19. 신한

- [ ] 시트명 `일반상품`, `건강` 포함 분기 유지.
- [ ] 일반상품 C 상품명 carry-down 유지.
- [ ] D/E 구분 결합 유지.
- [ ] D/E 공란이면 동일 상품명 직전 구분 전파 유지.
- [ ] 일반상품 H/I/J year1~3, year4 None 유지.
- [ ] 건강은 A열 `주보험` 행만 유지.
- [ ] 건강 plan_type 공란 유지.

---

## 10. 손해보험 parser별 회귀 방지 체크리스트

### 10-1. AIG

- [ ] PDF parser 유지.
- [ ] `판매 종료` 행 제외 유지.
- [ ] `납입 주기`는 전체 PDF에서 추출한 자동갱신 값 유지.
- [ ] coverage_type `보장` 고정 유지.
- [ ] plan_type 공란 유지.
- [ ] year1만 저장, year2~4 None 유지.
- [ ] dedupe `(product_name, pay_period, rate)` 유지.

### 10-2. DB손보

- [ ] `1. 수정률(GA)` 테이블만 사용 유지.
- [ ] `2. 수금수수료율` 이후 제외 유지.
- [ ] 병합셀 value matrix 전파 유지.
- [ ] raw numeric percent는 ×100 없이 그대로 저장 유지.
- [ ] 실손/연금/저축/태아 coverage_type 규칙 유지.
- [ ] 참좋은훼밀리더블플러스 특수 납기 조합 유지.
- [ ] 최초/갱신 단독실손 분기 유지.

### 10-3. 하나손보

- [ ] PyMuPDF 좌표 기반 parser 유지.
- [ ] 병합 상품명 block y-range 복원 유지.
- [ ] 상품분류 좌/우 컬럼에서 pay_period/plan_type 추출 유지.
- [ ] coverage_type `보장` 고정 유지.
- [ ] raw 수정률 그대로 저장 유지.
- [ ] dedupe `(product, pay, plan, rate)` 유지.

### 10-4. 현대해상

- [ ] 대상 시트 `G A`, `태아보험`, `실손의료비` 유지.
- [ ] percent format이면 ×100 유지.
- [ ] G A 시트 E열 상품명 continuation merge 유지.
- [ ] 태아보험 F열 없으면 G열 fallback 유지.
- [ ] 실손의료비 B/C 가입유형 기반 plan_type 유지.
- [ ] 보장/보장(태아)/단독실손(초회·갱신) 분기 유지.

### 10-5. KB손보

- [ ] `[GA채널_수정률]` 시트 유지.
- [ ] 병합셀 전파 map 유지.
- [ ] raw 수정률은 이미 백분율 값이므로 ×100, /100 금지.
- [ ] 실손 최초/갱신 2행 생성 가능 유지.
- [ ] 납입기간 + 보험기간 조합 유지.
- [ ] 재물 상품군 제외 유지.

### 10-6. 롯데손보

- [ ] 좌/우 병렬 block parser 유지.
- [ ] 우측 `좌동`이면 좌측 사용 유지.
- [ ] 우측 `판매중지`면 pair 전체 제외 유지.
- [ ] 그 외 우측 사용 유지.
- [ ] 병합셀 matrix 전파 유지.
- [ ] raw 수정률 그대로 year1 저장 유지.

### 10-7. 메리츠화재

- [ ] pdfplumber parser 유지.
- [ ] 담보명에 `기본계약` 또는 `반려견` 포함 행만 저장 유지.
- [ ] 주요 컬럼 carry-forward 유지.
- [ ] plan_type 공란이면 `사용안함` 유지.
- [ ] 납기=납입기간+보험기간 조합 유지.
- [ ] coverage_type 분기 유지.

### 10-8. 농협손보

- [ ] 색상 판별 금지 유지.
- [ ] 병합셀 matrix 전개 유지.
- [ ] 헤더 B~F = 납입기간/보험기간/계약구분/모집/수금 유지.
- [ ] 공란 셀은 헤더와 현재행 사이 같은 컬럼 마지막 텍스트 carry-down 유지.
- [ ] ◈ 상품 block + 【...】 plan 수집 유지.

### 10-9. 손해보험 지급률 fire_pay

- [ ] 대상 시트 `① 5천만,3천만↑` 유지.
- [ ] tier `5천만↑`만 정규화 유지.
- [ ] 보험사 canonical map 유지.
- [ ] 지급률 저장은 raw / 0.97 유지.
- [ ] PAY_HEADER_MAP 유지:
  - [ ] 초회 → col_first
  - [ ] 2~6회 → col_yr1
  - [ ] 7~12회 → col_m13
  - [ ] 13회 → col_yr2
  - [ ] 14회 → col_yr3
  - [ ] 15회 → col_m36
- [ ] PRODUCT_GROUPS 화이트리스트 유지.

---

## 11. 폴더 구조 변경 시 단계별 절차

### 11-1. Step A: 공통 helper 추가

- [ ] `commission/services/rate_example_normalizers/_common/` 폴더 생성.
- [ ] `__init__.py` 추가.
- [ ] text/decimal/excel/rows helper를 최소 단위로 추가.
- [ ] 기존 parser import는 아직 변경하지 않는다.
- [ ] `python manage.py check` 실행.

### 11-2. Step B: 저위험 parser 1개부터 적용

저위험 후보:

- [ ] `life_met.py`
- [ ] `life_dongyang.py`
- [ ] `life_abl.py`

절차:

- [ ] helper import 적용.
- [ ] 동일 입력 파일 기준 row count 비교.
- [ ] key fields 비교:
  - [ ] insurer
  - [ ] coverage_type
  - [ ] product_name
  - [ ] plan_type
  - [ ] pay_period
  - [ ] year1~year4
- [ ] log output 비교.
- [ ] 정상 확인 후 다음 parser로 확장.

### 11-3. Step C: 고위험 parser는 주석 보완만 먼저

고위험 후보:

- [ ] `life_chubb.py`
- [ ] `life_cardif.py`
- [ ] `life_hana.py`
- [ ] `life_heungkuk.py`
- [ ] `life_nh.py`
- [ ] `life_hanhwa.py`
- [ ] `fire_hana.py`
- [ ] `fire_nh.py`
- [ ] `fire_hyundai.py`

작업:

- [ ] 주석/타입 힌트 보완.
- [ ] logger 메시지 표준화.
- [ ] 중복 제거는 별도 패치로 분리.

### 11-4. Step D: 파일 이동은 마지막

- [ ] 기존 파일 경로 shim 추가.
- [ ] 신규 파일에서 실제 구현.
- [ ] dispatcher import 경로 변경.
- [ ] grep으로 기존 경로 import 확인.
- [ ] shim 제거 금지.

---

## 12. 패치 응답 작성 기준

실제 패치 요청 시 반드시 아래 형식을 따른다.

### 12-1. 변경 목적

```text
변경 목적:
- 기능 변화 없이 commission 백엔드 중복 helper를 정리합니다.
- 기존 URL/API/저장 정책은 유지합니다.
```

### 12-2. 수정 파일 목록 + 영향도

```text
수정 파일:
- commission/views/api_deposit_impl.py — JSON helper 중복 제거, 영향도 낮음
- commission/services/rate_example_normalizers/_common/text.py — 신규 공통 helper, 영향도 낮음
- commission/services/rate_example_normalizers/life_met.py — helper import 교체, 영향도 중간
```

### 12-3. diff 패치

- [ ] 기존 파일 수정은 반드시 diff 형식.
- [ ] 신규 파일은 최종완성본 전체 출력.
- [ ] 주요 기능별 주석 포함.
- [ ] 기존 코드를 생략하지 않는다.
- [ ] 파일 이동이 있으면 old/new 경로를 명확히 적는다.

### 12-4. 회귀 위험

반드시 항목별로 “영향 있음/없음” 표시.

| 점검 항목 | 영향 |
|---|---|
| 권한 스코프 | 없음 |
| URL reverse/name | 없음 |
| 템플릿 dataset/DOM id | 없음 |
| 첨부 다운로드 정책 | 없음 |
| 업로드 registry | 없음 |
| RateExample 저장 정책 | 있음/없음 |
| replace/append semantics | 없음 |
| audit log | 없음 |
| 운영 정적파일/Whitenoise | 없음 |

### 12-5. 검증 체크리스트

- [ ] `python manage.py check`
- [ ] `python manage.py test commission`
- [ ] `bash scripts/harness/security_lint.sh`
- [ ] `bash scripts/harness/quality_lint.sh`
- [ ] `bash scripts/harness/run_all.sh`
- [ ] 채권 업로드 1건
- [ ] 결재 업로드 1건
- [ ] 지점효율 업로드 1건
- [ ] 환수관리 업로드 1건
- [ ] 생보 환산율 업로드 1건
- [ ] 손보 수정률 업로드 1건
- [ ] 지급률 업로드 1건
- [ ] 환산율/수정률 조회 모달 확인
- [ ] 수수료 계산 API 확인
- [ ] 실패 엑셀 token 다운로드 확인
- [ ] superuser/head/leader/basic 권한별 조회 범위 확인

---

## 13. 테스트/검증 시나리오 상세

### 13-1. 공통 명령

PowerShell:

```powershell
python manage.py check
python manage.py test commission
bash scripts/harness/security_lint.sh
bash scripts/harness/quality_lint.sh
bash scripts/harness/run_all.sh
```

Windows에서 bash가 없을 경우 Git Bash 또는 WSL에서 실행한다.

### 13-2. Django shell row 비교 예시

```python
from commission.models import RateExampleConversionRow

qs = RateExampleConversionRow.objects.filter(
    insurer_type="life",
    category="conv",
    insurer="DB",
)

print(qs.count())
print(qs.values(
    "coverage_type",
    "product_name",
    "plan_type",
    "pay_period",
    "year1",
    "year2",
    "year3",
    "year4",
).order_by("product_name", "plan_type", "pay_period")[:10])
```

### 13-3. 업로드 registry 확인

```python
from commission.upload_handlers.registry import supported_upload_types

print(tuple(supported_upload_types()))
```

확인해야 할 타입:

- [ ] 최종지급액
- [ ] 환수지급예상
- [ ] 보증증액
- [ ] 채권지표
- [ ] 응당생보
- [ ] 응당손보
- [ ] 보증보험
- [ ] 기타채권
- [ ] 통산손보
- [ ] 통산생보
- [ ] 환수관리

### 13-4. 지급률 `/0.97` 검증

- [ ] 손해보험 지급률 raw 값이 323.33이면 저장값은 `333.3298...` 계열인지 확인.
- [ ] 생명보험 지급률도 기존 정책대로 raw/0.97이 적용되는지 확인.
- [ ] 손해보험 수정률 parser에는 `/0.97`이 적용되지 않는지 확인.

### 13-5. 수정률 raw 저장 검증

- [ ] KB손보 수정률 raw 160은 DB에 160으로 저장되어야 한다.
- [ ] 16000으로 저장되면 ×100 중복 보정 회귀다.
- [ ] 1.6으로 저장되면 /100 또는 percent 오판 회귀다.

### 13-6. PDF parser 검증

- [ ] PDF 라이브러리 미설치 시 사용자 메시지가 명확한지 확인.
- [ ] pypdf/PyPDF2/pdfplumber/PyMuPDF fallback 순서가 보험사별 기존 정책과 동일한지 확인.
- [ ] PDF 변환 결과가 빈 rows일 때 정상적으로 “조회된 데이터 없음” 흐름으로 이어지는지 확인.
- [ ] 예외 발생 시 transaction rollback이 되는지 확인.

### 13-7. 권한 검증

- [ ] superuser는 업로드 가능.
- [ ] head/leader/basic은 업로드 불가.
- [ ] collect 조회는 superuser/head/leader 가능.
- [ ] collect service scope가 head/leader별로 유지되는지 확인.
- [ ] deposit API 대상자 조회 권한이 기존과 동일한지 확인.
- [ ] 실패 엑셀 token은 owner_id가 있으면 본인만 다운로드 가능한지 확인.

---

## 14. 운영 배포 주의사항

### 14-1. migration

- [ ] 기능 변화 0 리팩토링에서는 migration이 없어야 한다.
- [ ] `python manage.py makemigrations --check --dry-run` 결과 변경 없음 확인.
- [ ] 모델 필드/제약 변경이 발생했다면 이번 범위를 벗어난 것이다.

### 14-2. 정적파일

- [ ] 백엔드만 수정하면 collectstatic 영향 없음.
- [ ] 프론트 JS/CSS를 함께 수정하면 운영 배포 전 `collectstatic --noinput` 필요.
- [ ] Manifest/Whitenoise 설정은 건드리지 않는다.

### 14-3. Celery

- [ ] commission 리팩토링이 Celery task name에 영향을 주면 안 된다.
- [ ] `bash scripts/harness/celery_check.sh` 통과 확인.
- [ ] 업로드 처리 task가 있는 경우 name 변경 금지.

### 14-4. 로그

- [ ] 예외는 `logger.exception`으로 traceback을 남긴다.
- [ ] 사용자 응답에는 내부 traceback/path를 노출하지 않는다.
- [ ] audit log 실패가 사용자 기능을 막지 않도록 방어한다.
- [ ] 민감정보, 보험료 원문, 파일 경로를 audit meta에 과도하게 남기지 않는다.

---

## 15. 작업 분할 권장안

### Phase 1. 안전한 views 중복 제거

- [ ] `api_deposit_impl.py` JSON helper 중복 제거.
- [ ] 다운로드 응답 `_excel_export.py` 사용 여부 재확인.
- [ ] `_files.py`, `_ym.py` 사용 누락 지점 정리.
- [ ] 주석 보완.

예상 위험: 낮음.

### Phase 2. upload_utils 정리

- [ ] empty-like 값 상수화.
- [ ] convert/detect/readers docstring 보완.
- [ ] legacy shim 주석 보완.
- [ ] import surface `__all__` 정리.

예상 위험: 낮음~중간.

### Phase 3. upload_handlers 정리

- [ ] approval/efficiency safe cell/text helper 정리.
- [ ] return dict 표준화.
- [ ] registry 주석 보완.
- [ ] upload log SSOT 주석 보강.

예상 위험: 중간.

### Phase 4. RateExample 저위험 parser 공통화

- [ ] `life_met.py`
- [ ] `life_dongyang.py`
- [ ] `life_abl.py`
- [ ] `life_db.py`

예상 위험: 중간.

### Phase 5. RateExample 고위험 parser는 별도 패치

- [ ] PDF parser
- [ ] 좌표 기반 parser
- [ ] product_kind 분기 parser
- [ ] block/pair parser
- [ ] 손해보험 수정률 특수 parser

예상 위험: 높음.

### Phase 6. 폴더 구조 변경

- [ ] shim 준비.
- [ ] dispatcher 경로 변경.
- [ ] 한 그룹씩 이동.
- [ ] 전체 upload/조회/계산 검증.

예상 위험: 높음. 반드시 별도 브랜치 권장.

---

## 16. 최종 DoD 체크리스트

### 코드 구조

- [ ] public import surface 유지.
- [ ] legacy shim 유지.
- [ ] SSOT helper 중복 제거.
- [ ] parser별 저장 정책 보존.
- [ ] 폴더 이동 시 shim 제공.
- [ ] 주석이 실제 동작과 일치.

### 보안

- [ ] 파일 직접 URL 노출 없음.
- [ ] 업로드/다운로드 권한 유지.
- [ ] CSRF 우회 신규 추가 없음.
- [ ] token 다운로드 owner 검증 유지.
- [ ] audit 로그 위치 제거 없음.
- [ ] 내부 path/traceback 사용자 노출 없음.

### 성능

- [ ] bulk_create/update_conflicts 유지.
- [ ] select_related/in_bulk/bulk map 유지.
- [ ] row-by-row save로 후퇴 없음.
- [ ] PDF/Excel parsing 루프에서 불필요 DB query 추가 없음.
- [ ] cache token 사용 정책 유지.

### 회귀

- [ ] `python manage.py check` 통과.
- [ ] `python manage.py test commission` 통과 또는 실패 사유 기록.
- [ ] 보안/품질 harness 결과 확인.
- [ ] 주요 업로드 유형 smoke test 완료.
- [ ] RateExample 조회 모달 정상.
- [ ] 수수료 계산 API 정상.
- [ ] 권한별 접근 범위 정상.

---

## 17. 패치 전 마지막 질문 목록

실제 리팩토링 패치 전에 아래 질문에 답한다.

- [ ] 이번 패치가 views만 대상으로 하는가?
- [ ] parser 공통화까지 포함하는가?
- [ ] 폴더 구조 변경을 포함하는가?
- [ ] 파일명 변경을 포함하는가?
- [ ] legacy shim을 몇 개 추가해야 하는가?
- [ ] 샘플 raw 파일 기준 row count를 비교할 수 있는가?
- [ ] 배포 직후 rollback 방법이 명확한가?
- [ ] migration이 발생하지 않는가?
- [ ] 프론트 수정이 필요한가?
- [ ] 운영 업로드/조회 권한에 영향이 없는가?

---

## 18. 요약

이번 commission 백엔드 리팩토링의 핵심은 “더 깔끔한 구조”가 아니라 **기존 보험사별 파싱 정책과 운영 계약을 절대 깨지 않는 정리**다.

따라서 작업 순서는 다음이 안전하다.

1. views 계층의 명백한 중복 제거
2. upload_utils 주석/상수/헬퍼 정비
3. upload_handlers의 안전한 내부 정리
4. RateExample 저위험 parser부터 공통 helper 적용
5. PDF/좌표/특수 parser는 별도 패치
6. 폴더 구조 변경은 shim과 함께 마지막에 수행

리팩토링 성공 기준은 코드 줄 수 감소가 아니라, 다음 세 가지다.

- [ ] 기존 업로드/조회/계산 결과가 동일하다.
- [ ] 다음 개발자가 보험사별 정책을 더 쉽게 찾을 수 있다.
- [ ] SSOT 위치가 명확해져 중복 수정 위험이 줄어든다.
---

# 19. 현재까지 완료된 리팩토링 반영 사항 (2026-05-21 기준)

## 19-1. 완료 요약

현재까지 완료된 저위험 리팩토링 구간은 아래와 같다.

```text
P2-1 upload_utils 정리        ✅ 완료
P2-2 upload_handlers 정리     ✅ 완료
P5 테스트 보강                ✅ 완료
P3 life_kb.py 저위험 정리     ✅ 완료
P1-4 Deposit 후속 정리        ✅ 완료
```

최종 검증 결과:

```text
python manage.py check                         ✅ 통과
python manage.py test commission               ✅ 32 tests OK
python manage.py makemigrations --check --dry-run ✅ No changes detected
```

---

## 19-2. P2-1 upload_utils 정리 완료

### 대상 파일

```text
commission/upload_utils/_convert.py
commission/upload_utils/_detect.py
commission/upload_utils/_readers.py
commission/upload_utils/_db.py
commission/upload_utils/__init__.py
commission/upload_utils/upload_utils.py
```

### 완료 항목

- [x] empty-like 값 상수화
- [x] `EMPTY_LIKE_VALUES = frozenset({"", "nan", "none", "-"})` 기준 정리
- [x] `_convert.py` module docstring 보강
- [x] Decimal 변환 함수 역할 명확화
  - [x] `_to_decimal()`은 일반 금액/실적 필드용
  - [x] `_safe_decimal_q2()`는 DecimalField(decimal_places=2) 저장용
- [x] `_detect.py` alias/ban group 주석 정리
- [x] `_readers.py` reader fallback 주석 보강
- [x] `_db.py` deprecated wrapper 주석 강화
- [x] `__all__` export surface 점검 및 설명 강화
- [x] legacy shim `upload_utils.py` 유지

### 보존된 정책

- [x] `_norm_emp_id("1234567.0") -> "1234567"` 유지
- [x] `_extract_emp7_from_a()`의 `s[-8:-1]` 정책 유지
- [x] pandas `isna` 방어 유지
- [x] 기존 import surface 유지
- [x] DB migration 없음

---

## 19-3. P2-2 upload_handlers 정리 완료

### 대상 파일

```text
commission/upload_handlers/approval.py
commission/upload_handlers/efficiency.py
commission/upload_handlers/collect.py
commission/upload_handlers/registry.py
commission/upload_handlers/deposit.py
commission/upload_handlers/__init__.py
```

### 완료 항목

- [x] `approval.py` `_safe_cell()` 공통 helper 사용 의도 명시
- [x] `efficiency.py` `_safe_text()` 공통 helper 사용 의도 명시
- [x] `_find_header_row_and_col_indices()` 타입 힌트/docstring 보강
- [x] handler return dict 구조 주석 정리
- [x] `registry.py` `UploadSpec` 설명 강화
- [x] `UploadSpec` return dict 계약 명시
- [x] `deposit.py` `_update_upload_log` SSOT 주석 강화
- [x] `upload_handlers/__init__.py` public API/legacy alias 주석 강화
- [x] `approval.py` 타입 힌트 import 누락 보정
  - [x] `List`
  - [x] `Sequence`

### 보존된 정책

- [x] approval raw matrix 위치 기반 파싱 유지
  - [x] B=이름
  - [x] C=사번
  - [x] N=실지급액
  - [x] O=결재값
- [x] approval 조건 유지
  - [x] `actual_pay > 0`
  - [x] `approval_flag == "N"`
  - [x] 유자격 `regist in {"손생등록", "생보등록", "손보등록"}`
- [x] efficiency 사번 E열 고정 유지
- [x] efficiency `구분 == "지급"` 금액만 합산 유지
- [x] `bulk_create(update_conflicts=True)` 유지
- [x] backward-compatible alias 유지
- [x] registry upload_type 문자열 변경 없음

---

## 19-4. P5 테스트 보강 완료

### 대상 파일

```text
commission/tests.py
```

### 완료 항목

- [x] upload_utils empty-like 테스트 추가
- [x] `_norm_emp_id()` 회귀 테스트 추가
- [x] `_extract_emp7_from_a()` 회귀 테스트 추가
- [x] fail token 생성/cache 저장 테스트 추가
- [x] Excel response smoke 테스트 추가
- [x] deposit service aggregate 테스트 추가
- [x] fail download permission helper 테스트 추가
- [x] Deposit serializer 테스트 추가

### 현재 테스트 커버리지 핵심

```text
RateExample decimal helper
RateExample merged Excel helper
upload_handlers._common helper
upload_utils convert helper
fail token / Excel response helper
Deposit service aggregate
Deposit serializers
fail download permission
```

### 최종 테스트 수

```text
32 tests OK
```

---

## 19-5. P3 life_kb.py 저위험 parser 정리 완료

### 대상 파일

```text
commission/services/rate_example_normalizers/life_kb.py
```

### 완료 항목

- [x] local Decimal parser 일부 공통 helper로 치환
- [x] `_clean_text()`에서 공통 `clean_text()` 사용
- [x] `_to_decimal()`에서 공통 `decimal_from_text()` 사용
- [x] `_rate_cell_to_decimal()`에서 공통 `decimal_percent_cell()` 사용
- [x] 불필요한 `InvalidOperation` import 제거
- [x] `Decimal` 타입 힌트 import 유지
- [x] KB parser 함수 import 확인 완료

### 보존된 정책

- [x] `build_life_kb_general_conversion_rows()` 함수명 유지
- [x] `build_life_kb_health_conversion_rows()` 함수명 유지
- [x] 일반상품/건강보험 분기 유지
- [x] 건강보험 B열 `특약` 등장 시 하단 전체 제외 유지
- [x] 건강보험 `coverage_type = "기타(보장성)"` 유지
- [x] Excel percent format `×100` 보정 유지
- [x] 문자열 `"80%"`는 `80`으로 저장 유지
- [x] row append 구조 변경 없음
- [x] DB 모델/마이그레이션 영향 없음

---

## 19-6. P1-4 Deposit 후속 정리 완료

### 대상 파일

```text
commission/views/api_deposit_impl.py
commission/services/deposit.py
commission/services/deposit_serializers.py
commission/tests.py
```

### 신규 파일

```text
commission/services/deposit_serializers.py
```

### 완료 항목

- [x] Deposit serializer helper 분리
- [x] `user_to_payload()` 분리
- [x] `summary_to_payload()` 분리
- [x] `surety_to_payload()` 분리
- [x] `other_to_payload()` 분리
- [x] `json_rows()` 분리
- [x] `json_user_detail()` 분리
- [x] `apply_deposit_summary_totals()` 분리
- [x] `DepositTotalPayload` dataclass 도입
- [x] `api_deposit_impl.py`는 request parsing, permission check, service 호출 중심으로 축소
- [x] `commission/services/deposit.py` docstring 보강
- [x] Deposit serializer regression test 추가

### 보존된 응답 계약

- [x] `api_user_detail` 응답에서 `data` + `user` 키 모두 유지
- [x] `api_deposit_summary` 응답에서 `rows` 유지
- [x] `surety_total_all`, `other_total_all` 유지
- [x] 화면 표시용 `surety_total`, `other_total` 필터 합계 정책 유지
- [x] `debt_keep_total` 유지
- [x] `deposit_home.html`의 `data-bind` 키 변경 없음
- [x] `deposit_home.js` alias 계약 변경 없음

---

## 19-7. 현재 완료 기준 DoD

### 코드 구조

- [x] public import surface 유지
- [x] legacy shim 유지
- [x] SSOT helper 중복 제거 일부 완료
- [x] upload_utils 역할 명확화
- [x] upload_handlers return 계약 명확화
- [x] Deposit serializer/service/view 책임 분리 강화
- [x] KB parser 저위험 공통 helper 적용 완료

### 보안

- [x] 파일 직접 URL 노출 없음
- [x] 업로드/다운로드 권한 완화 없음
- [x] CSRF 우회 신규 추가 없음
- [x] token 다운로드 owner 검증 유지
- [x] 내부 path/traceback 사용자 노출 없음

### 성능

- [x] bulk_create/update_conflicts 유지
- [x] QuerySet 유지 후 serializer 단계에서 list 변환
- [x] row-by-row save 후퇴 없음
- [x] 테스트 DB 기준 회귀 없음

### 회귀

- [x] `python manage.py check` 통과
- [x] `python manage.py test commission` 32개 통과
- [x] `python manage.py makemigrations --check --dry-run` 변경 없음
- [x] KB parser import 정상
- [x] upload registry 영향 없음
- [x] URL/DOM/dataset 변경 없음

---

## 19-8. 남은 작업

저위험 구간은 완료되었고, 다음 단계부터는 중간~고위험 구간이다.

### 다음 후보 1: P6 collect / collect_notice 정리

```text
commission/services/collect.py
commission/views/collect_notice_export.py
commission/services/collect_notice_excel.py
```

남은 항목:

- [ ] collect serializer helper 분리
- [ ] feedback payload builder 분리
- [ ] collect_notice workbook style helper 분리
- [ ] PDF/LibreOffice runtime helper 정리
- [ ] collect 권한 스코프 회귀 테스트 추가

위험도: 중간.

### 다음 후보 2: P3 고위험 parser 정리

```text
commission/services/rate_example_normalizers/life_chubb.py
commission/services/rate_example_normalizers/life_cardif.py
commission/services/rate_example_normalizers/life_hana.py
commission/services/rate_example_normalizers/life_heungkuk.py
commission/services/rate_example_normalizers/life_nh.py
commission/services/rate_example_normalizers/life_hanhwa.py
commission/services/rate_example_normalizers/fire_hana.py
commission/services/rate_example_normalizers/fire_nh.py
commission/services/rate_example_normalizers/fire_hyundai.py
commission/services/rate_example_normalizers/fire_lotte.py
commission/services/rate_example_normalizers/fire_pay.py
commission/services/rate_example_normalizers/fire_db.py
commission/services/rate_example_normalizers/fire_kb.py
```

남은 항목:

- [ ] PDF parser 주석/타입 보강
- [ ] 좌표 parser 공통화 여부 검토
- [ ] block/pair parser는 보험사별 단위로 분리 패치
- [ ] `%`, `×100`, `×12`, `/0.97` 저장 단위 혼용 방지
- [ ] row count 비교 필수

위험도: 높음.

### 다음 후보 3: P4 폴더 구조 이동

```text
commission/services/rate_example_normalizers/life/
commission/services/rate_example_normalizers/fire/
```

남은 항목:

- [ ] 신규 폴더 생성
- [ ] 기존 파일 shim 유지
- [ ] dispatcher import 변경
- [ ] grep 기반 import 검증
- [ ] 전체 업로드/조회/계산 smoke test

위험도: 높음. 별도 브랜치 권장.

---

## 20. 현재 권장 진행 순서

```text
완료:
P2-1 upload_utils
→ P2-2 upload_handlers
→ P5 테스트 보강
→ life_kb.py 저위험 P3
→ P1-4 Deposit 후속 구조 정리

남은 단계:
P6 collect/notice 정리
→ P3 고위험 parser
→ P4 폴더 구조 이동
```

---

## 21. 최종 요약

현재까지의 리팩토링은 기능 변화 없이 아래 효과를 달성했다.

- 업로드 유틸의 공란/Decimal/reader 정책이 명확해졌다.
- 업로드 핸들러의 결과 dict 및 registry 계약이 명확해졌다.
- 테스트가 16개에서 32개로 확대되어 회귀 방지력이 강화됐다.
- KB 생명보험 parser의 저위험 중복이 공통 helper로 정리됐다.
- Deposit API의 serializer 책임이 분리되어 view/service boundary가 개선됐다.

현재 상태는 “저위험 패치 완료”로 판단 가능하며, 이후 작업은 collect/notice 또는 고위험 parser 단위로 별도 검증을 강화해 진행한다.
