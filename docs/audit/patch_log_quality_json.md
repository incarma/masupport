# JSON 헬퍼 중복 제거 패치 로그 — STEP 4
> 날짜: 2026-05-06

## 수정 사항
| 파일 | 변경 내용 | 시그니처 호환 여부 |
|------|---------|-----------------|
| `commission/views/api_deposit_impl.py` | `_json_err` 함수 정의 삭제 (구 63-64줄) | ✅ 완전 호환 (케이스 1) |
| `commission/views/api_deposit_impl.py` | `from commission.views.utils_json import _json_error as _json_err` import 추가 (14줄) | — |

### 시그니처 비교
| 항목 | SSOT `_json_error` | 삭제된 `_json_err` |
|---|---|---|
| `message` | `str` | `str` |
| `status` | `int = 400` (위치/키워드 허용) | `int = 400` (keyword-only `*`) |
| 추가 필드 | `**extra` 지원 | 없음 |
| 반환 구조 | `{"ok": False, "message": ..., **extra}` | `{"ok": False, "message": ...}` |

모든 기존 호출부는 `_json_err("msg")` 또는 `_json_err("msg", status=NNN)` 패턴이므로 alias 방식으로 직접 교체 가능 (케이스 1).

### 수정 전 호출 현황 (6곳)
| 줄 (수정 전) | 호출 패턴 |
|---|---|
| 142 | `_json_err("권한이 없습니다.", status=403)` |
| 154 | `_json_err("user 파라미터가 필요합니다.")` |
| 158 | `_json_err("대상자를 찾지 못했습니다.", status=404)` |
| 338 | `_json_err("user 파라미터가 필요합니다.")` |
| 378 | `_json_err("user 파라미터가 필요합니다.")` |
| 396 | `_json_err("user 파라미터가 필요합니다.")` |

## python manage.py check 결과
```
System check identified no issues (0 silenced)
```

## quality_lint.sh 결과
- **Q-03 (JSON 헬퍼 중복)**: 항목 미출력 → 위반 해소 확인
- Q-01, Q-02a/b, URL-01: 기존 위반 (이번 STEP 4 패치 범위 외)

## 회귀 점검 결과
- [x] JSON 응답 `{"ok": false, "message": ...}` 구조 동일 — `_json_error` SSOT도 동일 구조 반환
- [x] `_json_err` 6개 호출부 모두 정상 — alias이므로 호출부 코드 변경 없음
- [x] commission 앱 다른 뷰 import 충돌 없음 — `utils_json._json_error`는 기존에도 `__all__` 공개 심볼
- [x] 권한 스코프 변경 없음
- [x] URL reverse / 네임스페이스 변경 없음
- [x] 템플릿 dataset / DOM id 변경 없음
- [x] 첨부 다운로드 정책 영향 없음
- [x] CSS 스코프 영향 없음
- [x] 운영 환경 영향 없음
- [x] JSON 응답 형식 앱 규약 준수
