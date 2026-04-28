# partner/services/pdf_service.py
"""
지점효율 사실확인서 PDF 생성 서비스 (ReportLab 직접 구현)

설계 기준: django_ma_esign_final_design.md v2.0 §8
운영 전제:
  - Render 환경 — LibreOffice 미사용
  - reportlab==4.4.4 (requirements.txt 확인됨)
  - 한글 폰트: NotoSansKR (static/fonts/ 에 이미 존재)
    탐색 순서: NotoSansKR-Regular.ttf → NotoSansKR-Medium.ttf → NotoSansKR-Bold.ttf
  - 폰트 파일이 없으면 Helvetica 폴백 (운영 장애 방지)
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
from reportlab.lib.styles import ParagraphStyle
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
# 폰트 등록 (한글 지원 — NotoSansKR)
# ─────────────────────────────────────────────────────────────────────────────
_FONT_REGISTERED = False
_BASE_FONT       = 'Helvetica'       # 폴백
_BASE_FONT_BOLD  = 'Helvetica-Bold'  # 폴백

# 탐색 후보 — (등록명, 파일명, is_bold)
_NOTO_CANDIDATES = [
    ('NotoSansKR',     'NotoSansKR-Regular.ttf',  False),
    ('NotoSansKR',     'NotoSansKR-Medium.ttf',   False),  # Regular 없을 경우 대체
    ('NotoSansKRBold', 'NotoSansKR-Bold.ttf',     True),
    ('NotoSansKRBold', 'NotoSansKR-SemiBold.ttf', True),   # Bold 없을 경우 대체
]


def _try_register_korean_font() -> None:
    """
    NotoSansKR 폰트를 등록한다.
    파일이 없으면 경고 로그 후 Helvetica 폴백으로 계속 동작.
    등록 성공 시 _BASE_FONT / _BASE_FONT_BOLD를 교체.
    """
    global _FONT_REGISTERED, _BASE_FONT, _BASE_FONT_BOLD

    if _FONT_REGISTERED:
        return

    fonts_dir = _find_fonts_dir()

    if not fonts_dir:
        logger.warning(
            "pdf_service: static/fonts/ 디렉토리를 찾을 수 없습니다 → Helvetica 폴백. "
            "한글이 깨질 수 있습니다."
        )
        _FONT_REGISTERED = True
        return

    # Regular 등록
    regular_registered = False
    for name, filename, is_bold in _NOTO_CANDIDATES:
        if is_bold:
            continue
        path = os.path.join(fonts_dir, filename)
        if os.path.isfile(path):
            try:
                pdfmetrics.registerFont(TTFont(name, path))
                _BASE_FONT = name
                regular_registered = True
                logger.info("pdf_service: 폰트 등록 완료 → %s (%s)", name, path)
                break
            except Exception as e:
                logger.warning("pdf_service: 폰트 등록 실패 (%s): %s", filename, e)

    if not regular_registered:
        logger.warning(
            "pdf_service: NotoSansKR Regular 폰트 파일을 찾을 수 없습니다 → Helvetica 폴백. "
            "static/fonts/NotoSansKR-Regular.ttf 또는 NotoSansKR-Medium.ttf 를 확인하세요."
        )
        _FONT_REGISTERED = True
        return

    # Bold 등록
    bold_registered = False
    for name, filename, is_bold in _NOTO_CANDIDATES:
        if not is_bold:
            continue
        path = os.path.join(fonts_dir, filename)
        if os.path.isfile(path):
            try:
                pdfmetrics.registerFont(TTFont(name, path))
                _BASE_FONT_BOLD = name
                bold_registered = True
                logger.info("pdf_service: Bold 폰트 등록 완료 → %s (%s)", name, path)
                break
            except Exception as e:
                logger.warning("pdf_service: Bold 폰트 등록 실패 (%s): %s", filename, e)

    if not bold_registered:
        # Bold 없으면 Regular를 Bold로도 사용
        try:
            pdfmetrics.registerFont(TTFont('NotoSansKRBold', os.path.join(fonts_dir, _get_registered_regular_filename(fonts_dir))))
            _BASE_FONT_BOLD = 'NotoSansKRBold'
        except Exception:
            _BASE_FONT_BOLD = _BASE_FONT  # Regular로 대체
        logger.info("pdf_service: Bold 폰트 없음 → Regular(%s)로 대체", _BASE_FONT)

    _FONT_REGISTERED = True


def _find_fonts_dir() -> str | None:
    """static/fonts/ 디렉토리 절대경로 반환. 없으면 None."""
    try:
        from django.conf import settings
        base = str(settings.BASE_DIR)
        candidates = [
            os.path.join(base, 'static', 'fonts'),
            os.path.join(base, 'staticfiles', 'fonts'),
        ]
        for p in candidates:
            if os.path.isdir(p):
                return p
    except Exception:
        pass
    return None


def _get_registered_regular_filename(fonts_dir: str) -> str:
    """등록된 Regular 파일명 반환 (Bold fallback용)."""
    for _, filename, is_bold in _NOTO_CANDIDATES:
        if not is_bold and os.path.isfile(os.path.join(fonts_dir, filename)):
            return filename
    return 'NotoSansKR-Regular.ttf'


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
        'date',
        fontName=_BASE_FONT,
        fontSize=10,
        leading=14,
        alignment=1,
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
    group  = getattr(sign_request, 'confirm_group', None)
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

    헤더: 번호|시작월|종료월|금액|공제대상자(성명/사번/서명일시)|지급대상자(성명/사번/서명일시)|비고
    데이터: EfficiencyChange rows (최대 10건)
    """
    from partner.models import EfficiencyConfirmSign

    # 서명자 signed_at 맵 구성: {signer_id: signed_at_str}
    deduct_signed_at: dict[str, str] = {}
    pay_signed_at:    dict[str, str] = {}

    for sign in sign_request.signs.all():
        ts = sign.signed_at.strftime('%Y-%m-%d\n%H:%M') if sign.signed_at else ''
        if sign.role == EfficiencyConfirmSign.ROLE_DEDUCT:
            deduct_signed_at[sign.signer_id] = ts
        elif sign.role == EfficiencyConfirmSign.ROLE_PAY:
            pay_signed_at[sign.signer_id] = ts

    # 헤더 행 1 (병합 기준)
    header1 = [
        Paragraph('번호',           small_center_style),
        Paragraph('시작월',         small_center_style),
        Paragraph('종료월',         small_center_style),
        Paragraph('금액\n(월지급액)', small_center_style),
        Paragraph('공제대상자',      small_center_style),
        '', '',  # 사번, 서명일시 (병합)
        Paragraph('지급대상자',      small_center_style),
        '', '',  # 사번, 서명일시 (병합)
        Paragraph('비고',           small_center_style),
    ]
    # 헤더 행 2
    header2 = [
        '', '', '', '',
        Paragraph('성명',   small_center_style),
        Paragraph('사번',   small_center_style),
        Paragraph('서명일시', small_center_style),
        Paragraph('성명',   small_center_style),
        Paragraph('사번',   small_center_style),
        Paragraph('서명일시', small_center_style),
        '',
    ]

    rows_data = [header1, header2]

    # 데이터 행 (최대 10건)
    group = sign_request.confirm_group
    efficiency_rows = list(group.efficiency_rows.all()[:10]) if group else []

    for idx, row in enumerate(efficiency_rows, start=1):
        amount_str = f"{row.amount:,}" if row.amount is not None else ''
        ded_sign   = deduct_signed_at.get(row.ded_id, '')
        pay_sign   = pay_signed_at.get(row.pay_id, '')

        rows_data.append([
            Paragraph(str(idx),         small_center_style),
            Paragraph(row.start_ym or '', small_center_style),
            Paragraph(row.end_ym or '',   small_center_style),
            Paragraph(amount_str,         small_center_style),
            Paragraph(row.ded_name or '', small_style),
            Paragraph(row.ded_id or '',   small_center_style),
            Paragraph(ded_sign,           small_center_style),
            Paragraph(row.pay_name or '', small_style),
            Paragraph(row.pay_id or '',   small_center_style),
            Paragraph(pay_sign,           small_center_style),
            Paragraph(row.content or '',  small_style),
        ])

    # 빈 행 채우기 (10건 미만)
    for i in range(len(efficiency_rows), 10):
        rows_data.append([
            Paragraph(str(i + 1), small_center_style),
            '', '', '', '', '', '', '', '', '', '',
        ])

    # 컬럼 너비 (A4 사용 가능 폭 ≈ 180mm)
    col_widths = [
        10 * mm,   # 번호
        16 * mm,   # 시작월
        16 * mm,   # 종료월
        20 * mm,   # 금액
        18 * mm,   # 공제자 성명
        18 * mm,   # 공제자 사번
        22 * mm,   # 공제자 서명일시
        18 * mm,   # 지급자 성명
        18 * mm,   # 지급자 사번
        22 * mm,   # 지급자 서명일시
        0,         # 비고 (나머지)
    ]
    total_fixed     = sum(w for w in col_widths if w)
    col_widths[-1]  = max(180 * mm - total_fixed, 10 * mm)

    table = Table(rows_data, colWidths=col_widths, repeatRows=2)
    table.setStyle(TableStyle([
        # 전체 테두리
        ('GRID',            (0, 0), (-1, -1), 0.5, colors.black),
        # 헤더 배경
        ('BACKGROUND',      (0, 0), (-1, 1),  colors.HexColor('#F2F2F2')),
        # 헤더 셀 병합: 공제대상자(4~6열 행0), 지급대상자(7~9열 행0)
        ('SPAN',            (4, 0), (6, 0)),
        ('SPAN',            (7, 0), (9, 0)),
        # 번호/시작월/종료월/금액/비고: 2행 병합
        ('SPAN',            (0, 0), (0, 1)),
        ('SPAN',            (1, 0), (1, 1)),
        ('SPAN',            (2, 0), (2, 1)),
        ('SPAN',            (3, 0), (3, 1)),
        ('SPAN',            (10, 0), (10, 1)),
        # 폰트
        ('FONTNAME',        (0, 0), (-1, -1), _BASE_FONT),
        ('FONTSIZE',        (0, 0), (-1, -1), 8),
        # 정렬
        ('VALIGN',          (0, 0), (-1, -1), 'MIDDLE'),
        ('ALIGN',           (0, 0), (-1, 1),  'CENTER'),
        # 짝수/홀수 행 배경
        ('ROWBACKGROUNDS',  (0, 2), (-1, -1),
         [colors.white, colors.HexColor('#FAFAFA')]),
    ]))

    return table


