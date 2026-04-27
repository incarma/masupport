# partner/services/pdf_service.py
"""
지점효율 사실확인서 PDF 생성 서비스 (ReportLab 직접 구현)

설계 기준: django_ma_esign_final_design.md v2.0 §8
운영 전제:
  - Render 환경 — LibreOffice 미사용
  - reportlab==4.4.4 (requirements.txt 확인됨)
  - 한글 폰트: NanumGothic 우선, 없으면 Helvetica 폴백 (운영 장애 방지)
  - 폰트 파일 위치: static/fonts/NanumGothic.ttf (없으면 폴백 동작)
"""

from __future__ import annotations

import logging
import os
from io import BytesIO

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# ReportLab 임포트
# ─────────────────────────────────────────────────────────────────────────────
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

# ─────────────────────────────────────────────────────────────────────────────
# 폰트 등록 (한글 지원)
# ─────────────────────────────────────────────────────────────────────────────
_FONT_REGISTERED = False
_BASE_FONT       = 'Helvetica'       # 폴백
_BASE_FONT_BOLD  = 'Helvetica-Bold'  # 폴백


def _try_register_korean_font() -> None:
    """
    NanumGothic 폰트를 등록한다.
    파일이 없으면 경고 로그 후 Helvetica 폴백으로 계속 동작.
    등록 성공 시 _BASE_FONT / _BASE_FONT_BOLD를 교체.
    """
    global _FONT_REGISTERED, _BASE_FONT, _BASE_FONT_BOLD

    if _FONT_REGISTERED:
        return

    # 탐색 경로 우선순위: Django STATICFILES_DIRS → BASE_DIR/static → BASE_DIR/var/fonts
    candidate_paths = []
    try:
        from django.conf import settings
        base = str(settings.BASE_DIR)
        candidate_paths += [
            os.path.join(base, 'static', 'fonts', 'NanumGothic.ttf'),
            os.path.join(base, 'static', 'fonts', 'NanumGothicBold.ttf'),
            os.path.join(base, 'var', 'fonts', 'NanumGothic.ttf'),
        ]
    except Exception:
        pass

    regular_path = None
    bold_path    = None

    for p in candidate_paths:
        if 'Bold' not in p and os.path.isfile(p):
            regular_path = p
        if 'Bold' in p and os.path.isfile(p):
            bold_path = p

    if regular_path:
        try:
            pdfmetrics.registerFont(TTFont('NanumGothic', regular_path))
            _BASE_FONT = 'NanumGothic'

            if bold_path:
                pdfmetrics.registerFont(TTFont('NanumGothicBold', bold_path))
                _BASE_FONT_BOLD = 'NanumGothicBold'
            else:
                # Bold 없으면 Regular를 Bold로도 등록 (글자 깨짐 방지)
                pdfmetrics.registerFont(TTFont('NanumGothicBold', regular_path))
                _BASE_FONT_BOLD = 'NanumGothicBold'

            logger.info("pdf_service: NanumGothic 폰트 등록 완료 (%s)", regular_path)
        except Exception as e:
            logger.warning("pdf_service: NanumGothic 폰트 등록 실패 → Helvetica 폴백 (%s)", e)
    else:
        logger.warning(
            "pdf_service: NanumGothic.ttf 파일을 찾을 수 없습니다 → Helvetica 폴백. "
            "한글이 깨질 수 있습니다. static/fonts/NanumGothic.ttf 에 파일을 배치하세요."
        )

    _FONT_REGISTERED = True


# ─────────────────────────────────────────────────────────────────────────────
# 메인 함수
# ─────────────────────────────────────────────────────────────────────────────

