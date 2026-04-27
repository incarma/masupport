# partner/views/esign.py
"""
지점효율 전자서명 뷰 레이어

설계 기준: django_ma_esign_final_design.md v2.0
Playbook 규칙:
  - 뷰는 얇게 (비즈니스 로직은 esign_service로 위임)
  - JSON 응답: _ok / _err 헬퍼로 포맷 통일
  - 권한: grade_required 데코레이터 사용 (inactive 자동 차단)
  - 파일: pdf_file.url 직접 노출 금지 → FileResponse + RFC5987 파일명
  - 감사 로그: audit.services.log_action 연계
  - 저장 트랜잭션: transaction.atomic() + esign_service 호출
"""

from __future__ import annotations

import json
import logging
import unicodedata
from urllib.parse import quote

from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import FileResponse, Http404, JsonResponse
from django.shortcuts import render
from django.urls import reverse
from django.views.decorators.http import require_POST, require_http_methods

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# JSON 응답 헬퍼 (프로젝트 공통 포맷)
# ─────────────────────────────────────────────────────────────────────────────

def _ok(data: dict | None = None, **kwargs) -> JsonResponse:
    payload = {'status': 'success'}
    if data:
        payload.update(data)
    payload.update(kwargs)
    return JsonResponse(payload)


def _err(message: str, status: int = 400) -> JsonResponse:
    return JsonResponse({'status': 'error', 'message': message}, status=status)


def _require_login(request):
    """로그인 여부 확인 — inactive는 Django 세션 레벨에서 차단됨."""
    if not request.user.is_authenticated:
        return _err('로그인이 필요합니다.', status=401)
    return None


def _parse_json(request) -> tuple[dict | None, JsonResponse | None]:
    """request.body JSON 파싱. 실패 시 (None, error_response) 반환."""
    try:
        return json.loads(request.body or '{}'), None
    except (json.JSONDecodeError, ValueError):
        return None, _err('잘못된 JSON 형식입니다.')


# ─────────────────────────────────────────────────────────────────────────────
# P3-3-1. 페이지 뷰
# ─────────────────────────────────────────────────────────────────────────────

@login_required
def esign_confirm_page(request):
    """
    /partner/esign/ — 전자서명 메인 페이지

    접근: superuser / head / leader / basic (inactive 세션 레벨 차단)
    내용입력 카드: superuser / head / leader만 표시 (basic 숨김)
    """
    user = request.user
    grade = getattr(user, 'grade', 'basic')

    # 내용 입력 카드 노출 여부 (템플릿에서 사용)
    can_input = grade in ('superuser', 'head', 'leader')
    # 삭제 버튼 노출 여부
    can_delete = grade in ('superuser', 'head')

    context = {
        'can_input':  can_input,
        'can_delete': can_delete,
        'search_user_url': reverse('accounts:api_search_user'),
    }
    return render(request, 'partner/esign_confirm.html', context)


# ─────────────────────────────────────────────────────────────────────────────
# P3-3-2. 데이터 조회
# ─────────────────────────────────────────────────────────────────────────────

@login_required
@require_http_methods(['GET'])
def esign_fetch(request):
    """
    GET /partner/api/esign/fetch/?month=YYYY-MM&branch=...

    권한 스코프: esign_service.build_esign_queryset 위임
    """
    from partner.services.esign_service import (
        build_esign_queryset,
        get_my_sign_status,
        get_my_sign_id,
    )

    user   = request.user
    month  = request.GET.get('month', '').strip()
    branch = request.GET.get('branch', '').strip()

    qs = build_esign_queryset(user, branch_filter=branch)
    if month:
        qs = qs.filter(ym=month)

    groups = []
    for req in qs:
        group  = req.confirm_group
        rows   = list(group.efficiency_rows.all()) if group else []
        signs  = list(req.signs.select_related('signer').all())

        my_status = get_my_sign_status(req, user)
        my_sid    = get_my_sign_id(req, user)

        # 서명자 목록
        signers_data = [
            {
                'sign_id':     s.pk,
                'signer_id':   s.signer_id,
                'signer_name': getattr(s.signer, 'name', ''),
                'role':        s.role,
                'signed':      s.signed_at is not None,
                'signed_at':   s.signed_at.strftime('%Y-%m-%d %H:%M') if s.signed_at else None,
            }
            for s in signs
        ]

        # 행 데이터
        rows_data = [
            {
                'id':             r.pk,
                'requester_name': getattr(r.requester, 'name', '') if r.requester else '',
                'requester_id':   r.requester_id or '',
                'start_ym':       r.start_ym or '',
                'end_ym':         r.end_ym or '',
                'category':       r.category or '',
                'amount':         r.amount or 0,
                'ded_name':       r.ded_name or '',
                'ded_id':         r.ded_id or '',
                'pay_name':       r.pay_name or '',
                'pay_id':         r.pay_id or '',
                'content':        r.content or '',
                # 서명일시: ded/pay 각각의 signed_at
                'signed_at': _row_signed_at(r, signs),
            }
            for r in rows
        ]

        # PDF URL — pdf_file.url 직접 노출 금지, 뷰 URL로만 제공
        pdf_ready = bool(req.pdf_file)
        pdf_url   = (
            reverse('partner:esign_pdf', kwargs={'request_id': req.pk})
            if pdf_ready else None
        )

        groups.append({
            'confirm_group_id': getattr(group, 'confirm_group_id', '') if group else '',
            'group_pk':         group.pk if group else None,
            'sign_request_id':  req.pk,
            'title':            getattr(group, 'title', '') if group else f'{req.ym}/{req.branch}',
            'month':            req.ym,
            'branch':           req.branch,
            'row_count':        len(rows),
            'sign_status':      req.status,
            'my_sign_status':   my_status,
            'my_sign_id':       my_sid,
            'pdf_ready':        pdf_ready,
            'pdf_url':          pdf_url,
            'signers':          signers_data,
            'rows':             rows_data,
        })

    return _ok({'kind': 'esign', 'groups': groups})


