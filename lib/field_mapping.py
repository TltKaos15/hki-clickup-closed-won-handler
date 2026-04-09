"""
Field mapping and value formatting for HKI ClickUp custom fields.
Maps the 7 shared custom fields between Sales CRM and Client Snapshot tasks.
"""

# Fields to propagate to ALL tasks in the Discovery + Intake list (not just Client Snapshot)
PROPAGATE_FIELD_IDS = {
    "7c409897-f0c8-451f-bd6c-79fa0dbf2cd6",  # Company
    "3f019ca2-cde2-4de8-9830-08ceea00234b",  # Primary Contact
    "b27b1a2f-e31c-4266-9339-42692223b899",  # Contact Email
    "1787374a-cf49-4b29-a218-37a7e4f9a441",  # Contact Phone
}

FIELD_MAP = {
    "0432418c-591c-4202-a07a-9a53a2d414f9": {"name": "Comments", "type": "text"},
    "7c409897-f0c8-451f-bd6c-79fa0dbf2cd6": {"name": "Company", "type": "short_text"},
    "3f019ca2-cde2-4de8-9830-08ceea00234b": {"name": "Primary Contact", "type": "short_text"},
    "b27b1a2f-e31c-4266-9339-42692223b899": {"name": "Contact Email", "type": "email"},
    "1787374a-cf49-4b29-a218-37a7e4f9a441": {"name": "Contact Phone", "type": "phone"},
    "e70535bc-bccc-4834-9ccf-0961ddac4ab4": {"name": "Opportunity Type", "type": "drop_down"},
    "2cf4a2e5-3c0b-4960-b296-80f9dbb3ed1a": {"name": "Estimated Value", "type": "currency"},
    "00819039-5cb0-4905-b20e-16ff7176cc72": {"name": "Last Contact", "type": "date"},
}

# Valid Opportunity Type option IDs
OPPORTUNITY_TYPE_OPTIONS = {
    "002e215f-3327-45eb-8172-75d818dc58c1": "Training",
    "3c30d4f2-3a8b-44b3-91eb-9ccefcd1ffd1": "Presentation",
    "2684f90a-37ac-400c-ba56-61d1ae582d29": "Workflow",
    "b7ad395c-fbb3-4b49-8746-49b01a3749f1": "Custom App",
}


def extract_field_values(custom_fields):
    """Extract values for our 7 tracked fields from a task's custom_fields array.

    Returns dict of {field_id: raw_value} for fields that have non-null values.
    """
    values = {}
    for field in custom_fields:
        field_id = field.get("id")
        if field_id not in FIELD_MAP:
            continue

        field_type = FIELD_MAP[field_id]["type"]
        value = field.get("value")

        # Drop-down fields: value may be an integer orderindex or None
        # Also check type_config.options for the selected option
        if field_type == "drop_down":
            if value is not None:
                # ClickUp returns orderindex as an integer for dropdown value
                # We need to find the corresponding option to get its ID
                type_config = field.get("type_config", {})
                options = type_config.get("options", [])
                if isinstance(value, int) and options:
                    # value is the orderindex — find the option at that index
                    for opt in options:
                        if opt.get("orderindex") == value:
                            values[field_id] = opt.get("id")
                            break
                    else:
                        # Fallback: store raw value
                        values[field_id] = value
                elif isinstance(value, str):
                    # Already an option ID string
                    values[field_id] = value
                else:
                    values[field_id] = value
            continue

        # Skip null/empty values
        if value is None or value == "":
            continue

        values[field_id] = value

    return values


def format_value_for_update(field_id, raw_value):
    """Format a raw field value into the payload expected by the ClickUp update API.

    Returns the value to send in {"value": <returned_value>}.
    """
    field_type = FIELD_MAP[field_id]["type"]

    if field_type in ("text", "short_text", "email", "phone"):
        return str(raw_value)

    if field_type == "currency":
        return float(raw_value)

    if field_type == "date":
        # ClickUp expects millisecond timestamp
        return int(raw_value)

    if field_type == "drop_down":
        # For updates, ClickUp expects the option UUID
        return str(raw_value)

    return raw_value