def render_confirm_pdf(sign_request) -> bytes:
    """
    지점효율 사실확인서 PDF 생성.

    Args:
        sign_request: EfficiencySignRequest (prefetch_related 완료 상태 권장)
                      - confirm_group.efficiency_rows
                      - signs (signer 포함)

    Returns:
        bytes: PDF 바이트 스트림

    예외:
        예외 발생 시 caller(_finalize_request)에서 캐치·로깅하므로 그대로 raise.
    """
    _try_register_korean_font()

    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        topMargin=20 * mm,
        bottomMargin=20 * mm,
        leftMargin=15 * mm,
        rightMargin=15 * mm,
    )

    story = []

    # ── 스타일 정의 ──────────────────────────────────────────────────────────
    normal = ParagraphStyle(
        'normal',
        fontName=_BASE_FONT,
        fontSize=9,
        leading=14,
    )
    bold_center = ParagraphStyle(
        'bold_center',
        fontName=_BASE_FONT_BOLD,
        fontSize=13,
        leading=18,
        alignment=1,  # CENTER
    )
    sub_title = ParagraphStyle(
        'sub_title',
        fontName=_BASE_FONT,
        fontSize=10,
        leading=14,
        alignment=1,
    )
    small = ParagraphStyle(
        'small',
        fontName=_BASE_FONT,
        fontSize=8,
        leading=12,
    )
    small_center = ParagraphStyle(
        'small_center',
        fontName=_BASE_FONT,
        fontSize=8,
        leading=12,
        alignment=1,
    )
    right_align = ParagraphStyle(
        'right_align',
        fontName=_BASE_FONT,
        fontSize=9,
        leading=14,
        alignment=2,  # RIGHT
    )

    # ── 제목 ─────────────────────────────────────────────────────────────────
    story.append(Paragraph('[다인용]', sub_title))
    story.append(Spacer(1, 4 * mm))
    story.append(Paragraph('지점효율 지급(공제) 사실확인서', bold_center))
    story.append(Spacer(1, 6 * mm))

    # ── 본문 약관 ─────────────────────────────────────────────────────────────
    terms_text = (
        "1. 본 확인서는 지점효율 지급(공제) 관련 사실을 확인하는 문서입니다.<br/>"
        "2. 서명자는 아래 내역을 충분히 확인하였으며, "
        "기재된 내용이 사실임을 전자서명으로 확인합니다.<br/>"
        "3. 본 문서는 전자서명법 제2조 제1항에 따른 전자서명이 적용된 문서입니다."
    )
    story.append(Paragraph(terms_text, normal))
    story.append(Spacer(1, 6 * mm))

    # ── 데이터 테이블 ─────────────────────────────────────────────────────────
    story.append(_build_data_table(sign_request, small, small_center))
    story.append(Spacer(1, 8 * mm))

    # ── 서명일 ────────────────────────────────────────────────────────────────
    completed_at = sign_request.updated_at or sign_request.created_at
    date_str = completed_at.strftime('%Y년 %m월 %d일')
    story.append(Paragraph(date_str, ParagraphStyle(
        'date', fontName=_BASE_FONT, fontSize=10, leading=14, alignment=1,
    )))
    story.append(Spacer(1, 6 * mm))

    # ── 확인자(head) ──────────────────────────────────────────────────────────
    story.append(_build_head_confirm_section(sign_request, normal))
    story.append(Spacer(1, 4 * mm))

    # ── 담당자 귀중 ───────────────────────────────────────────────────────────
    story.append(Paragraph(
        '인카금융서비스 주식회사 담당자 귀중',
        right_align,
    ))
    story.append(Spacer(1, 6 * mm))

    # ── 문서 ID ───────────────────────────────────────────────────────────────
    group = getattr(sign_request, 'confirm_group', None)
    doc_id = getattr(group, 'confirm_group_id', str(sign_request.pk)) if group else str(sign_request.pk)
    story.append(Paragraph(f'문서 ID : {doc_id}', small))

    # ── PDF 빌드 ──────────────────────────────────────────────────────────────
    doc.build(story)
    return buf.getvalue()


# ─────────────────────────────────────────────────────────────────────────────
# 내부 빌더 함수
# ─────────────────────────────────────────────────────────────────────────────

