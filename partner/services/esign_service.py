# partner/services/esign_service.py
"""
지점효율 전자서명 서비스 레이어 (SSOT)

설계 기준: django_ma_esign_final_design.md v2.0
Playbook 규칙:
  - 비즈니스 로직은 서비스로 (뷰에서 if 난립 금지)
  - select_for_update로 중복 서명 방지
  - transaction.on_commit 후 PDF 생성 (DB 커밋 보장)
  - 감사 로그: audit.services.log_action 연계
  - ⚠️ pdf_file.url 직접 노출 절대 금지 — 뷰에서 FileResponse로만 제공
"""

from __future__ import annotations

import hashlib
import logging
from io import BytesIO

from django.core.files.base import ContentFile
from django.db import transaction
from django.utils import timezone

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# 내부 import (함수 내부에서 지연 import → 순환 참조 방지)
# ─────────────────────────────────────────────────────────────────────────────

def _get_models():
    from partner.models import EfficiencySignRequest, EfficiencyConfirmSign
    from accounts.models import CustomUser
    return EfficiencySignRequest, EfficiencyConfirmSign, CustomUser


# ─────────────────────────────────────────────────────────────────────────────
# 1. 헬퍼 함수
# ─────────────────────────────────────────────────────────────────────────────

def resolve_head_for_branch(branch: str):
    """
    해당 branch의 활성 최고관리자(head)를 조회한다.

    반환: CustomUser 또는 None
    없으면 None (저장 뷰에서 ValueError로 처리)
    """
    from accounts.models import CustomUser
    return CustomUser.objects.filter(
        grade='head',
        branch=branch,
        status='재직',
    ).first()


def get_my_sign_status(request_obj, user) -> str:
    """
    현재 요청 사용자 기준 서명 상태 반환.

    반환값:
      'unsigned'     — 서명 대상자이고 아직 미서명
      'signed'       — 서명 대상자이고 이미 서명 완료
      'not_required' — 서명 대상자가 아님 (조회만 가능)
    """
    try:
        sign = request_obj.signs.get(signer=user)
    except Exception:
        return 'not_required'
    return 'signed' if sign.signed_at else 'unsigned'


def get_my_sign_id(request_obj, user):
    """
    현재 사용자의 EfficiencyConfirmSign.id 반환.
    없으면 None.
    """
    try:
        sign = request_obj.signs.get(signer=user)
        return sign.pk
    except Exception:
        return None


# ─────────────────────────────────────────────────────────────────────────────
# 2. 저장 — create_sign_request
# ─────────────────────────────────────────────────────────────────────────────

def create_sign_request(
    *,
    created_by,
    confirm_group,
    rows,           # list[EfficiencyChange] — bulk_create 완료 후 전달
    branch: str,
    ym: str,
):
    """
    EfficiencySignRequest + EfficiencyConfirmSign 생성.

    호출 전제: 이미 transaction.atomic() 블록 내부에서 호출됨.

    처리 순서:
      1. branch head 조회 (없으면 ValueError)
      2. EfficiencySignRequest 생성
      3. 서명 참여자(공제자·지급자·head) 고유 집합 추출
      4. EfficiencyConfirmSign bulk_create

    반환: EfficiencySignRequest
    """
    EfficiencySignRequest, EfficiencyConfirmSign, CustomUser = _get_models()

    # ── 1. head 조회 ─────────────────────────────────────────────────────────
    head = resolve_head_for_branch(branch)
    if head is None:
        raise ValueError(
            f"'{branch}' 지점의 활성 최고관리자(head)를 찾을 수 없습니다. "
            "권한관리에서 head 계정을 먼저 등록해 주세요."
        )

    # ── 2. EfficiencySignRequest 생성 ─────────────────────────────────────────
    sign_request = EfficiencySignRequest.objects.create(
        confirm_group=confirm_group,
        ym=ym,
        branch=branch,
        created_by=created_by,
        status=EfficiencySignRequest.STATUS_PENDING,
    )

    # ── 3. 참여자 집합 구성 ───────────────────────────────────────────────────
    # ded_id / pay_id 중복 제거 + head 추가
    # unique_together = (request, signer) 이므로 같은 사람이 ded/pay 모두이면 1건만
    signer_role_map: dict[str, str] = {}  # {user_id: role}

    for row in rows:
        ded_id = (row.ded_id or '').strip()
        pay_id = (row.pay_id or '').strip()
        if ded_id and ded_id not in signer_role_map:
            signer_role_map[ded_id] = EfficiencyConfirmSign.ROLE_DEDUCT
        if pay_id and pay_id not in signer_role_map:
            # ded_id와 겹치면 deduct 우선 유지 (이미 등록된 경우 skip)
            if pay_id != ded_id:
                signer_role_map[pay_id] = EfficiencyConfirmSign.ROLE_PAY

    # head 등록 — head가 이미 ded/pay 대상자이더라도 head_confirm role 우선
    signer_role_map[head.pk] = EfficiencyConfirmSign.ROLE_HEAD_CONFIRM

    # ── 4. 사번 → CustomUser 조회 ─────────────────────────────────────────────
    user_ids = [uid for uid in signer_role_map if uid != head.pk]
    if user_ids:
        users_qs = CustomUser.objects.filter(pk__in=user_ids)
        users_map = {u.pk: u for u in users_qs}
    else:
        users_map = {}

    # ── 5. EfficiencyConfirmSign bulk_create ─────────────────────────────────
    sign_objs = []
    missing_ids = []

    for user_id, role in signer_role_map.items():
        if user_id == head.pk:
            signer_obj = head
        else:
            signer_obj = users_map.get(user_id)
            if signer_obj is None:
                missing_ids.append(user_id)
                continue

        sign_objs.append(EfficiencyConfirmSign(
            request=sign_request,
            signer=signer_obj,
            role=role,
        ))

    if missing_ids:
        # 존재하지 않는 사번 포함 시 롤백 (transaction.atomic 보장)
        raise ValueError(
            f"다음 사번을 시스템에서 찾을 수 없습니다: {', '.join(missing_ids)}"
        )

    EfficiencyConfirmSign.objects.bulk_create(sign_objs)

    logger.info(
        "esign create_sign_request: request_id=%s ym=%s branch=%s "
        "signers=%d created_by=%s",
        sign_request.pk, ym, branch, len(sign_objs), created_by.pk,
    )
    return sign_request


