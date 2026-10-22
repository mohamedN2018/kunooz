from django import template

register = template.Library()


@register.simple_tag
def widthpct(value, top):
    """عرض شريط نسبةً لأكبر قيمة (رقم بنقطة عشرية دائماً، صالح داخل CSS)."""
    try:
        value, top = float(value), float(top)
    except (TypeError, ValueError):
        return '0'
    if top <= 0:
        return '0'
    return '%.1f' % max(2.0, min(100.0, value * 100 / top))
