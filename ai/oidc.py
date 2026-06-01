# django_ma/ai/oidc.py
# Open WebUI OIDC 연동을 위한 커스텀 UserInfo 클래스

from django.http import JsonResponse
from oauth2_provider.views import UserInfoView


class CustomUserInfoView(UserInfoView):
    """
    CustomUser는 email 필드가 없으므로
    사번@incar.co.kr 형태로 email 클레임을 가공하여 반환한다.

    접근 정책:
    - superuser grade만 허용
    - is_active=False 계정 즉시 차단 (실시간 재검증)

    Open WebUI가 요구하는 최소 클레임:
    - sub: 사용자 고유 식별자 (사번)
    - name: 표시 이름
    - email: 이메일 (가공값 사번@incar.co.kr)
    - email_verified: True 고정

    토큰 검증은 부모 클래스(UserInfoView → ProtectedResourceView)의
    dispatch()가 담당하므로 여기서는 grade/is_active만 검증한다.
    """

    def get(self, request, *args, **kwargs):
        user = request.user

        if not hasattr(user, "grade") or user.grade != "superuser":
            return JsonResponse({"error": "access_denied"}, status=403)

        if not user.is_active:
            return JsonResponse({"error": "account_inactive"}, status=403)

        claims = {
            "sub": str(user.id),
            "name": user.name,
            "email": f"{user.id}@incar.co.kr",
            "email_verified": True,
        }
        return JsonResponse(claims)
