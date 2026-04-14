# django_ma/board/templatetags/industry_tags.py

from django import template

register = template.Library()


@register.filter
def get_item(mapping, key):
    """
    딕셔너리에서 key로 값을 꺼내기 위한 템플릿 필터

    사용 예:
        pref_map|get_item:article.id
    """
    if not mapping:
        return None
    return mapping.get(key)