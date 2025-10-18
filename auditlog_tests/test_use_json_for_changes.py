from django.test import TestCase, override_settings
from django.db import models
from test_app.models import JSONModel, NullableFieldModel, RelatedModel, SimpleModel, TestModel

from auditlog.models import LogEntry
from auditlog.registry import AuditlogModelRegistry, auditlog


class JSONForChangesTest(TestCase):

    def setUp(self):
        self.test_auditlog = AuditlogModelRegistry()

    @override_settings(AUDITLOG_STORE_JSON_CHANGES="str")
    def test_wrong_setting_type(self):
        with self.assertRaisesMessage(
            TypeError, "Setting 'AUDITLOG_STORE_JSON_CHANGES' must be a boolean"
        ):
            self.test_auditlog.register_from_settings()

    @override_settings(AUDITLOG_STORE_JSON_CHANGES=True)
    def test_use_json_for_changes_with_simplemodel(self):
        self.test_auditlog.register_from_settings()

        smm = SimpleModel()
        smm.save()
        changes_dict = smm.history.latest().changes_dict

        # compare the id, text, boolean and datetime fields
        id_field_changes = changes_dict["id"]
        self.assertIsNone(id_field_changes[0])
        self.assertIsInstance(
            id_field_changes[1], int
        )  # the id depends on state of the database

        text_field_changes = changes_dict["text"]
        self.assertEqual(text_field_changes, [None, ""])

        boolean_field_changes = changes_dict["boolean"]
        self.assertEqual(boolean_field_changes, [None, False])

        # datetime should be serialized to string
        datetime_field_changes = changes_dict["datetime"]
        self.assertIsNone(datetime_field_changes[0])
        self.assertIsInstance(datetime_field_changes[1], str)

    @override_settings(AUDITLOG_STORE_JSON_CHANGES=True)
    def test_use_json_for_changes_with_jsonmodel(self):
        self.test_auditlog.register_from_settings()

        json_model = JSONModel()
        json_model.json = {"test_key": "test_value"}
        json_model.save()
        changes_dict = json_model.history.latest().changes_dict

        id_field_changes = changes_dict["json"]
        self.assertEqual(id_field_changes, [None, {"test_key": "test_value"}])

    @override_settings(AUDITLOG_STORE_JSON_CHANGES=True)
    def test_use_json_for_changes_with_jsonmodel_with_empty_list(self):
        self.test_auditlog.register_from_settings()

        json_model = JSONModel()
        json_model.json = []
        json_model.save()
        changes_dict = json_model.history.latest().changes_dict

        id_field_changes = changes_dict["json"]
        self.assertEqual(id_field_changes, [None, []])

    @override_settings(AUDITLOG_STORE_JSON_CHANGES=True)
    def test_use_json_for_changes_with_jsonmodel_with_complex_data(self):
        self.test_auditlog.register_from_settings()

        json_model = JSONModel()
        json_model.json = {
            "key": "test_value",
            "key_dict": {"inner_key": "inner_value"},
            "key_tuple": ("item1", "item2", "item3"),
        }
        json_model.save()
        changes_dict = json_model.history.latest().changes_dict

        id_field_changes = changes_dict["json"]
        self.assertEqual(
            id_field_changes,
            [
                None,
                {
                    "key": "test_value",
                    "key_dict": {"inner_key": "inner_value"},
                    "key_tuple": [
                        "item1",
                        "item2",
                        "item3",
                    ],  # tuple is converted to list, that's ok
                },
            ],
        )

    @override_settings(AUDITLOG_STORE_JSON_CHANGES=True)
    def test_use_json_for_changes_with_jsonmodel_with_related_model(self):
        self.test_auditlog.register_from_settings()

        simple = SimpleModel.objects.create()
        one_simple = SimpleModel.objects.create()
        related_model = RelatedModel.objects.create(
            one_to_one=simple, related=one_simple
        )
        related_model.save()
        changes_dict = related_model.history.latest().changes_dict

        field_related_changes = changes_dict["related"]
        self.assertEqual(field_related_changes, [None, one_simple.id])

        field_one_to_one_changes = changes_dict["one_to_one"]
        self.assertEqual(field_one_to_one_changes, [None, simple.id])

    @override_settings(AUDITLOG_STORE_JSON_CHANGES=True)
    def test_use_json_for_changes_update(self):
        self.test_auditlog.register_from_settings()

        simple = SimpleModel(text="original")
        simple.save()
        simple.text = "new"
        simple.save()

        changes_dict = simple.history.latest().changes_dict

        text_changes = changes_dict["text"]
        self.assertEqual(text_changes, ["original", "new"])

    @override_settings(AUDITLOG_STORE_JSON_CHANGES=True)
    def test_use_json_for_changes_delete(self):
        self.test_auditlog.register_from_settings()

        simple = SimpleModel()
        simple.save()
        simple.delete()

        history = LogEntry.objects.all()

        self.assertEqual(history.count(), 1, '"DELETE" record is always retained')

        changes_dict = history.first().changes_dict

        self.assertTrue(
            all(v[1] is None for k, v in changes_dict.items()),
            'all values in the changes dict should None, not "None"',
        )

    @override_settings(AUDITLOG_STORE_JSON_CHANGES=False)
    def test_nullable_field_with_none_not_logged(self):
        self.test_auditlog.register_from_settings()

        obj = NullableFieldModel.objects.create(time=None, optional_text=None)
        changes_dict = obj.history.latest().changes_dict

        # None → None should NOT be logged as a change
        self.assertNotIn("time", changes_dict)
        self.assertNotIn("optional_text", changes_dict)

    @override_settings(AUDITLOG_STORE_JSON_CHANGES=False)
    def test_nullable_field_with_value_logged(self):
        self.test_auditlog.register_from_settings()

        obj = NullableFieldModel.objects.create(optional_text="something")
        changes_dict = obj.history.latest().changes_dict

        # None → "something" should be logged
        self.assertIn("optional_text", changes_dict)
        self.assertEqual(changes_dict["optional_text"], ["None", "something"])

    @override_settings(AUDITLOG_STORE_JSON_CHANGES=True)
    def test_nullable_field_with_none_not_logged_json_mode(self):
        self.test_auditlog.register_from_settings()

        obj = NullableFieldModel.objects.create(time=None, optional_text=None)
        changes_dict = obj.history.latest().changes_dict

        # None → None should NOT be logged
        self.assertNotIn("time", changes_dict)
        self.assertNotIn("optional_text", changes_dict)

    @override_settings(AUDITLOG_STORE_JSON_CHANGES=False)
    def test_nullable_field_update_none_to_value(self):
        self.test_auditlog.register_from_settings()

        obj = NullableFieldModel.objects.create(optional_text=None)
        obj.optional_text = "updated"
        obj.save()

        changes_dict = obj.history.latest().changes_dict

        # None → "updated" should be logged
        self.assertIn("optional_text", changes_dict)
        self.assertEqual(changes_dict["optional_text"], ["None", "updated"])


