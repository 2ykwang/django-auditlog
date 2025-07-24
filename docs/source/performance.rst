Performance Optimization
=======================

대용량 데이터 환경에서 Auditlog의 성능을 최적화하는 방법을 설명합니다.

개요
-----

Auditlog는 기본적으로 모든 모델의 변경사항을 로깅하므로, 시간이 지남에 따라 LogEntry 테이블이 매우 커질 수 있습니다. 
1억개 이상의 레코드가 있는 환경에서는 기본 설정으로는 성능이 크게 저하될 수 있습니다.

성능 문제의 주요 원인
---------------------

1. **페이징 성능**: `ORDER BY timestamp DESC`는 대용량 데이터에서 매우 느림
2. **관련 객체 로딩**: `content_type`, `actor` 등 관련 객체의 반복 로딩
3. **JSON 필드 파싱**: `changes`, `serialized_data` 필드의 파싱 오버헤드
4. **검색 성능**: JSON 필드나 텍스트 필드의 비효율적인 검색

최적화 방법
-----------

데이터베이스 인덱스 최적화
~~~~~~~~~~~~~~~~~~~~~~~~~~

가장 중요한 최적화는 적절한 인덱스를 추가하는 것입니다:

.. code-block:: sql

    -- 복합 인덱스: timestamp + action (가장 일반적인 쿼리 패턴)
    CREATE INDEX CONCURRENTLY auditlog_logentry_timestamp_action_idx 
    ON auditlog_logentry (timestamp DESC, action);
    
    -- 복합 인덱스: timestamp + content_type (특정 모델의 로그 조회)
    CREATE INDEX CONCURRENTLY auditlog_logentry_timestamp_content_type_idx 
    ON auditlog_logentry (timestamp DESC, content_type_id);
    
    -- 복합 인덱스: timestamp + actor (특정 사용자의 로그 조회)
    CREATE INDEX CONCURRENTLY auditlog_logentry_timestamp_actor_idx 
    ON auditlog_logentry (timestamp DESC, actor_id);
    
    -- 부분 인덱스: 최근 데이터만 인덱싱 (예: 최근 1년)
    CREATE INDEX CONCURRENTLY auditlog_logentry_recent_idx 
    ON auditlog_logentry (timestamp DESC) 
    WHERE timestamp > NOW() - INTERVAL '1 year';

Admin 인터페이스 최적화
~~~~~~~~~~~~~~~~~~~~~~

Admin 인터페이스에서 성능을 개선하는 설정:

.. code-block:: python

    # settings.py
    AUDITLOG_ADMIN_LIST_PER_PAGE = 50  # 페이지당 레코드 수 제한
    AUDITLOG_DEFAULT_DATE_RANGE_DAYS = 365  # 기본적으로 최근 1년 데이터만 표시
    AUDITLOG_ENABLE_CACHING = True  # 캐싱 활성화
    AUDITLOG_CACHE_TIMEOUT = 300  # 캐시 타임아웃 (초)

데이터 아카이빙
~~~~~~~~~~~~~~

오래된 데이터를 별도 테이블로 이동하여 메인 테이블의 크기를 줄입니다:

.. code-block:: bash

    # 오래된 로그 아카이브 (1년 이상)
    python manage.py archive_old_logs --days 365 --batch-size 1000

정기적인 아카이빙을 위해 cron job 설정:

.. code-block:: bash

    # crontab -e
    0 2 * * 0 /path/to/venv/bin/python /path/to/manage.py archive_old_logs --days 365

성능 모니터링
~~~~~~~~~~~~

정기적으로 성능을 분석하고 최적화가 필요한 부분을 확인:

.. code-block:: bash

    # 기본 성능 분석
    python manage.py analyze_performance
    
    # 상세 성능 분석
    python manage.py analyze_performance --detailed

데이터 파티셔닝
~~~~~~~~~~~~~~

매우 큰 데이터셋의 경우 테이블 파티셔닝을 고려:

.. code-block:: sql

    -- 월별 파티셔닝 예시 (PostgreSQL)
    CREATE TABLE auditlog_logentry_2024_01 PARTITION OF auditlog_logentry
    FOR VALUES FROM ('2024-01-01') TO ('2024-02-01');
    
    CREATE TABLE auditlog_logentry_2024_02 PARTITION OF auditlog_logentry
    FOR VALUES FROM ('2024-02-01') TO ('2024-03-01');

캐싱 전략
~~~~~~~~~

Redis를 사용한 쿼리 결과 캐싱:

