from django.core.management.base import BaseCommand
from django.db import connection
from django.utils import timezone
from datetime import timedelta
from auditlog.models import LogEntry
import time
from django.db import models


class Command(BaseCommand):
    help = 'Auditlog 성능 분석 및 최적화 권장사항 제공'

    def add_arguments(self, parser):
        parser.add_argument(
            '--detailed',
            action='store_true',
            help='상세한 성능 분석 실행'
        )

    def handle(self, *args, **options):
        detailed = options['detailed']
        
        self.stdout.write(
            self.style.SUCCESS('=== Auditlog 성능 분석 ===')
        )
        
        # 기본 통계
        self.analyze_basic_stats()
        
        # 인덱스 사용 현황
        self.analyze_index_usage()
        
        # 쿼리 성능 테스트
        self.test_query_performance()
        
        if detailed:
            self.analyze_detailed_stats()
    
    def analyze_basic_stats(self):
        """기본 통계 분석"""
        self.stdout.write('\n--- 기본 통계 ---')
        
        # 전체 레코드 수
        start_time = time.time()
        total_count = LogEntry.objects.count()
        count_time = time.time() - start_time
        
        self.stdout.write(f'전체 레코드 수: {total_count:,}')
        self.stdout.write(f'카운트 쿼리 시간: {count_time:.3f}초')
        
        # 최근 데이터 분포
        now = timezone.now()
        recent_1d = LogEntry.objects.filter(
            timestamp__gte=now - timedelta(days=1)
        ).count()
        recent_7d = LogEntry.objects.filter(
            timestamp__gte=now - timedelta(days=7)
        ).count()
        recent_30d = LogEntry.objects.filter(
            timestamp__gte=now - timedelta(days=30)
        ).count()
        
        self.stdout.write(f'최근 1일: {recent_1d:,} 레코드')
        self.stdout.write(f'최근 7일: {recent_7d:,} 레코드')
        self.stdout.write(f'최근 30일: {recent_30d:,} 레코드')
        
        # Action별 분포
        action_stats = LogEntry.objects.values('action').annotate(
            count=models.Count('id')
        ).order_by('action')
        
        self.stdout.write('\nAction별 분포:')
        for stat in action_stats:
            action_name = dict(LogEntry.Action.choices)[stat['action']]
            self.stdout.write(f'  {action_name}: {stat["count"]:,}')
    
    def analyze_index_usage(self):
        """인덱스 사용 현황 분석"""
        self.stdout.write('\n--- 인덱스 분석 ---')
        
        # PostgreSQL의 경우 인덱스 사용 통계 확인
        if connection.vendor == 'postgresql':
            with connection.cursor() as cursor:
                cursor.execute("""
                    SELECT schemaname, tablename, indexname, idx_scan, idx_tup_read, idx_tup_fetch
                    FROM pg_stat_user_indexes 
                    WHERE tablename = 'auditlog_logentry'
                    ORDER BY idx_scan DESC
                """)
                
                indexes = cursor.fetchall()
                if indexes:
                    self.stdout.write('인덱스 사용 통계:')
                    for idx in indexes:
                        self.stdout.write(
                            f'  {idx[2]}: 스캔 {idx[3]:,}회, 읽기 {idx[4]:,}회'
                        )
                else:
                    self.stdout.write('인덱스 사용 통계를 찾을 수 없습니다.')
        
        # 테이블 크기 확인
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT pg_size_pretty(pg_total_relation_size('auditlog_logentry'))
            """)
            table_size = cursor.fetchone()[0]
            self.stdout.write(f'테이블 크기: {table_size}')
    
    def test_query_performance(self):
        """쿼리 성능 테스트"""
        self.stdout.write('\n--- 쿼리 성능 테스트 ---')
        
        # 최근 데이터 조회 성능
        start_time = time.time()
        recent_logs = LogEntry.objects.filter(
            timestamp__gte=timezone.now() - timedelta(days=7)
        ).order_by('-timestamp')[:100]
        list(recent_logs)  # 실제 쿼리 실행
        recent_time = time.time() - start_time
        
        self.stdout.write(f'최근 7일 데이터 100개 조회: {recent_time:.3f}초')
        
        # 특정 사용자의 로그 조회 성능
        if LogEntry.objects.filter(actor__isnull=False).exists():
            start_time = time.time()
            user_logs = LogEntry.objects.filter(
                actor__isnull=False
            ).order_by('-timestamp')[:100]
            list(user_logs)
            user_time = time.time() - start_time
            
            self.stdout.write(f'사용자별 로그 100개 조회: {user_time:.3f}초')
        
        # 검색 성능 테스트
        start_time = time.time()
        search_logs = LogEntry.objects.filter(
            object_repr__icontains='test'
        ).order_by('-timestamp')[:100]
        list(search_logs)
        search_time = time.time() - start_time
        
        self.stdout.write(f'검색 쿼리 100개 조회: {search_time:.3f}초')
    
    def analyze_detailed_stats(self):
        """상세 통계 분석"""
        self.stdout.write('\n--- 상세 통계 ---')
        
        # 월별 데이터 분포
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT DATE_TRUNC('month', timestamp) as month, COUNT(*)
                FROM auditlog_logentry
                GROUP BY month
                ORDER BY month DESC
                LIMIT 12
            """)
            
            monthly_stats = cursor.fetchall()
            self.stdout.write('월별 데이터 분포 (최근 12개월):')
            for month, count in monthly_stats:
                self.stdout.write(f'  {month.strftime("%Y-%m")}: {count:,}')
        
        # JSON 필드 크기 분석
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT 
                    AVG(LENGTH(changes::text)) as avg_changes_size,
                    AVG(LENGTH(serialized_data::text)) as avg_serialized_size
                FROM auditlog_logentry
                WHERE changes IS NOT NULL OR serialized_data IS NOT NULL
            """)
            
            size_stats = cursor.fetchone()
            if size_stats[0]:
                self.stdout.write(f'평균 changes 필드 크기: {size_stats[0]:.0f} 문자')
            if size_stats[1]:
                self.stdout.write(f'평균 serialized_data 크기: {size_stats[1]:.0f} 문자')
    
    def provide_recommendations(self):
        """성능 최적화 권장사항 제공"""
        self.stdout.write('\n--- 최적화 권장사항 ---')
        
        recommendations = [
            "1. 오래된 데이터 아카이빙: 1년 이상 된 데이터는 별도 테이블로 이동",
            "2. 인덱스 최적화: 복합 인덱스 추가 (timestamp + action, timestamp + content_type)",
            "3. 페이지네이션 최적화: 커서 기반 페이지네이션 사용",
            "4. 데이터 파티셔닝: 월별 또는 연도별 테이블 파티셔닝",
            "5. 캐싱 도입: Redis를 사용한 쿼리 결과 캐싱",
            "6. 검색 최적화: Elasticsearch 또는 PostgreSQL Full-text search 사용",
            "7. Admin 인터페이스 최적화: 기본적으로 최근 데이터만 표시",
            "8. 배치 처리: 대량 데이터 처리를 위한 배치 작업 구현"
        ]
        
        for rec in recommendations:
            self.stdout.write(rec)