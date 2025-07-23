"""
Template tags and filters for auditlog.
"""
from django import template

from auditlog.render import render_changes

register = template.Library()


@register.filter
def format_changes(log_entry):
    """
    Format LogEntry changes as HTML.
    
    Usage in template:
    {{ entry|format_changes|safe }}
    """
    return render_changes(log_entry) 