# ─────────────────────────────────────────────────────────────────────────────
# 3. 서명 처리 — process_sign
# ─────────────────────────────────────────────────────────────────────────────

def process_sign(
    *,
    request_id: int,
    signer,
    http_request,
) -> dict:
    """
    개별 서명 처리.

    - select_for_update로 중복 서명 방지
    - 감사추적 기록 (IP / UA / 세션키 / pass_verified_at 스냅샷)
    - 전원 서명 완료 시 transaction.on_commit 후 _finalize_request 호출
    - 반환: {'all_signed': bool, 'signed_at': str, 'pdf_ready': bool}

    예외:
      EfficiencyConfirmSign.DoesNotExist → 서명 권한 없음 또는 이미 서명 (호출자에서 처리)
    """
    EfficiencySignRequest, EfficiencyConfirmSign, _ = _get_models()

    with transaction.atomic():
        # 중복 서명 방지: signed_at__isnull=True 조건 포함
        sign = EfficiencyConfirmSign.objects.select_for_update().get(
            request_id=request_id,
            signer=signer,
            signed_at__isnull=True,
        )

        now = timezone.now()

        # 감사추적 기록
        sign.signed_at             = now
        sign.ip_address            = _get_client_ip(http_request)
        sign.user_agent            = http_request.META.get('HTTP_USER_AGENT', '')[:500]
        sign.session_key           = (http_request.session.session_key or '')[:40]
        sign.pass_verified_at_sign = getattr(signer, 'pass_verified_at', None)
        sign.save(update_fields=[
            'signed_at', 'ip_address', 'user_agent',
            'session_key', 'pass_verified_at_sign',
        ])

        # 전체 서명 완료 여부 확인
        req = EfficiencySignRequest.objects.select_for_update().get(pk=request_id)
        all_signs = list(req.signs.all())
        all_signed = all(s.signed_at for s in all_signs)
        any_signed = any(s.signed_at for s in all_signs)

        # status 갱신
        if all_signed:
            req.status = EfficiencySignRequest.STATUS_COMPLETED
        elif any_signed:
            req.status = EfficiencySignRequest.STATUS_PARTIAL
        req.save(update_fields=['status', 'updated_at'])

        # on_commit 후 PDF 생성 (DB 트랜잭션 완전 커밋 보장)
        if all_signed:
            req_id = req.pk
            transaction.on_commit(lambda: _finalize_request(req_id))

    signed_at_str = now.strftime('%Y-%m-%d %H:%M')

    logger.info(
        "esign process_sign: request_id=%s signer=%s all_signed=%s",
        request_id, signer.pk, all_signed,
    )

    return {
        'all_signed': all_signed,
        'signed_at':  signed_at_str,
        'pdf_ready':  False,   # on_commit 비동기 생성 → 즉시 False 반환이 안전
    }


# ─────────────────────────────────────────────────────────────────────────────
# 4. 완료 처리 — _finalize_request (on_commit 후 호출)
# ─────────────────────────────────────────────────────────────────────────────