def _row_signed_at(row, signs: list) -> str | None:
    """행의 ded_id에 해당하는 서명일시 반환 (아코디언 '서명일시' 컬럼용)."""
    for s in signs:
        if s.signer_id == row.ded_id and s.signed_at:
            return s.signed_at.strftime('%Y-%m-%d %H:%M')
    return None


# ─────────────────────────────────────────────────────────────────────────────
# P3-3-3. 저장
# ─────────────────────────────────────────────────────────────────────────────

@login_required
@require_POST
def esign_save(request):
    """
    POST /partner/api/esign/save/

    저장 권한: superuser / head / leader
    트랜잭션: atomic — EfficiencyConfirmGroup + EfficiencyChange + EfficiencySignRequest + EfficiencyConfirmSign
    """
    from audit.constants import ACTION
    from audit.services import log_action
    from partner.models import EfficiencyChange, EfficiencyConfirmGroup
    from partner.services.esign_service import create_sign_request

    user  = request.user
    grade = getattr(user, 'grade', 'basic')

    if grade not in ('superuser', 'head', 'leader'):
        return _err('저장 권한이 없습니다.', status=403)

    body, err = _parse_json(request)
    if err:
        return err

    month  = (body.get('month') or '').strip()
    part   = (body.get('part')  or '').strip()
    branch = (body.get('branch') or '').strip()
    rows   = body.get('rows', [])

    # ── 기본 검증 ────────────────────────────────────────────────────────────
    if not month or not branch:
        return _err('월도와 지점은 필수입니다.')
    if not isinstance(rows, list) or len(rows) == 0:
        return _err('저장할 행이 없습니다.')
    if len(rows) > 10:
        return _err('최대 10건까지 저장할 수 있습니다.')

    for i, row in enumerate(rows, start=1):
        start_ym = (row.get('start_ym') or '').strip()
        end_ym   = (row.get('end_ym')   or '').strip()
        if not start_ym or not end_ym:
            return _err(f'{i}번 행: 시작월도와 종료월도는 필수입니다.')
        if start_ym > end_ym:
            return _err(f'{i}번 행: 종료월도는 시작월도 이후여야 합니다.')
        if not (row.get('ded_id') or '').strip():
            return _err(f'{i}번 행: 공제자 사번은 필수입니다.')
        if not (row.get('pay_id') or '').strip():
            return _err(f'{i}번 행: 지급자 사번은 필수입니다.')

    # ── 트랜잭션 ─────────────────────────────────────────────────────────────
    try:
        with transaction.atomic():
            # 1) EfficiencyConfirmGroup 생성 (기존 _generate_confirm_group_id 재사용)
            group_id = _generate_confirm_group_id(user)
            group = EfficiencyConfirmGroup.objects.create(
                confirm_group_id=group_id,
                uploader=user,
                part=part or getattr(user, 'part', '-'),
                branch=branch,
                month=month,
                title=f'{month} / {branch}',
            )

            # 2) EfficiencyChange bulk_create
            change_objs = []
            for row in rows:
                amount_raw = row.get('amount')
                try:
                    amount = int(str(amount_raw).replace(',', '')) if amount_raw else None
                except (ValueError, TypeError):
                    amount = None

                change_objs.append(EfficiencyChange(
                    requester=user,
                    part=part or getattr(user, 'part', '-'),
                    branch=branch,
                    month=month,
                    confirm_group=group,
                    start_ym=(row.get('start_ym') or '').strip(),
                    end_ym=(row.get('end_ym')   or '').strip(),
                    category=(row.get('category') or '').strip(),
                    amount=amount,
                    ded_name=(row.get('ded_name') or '').strip(),
                    ded_id=(row.get('ded_id')   or '').strip(),
                    pay_name=(row.get('pay_name') or '').strip(),
                    pay_id=(row.get('pay_id')   or '').strip(),
                    content=(row.get('content') or '').strip()[:80],
                ))

            saved_rows = EfficiencyChange.objects.bulk_create(change_objs)

            # 3) EfficiencySignRequest + EfficiencyConfirmSign
            sign_request = create_sign_request(
                created_by=user,
                confirm_group=group,
                rows=saved_rows,
                branch=branch,
                ym=month,
            )

    except ValueError as e:
        logger.warning("esign_save ValueError: %s user=%s", e, user.pk)
        return _err(str(e))
    except Exception:
        logger.exception("esign_save unexpected error: user=%s", user.pk)
        return _err('저장 중 오류가 발생했습니다. 잠시 후 다시 시도해 주세요.')

    # 감사 로그
    try:
        log_action(
            actor=user,
            action=ACTION.PARTNER_ESIGN_CREATE,
            target=f'EfficiencySignRequest:{sign_request.pk}',
            metadata={
                'ym': month, 'branch': branch,
                'row_count': len(rows),
                'sign_request_id': sign_request.pk,
            },
            success=True,
        )
    except Exception:
        logger.warning("esign_save audit log failed (non-critical)", exc_info=True)

    return _ok({
        'confirm_group_id': group.confirm_group_id,
        'sign_request_id':  sign_request.pk,
        'saved_count':      len(rows),
        'signer_count':     sign_request.signs.count(),
    })


