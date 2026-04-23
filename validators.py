def parse_positive_float(value, field_name, min_val=0.001):
    try:
        val = float(str(value).strip())
    except (TypeError, ValueError):
        raise ValueError(f"{field_name} must be a number")
    if val < min_val:
        raise ValueError(f"{field_name} must be greater than {min_val}")
    return val

def parse_non_negative_float(value, field_name):
    try:
        val = float(str(value).strip())
    except (TypeError, ValueError):
        raise ValueError(f"{field_name} must be a number")
    if val < 0:
        raise ValueError(f"{field_name} cannot be negative")
    return val

def parse_gst_rate(value):
    try:
        val = float(str(value).strip())
    except (TypeError, ValueError):
        raise ValueError("GST rate must be a number")
    allowed = [0, 5, 12, 18, 28]
    if val not in allowed:
        raise ValueError(f"GST rate must be one of: {allowed}")
    return val
