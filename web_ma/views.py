# django_ma/web_ma/views.py
import logging
from django.http import HttpResponseServerError
from django.views.decorators.csrf import requires_csrf_token

logger = logging.getLogger(__name__)

@requires_csrf_token
def handler500(request):
    # 현재 예외 컨텍스트를 강제로 로깅 (traceback 포함)
    logger.exception("Unhandled server error (500)")
    return HttpResponseServerError("Server Error (500)")