def _generate_confirm_group_id(user) -> str:
    """
    EfficiencyConfirmGroup ID 생성.
    기존 manage_efficiency의 _generate_confirm_group_id 규약과 동일한 포맷 유지.
    포맷: YYYYMMHHMM_<user_id>_<seq2>
    """
    from django.utils import timezone as tz
    from partner.models import EfficiencyConfirmGroup

    now   = tz.localtime()
    base  = now.strftime('%Y%m%d%H%M')
    prefix = f"{base}_{user.pk}_"

    last = (
        EfficiencyConfirmGroup.objects
        .filter(confirm_group_id__startswith=prefix)
        .order_by('-confirm_group_id')
        .first()
    )
    if last:
        try:
            seq = int(last.confirm_group_id.rsplit('_', 1)[-1]) + 1
        except (ValueError, IndexError):
            seq = 1
    else:
        seq = 1

    return f"{prefix}{seq:02d}"


# ─────────────────────────────────────────────────────────────────────────────
# P3-3-4. 서명하기
# ─────────────────────────────────────────────────────────────────────────────

@login_required
@require_POST
def esign_sign(request, request_id: int):
    """
    POST /partner/api/esign/{request_id}/sign/

    - 로그인 세션 기반 서명 (Phase 2 이전)
    - select_for_update로 중복 서명 방지 (esign_service에서 처리)
    """
    from audit.constants import ACTION
    from audit.services import log_action
    from partner.models import EfficiencyConfirmSign
    from partner.services.esign_service import process_sign

    user = request.user

    try:
        result = process_sign(
            request_id=request_id,
            signer=user,
            http_request=request,
        )
    except EfficiencyConfirmSign.DoesNotExist:
        return _err('서명 권한이 없거나 이미 서명이 완료된 항목입니다.', status=403)
    except Exception:
        logger.exception("esign_sign unexpected error: request_id=%s user=%s", request_id, user.pk)
        return _err('서명 처리 중 오류가 발생했습니다.')

    # 감사 로그
    try:
        log_action(
            actor=user,
            action=ACTION.PARTNER_ESIGN_SIGN,
            target=f'EfficiencySignRequest:{request_id}',
            metadata={
                'signed_at': result['signed_at'],
                'all_signed': result['all_signed'],
            },
            success=True,
        )
    except Exception:
        logger.warning("esign_sign audit log failed (non-critical)", exc_info=True)

    return _ok(result)


