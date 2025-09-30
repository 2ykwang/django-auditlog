import json
from datetime import timezone
from typing import Callable, Optional

from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist
from django.db.models import NOT_PROVIDED, DateTimeField, ForeignKey, JSONField, Model
from django.utils import timezone as django_timezone
from django.utils.encoding import smart_str
from django.utils.module_loading import import_string


def track_field(field):
    """
    Returns whether the given field should be tracked by Auditlog.

    Untracked fields are many-to-many relations and relations to the Auditlog LogEntry model.

    :param field: The field to check.
    :type field: Field
    :return: Whether the given field should be tracked.
    :rtype: bool
    """
    from auditlog.models import LogEntry

    # Do not track many to many relations
    if field.many_to_many:
        return False

    # Do not track relations to LogEntry
    if (
        getattr(field, "remote_field", None) is not None
        and field.remote_field.model == LogEntry
    ):
        return False

    return True


def get_fields_in_model(instance):
    """
    Returns the list of fields in the given model instance. Checks whether to use the official
    _meta API or use the raw data. This method excludes many to many fields.

    :param instance: The model instance to get the fields for
    :type instance: Model
    :return: The list of fields for the given model (instance)
    :rtype: list
    """
    assert isinstance(instance, Model)

    return [f for f in instance._meta.get_fields() if track_field(f)]


def get_field_value(obj, field, use_json_for_changes=False):
    """
    Gets the value of a given model instance field and normalizes it for comparison.

    :param obj: The model instance.
    :type obj: Model
    :param field: The field you want to find the value of.
    :type field: Any
    :param use_json_for_changes: Whether to keep values in JSON-compatible format.
    :type use_json_for_changes: bool
    :return: The field value, normalized for comparison.
    :rtype: Any
    """
    # JSONField needs immediate processing to handle expressions like Value(None)
    # But only if obj is not None
    if obj is not None and isinstance(field, JSONField):
        raw_value = _get_raw_field_value(obj, field)
        # Process immediately to preserve Django expressions before they're evaluated
        if not use_json_for_changes:
            try:
                return json.dumps(raw_value, sort_keys=True, cls=field.encoder)
            except TypeError:
                return raw_value
        return raw_value

    raw_value = _get_raw_field_value(obj, field)
    return _normalize_value(raw_value, field, use_json_for_changes)


def _get_raw_field_value(obj, field):
    """
    Extracts the raw value from a field without any normalization.

    :param obj: The model instance (can be None).
    :type obj: Model or None
    :param field: The field to extract the value from.
    :return: The raw field value.
    """

    def get_default_value():
        """Get the default value for a field from the model's field definition."""
        if obj is None:
            return None
        try:
            model_field = obj._meta.get_field(field.name)
            default = model_field.default
            if default is NOT_PROVIDED:
                return None
            if callable(default):
                return default()
            return default
        except AttributeError:
            return None

    if obj is None:
        return get_default_value()

    try:
        if isinstance(field, DateTimeField):
            # DateTimeFields are timezone-aware, so we need to convert the field
            # to its naive form before we can accurately compare them for changes.
            value = getattr(obj, field.name)
            try:
                value = field.to_python(value)
            except TypeError:
                return value
            if (
                value is not None
                and settings.USE_TZ
                and not django_timezone.is_naive(value)
            ):
                value = django_timezone.make_naive(value, timezone=timezone.utc)
            return value
        elif isinstance(field, JSONField):
            return field.to_python(getattr(obj, field.name))
        elif (field.one_to_one or field.many_to_one) and hasattr(field, "rel_class"):
            # For ForeignKey fields, get the attribute name (e.g., "related_id")
            return getattr(obj, field.get_attname())
        else:
            return getattr(obj, field.name)
    except (ObjectDoesNotExist, AttributeError):
        return get_default_value()


def _normalize_value(value, field, use_json_for_changes):
    """
    Normalizes a field value for comparison in auditlog.

    :param value: The raw field value.
    :param field: The field instance.
    :param use_json_for_changes: Whether to keep values in JSON-compatible format.
    :type use_json_for_changes: bool
    :return: The normalized value.
    """
    # JSON mode: keep primitives as-is, convert complex types to strings
    if use_json_for_changes:
        # None values are kept as None for accurate comparison
        if value is None:
            return None
        if not is_primitive(value):
            return smart_str(value)
        return value

    # Non-JSON mode: convert everything to strings for storage
    # (JSONField is handled separately in get_field_value)

    # None values for non-JSON fields are kept as None for accurate comparison
    if value is None:
        return None

    if (field.one_to_one or field.many_to_one) and hasattr(field, "rel_class"):
        return smart_str(value, strings_only=True)

    # Regular fields: convert to string
    try:
        value_str = smart_str(value)
        if type(value_str).__name__ == "__proxy__":
            value_str = str(value_str)
        return value_str
    except (ObjectDoesNotExist, AttributeError):
        # If __str__() raises an error (e.g., accessing deleted related objects),
        # return a placeholder (lazy import to avoid circular dependency)
        from auditlog.models import DEFAULT_OBJECT_REPR

        return DEFAULT_OBJECT_REPR


