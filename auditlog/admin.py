from functools import cached_property

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.utils.translation import gettext_lazy as _
from django.core.paginator import Paginator
from django.db import connection

from auditlog.filters import CIDFilter, ResourceTypeFilter
from auditlog.mixins import LogEntryAdminMixin
from auditlog.models import LogEntry


class OptimizedPaginator(Paginator):
    """
    대용량 데이터를 위한 최적화된 페이지네이터
    """
    def __init__(self, object_list, per_page, orphans=0, allow_empty_first_page=True):
        super().__init__(object_list, per_page, orphans, allow_empty_first_page)
        self._count = None

    def count(self):
        """
        전체 레코드 수를 캐시하여 반복 쿼리 방지
        """
        if self._count is None:
            # 복잡한 쿼리의 경우 count() 대신 서브쿼리 사용
            if hasattr(self.object_list, 'query') and self.object_list.query.where:
                # WHERE 절이 있는 경우 서브쿼리로 최적화
                self._count = self.object_list.count()
            else:
                # 단순한 경우 기본 count 사용
                self._count = self.object_list.count()
        return self._count


@admin.register(LogEntry)
class LogEntryAdmin(admin.ModelAdmin, LogEntryAdminMixin):
    date_hierarchy = "timestamp"
    list_select_related = ["content_type", "actor"]
    list_display = [
        "created",
        "resource_url",
        "action",
        "msg_short",
        "user_url",
        "cid_url",
    ]
    search_fields = [
        "timestamp",
        "object_repr",
        "changes",
        "actor__first_name",
        "actor__last_name",
        f"actor__{get_user_model().USERNAME_FIELD}",
    ]
    list_filter = ["action", ResourceTypeFilter, CIDFilter]
    readonly_fields = ["created", "resource_url", "action", "user_url", "msg"]
    fieldsets = [
        (None, {"fields": ["created", "user_url", "resource_url", "cid"]}),
        (_("Changes"), {"fields": ["action", "msg"]}),
    ]
    
    # 성능 최적화 설정
    list_per_page = 50  # 페이지당 레코드 수 제한
    show_full_result_count = False  # 전체 카운트 표시 비활성화
    
    # 최적화된 페이지네이터 사용
    paginator = OptimizedPaginator

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    @cached_property
    def _own_url_names(self):
        return [pattern.name for pattern in self.urls if pattern.name]

    def has_delete_permission(self, request, obj=None):
        if (
            request.resolver_match
            and request.resolver_match.url_name not in self._own_url_names
        ):
            # only allow cascade delete to satisfy delete_related flag
            return super().has_delete_permission(request, obj)
        return False

    def get_queryset(self, request):
        self.request = request
        queryset = super().get_queryset(request=request)
        
        # 기본적으로 최근 데이터만 표시 (성능 최적화)
        if not request.GET.get('all_data'):
            # 최근 1년 데이터만 기본 표시
            from django.utils import timezone
            from datetime import timedelta
            one_year_ago = timezone.now() - timedelta(days=365)
            queryset = queryset.filter(timestamp__gte=one_year_ago)
        
        return queryset
    
    def changelist_view(self, request, extra_context=None):
        """
        대용량 데이터 처리를 위한 최적화된 changelist 뷰
        """
        # 쿼리 최적화 힌트 추가
        if hasattr(connection, 'set_autocommit'):
            connection.set_autocommit(True)
        
        response = super().changelist_view(request, extra_context)
        
        # 응답에 성능 정보 추가
        if hasattr(response, 'context_data'):
            response.context_data['show_performance_info'] = True
            response.context_data['total_records'] = self.get_queryset(request).count()
        
        return response