.. code-block:: python

    # settings.py
    CACHES = {
        'default': {
            'BACKEND': 'django_redis.cache.RedisCache',
            'LOCATION': 'redis://127.0.0.1:6379/1',
            'OPTIONS': {
                'CLIENT_CLASS': 'django_redis.client.DefaultClient',
            }
        }
    }
    
    AUDITLOG_ENABLE_CACHING = True
    AUDITLOG_CACHE_TIMEOUT = 300

검색 최적화
~~~~~~~~~~

대용량 데이터에서 검색 성능을 개선:

1. **PostgreSQL Full-text Search 사용**:

.. code-block:: sql

    -- Full-text search 인덱스 추가
    ALTER TABLE auditlog_logentry ADD COLUMN search_vector tsvector;
    CREATE INDEX auditlog_logentry_search_idx ON auditlog_logentry USING gin(search_vector);
    
    -- 검색 벡터 업데이트 함수
    CREATE OR REPLACE FUNCTION auditlog_update_search_vector() RETURNS trigger AS $$
    BEGIN
        NEW.search_vector :=
            setweight(to_tsvector('english', COALESCE(NEW.object_repr, '')), 'A') ||
            setweight(to_tsvector('english', COALESCE(NEW.changes_text, '')), 'B');
        RETURN NEW;
    END;
    $$ LANGUAGE plpgsql;
    
    CREATE TRIGGER auditlog_search_vector_update
        BEFORE INSERT OR UPDATE ON auditlog_logentry
        FOR EACH ROW EXECUTE FUNCTION auditlog_update_search_vector();

2. **Elasticsearch 사용** (대용량 검색):

.. code-block:: python

    # settings.py
    AUDITLOG_USE_ELASTICSEARCH = True
    AUDITLOG_ELASTICSEARCH_HOST = 'localhost'
    AUDITLOG_ELASTICSEARCH_PORT = 9200

커서 기반 페이지네이션
~~~~~~~~~~~~~~~~~~~~~

대용량 데이터에서 오프셋 기반 페이지네이션 대신 커서 기반 페이지네이션 사용:

.. code-block:: python

    # settings.py
    AUDITLOG_USE_CURSOR_PAGINATION = True

설정 예시
---------

대용량 환경을 위한 권장 설정:

.. code-block:: python

    # settings.py
    
    # 성능 최적화 설정
    AUDITLOG_ADMIN_LIST_PER_PAGE = 50
    AUDITLOG_DEFAULT_DATE_RANGE_DAYS = 365
    AUDITLOG_ENABLE_ARCHIVING = True
    AUDITLOG_ARCHIVE_AFTER_DAYS = 365
    AUDITLOG_USE_CURSOR_PAGINATION = True
    AUDITLOG_ENABLE_CACHING = True
    AUDITLOG_CACHE_TIMEOUT = 300
    
    # 캐시 설정
    CACHES = {
        'default': {
            'BACKEND': 'django_redis.cache.RedisCache',
            'LOCATION': 'redis://127.0.0.1:6379/1',
        }
    }

모니터링 및 유지보수
-------------------

정기적인 성능 모니터링:

1. **주간 성능 분석**:
   .. code-block:: bash
       python manage.py analyze_performance --detailed

2. **월간 데이터 아카이빙**:
   .. code-block:: bash
       python manage.py archive_old_logs --days 365

3. **인덱스 사용 통계 확인**:
   .. code-block:: sql
       SELECT schemaname, tablename, indexname, idx_scan, idx_tup_read
       FROM pg_stat_user_indexes 
       WHERE tablename = 'auditlog_logentry'
       ORDER BY idx_scan DESC;

성능 최적화 체크리스트
---------------------

- [ ] 복합 인덱스 추가 (timestamp + action, timestamp + content_type)
- [ ] Admin 인터페이스 최적화 (페이지 크기 제한, 기본 날짜 범위)
- [ ] 데이터 아카이빙 설정
- [ ] 캐싱 활성화
- [ ] 검색 최적화 (Full-text search 또는 Elasticsearch)
- [ ] 커서 기반 페이지네이션 활성화
- [ ] 정기적인 성능 모니터링 설정
- [ ] 테이블 파티셔닝 고려 (매우 큰 데이터셋의 경우)

추가 리소스
-----------

- `PostgreSQL 성능 튜닝 가이드 <https://www.postgresql.org/docs/current/performance.html>`_
- `Django 성능 최적화 <https://docs.djangoproject.com/en/stable/topics/performance/>`_
- `Redis 캐싱 전략 <https://redis.io/topics/caching>`_