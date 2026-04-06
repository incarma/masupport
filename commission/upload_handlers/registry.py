# django_ma/commission/upload_handlers/registry.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Dict, Iterable, Literal

from . import deposit
from . import collect as collect_handler

Mode = Literal["df", "file"]


@dataclass(frozen=True)
class UploadSpec:
    """
    SSOT 업로드 스펙

    - mode == "df"
      views에서 _read_excel_safely로 DataFrame을 만든 후 fn(df) 호출
    - mode == "file"
      views에서 임시 저장된 file_path/original_name을 fn(file_path, original_name)로 전달
    """
    upload_type: str
    mode: Mode
    fn: Callable
    msg_tpl: str


# =============================================================================
# SSOT Registry
# - upload_type 문자열이 "유일키"
# - views는 이 레지스트리만 믿고 처리한다.
# =============================================================================
_REGISTRY: Dict[str, UploadSpec] = {
    # -----------------------------------------------------------------
    # DataFrame 기반(일반 Excel)
    # -----------------------------------------------------------------
    "최종지급액": UploadSpec(
        upload_type="최종지급액",
        mode="df",
        fn=deposit.handle_upload_final_payment,
        msg_tpl="✅ 최종지급액 업로드 완료 ({n}건)",
    ),
    "환수지급예상": UploadSpec(
        upload_type="환수지급예상",
        mode="df",
        fn=deposit.handle_upload_refund_pay_expected,
        msg_tpl="✅ 환수/지급예상 업로드 완료 ({n}건)",
    ),

    # 기존 보증증액(호환 유지) → 내부적으로는 채권지표 로직과 동일
    "보증증액": UploadSpec(
        upload_type="보증증액",
        mode="df",
        fn=deposit.handle_upload_guarantee_increase,
        msg_tpl="✅ 보증증액 업로드 완료 ({n}건)",
    ),

    # ✅ 신규: 채권지표
    "채권지표": UploadSpec(
        upload_type="채권지표",
        mode="df",
        fn=deposit.handle_upload_deposit_metrics,
        msg_tpl="✅ 채권지표 업로드 완료 ({n}건)",
    ),

    "응당생보": UploadSpec(
        upload_type="응당생보",
        mode="df",
        fn=deposit.handle_upload_ls_due,
        msg_tpl="✅ 응당생보 업로드 완료 ({n}건)",
    ),
    "응당손보": UploadSpec(
        upload_type="응당손보",
        mode="df",
        fn=deposit.handle_upload_ns_due,
        msg_tpl="✅ 응당손보 업로드 완료 ({n}건)",
    ),
    "보증보험": UploadSpec(
        upload_type="보증보험",
        mode="df",
        fn=deposit.handle_upload_surety,
        msg_tpl="✅ 보증보험 업로드 완료 ({n}건)",
    ),
    "기타채권": UploadSpec(
        upload_type="기타채권",
        mode="df",
        fn=deposit.handle_upload_other_debt,
        msg_tpl="✅ 기타채권 업로드 완료 ({n}건)",
    ),

    # -----------------------------------------------------------------
    # Raw matrix 기반(통산손/생보)
    # -----------------------------------------------------------------
    "통산손보": UploadSpec(
        upload_type="통산손보",
        mode="file",
        fn=deposit.handle_upload_ns_total_from_file,
        msg_tpl="✅ 통산손보 업로드 완료 ({n}건)",
    ),
    "통산생보": UploadSpec(
        upload_type="통산생보",
        mode="file",
        fn=deposit.handle_upload_ls_total_from_file,
        msg_tpl="✅ 통산생보 업로드 완료 ({n}건)",
    ),

    # -----------------------------------------------------------------
    # 환수관리 전용 업로드 — Step 4
    # upload_type="환수관리" 로 기존 upload_excel 뷰에서 자동 라우팅
    # -----------------------------------------------------------------
    "환수관리": UploadSpec(
        upload_type="환수관리",
        mode="df",
        fn=collect_handler.handle_upload_collect,
        msg_tpl="✅ 환수관리 업로드 완료 ({n}건)",
    ),
}


def get_upload_spec(upload_type: str) -> UploadSpec:
    """upload_type -> UploadSpec (없으면 KeyError)"""
    try:
        return _REGISTRY[upload_type]
    except KeyError:
        raise KeyError(f"Unsupported upload_type: {upload_type}")


def supported_upload_types() -> Iterable[str]:
    """지원 업로드 타입 목록"""
    return tuple(_REGISTRY.keys())


__all__ = ["UploadSpec", "get_upload_spec", "supported_upload_types"]