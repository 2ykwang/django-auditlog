"""
PostgreSQL-specific tests for Django Auditlog.

These tests are only run when AUDITLOG_TEST_TYPE=postgres.
They test PostgreSQL-specific features like ArrayField.
"""

import os
import unittest

from django.test import TestCase

# Skip all PostgreSQL tests if not using PostgreSQL backend
TEST_TYPE = os.getenv("AUDITLOG_TEST_TYPE", "sqlite")

@unittest.skipUnless(TEST_TYPE == "postgres", "PostgreSQL-specific tests")
class PostgresArrayFieldModelTest(TestCase):
    """
    Test PostgreSQL ArrayField functionality with auditlog.
    """
    databases = "__all__"

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Only import when PostgreSQL is being used
        try:
            from test_app.models import PostgresArrayFieldModel
            cls.PostgresArrayFieldModel = PostgresArrayFieldModel
        except ImportError:
            raise unittest.SkipTest("PostgresArrayFieldModel not available")

    def setUp(self):
        self.obj = self.PostgresArrayFieldModel.objects.create(
            arrayfield=[
                self.PostgresArrayFieldModel.RED, 
                self.PostgresArrayFieldModel.GREEN
            ],
        )

    @property
    def latest_array_change(self):
        return self.obj.history.latest().changes_display_dict["arrayfield"][1]

    def test_changes_display_dict_arrayfield(self):
        """Test that ArrayField changes are properly displayed."""
        self.assertEqual(
            self.latest_array_change,
            "Red, Green",
            msg="The human readable text for the two choices, 'Red, Green' is displayed.",
        )
        
        self.obj.arrayfield = [self.PostgresArrayFieldModel.GREEN]
        self.obj.save()
        self.assertEqual(
            self.latest_array_change,
            "Green",
            msg="The human readable text 'Green' is displayed.",
        )
        
        self.obj.arrayfield = []
        self.obj.save()
        self.assertEqual(
            self.latest_array_change,
            "",
            msg="The human readable text '' is displayed.",
        )
        
        self.obj.arrayfield = [self.PostgresArrayFieldModel.GREEN]
        self.obj.save()
        self.assertEqual(
            self.latest_array_change,
            "Green",
            msg="The human readable text 'Green' is displayed.",
        )

    def test_arrayfield_audit_creation(self):
        """Test that ArrayField model creation is properly audited."""
        # Check that an audit log entry was created
        self.assertEqual(self.obj.history.count(), 1)
        
        # Check the audit log entry details
        log_entry = self.obj.history.first()
        self.assertEqual(log_entry.action, 0)  # CREATE action
        self.assertIn("arrayfield", log_entry.changes_display_dict)

    def test_arrayfield_audit_update(self):
        """Test that ArrayField model updates are properly audited."""
        initial_count = self.obj.history.count()
        
        # Update the arrayfield
        self.obj.arrayfield = [self.PostgresArrayFieldModel.YELLOW]
        self.obj.save()
        
        # Check that a new audit log entry was created
        self.assertEqual(self.obj.history.count(), initial_count + 1)
        
        # Check the audit log entry details
        log_entry = self.obj.history.first()
        self.assertEqual(log_entry.action, 1)  # UPDATE action
        self.assertIn("arrayfield", log_entry.changes_display_dict)

    def test_arrayfield_audit_delete(self):
        """Test that ArrayField model deletion is properly audited."""
        obj_pk = self.obj.pk
        initial_count = self.obj.history.count()
        
        # Delete the object
        self.obj.delete()
        
        # Check that audit log entries still exist
        from auditlog.models import LogEntry
        from django.contrib.contenttypes.models import ContentType
        
        ct = ContentType.objects.get_for_model(self.PostgresArrayFieldModel)
        log_entries = LogEntry.objects.filter(
            content_type=ct,
            object_pk=str(obj_pk)
        )
        
        # Should have original entries plus delete entry
        self.assertEqual(log_entries.count(), initial_count + 1)
        
        # Check the delete log entry
        delete_entry = log_entries.filter(action=2).first()  # DELETE action
        self.assertIsNotNone(delete_entry)


@unittest.skipUnless(TEST_TYPE == "postgres", "PostgreSQL-specific tests")  
class PostgresContribAppTest(TestCase):
    """
    Test that django.contrib.postgres is properly configured.
    """
    
    def test_postgres_contrib_installed(self):
        """Test that django.contrib.postgres is in INSTALLED_APPS when using PostgreSQL."""
        from django.conf import settings
        self.assertIn("django.contrib.postgres", settings.INSTALLED_APPS)

    def test_postgres_arrayfield_import(self):
        """Test that PostgreSQL ArrayField can be imported."""
        try:
            from django.contrib.postgres.fields import ArrayField
            self.assertTrue(True, "ArrayField imported successfully")
        except ImportError:
            self.fail("Could not import ArrayField from django.contrib.postgres.fields")


@unittest.skipUnless(TEST_TYPE == "postgres", "PostgreSQL-specific tests")
class PostgresDatabaseTest(TestCase):
    """
    Test PostgreSQL database configuration and connectivity.
    """
    
    def test_postgres_engine(self):
        """Test that PostgreSQL engine is being used."""
        from django.conf import settings
        engine = settings.DATABASES['default']['ENGINE']
        self.assertEqual(engine, 'django.db.backends.postgresql')

    def test_postgres_connection(self):
        """Test that we can connect to PostgreSQL database."""
        from django.db import connection
        with connection.cursor() as cursor:
            cursor.execute("SELECT version()")
            result = cursor.fetchone()
            self.assertTrue(result[0].startswith('PostgreSQL'))

    def test_postgres_table_creation(self):
        """Test that PostgreSQL-specific models can create tables."""
        from django.core.management import call_command
        from django.db import connection
        
        # Ensure tables are created
        call_command('migrate', verbosity=0, interactive=False)
        
        # Check that our PostgreSQL-specific table exists
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT table_name 
                FROM information_schema.tables 
                WHERE table_schema = 'public' 
                AND table_name = 'test_app_postgresarrayfieldmodel'
            """)
            result = cursor.fetchone()
            self.assertIsNotNone(result, "PostgresArrayFieldModel table should exist") 