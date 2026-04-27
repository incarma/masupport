# django_ma/join/views.py

import os
import tempfile
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponse, JsonResponse, FileResponse
from django.conf import settings
from django.db import connection
from .tasks import delete_file_task
from .models import JoinInfo, Manual
from .forms import JoinForm, ManualForm
from join.tasks import generate_pdf_task
from accounts.decorators import grade_required


@login_required
def db_test_view(request):
    return HttpResponse("DB 테스트 뷰입니다.")

# ✅ 기본 수수료 페이지 접속 시 → 채권관리 페이지로 자동 이동
@login_required
def redirect_to_manual(request):
    return redirect('join:manual_basic')

def manual_basic(request): return render(request, "manual/manual_basic.html")
def manual_head(request): return render(request, "manual/manual_head.html")
def rules_basic(request): return render(request, "manual/rules_basic.html")
def rules_head(request): return render(request, "manual/rules_head.html")

@login_required
def join_form(request):
    """
    사용자가 가입신청서를 제출하면, PDF 생성 작업을 Celery에 비동기로 위임합니다.
    메인 서버는 즉시 응답하여 서버 부하 없이 안정적인 처리를 보장합니다.
    """
    if request.method == 'POST':
        form = JoinForm(request.POST)
        if form.is_valid():
            # ✅ join_info 객체 생성 및 저장
            join_info = form.save(commit=False)

            join_info.user_id = request.user.id
            join_info.user_name = request.user.name
            join_info.user_branch = request.user.branch

            postcode = form.cleaned_data.get('postcode', '').strip()
            address = form.cleaned_data.get('address', '').strip()
            address_detail = form.cleaned_data.get('address_detail', '').strip()
            email = form.cleaned_data.get('email') or None

            join_info.postcode = postcode
            join_info.address = address
            join_info.address_detail = address_detail
            join_info.email = email
            
            join_info.save()

            # ✅ 전체 주소 조합
            combined_address = f"{address}, {address_detail}" if address_detail else address

            # ✅ PDF 템플릿 경로 설정
            pdf_template_path = os.path.join(settings.BASE_DIR, 'static', 'pdf', 'template.pdf')

            # ✅ PDF 데이터 구성
            data = {
                "name": join_info.name,
                "ssn": join_info.ssn,
                "address": combined_address,
                "phone": join_info.phone,
                "email": email or '',
                "postcode": postcode,
                "address_detail": address_detail,
            }

            # ✅ Celery에 비동기 작업 위임
            task = generate_pdf_task.delay(pdf_template_path, data)

            # ✅ 즉시 사용자에게 응답 (서버 부하 X)
            return render(request, 'join/pdf_processing.html', {
                'task_id': task.id,
                'join_info': join_info,
            })

        # 폼 검증 실패
        return render(request, 'join/join_form.html', {'form': form})

    # GET 요청 → 빈 폼 렌더링
    form = JoinForm()
    return render(request, 'join/join_form.html', {'form': form})


@login_required
def task_status(request, task_id):
    """
    Celery Task 상태를 조회하는 API (AJAX 요청용)
    """
    from celery.result import AsyncResult
    result = AsyncResult(task_id)

    if result.state == 'SUCCESS':
        pdf_path = result.get()  # fill_pdf가 반환한 경로
        if os.path.exists(pdf_path):
            return JsonResponse({'status': 'SUCCESS', 'pdf_ready': True})
        else:
            return JsonResponse({'status': 'SUCCESS', 'pdf_ready': False})
    elif result.state == 'PENDING':
        return JsonResponse({'status': 'PENDING'})
    elif result.state == 'FAILURE':
        return JsonResponse({'status': 'FAILURE'})
    else:
        return JsonResponse({'status': result.state})


@login_required
def download_pdf(request, task_id):
    """
    작업이 완료된 PDF 파일을 다운로드합니다.
    삭제는 Celery를 통해 일정 시간 후에 처리됩니다.
    """
    from celery.result import AsyncResult
    result = AsyncResult(task_id)
    pdf_path = result.get() if result.state == 'SUCCESS' else None

    if pdf_path and os.path.exists(pdf_path):
        # ✅ 파일 응답
        response = FileResponse(open(pdf_path, 'rb'), content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="가입신청서.pdf"'

        # ✅ 삭제 예약 (Celery 비동기 작업으로)
        delete_file_task.delay(pdf_path, delay=10)  # 10초 뒤 삭제

        return response

    return HttpResponse("PDF 파일을 찾을 수 없습니다.", status=404)


@login_required
def success_view(request):
    """PDF 생성 완료 또는 가입 성공 후 보여줄 안내 페이지"""
    return render(request, 'join/success.html')


def manual_list(request):
    qs = Manual.objects.all().order_by("-updated_at")
    is_admin = (
        request.user.is_authenticated
        and getattr(request.user, "grade", "") in ("superuser", "main_admin")
    )
    return render(request, "manual/manual_list.html", {"manuals": qs, "is_admin": is_admin})

def manual_detail(request, pk):
    manual = get_object_or_404(Manual, pk=pk)
    # 비관리자는 비공개 접근 차단
    if not manual.is_published:
        if not (request.user.is_authenticated and getattr(request.user, "grade", "") in ["superuser", "main_admin"]):
            return redirect("join:manual_list")
    return render(request, "manual/manual_detail.html", {"manual": manual})

@grade_required("superuser")
def manual_create(request):
    if request.method == "POST":
        form = ManualForm(request.POST, request.FILES)
        if form.is_valid():
            manual = form.save()
            return redirect("join:manual_detail", pk=manual.pk)
    else:
        form = ManualForm()
    return render(request, "manual/manual_form.html", {"form": form, "mode": "create"})

@grade_required("superuser")
def manual_edit(request, pk):
    manual = get_object_or_404(Manual, pk=pk)
    if request.method == "POST":
        form = ManualForm(request.POST, request.FILES, instance=manual)
        if form.is_valid():
            manual = form.save()
            return redirect("join:manual_detail", pk=manual.pk)
    else:
        form = ManualForm(instance=manual)
    return render(request, "manual/manual_form.html", {"form": form, "mode": "edit", "manual": manual})