def is_primitive(obj) -> bool:
    """
    Checks if the given object is a primitive Python type that can be safely serialized to JSON.

    :param obj: The object to check
    :return: True if the object is a primitive type, False otherwise
    :rtype: bool
    """
    primitive_types = (type(None), bool, int, float, str, list, tuple, dict, set)
    return isinstance(obj, primitive_types)


def get_mask_function(mask_callable: Optional[str] = None) -> Callable[[str], str]:
    """
    Get the masking function to use based on the following priority:
    1. Model-specific mask_callable if provided
    2. mask_callable from settings if configured
    3. Default mask_str function

    :param mask_callable: The dotted path to a callable that will be used for masking.
    :type mask_callable: str
    :return: A callable that takes a string and returns a masked version.
    :rtype: Callable[[str], str]
    """

    if mask_callable:
        return import_string(mask_callable)

    default_mask_callable = settings.AUDITLOG_MASK_CALLABLE
    if default_mask_callable:
        return import_string(default_mask_callable)

    return mask_str


def mask_str(value: str) -> str:
    """
    Masks the first half of the input string to remove sensitive data.

    :param value: The value to mask.
    :type value: str
    :return: The masked version of the string.
    :rtype: str
    """
    mask_limit = int(len(value) / 2)
    return "*" * mask_limit + value[mask_limit:]


def model_instance_diff(
    old: Optional[Model],
    new: Optional[Model],
    fields_to_check=None,
    use_json_for_changes=False,
):
    """
    Calculates the differences between two model instances. One of the instances may be ``None``
    (i.e., a newly created model or deleted model). This will cause all fields with a value to have
    changed (from ``None``).

    :param old: The old state of the model instance.
    :type old: Model
    :param new: The new state of the model instance.
    :type new: Model
    :param fields_to_check: An iterable of the field names to restrict the diff to, while ignoring the rest of
        the model's fields. This is used to pass the `update_fields` kwarg from the model's `save` method.
    :param use_json_for_changes: whether or not to use a JSON for changes
        (see settings.AUDITLOG_STORE_JSON_CHANGES)
    :type fields_to_check: Iterable
    :return: A dictionary with the names of the changed fields as keys and a two tuple of the old and new
            field values as value.
    :rtype: dict
    """
    from auditlog.registry import auditlog

    if not (old is None or isinstance(old, Model)):
        raise TypeError("The supplied old instance is not a valid model instance.")
    if not (new is None or isinstance(new, Model)):
        raise TypeError("The supplied new instance is not a valid model instance.")

    diff = {}

    if old is not None and new is not None:
        fields = set(old._meta.fields + new._meta.fields)
        model_fields = auditlog.get_model_fields(new._meta.model)
    elif old is not None:
        fields = set(get_fields_in_model(old))
        model_fields = auditlog.get_model_fields(old._meta.model)
    elif new is not None:
        fields = set(get_fields_in_model(new))
        model_fields = auditlog.get_model_fields(new._meta.model)
    else:
        fields = set()
        model_fields = None

    if fields_to_check:
        fields = {
            field
            for field in fields
            if (
                (isinstance(field, ForeignKey) and field.attname in fields_to_check)
                or (field.name in fields_to_check)
            )
        }

    # Check if fields must be filtered
    if (
        model_fields
        and (model_fields["include_fields"] or model_fields["exclude_fields"])
        and fields
    ):
        filtered_fields = []
        if model_fields["include_fields"]:
            filtered_fields = [
                field
                for field in fields
                if field.name in model_fields["include_fields"]
            ]
        else:
            filtered_fields = fields
        if model_fields["exclude_fields"]:
            filtered_fields = [
                field
                for field in filtered_fields
                if field.name not in model_fields["exclude_fields"]
            ]
        fields = filtered_fields

    for field in fields:
        old_value = get_field_value(old, field, use_json_for_changes)
        new_value = get_field_value(new, field, use_json_for_changes)

        if old_value != new_value:
            if model_fields and field.name in model_fields["mask_fields"]:
                mask_func = get_mask_function(model_fields.get("mask_callable"))
                diff[field.name] = (
                    mask_func(smart_str(old_value)),
                    mask_func(smart_str(new_value)),
                )
            else:
                # Values are already normalized by get_field_value
                # But for non-JSON mode, convert None to "None" for storage
                if not use_json_for_changes:
                    diff[field.name] = (smart_str(old_value), smart_str(new_value))
                else:
                    diff[field.name] = (old_value, new_value)

    if len(diff) == 0:
        diff = None

    return diff