def _build_data_table(sign_request, small_style, small_center_style) -> Table:
    """
    데이터 행 테이블 생성.

    헤더:
      번호 | 시작월 | 종료월 | 금액(월지급액) | 공제대상자 | 사번 | 서명일시 |
      지급대상자 | 사번 | 서명일시 | 비고

    데이터:
      EfficiencyChange rows (최대 10건)
      G열(공제자 서명일시): role='deduct' 서명자의 signed_at
      J열(지급자 서명일시): role='pay' 서명자의 signed_at
    """
    from partner.models import EfficiencyConfirmSign

    # 서명자 signed_at 맵 구성: {signer_id: signed_at}
    deduct_signed_at: dict[str, str] = {}
    pay_signed_at:    dict[str, str] = {}

    for sign in sign_request.signs.all():
        if sign.signed_at:
            ts = sign.signed_at.strftime('%Y-%m-%d\n%H:%M')
        else:
            ts = ''
        if sign.role == EfficiencyConfirmSign.ROLE_DEDUCT:
            deduct_signed_at[sign.signer_id] = ts
        elif sign.role == EfficiencyConfirmSign.ROLE_PAY:
            pay_signed_at[sign.signer_id] = ts

    # 헤더 행 1 (병합용)
    header1 = [
        Paragraph('번호', small_center_style),
        Paragraph('시작월', small_center_style),
        Paragraph('종료월', small_center_style),
        Paragraph('금액\n(월지급액)', small_center_style),
        Paragraph('공제대상자', small_center_style),
        '',  # 사번 (병합)
        '',  # 서명일시 (병합)
        Paragraph('지급대상자', small_center_style),
        '',  # 사번 (병합)
        '',  # 서명일시 (병합)
        Paragraph('비고', small_center_style),
    ]
    # 헤더 행 2
    header2 = [
        '', '', '', '',
        Paragraph('성명', small_center_style),
        Paragraph('사번', small_center_style),
        Paragraph('서명일시', small_center_style),
        Paragraph('성명', small_center_style),
        Paragraph('사번', small_center_style),
        Paragraph('서명일시', small_center_style),
        '',
    ]

    rows_data = [header1, header2]

    # 데이터 행 (최대 10건)
    group = sign_request.confirm_group
    efficiency_rows = (
        list(group.efficiency_rows.all()[:10]) if group else []
    )

    for idx, row in enumerate(efficiency_rows, start=1):
        amount_str = f"{row.amount:,}" if row.amount is not None else ''
        ded_sign   = deduct_signed_at.get(row.ded_id, '')
        pay_sign   = pay_signed_at.get(row.pay_id, '')

        rows_data.append([
            Paragraph(str(idx), small_center_style),
            Paragraph(row.start_ym or '', small_center_style),
            Paragraph(row.end_ym or '', small_center_style),
            Paragraph(amount_str, small_center_style),
            Paragraph(row.ded_name or '', small_style),
            Paragraph(row.ded_id or '', small_center_style),
            Paragraph(ded_sign, small_center_style),
            Paragraph(row.pay_name or '', small_style),
            Paragraph(row.pay_id or '', small_center_style),
            Paragraph(pay_sign, small_center_style),
            Paragraph(row.content or '', small_style),
        ])

    # 빈 행 채우기 (10건 미만 시 빈 행으로 채움)
    for i in range(len(efficiency_rows), 10):
        rows_data.append([
            Paragraph(str(i + 1), small_center_style),
            '', '', '', '', '', '', '', '', '', '',
        ])

    # 컬럼 너비 (A4 width ≈ 180mm 사용 가능)
    col_widths = [
        10 * mm,  # 번호
        16 * mm,  # 시작월
        16 * mm,  # 종료월
        20 * mm,  # 금액
        18 * mm,  # 공제자 성명
        18 * mm,  # 공제자 사번
        22 * mm,  # 공제자 서명일시
        18 * mm,  # 지급자 성명
        18 * mm,  # 지급자 사번
        22 * mm,  # 지급자 서명일시
        0,        # 비고 (나머지)
    ]
    # 비고 = 전체 - 합계
    total_fixed = sum(w for w in col_widths if w)
    available   = 180 * mm
    col_widths[-1] = max(available - total_fixed, 10 * mm)

    table = Table(rows_data, colWidths=col_widths, repeatRows=2)
    table.setStyle(TableStyle([
        # 전체 테두리
        ('GRID',        (0, 0), (-1, -1), 0.5, colors.black),
        # 헤더 배경
        ('BACKGROUND',  (0, 0), (-1, 1),  colors.HexColor('#F2F2F2')),
        # 헤더 셀 병합: 공제대상자(4~6열 행1), 지급대상자(7~9열 행1)
        ('SPAN',        (4, 0), (6, 0)),   # 공제대상자
        ('SPAN',        (7, 0), (9, 0)),   # 지급대상자
        # 번호/시작월/종료월/금액/비고: 2행 병합
        ('SPAN',        (0, 0), (0, 1)),
        ('SPAN',        (1, 0), (1, 1)),
        ('SPAN',        (2, 0), (2, 1)),
        ('SPAN',        (3, 0), (3, 1)),
        ('SPAN',        (10, 0), (10, 1)),
        # 폰트
        ('FONTNAME',    (0, 0), (-1, -1), _BASE_FONT),
        ('FONTSIZE',    (0, 0), (-1, -1), 8),
        # 정렬
        ('VALIGN',      (0, 0), (-1, -1), 'MIDDLE'),
        ('ALIGN',       (0, 0), (-1, 1),  'CENTER'),
        # 행 높이 — 데이터 행
        ('ROWBACKGROUNDS', (0, 2), (-1, -1), [colors.white, colors.HexColor('#FAFAFA')]),
    ]))

    return table


def _build_head_confirm_section(sign_request, normal_style) -> Table:
    """
    확인자(최고관리자) 서명 정보 테이블 생성.

    출력 예:
      확인자 최고관리자 : 박지점장   서명일시: 2025-02-12 14:32   (인)
    """
    from partner.models import EfficiencyConfirmSign

    head_sign = None
    for sign in sign_request.signs.all():
        if sign.role == EfficiencyConfirmSign.ROLE_HEAD_CONFIRM:
            head_sign = sign
            break

    if head_sign:
        head_name = getattr(head_sign.signer, 'name', '-')
        if head_sign.signed_at:
            signed_str = head_sign.signed_at.strftime('%Y-%m-%d %H:%M')
        else:
            signed_str = '(미서명)'
    else:
        head_name  = '-'
        signed_str = '-'

    text = (
        f'확인자 최고관리자 : {head_name}'
        f'　　서명일시: {signed_str}　　(인)'
    )
    data = [[Paragraph(text, normal_style)]]
    table = Table(data, colWidths=[180 * mm])
    table.setStyle(TableStyle([
        ('BOX',      (0, 0), (-1, -1), 0.5, colors.black),
        ('FONTNAME', (0, 0), (-1, -1), _BASE_FONT),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('TOPPADDING',    (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
    ]))
    return table