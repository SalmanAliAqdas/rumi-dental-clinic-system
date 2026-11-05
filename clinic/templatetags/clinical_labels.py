from django import template
register = template.Library()

@register.filter
def clinical_label(value):
    return str(value).replace('_', ' ').title()