# ─────────────────────────────────────────────────────────────────────────────
# P3-3-5. PDF 다운로드
# ─────────────────────────────────────────────────────────────────────────────

@login_required
@require_http_methods(['GET'])
def esign_pdf_download(request, request_id: int):
    """
    GET /partner/api/esign/{request_id}/pdf/

    ⚠️ pdf_file.url 직접 노출 절대 금지 — 이 뷰를 반드시 경유할 것.

    권한:
      superuser    → 전체
      head         → 본인 branch
      leader/basic → 본인이 서명 참여자인 내역만
    """
    from audit.constants import ACTION
    from audit.services import log_action
    from partner.models import EfficiencySignRequest

    user = request.user

    try:
        req = EfficiencySignRequest.objects.select_related('confirm_group').get(pk=request_id)
    except EfficiencySignRequest.DoesNotExist:
        raise Http404

    if not req.pdf_file:
        return _err('서명이 완료되지 않아 확인서를 다운로드할 수 없습니다.', status=404)

    # 권한 검증
    grade = getattr(user, 'grade', 'basic')
    if grade == 'superuser':
        pass
    elif grade == 'head':
        if user.branch != req.branch:
            return _err('접근 권한이 없습니다.', status=403)
    else:
        # leader / basic: 서명 참여자인지 확인
        is_participant = req.signs.filter(signer=user).exists()
        if not is_participant:
            return _err('접근 권한이 없습니다.', status=403)

    # 감사 로그
    try:
        log_action(
            actor=user,
            action=ACTION.PARTNER_ESIGN_PDF_DL,
            target=f'EfficiencySignRequest:{request_id}',
            metadata={'branch': req.branch, 'ym': req.ym},
            success=True,
        )
    except Exception:
        logger.warning("esign_pdf_download audit log failed (non-critical)", exc_info=True)

    # RFC5987 한글 파일명 — 다운로드 시 깨짐 방지
    group  = req.confirm_group
    doc_id = getattr(group, 'confirm_group_id', str(req.pk)) if group else str(req.pk)
    display_filename = f"지점효율_사실확인서_{req.ym}_{req.branch}_{doc_id}.pdf"
    encoded_filename = quote(display_filename, safe='')
    content_disposition = (
        f"attachment; filename=\"esign_{req.pk}.pdf\"; "
        f"filename*=UTF-8''{encoded_filename}"
    )

    try:
        file_handle = req.pdf_file.open('rb')
    except Exception:
        logger.exception("esign_pdf_download file open error: request_id=%s", request_id)
        return _err('파일을 열 수 없습니다. 관리자에게 문의해 주세요.', status=500)

    response = FileResponse(file_handle, content_type='application/pdf')
    response['Content-Disposition'] = content_disposition
    return response


# ─────────────────────────────────────────────────────────────────────────────
# P3-3-6. 그룹 삭제
# ─────────────────────────────────────────────────────────────────────────────

@login_required
@require_POST
def esign_delete_group(request):
    """
    POST /partner/api/esign/delete-group/

    조건: status == 'pending' 이고 superuser 또는 해당 branch head만 가능
    연쇄 삭제: EfficiencySignRequest → EfficiencyConfirmSign (CASCADE)
               EfficiencyConfirmGroup → EfficiencyChange
    """
    from audit.constants import ACTION
    from audit.services import log_action
    from partner.models import EfficiencySignRequest
    from partner.services.esign_service import delete_sign_request

    user  = request.user
    body, err = _parse_json(request)
    if err:
        return err

    sign_request_id = body.get('sign_request_id')
    if not sign_request_id:
        return _err('sign_request_id가 필요합니다.')

    try:
        req = EfficiencySignRequest.objects.get(pk=sign_request_id)
    except EfficiencySignRequest.DoesNotExist:
        return _err('해당 서명 요청을 찾을 수 없습니다.', status=404)

    try:
        delete_sign_request(sign_request=req, actor=user)
    except PermissionError as e:
        return _err(str(e), status=403)
    except ValueError as e:
        return _err(str(e))
    except Exception:
        logger.exception(
            "esign_delete_group unexpected error: request_id=%s user=%s",
            sign_request_id, user.pk,
        )
        return _err('삭제 중 오류가 발생했습니다.')

    # 감사 로그
    try:
        log_action(
            actor=user,
            action=ACTION.PARTNER_ESIGN_DELETE,
            target=f'EfficiencySignRequest:{sign_request_id}',
            metadata={},
            success=True,
        )
    except Exception:
        logger.warning("esign_delete_group audit log failed (non-critical)", exc_info=True)

    return _ok({'deleted': True})