def _build_head_confirm_section(sign_request, normal_style) -> Table:
    """
    확인자(최고관리자) 서명 정보 테이블 생성.
    - 이름: Bold 처리 (인라인 <b> 태그)
    - '(인)' 문구 제거
    """
    from partner.models import EfficiencyConfirmSign

    head_sign = None
    for sign in sign_request.signs.all():
        if sign.role == EfficiencyConfirmSign.ROLE_HEAD_CONFIRM:
            head_sign = sign
            break

    if head_sign:
        head_name  = getattr(head_sign.signer, 'name', '-')
        signed_str = (
            head_sign.signed_at.strftime('%Y-%m-%d %H:%M')
            if head_sign.signed_at else '(미서명)'
        )
    else:
        head_name  = '-'
        signed_str = '-'

    # 이름 Bold — ReportLab Paragraph 인라인 태그 사용
    # fontName을 Bold체로 지정해야 <b> 태그가 실제로 굵게 렌더됨
    text = (
        f'확인자 최고관리자 : '
        f'<font name="{_BASE_FONT_BOLD}"><b>{head_name}</b></font>'
        f'　　서명일시: {signed_str}'
    )

    # Paragraph에 XML 파싱 허용 (allowMarkup=True 대신 ParagraphStyle에 적용)
    head_style = ParagraphStyle(
        'head_confirm',
        fontName=_BASE_FONT,
        fontSize=9,
        leading=14,
    )

    data  = [[Paragraph(text, head_style)]]
    table = Table(data, colWidths=[180 * mm])
    table.setStyle(TableStyle([
        ('BOX',           (0, 0), (-1, -1), 0.5, colors.black),
        ('FONTNAME',      (0, 0), (-1, -1), _BASE_FONT),
        ('FONTSIZE',      (0, 0), (-1, -1), 9),
        ('TOPPADDING',    (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
    ]))
    return table