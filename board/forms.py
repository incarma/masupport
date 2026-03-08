# django_ma/board/forms.py

from django import forms
from django.core.exceptions import ValidationError

from .models import Post, Comment, Task, TaskComment
from .constants import POST_CATEGORY_CHOICES, TASK_CATEGORY_CHOICES


# =========================================================
# Base Form: category/title/content 공통 UI
# =========================================================
class _BaseCategoryTitleContentForm(forms.ModelForm):
    """
    서버단 입력 검증 보강
    - 공백-only 입력 차단
    - category 허용값 검증
    - title/content 최대 길이 방어
    Post/Task 공통 폼 패턴
    - category optional
    - category가 '선택'/'빈값'이면 ""로 정규화
    """

    category_choices = POST_CATEGORY_CHOICES

    class Meta:
        fields = ["category", "title", "content"]
        widgets = {
            "category": forms.Select(attrs={"class": "form-select"}),
            "title": forms.TextInput(attrs={"class": "form-control", "placeholder": "제목을 입력하세요"}),
            "content": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 6,
                    "placeholder": (
                        "요청 내용을 구체적으로 작성해주세요.\n\n"
                        "개별 계약 건별 요청인 경우\n"
                        "증권번호 및 보험사 전산화면 캡처본(촬영본)을 첨부해주시면\n"
                        "더 빠르고 정확하게 안내드릴 수 있습니다."
                    ),
                }
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        f = self.fields.get("category")
        if not f:
            return

        f.required = False
        choices = list(self.category_choices or [])
        f.choices = choices

        # widget이 Select가 아니거나 choices 누락되는 케이스 방어
        if not isinstance(f.widget, forms.Select):
            f.widget = forms.Select(attrs={"class": "form-select"})
        f.widget.choices = choices

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("category") in (None, "", "선택"):
            cleaned["category"] = ""
        return cleaned
    
    def clean_category(self):
        value = (self.cleaned_data.get("category") or "").strip()
        allowed_values = {str(v) for v, _ in (self.category_choices or []) if str(v).strip()}
        if value and value not in allowed_values:
            raise ValidationError("올바르지 않은 구분값입니다.")
        return value

    def clean_title(self):
        value = (self.cleaned_data.get("title") or "").strip()
        if not value:
            raise ValidationError("제목을 입력해주세요.")

        max_len = getattr(self._meta.model._meta.get_field("title"), "max_length", None)
        if max_len and len(value) > max_len:
            raise ValidationError(f"제목은 {max_len}자 이하로 입력해주세요.")
        return value

    def clean_content(self):
        value = (self.cleaned_data.get("content") or "").strip()
        if not value:
            raise ValidationError("내용을 입력해주세요.")

        model_field = self._meta.model._meta.get_field("content")
        max_len = getattr(model_field, "max_length", None)
        if max_len and len(value) > max_len:
            raise ValidationError(f"내용은 {max_len}자 이하로 입력해주세요.")
        return value


class PostForm(_BaseCategoryTitleContentForm):
    """
    ✅ 업무요청(Post): 기본 항목 유지
    """
    category_choices = POST_CATEGORY_CHOICES

    class Meta(_BaseCategoryTitleContentForm.Meta):
        model = Post


class TaskForm(_BaseCategoryTitleContentForm):
    """
    ✅ 직원업무(Task): Post 구분 + 추가 구분(민원/신규제휴)
    """
    category_choices = TASK_CATEGORY_CHOICES

    class Meta(_BaseCategoryTitleContentForm.Meta):
        model = Task


# =========================================================
# Comment Forms
# =========================================================
class _BaseCommentForm(forms.ModelForm):
    class Meta:
        fields = ["content"]
        widgets = {
            "content": forms.Textarea(
                attrs={
                    "rows": 1,
                    "placeholder": "댓글을 입력하세요...",
                    "class": "form-control-sm board-comment-input",
                }
            ),
        }

    def clean_content(self):
        value = (self.cleaned_data.get("content") or "").strip()
        if not value:
            raise ValidationError("댓글 내용을 입력해주세요.")

        model_field = self._meta.model._meta.get_field("content")
        max_len = getattr(model_field, "max_length", None)
        if max_len and len(value) > max_len:
            raise ValidationError(f"댓글은 {max_len}자 이하로 입력해주세요.")

        # TextField인 경우 과도한 입력 방어
        if not max_len and len(value) > 5000:
            raise ValidationError("댓글은 5000자 이하로 입력해주세요.")
        return value

    def clean(self):
        cleaned = super().clean()
        cleaned["content"] = (cleaned.get("content") or "").strip()
        return cleaned


class CommentForm(_BaseCommentForm):
    class Meta(_BaseCommentForm.Meta):
        model = Comment


class TaskCommentForm(_BaseCommentForm):
    class Meta(_BaseCommentForm.Meta):
        model = TaskComment
