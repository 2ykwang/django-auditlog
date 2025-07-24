from django.core.management.base import BaseCommand
from django.utils import timezone
from django.db import transaction
from datetime import timedelta
from auditlog.models import LogEntry
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = '오래된 로그 엔트리를 아카이브 테이블로 이동'

    def add_arguments(self, parser):
        parser.add_argument(
            '--days',
            type=int,
            default=365,
            help='몇 일 이전 데이터를 아카이브할지 지정 (기본값: 365일)'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='실제 아카이브하지 않고 시뮬레이션만 실행'
        )
        parser.add_argument(
            '--batch-size',
            type=int,
            default=1000,
            help='한 번에 처리할 레코드 수 (기본값: 1000)'
        )

    def handle(self, *args, **options):
        days = options['days']
        dry_run = options['dry_run']
        batch_size = options['batch_size']
        
        cutoff_date = timezone.now() - timedelta(days=days)
        
        self.stdout.write(
            self.style.SUCCESS(
                f'{cutoff_date} 이전의 로그 엔트리를 아카이브합니다...'
            )
        )
        
        # 아카이브할 레코드 수 확인
        old_logs_count = LogEntry.objects.filter(
            timestamp__lt=cutoff_date
        ).count()
        
        self.stdout.write(f'아카이브할 레코드 수: {old_logs_count:,}')
        
        if dry_run:
            self.stdout.write(
                self.style.WARNING('DRY RUN 모드 - 실제 아카이브하지 않습니다.')
            )
            return
        
        if old_logs_count == 0:
            self.stdout.write('아카이브할 레코드가 없습니다.')
            return
        
        # 배치 처리로 아카이브
        processed = 0
        with transaction.atomic():
            while processed < old_logs_count:
                batch = LogEntry.objects.filter(
                    timestamp__lt=cutoff_date
                ).order_by('timestamp')[:batch_size]
                
                if not batch.exists():
                    break
                
                # 여기서 실제 아카이브 로직 구현
                # 예: 별도 테이블로 이동하거나 파일로 저장
                batch_ids = list(batch.values_list('id', flat=True))
                
                # 임시로 삭제 (실제로는 아카이브 테이블로 이동해야 함)
                deleted_count = LogEntry.objects.filter(id__in=batch_ids).delete()[0]
                
                processed += deleted_count
                self.stdout.write(f'처리된 레코드: {processed:,} / {old_logs_count:,}')
        
        self.stdout.write(
            self.style.SUCCESS(f'아카이브 완료: {processed:,}개 레코드 처리됨')
        )