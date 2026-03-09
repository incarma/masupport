# django_ma/dash/viewmods/api_upload.py
from __future__ import annotations

import logging
import re
from datetime import datetime

import pandas as pd
from django.db import transaction
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.http import require_POST

from accounts.decorators import grade_required
from accounts.models import CustomUser
from dash.models import SalesRecord

from .constants import REQUIRED_COLS, AUTO_REQUIRED_COLS
from .utils import (
    json_err,
    normalize_columns,
    is_auto_excel,
    to_date,
    to_policy_no,
    to_str_emp_id,
    to_int_money,
    normalize_part_snapshot,
    life_nl_from_insurer,
    parse_ins_period,
)

logger = logging.getLogger(__name__)


@grade_required("superuser")
@require_POST
def upload_sales_excel(request):
    f = request.FILES.get("excel_file")
    if not f:
        return json_err("엑셀 파일(excel_file)이 없습니다.", 400)

    try:
        df = pd.read_excel(f)
        df = normalize_columns(df)
    except Exception as e:
        logger.exception("dash upload read_excel failed")
        return json_err(f"엑셀 읽기 실패: {e}", 400)

    is_auto = is_auto_excel(df)
    required = AUTO_REQUIRED_COLS if is_auto else REQUIRED_COLS

    missing = [c for c in required if c not in df.columns]
    if missing:
        tag = "[자동차]" if is_auto else "[일반]"
        return json_err(f"{tag} 필수 컬럼이 없습니다: {missing}", 400)

    df = df[~df["증권번호"].isna()].copy()

    matched_users = missing_users = upserted_rows = skipped_rows = 0
    first_row_error = None
    touched_yms: set[str] = set()

    def _valid_ym(s: str) -> bool:
        if not s:
            return False
        if not re.fullmatch(r"\d{4}-\d{2}", s):
            return False
        try:
            y, m = map(int, s.split("-"))
            if not (1 <= m <= 12):
                return False
            now = timezone.now().date()
            min_y = now.year - 3
            max_y = now.year + 1
            if not (min_y <= y <= max_y):
                return False
            return True
        except Exception:
            return False

    def _pick_yms_to_process(yms: set[str]) -> list[str]:
        cleaned = [x for x in yms if _valid_ym(x)]
        cleaned.sort(reverse=True)
        return cleaned[:3]

    try:
        with transaction.atomic():
            for idx, r in df.iterrows():
                try:
                    policy_no = to_policy_no(r.get("증권번호"))
                    insurer = (str(r.get("보험사")).strip() if not pd.isna(r.get("보험사")) else "")

                    if not policy_no or not insurer:
                        skipped_rows += 1
                        continue

                    rd = to_date(r.get("영수일자"))
                    ym = rd.strftime("%Y-%m") if rd else datetime.now().strftime("%Y-%m")
                    touched_yms.add(ym)

                    if is_auto:
                        emp_id = to_str_emp_id(r.get("담당자코드"))
                        name = (str(r.get("담당자명")).strip() if not pd.isna(r.get("담당자명")) else None)
                        raw_part = (str(r.get("소속")).strip() if not pd.isna(r.get("소속")) else None)
                        part = normalize_part_snapshot(raw_part)
                        branch = (str(r.get("파트너")).strip() if not pd.isna(r.get("파트너")) else None)

                        if not emp_id:
                            skipped_rows += 1
                            continue

                        user = CustomUser.objects.filter(id=emp_id).first()
                        matched_users += 1 if user else 0
                        missing_users += 0 if user else 1

                        ins_start, ins_end = parse_ins_period(r.get("보험기간"))

                        liability = to_int_money(r.get("책임"))
                        optional = to_int_money(r.get("임의"))
                        total = to_int_money(r.get("합계"))
                        status = (str(r.get("상태")).strip() if not pd.isna(r.get("상태")) else None)
                        vehicle_no = (str(r.get("차량번호")).strip() if not pd.isna(r.get("차량번호")) else None)

                        SalesRecord.objects.update_or_create(
                            policy_no=policy_no,
                            defaults={
                                "user": user,
                                "part_snapshot": part,
                                "branch_snapshot": branch,
                                "name_snapshot": name,
                                "emp_id_snapshot": emp_id,

                                "insurer": insurer,
                                "contractor": None,
                                "insured": (str(r.get("피보험자명")).strip() if not pd.isna(r.get("피보험자명")) else None),

                                "vehicle_no": vehicle_no,
                                "ins_start": ins_start,
                                "ins_end": ins_end,
                                "pay_method": (str(r.get("납입방법")).strip() if not pd.isna(r.get("납입방법")) else None),

                                "receipt_date": rd,
                                "receipt_amount": total,

                                "car_liability": liability,
                                "car_optional": optional,
                                "status": status,

                                "product_code": None,
                                "product_name": None,

                                "life_nl": "자동차",
                                "ym": ym,
                            },
                        )
                        upserted_rows += 1

                    else:
                        emp_id = to_str_emp_id(r.get("설계사CD"))
                        name = (str(r.get("설계사")).strip() if not pd.isna(r.get("설계사")) else None)
                        raw_part = (str(r.get("소속")).strip() if not pd.isna(r.get("소속")) else None)
                        part = normalize_part_snapshot(raw_part)
                        branch = (str(r.get("영업가족")).strip() if not pd.isna(r.get("영업가족")) else None)

                        if not emp_id:
                            skipped_rows += 1
                            continue

                        user = CustomUser.objects.filter(id=emp_id).first()
                        matched_users += 1 if user else 0
                        missing_users += 0 if user else 1

                        receipt_amount = to_int_money(r.get("영수금"))

                        SalesRecord.objects.update_or_create(
                            policy_no=policy_no,
                            defaults={
                                "user": user,
                                "part_snapshot": part,
                                "branch_snapshot": branch,
                                "name_snapshot": name,
                                "emp_id_snapshot": emp_id,

                                "insurer": insurer,
                                "contractor": (str(r.get("계약자")).strip() if not pd.isna(r.get("계약자")) else None),
                                "insured": (str(r.get("주피")).strip() if not pd.isna(r.get("주피")) else None),

                                "ins_start": to_date(r.get("보험시작")),
                                "ins_end": to_date(r.get("보험종기")),
                                "pay_method": (str(r.get("납입방법")).strip() if not pd.isna(r.get("납입방법")) else None),

                                "receipt_date": rd,
                                "receipt_amount": receipt_amount,

                                "product_code": (str(r.get("보험사 상품코드")).strip() if not pd.isna(r.get("보험사 상품코드")) else None),
                                "product_name": (str(r.get("보험사 상품명")).strip() if not pd.isna(r.get("보험사 상품명")) else None),

                                "vehicle_no": None,
                                "car_liability": None,
                                "car_optional": None,
                                "status": (str(r.get("상태")).strip() if ("상태" in df.columns and not pd.isna(r.get("상태"))) else None),

                                "life_nl": life_nl_from_insurer(insurer),
                                "ym": ym,
                            },
                        )
                        upserted_rows += 1

                except Exception as row_e:
                    skipped_rows += 1
                    if first_row_error is None:
                        first_row_error = f"row={idx} policy_no={r.get('증권번호')} err={row_e}"
                    logger.exception("dash upload row failed: idx=%s", idx)

        # 업로드 직후 예측 생성 enqueue
        try:
            yms_to_process = _pick_yms_to_process(touched_yms)
            if yms_to_process:
                from dash.tasks import build_sales_forecasts_for_yms
                build_sales_forecasts_for_yms.delay(yms_to_process)
        except Exception:
            logger.exception("dash upload: forecast task enqueue failed")

        return JsonResponse(
            {
                "ok": True,
                "message": "업로드 완료",
                "summary": {
                    "detected_type": "auto" if is_auto else "default",
                    "users_matched": matched_users,
                    "users_missing_in_accounts": missing_users,
                    "rows_upserted": upserted_rows,
                    "rows_skipped": skipped_rows,
                    "rows_in_file": int(len(df)),
                    "first_row_error": first_row_error,
                    "touched_yms": sorted(touched_yms),
                    "enqueued_yms": _pick_yms_to_process(touched_yms),
                },
            }
        )

    except Exception as e:
        logger.exception("dash upload failed (500)")
        return json_err(f"서버 오류(업로드 처리 중): {e}", 500)