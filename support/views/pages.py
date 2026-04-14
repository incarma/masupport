# django_ma/support/views/pages.py

from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect


@login_required
def industry_info(request):
    """
    support 업계정보 레거시 진입점

    2단계 이관 정책:
    - 업계정보의 공식 진입점은 board:industry_info 로 전환
    - 기존 /support/ 링크/북마크/외부 참조가 끊기지 않도록 redirect 유지
    - topic 파라미터가 있으면 그대로 board로 전달
    """

    topic = (request.GET.get("topic") or "").strip()

    if topic:
        return redirect(f"/board/industry-info/?topic={topic}")
    return redirect("board:industry_info")