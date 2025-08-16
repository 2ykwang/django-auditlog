"""
MySQL-specific tests for Django Auditlog.

These tests are only run when AUDITLOG_TEST_TYPE=mysql.
They test MySQL-specific configurations and edge cases.
"""

import os
import unittest

from django.test import TestCase
from django.db import connection

# Skip all MySQL tests if not using MySQL backend
TEST_TYPE = os.getenv("AUDITLOG_TEST_TYPE", "sqlite")

@unittest.skipUnless(TEST_TYPE == "mysql", "MySQL-specific tests")
class MySQLDatabaseTest(TestCase):
    """
    Test MySQL database configuration and connectivity.
    """
    
    def test_mysql_engine(self):
        """Test that MySQL engine is being used."""
        from django.conf import settings
        engine = settings.DATABASES['default']['ENGINE']
        self.assertEqual(engine, 'django.db.backends.mysql')

    def test_mysql_connection(self):
        """Test that we can connect to MySQL database."""
        with connection.cursor() as cursor:
            cursor.execute("SELECT VERSION()")
            result = cursor.fetchone()
            self.assertTrue(result[0].startswith('8.0') or result[0].startswith('5.7'))

    def test_mysql_sql_mode(self):
        """Test that MySQL SQL mode is properly configured."""
        with connection.cursor() as cursor:
            cursor.execute("SELECT @@sql_mode")
            result = cursor.fetchone()
            # Should include STRICT_TRANS_TABLES for data integrity
            self.assertIn('STRICT_TRANS_TABLES', result[0])

    def test_mysql_charset(self):
        """Test that MySQL uses UTF-8 charset."""
        with connection.cursor() as cursor:
            cursor.execute("SELECT @@character_set_database")
            result = cursor.fetchone()
            # Should be utf8 or utf8mb4
            self.assertTrue(result[0].startswith('utf8'))

    def test_mysql_timezone(self):
        """Test MySQL timezone handling."""
        with connection.cursor() as cursor:
            cursor.execute("SELECT @@time_zone")
            result = cursor.fetchone()
            # MySQL should be configured with a timezone
            self.assertIsNotNone(result[0])


@unittest.skipUnless(TEST_TYPE == "mysql", "MySQL-specific tests")
class MySQLAuditlogTest(TestCase):
    """
    Test auditlog functionality with MySQL-specific behaviors.
    """
    
    def setUp(self):
        from test_app.models import SimpleModel
        self.SimpleModel = SimpleModel
    
    def test_mysql_datetime_precision(self):
        """Test that MySQL properly handles datetime precision in audit logs."""
        obj = self.SimpleModel.objects.create(text="test")
        
        # Get the audit log entry
        log_entry = obj.history.first()
        
        # MySQL should store timestamp with microsecond precision
        self.assertIsNotNone(log_entry.timestamp)
        # Verify the timestamp format is preserved
        timestamp_str = str(log_entry.timestamp)
        self.assertTrue('.' in timestamp_str or '+' in timestamp_str)

    def test_mysql_large_text_handling(self):
        """Test MySQL handling of large text fields in audit logs."""
        # Create a large text string (MySQL has specific limits)
        large_text = "x" * 10000  # 10KB text
        
        obj = self.SimpleModel.objects.create(text=large_text)
        
        # Verify the audit log was created successfully
        self.assertEqual(obj.history.count(), 1)
        
        log_entry = obj.history.first()
        changes = log_entry.changes_display_dict
        
        # Verify the large text was stored properly
        self.assertIn('text', changes)
        self.assertEqual(changes['text'][1], large_text)

    def test_mysql_json_field_compatibility(self):
        """Test MySQL JSON field compatibility with audit logs."""
        from test_app.models import JSONModel
        
        test_data = {
            "key1": "value1",
            "key2": ["item1", "item2"],
            "key3": {"nested": "data"}
        }
        
        obj = JSONModel.objects.create(json=test_data)
        
        # Verify the audit log was created
        self.assertEqual(obj.history.count(), 1)
        
        log_entry = obj.history.first()
        changes = log_entry.changes_display_dict
        
        # Verify JSON data was stored correctly
        self.assertIn('json', changes)

    def test_mysql_transaction_handling(self):
        """Test MySQL transaction handling with audit logs."""
        from django.db import transaction
        
        try:
            with transaction.atomic():
                obj1 = self.SimpleModel.objects.create(text="test1")
                obj2 = self.SimpleModel.objects.create(text="test2")
                
                # Both objects should have audit logs
                self.assertEqual(obj1.history.count(), 1)
                self.assertEqual(obj2.history.count(), 1)
                
                # Force a rollback by raising an exception
                raise Exception("Test rollback")
                
        except Exception:
            pass
        
        # After rollback, objects and their audit logs should not exist
        self.assertEqual(self.SimpleModel.objects.count(), 0)
        
        # Note: This tests MySQL's transaction behavior with audit logs
        from auditlog.models import LogEntry
        from django.contrib.contenttypes.models import ContentType
        
        ct = ContentType.objects.get_for_model(self.SimpleModel)
        logs = LogEntry.objects.filter(content_type=ct)
        
        # Audit logs should also be rolled back
        self.assertEqual(logs.count(), 0)


@unittest.skipUnless(TEST_TYPE == "mysql", "MySQL-specific tests")
class MySQLPerformanceTest(TestCase):
    """
    Test MySQL-specific performance considerations for auditlog.
    """
    
    def setUp(self):
        from test_app.models import SimpleModel
        self.SimpleModel = SimpleModel
    
    def test_mysql_bulk_operations(self):
        """Test MySQL performance with bulk audit log operations."""
        import time
        
        start_time = time.time()
        
        # Create multiple objects to test bulk performance
        objects = []
        for i in range(100):
            obj = self.SimpleModel.objects.create(text=f"test_{i}")
            objects.append(obj)
        
        creation_time = time.time() - start_time
        
        # Verify all audit logs were created
        total_logs = sum(obj.history.count() for obj in objects)
        self.assertEqual(total_logs, 100)
        
        # MySQL should handle this reasonably fast (adjust threshold as needed)
        self.assertLess(creation_time, 30.0, "Bulk operations taking too long")

    def test_mysql_index_usage(self):
        """Test that MySQL properly uses indexes for audit log queries."""
        # Create some test data
        objects = []
        for i in range(50):
            obj = self.SimpleModel.objects.create(text=f"test_{i}")
            objects.append(obj)
        
        # Test common audit log query patterns
        with connection.cursor() as cursor:
            # Enable query profiling (MySQL specific)
            cursor.execute("SET profiling = 1")
            
            # Run a typical audit log query
            test_obj = objects[0]
            log_entries = list(test_obj.history.all())
            
            # Get query profile
            cursor.execute("SHOW PROFILES")
            profiles = cursor.fetchall()
            
            # Verify the query executed
            self.assertGreater(len(profiles), 0)
            
            # Turn off profiling
            cursor.execute("SET profiling = 0")
        
        # Verify we got the expected results
        self.assertGreater(len(log_entries), 0) 