from django.contrib.auth.decorators import login_required
from django.http import HttpResponseRedirect

from accounts.decorators import grade_required

_LLM_URL = "https://ai.ma-support.kr"


@login_required
@grade_required("superuser")
def llm_redirect(request):
    return HttpResponseRedirect(_LLM_URL)