class DateTimeFieldCreateWithNullDateTimeTest(TestCase):
    """Ensure creating with DateTimeField=None does not log a spurious change when using text changes"""
    
    @override_settings(AUDITLOG_STORE_JSON_CHANGES=False)
    def test_datetimefield_none_should_not_create_change_on_create(self):
        """
        Test that creating a new record with DateTimeField=None should not 
        create a change entry when AUDITLOG_STORE_JSON_CHANGES=False.
        
        This reproduces issue #770 where the field gets added to diff as (None, None)
        due to type mismatch: "None" (string) vs None (actual value).
        """
        # Create a new instance with datetime=None
        instance = TestModel.objects.create(text="abc", datetime=None)
        
        # Get the log entry for this creation
        log_entries = LogEntry.objects.get_for_object(instance)
        self.assertEqual(log_entries.count(), 1)
        
        log_entry = log_entries.first()
        self.assertEqual(log_entry.action, LogEntry.Action.CREATE)
        
        # The changes should NOT contain the datetime field since it didn't actually change
        # (it was None from the start)
        changes = log_entry.changes_dict
        self.assertIsNotNone(changes)
        
        # This is the bug: datetime field should not be in changes
        # Currently it will be there as ("None", "None") due to type mismatch
        if 'datetime' in changes:
            print(f"BUG REPRODUCED: datetime field found in changes: {changes['datetime']}")
            print(f"Expected: datetime field should not be in changes")
            print(f"Actual changes: {changes}")
            
            # This assertion will fail, demonstrating the bug
            self.assertNotIn('datetime', changes, 
                f"datetime field should not be in changes when creating with datetime=None. "
                f"Changes: {changes}")
        else:
            print("SUCCESS: datetime field correctly not included in changes")
    
    @override_settings(AUDITLOG_STORE_JSON_CHANGES=False)
    def test_datetimefield_none_vs_actual_change(self):
        """
        Test to verify that a real change to datetime field IS detected,
        while None->None should not be detected.
        """
        # Create instance with datetime=None
        instance = TestModel.objects.create(text="abc", datetime=None)
        
        # Get initial log entry
        initial_logs = LogEntry.objects.get_for_object(instance)
        self.assertEqual(initial_logs.count(), 1)
        
        # Now make an actual change to datetime field
        from django.utils import timezone
        new_datetime = timezone.now()
        instance.datetime = new_datetime
        instance.save()
        
        # Should have 2 log entries now
        all_logs = LogEntry.objects.get_for_object(instance)
        self.assertEqual(all_logs.count(), 2)
        
        # The update log should show the datetime change
        update_log = all_logs.filter(action=LogEntry.Action.UPDATE).first()
        self.assertIsNotNone(update_log)
        
        changes = update_log.changes_dict
        self.assertIn('datetime', changes)
        
        # The change should show None -> actual datetime value
        old_value, new_value = changes['datetime']
        self.assertEqual(old_value, "None")  # This will be "None" string
        self.assertIn("2025", new_value)  # Should contain the actual datetime
    
    @override_settings(AUDITLOG_STORE_JSON_CHANGES=True)
    def test_datetimefield_none_with_json_changes_true(self):
        """
        Test that the issue doesn't occur when AUDITLOG_STORE_JSON_CHANGES=True
        """
        # Create a new instance with datetime=None
        instance = TestModel.objects.create(text="abc", datetime=None)
        
        # Get the log entry for this creation
        log_entries = LogEntry.objects.get_for_object(instance)
        self.assertEqual(log_entries.count(), 1)
        
        log_entry = log_entries.first()
        changes = log_entry.changes_dict
        
        # With JSON changes, the datetime field should not be in changes
        # because the comparison logic is different
        if 'datetime' in changes:
            print(f"With JSON changes, datetime found: {changes['datetime']}")
            # This might still be an issue, let's see
            self.assertNotIn('datetime', changes, 
                f"datetime field should not be in changes even with JSON changes. "
                f"Changes: {changes}")
        else:
            print("SUCCESS: datetime field correctly not included in changes with JSON=True")
