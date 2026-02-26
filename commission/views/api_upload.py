# django_ma/commission/views/api_upload.py
from __future__ import annotations

"""
Deposit(채권) Excel Upload API (superuser only)

리팩토링 포인트(기능 변화 없음):
- 임시 업로드 파일 저장/삭제 로직을 views/_files.py로 SSOT화
- 결과 건수 산정/실패목록 토큰 생성 로직은 그대로 유지
"""

from django.db import transaction
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from accounts.decorators import grade_required
from commission.upload_handlers import _update_upload_log
from commission.upload_handlers.registry import get_upload_spec, supported_upload_types
from commission.upload_utils import _read_excel_safely

from ._files import save_temp_upload, safe_delete
from .constants import SUPPORTED_UPLOAD_TYPES
from .utils_fail_excel import store_fail_rows_as_excel
from .utils_json import _json_error, _json_ok


def _get_uploaded_n(result: dict) -> int:
    """
    업로드 결과 dict의 키가 handler별로 달라도 안전하게 업로드 건수 산정.
    - deposit 계열: {"updated": n, ...}
    - approval/efficiency 계열: {"inserted_or_updated": n, ...}
    """
    return int(result.get("updated") or result.get("inserted_or_updated") or 0)


def _build_fail_excel_token(*, part: str, upload_type: str, result: dict) -> tuple[str, list]:
    """
    handler 결과에 missing_sample이 있으면 fail excel token을 생성한다.
    - missing_sample: ["1234567", "2345678", ...] 형태(상위 일부 샘플)
    """
    missing_sample = result.get("missing_sample") or []
    if not missing_sample:
        return "", []

    rows = [{"user_id": uid, "reason": "사용자 미존재 또는 스코프 제외"} for uid in missing_sample]
    token = store_fail_rows_as_excel(
        rows=rows,
        filename=f"upload_fail_{part}_{upload_type}.xlsx",
    )
    return token, missing_sample


@csrf_exempt
@require_POST
@grade_required("superuser")
def upload_excel(request):
    """
    채권(Deposit) 업로드 API (superuser 전용)

    SSOT(commission.upload_handlers.registry)를 기반으로 업로드 타입을 결정한다.
    - mode=="df"  : 엑셀 -> DataFrame -> handler(df)
    - mode=="file": 파일 경로/원본명 -> handler(file_path, original_name)
    """
    part = (request.POST.get("part") or "").strip()
    upload_type = (request.POST.get("upload_type") or "").strip()
    excel_file = request.FILES.get("excel_file")

    if not part:
        return _json_error("부서를 선택해주세요.", status=400)

    # ✅ constants.SUPPORTED_UPLOAD_TYPES는 registry 기반 자동 생성(SSOT)
    if upload_type not in SUPPORTED_UPLOAD_TYPES:
        return _json_error(
            f"현재는 {sorted(SUPPORTED_UPLOAD_TYPES)} 업로드만 지원됩니다.",
            status=400,
        )

    if not excel_file:
        return _json_error("엑셀 파일이 전달되지 않았습니다.", status=400)

    # ------------------------------------------------------------------
    # SSOT registry에서 spec 조회 (없으면 500이 아니라 400이 맞음)
    # ------------------------------------------------------------------
    try:
        spec = get_upload_spec(upload_type)
    except KeyError:
        return _json_error(
            f"지원하지 않는 업로드 타입입니다: {upload_type}",
            status=400,
            supported=sorted(supported_upload_types()),
        )

    # ------------------------------------------------------------------
    # 1) 임시 저장 → 2) 처리 → 3) finally에서 삭제
    # ------------------------------------------------------------------
    temp = save_temp_upload(excel_file)
    df = None

    try:
        with transaction.atomic():
            if spec.mode == "df":
                df = _read_excel_safely(temp.file_path, original_name=temp.original_name)
                result = spec.fn(df)
            elif spec.mode == "file":
                result = spec.fn(temp.file_path, temp.original_name)
            else:
                return _json_error(f"핸들러 mode가 올바르지 않습니다: {spec.mode}", status=500)

            uploaded_n = _get_uploaded_n(result)

            # 업로드 로그 갱신 (SSOT)
            uploaded_date = _update_upload_log(
                part=part,
                upload_type=upload_type,
                excel_file_name=temp.original_name,
                count=uploaded_n,
            )

        # 실패 목록 엑셀(token) 생성 (missing_sample 기반)
        fail_token, missing_sample = _build_fail_excel_token(
            part=part,
            upload_type=upload_type,
            result=result,
        )

        return _json_ok(
            spec.msg_tpl.format(n=uploaded_n),
            uploaded=uploaded_n,
            missing_users=int(result.get("missing_users") or 0),
            existing_users=int(result.get("existing_users") or 0),
            missing_sample=missing_sample,
            matched_columns=result.get("matched_columns") or {},
            part=part,
            upload_type=upload_type,
            uploaded_date=uploaded_date,
            fail_token=fail_token,
            fail_download_url=(f"/commission/download/upload-fail/?token={fail_token}" if fail_token else ""),
        )

    except ValueError as ve:
        # 컬럼 매칭 실패 등 사용자 입력 오류
        detected_columns = []
        if (spec.mode == "df") and (df is not None):
            try:
                detected_columns = [str(c) for c in df.columns]
            except Exception:
                detected_columns = []
        return _json_error(
            str(ve),
            status=400,
            detected_columns=detected_columns,
        )

    except Exception as e:
        # 엑셀 형식 오류 힌트(기존 유지)
        msg = str(e)
        if ("Expected BOF record" in msg) or ("Unsupported format" in msg) or ("XLRDError" in msg):
            return _json_error(
                "업로드 실패: 엑셀 파일 형식이 올바르지 않습니다. "
                "엑셀에서 '다른 이름으로 저장' → .xlsx로 저장 후 업로드해주세요.",
                status=400,
            )
        return _json_error(f"⚠️ 업로드 실패: {msg}", status=500)

    finally:
        safe_delete(temp)