def _finalize_request(req_id: int) -> None:
    """
    모든 서명 완료 후 PDF 생성 및 req 저장.

    transaction.on_commit() 후 호출되므로 별도 atomic 블록 사용.
    PDF 생성 실패 시 로거 기록 (status는 completed 유지 — 재생성 가능하도록).
    """
    EfficiencySignRequest, _, _ = _get_models()

    try:
        from partner.services.pdf_service import render_confirm_pdf

        req = EfficiencySignRequest.objects.select_related(
            'confirm_group', 'created_by'
        ).prefetch_related(
            'signs__signer',
            'confirm_group__efficiency_rows',
        ).get(pk=req_id)

        # PDF 생성
        pdf_bytes = render_confirm_pdf(req)

        # SHA-256 해시
        doc_hash = hashlib.sha256(pdf_bytes).hexdigest()

        # 파일명: esign_YYYYMM_branch_reqid.pdf (한글 포함 시 RFC5987 뷰에서 처리)
        safe_branch = req.branch.replace(' ', '_')
        filename = f"esign_{req.ym.replace('-', '')}_{safe_branch}_{req.pk}.pdf"

        with transaction.atomic():
            req.pdf_file.save(filename, ContentFile(pdf_bytes), save=False)
            req.doc_hash = doc_hash
            req.status   = EfficiencySignRequest.STATUS_COMPLETED
            req.save(update_fields=['pdf_file', 'doc_hash', 'status', 'updated_at'])

        logger.info(
            "esign _finalize_request: request_id=%s pdf=%s hash=%s",
            req_id, filename, doc_hash[:12],
        )

    except Exception:
        logger.exception(
            "esign _finalize_request FAILED: request_id=%s — "
            "status는 completed로 유지 (PDF 재생성 필요)",
            req_id,
        )


# ─────────────────────────────────────────────────────────────────────────────
# 5. 조회 범위 쿼리 빌더
# ─────────────────────────────────────────────────────────────────────────────

def build_esign_queryset(user, branch_filter: str = ''):
    """
    사용자 권한 스코프에 맞는 EfficiencySignRequest QuerySet 반환.

    조회 범위 정책 (설계 §10-2):
      superuser  → 전체 (branch_filter 있으면 해당 branch만)
      head       → 본인 branch 전체
      leader     → 본인 위계(팀) 내역 + 본인이 서명 대상자인 내역
      basic      → 본인이 서명 대상자인 내역만
    """
    from django.db.models import Q
    from partner.models import EfficiencySignRequest

    grade = getattr(user, 'grade', 'basic')
    qs = EfficiencySignRequest.objects.select_related(
        'confirm_group', 'created_by'
    ).prefetch_related(
        'signs__signer',
        'confirm_group__efficiency_rows',
    )

    if grade == 'superuser':
        if branch_filter:
            qs = qs.filter(branch__iexact=branch_filter)

    elif grade == 'head':
        qs = qs.filter(branch__iexact=user.branch)

    elif grade == 'leader':
        # 본인 branch/팀 내 업로더 그룹 + 본인이 서명 대상자인 그룹
        qs = qs.filter(
            Q(branch__iexact=user.branch) |
            Q(signs__signer=user)
        ).distinct()

    else:
        # basic: 본인이 서명 대상자인 내역만
        qs = qs.filter(signs__signer=user).distinct()

    return qs.order_by('-created_at')


# ─────────────────────────────────────────────────────────────────────────────
# 6. 삭제 — delete_sign_request
# ─────────────────────────────────────────────────────────────────────────────

def delete_sign_request(*, sign_request, actor) -> None:
    """
    서명 요청 삭제.

    조건:
      - status == 'pending' 일 때만 허용
      - superuser 또는 해당 branch head만 가능
    연쇄 삭제:
      EfficiencySignRequest → EfficiencyConfirmSign (CASCADE)
      EfficiencyConfirmGroup → EfficiencyChange (PROTECT → 뷰에서 직접 삭제)

    예외:
      PermissionError — 권한 없음
      ValueError      — pending 상태가 아님
    """
    grade = getattr(actor, 'grade', 'basic')

    # 권한 검증
    if grade == 'superuser':
        pass
    elif grade == 'head' and actor.branch == sign_request.branch:
        pass
    else:
        raise PermissionError("삭제 권한이 없습니다.")

    # 상태 검증
    if not sign_request.is_pending:
        raise ValueError(
            "서명이 진행 중이거나 완료된 확인서는 삭제할 수 없습니다. "
            f"(현재 상태: {sign_request.get_status_display()})"
        )

    with transaction.atomic():
        group = sign_request.confirm_group

        # EfficiencySignRequest 삭제 (EfficiencyConfirmSign CASCADE 포함)
        sign_request.delete()

        # EfficiencyConfirmGroup + EfficiencyChange 삭제
        if group is not None:
            group.efficiency_rows.all().delete()
            group.delete()

    logger.info(
        "esign delete_sign_request: deleted by=%s",
        actor.pk,
    )


# ─────────────────────────────────────────────────────────────────────────────
# 7. 내부 유틸
# ─────────────────────────────────────────────────────────────────────────────

def _get_client_ip(request) -> str:
    """X-Forwarded-For → REMOTE_ADDR 순으로 클라이언트 IP 추출."""
    xff = request.META.get('HTTP_X_FORWARDED_FOR', '')
    if xff:
        return xff.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR', '')