from django import urls as urlresolvers
from django.conf import settings
from django.contrib import admin
from django.core.exceptions import FieldDoesNotExist
from django.forms.utils import pretty_name
from django.http import HttpRequest
from django.urls.exceptions import NoReverseMatch
from django.utils.html import format_html, format_html_join
from django.utils.safestring import mark_safe
from django.utils.timezone import is_aware, localtime
from django.utils.translation import gettext_lazy as _

from auditlog.models import LogEntry
from auditlog.registry import auditlog
from auditlog.signals import accessed

MAX = 75


class LogEntryAdminMixin:
    request: HttpRequest
    CID_TITLE = _("Click to filter by records with this correlation id")

    @admin.display(description=_("Created"))
    def created(self, obj):
        if is_aware(obj.timestamp):
            return localtime(obj.timestamp)
        return obj.timestamp

    @admin.display(description=_("User"))
    def user_url(self, obj):
        if obj.actor:
            app_label, model = settings.AUTH_USER_MODEL.split(".")
            viewname = f"admin:{app_label}_{model.lower()}_change"
            try:
                link = urlresolvers.reverse(viewname, args=[obj.actor.pk])
            except NoReverseMatch:
                return "%s" % (obj.actor)
            return format_html('<a href="{}">{}</a>', link, obj.actor)

        return "system"

    @admin.display(description=_("Resource"))
    def resource_url(self, obj):
        app_label, model = obj.content_type.app_label, obj.content_type.model
        viewname = f"admin:{app_label}_{model}_change"
        try:
            args = [obj.object_pk] if obj.object_id is None else [obj.object_id]
            link = urlresolvers.reverse(viewname, args=args)
        except NoReverseMatch:
            return obj.object_repr
        else:
            return format_html(
                '<a href="{}">{} - {}</a>', link, obj.content_type, obj.object_repr
            )

    @admin.display(description=_("Changes"))
    def msg_short(self, obj):
        if obj.action in [LogEntry.Action.DELETE, LogEntry.Action.ACCESS]:
            return ""  # delete
        changes = obj.changes_dict
        s = "" if len(changes) == 1 else "s"
        fields = ", ".join(changes.keys())
        if len(fields) > MAX:
            i = fields.rfind(" ", 0, MAX)
            fields = fields[:i] + " .."
        return "%d change%s: %s" % (len(changes), s, fields)

    @admin.display(description=_("Changes"))
    def msg(self, obj):
        from auditlog.render import render_changes
        return render_changes(obj)

    @admin.display(description="Correlation ID")
    def cid_url(self, obj):
        cid = obj.cid
        if cid:
            url = self._add_query_parameter("cid", cid)
            return format_html(
                '<a href="{}" title="{}">{}</a>', url, self.CID_TITLE, cid
            )

    def _add_query_parameter(self, key: str, value: str):
        full_path = self.request.get_full_path()
        delimiter = "&" if "?" in full_path else "?"

        return f"{full_path}{delimiter}{key}={value}"


class LogAccessMixin:
    def render_to_response(self, context, **response_kwargs):
        obj = self.get_object()
        accessed.send(obj.__class__, instance=obj)
        return super().render_to_response(context, **response_kwargs)


class AuditlogHistoryAdminMixin:
    """Add an audit log history view to a model admin.

    Set :pyattr:`show_auditlog_link` to ``True`` to automatically include a link
    in ``list_display`` that leads to the object's audit log. The default
    template shows each log entry chronologically with a table of field changes.
    Override :pyattr:`auditlog_history_template` to customize the page.
    """

    auditlog_history_template = "auditlog/object_history.html"
    show_auditlog_link = False

    def get_list_display(self, request):
        list_display = list(super().get_list_display(request))
        if self.show_auditlog_link and "auditlog_link" not in list_display:
            list_display.append("auditlog_link")
        return list_display

    def get_urls(self):
        from django.urls import path

        opts = self.model._meta
        info = opts.app_label, opts.model_name
        my_urls = [
            path(
                "<path:object_id>/auditlog/",
                self.admin_site.admin_view(self.auditlog_history_view),
                name="%s_%s_auditlog" % info,
            )
        ]
        return my_urls + super().get_urls()

    def auditlog_history_view(self, request, object_id, extra_context=None):
        from urllib.parse import unquote

        from django.contrib.admin.views.main import PAGE_VAR
        from django.core.exceptions import PermissionDenied
        from django.template.response import TemplateResponse
        from django.utils.text import capfirst
        from django.utils.translation import gettext as _

        obj = self.get_object(request, unquote(object_id))
        if not self.has_view_permission(request, obj):
            raise PermissionDenied

        log_entries = (
            LogEntry.objects.get_for_object(obj)
            .select_related("actor")
            .order_by("-timestamp")
        )

        paginator = self.get_paginator(request, log_entries, 5)
        page_number = request.GET.get(PAGE_VAR, 1)
        page_obj = paginator.get_page(page_number)
        page_range = paginator.get_elided_page_range(page_obj.number)

        context = {
            **self.admin_site.each_context(request),
            "title": _("Audit log: %s") % obj,
            "module_name": str(capfirst(self.model._meta.verbose_name_plural)),
            "page_range": page_range,
            "page_var": PAGE_VAR,
            "pagination_required": paginator.count > 5,
            "object": obj,
            "opts": self.model._meta,
            "log_entries": page_obj,
            **(extra_context or {}),
        }

        request.current_app = self.admin_site.name
        return TemplateResponse(request, self.auditlog_history_template, context)

    @admin.display(description=_("Audit log"))
    def auditlog_link(self, obj):
        from django.urls import reverse

        opts = self.model._meta
        url = reverse(
            f"admin:{opts.app_label}_{opts.model_name}_auditlog",
            args=[obj.pk],
        )
        return format_html('<a href="{}">{}</a>', url, _("View"))
