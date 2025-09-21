from django import template

register = template.Library()

@register.filter
def sum_weight(queryset):
    """Calculate total weight from Content queryset"""
    if not queryset:
        return 0
    total = 0
    for obj in queryset:
        if hasattr(obj, 'box_weight') and hasattr(obj, 'count_of_box'):
            total += (obj.box_weight or 0) * (obj.count_of_box or 0)
    return total

@register.filter
def sum_volume(queryset):
    """Calculate total volume from Content queryset"""
    if not queryset:
        return 0
    total = 0
    for obj in queryset:
        if hasattr(obj, 'total_volumetric') and hasattr(obj, 'count_of_box'):
            total += (obj.total_volumetric or 0) * (obj.count_of_box or 0)
    return total
