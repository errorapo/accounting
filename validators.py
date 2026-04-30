import re
from decimal import Decimal, InvalidOperation

def parse_positive_float(value, field_name, min_val=0.001):
    try:
        val = float(str(value).strip())
    except (TypeError, ValueError):
        raise ValueError(f"{field_name} must be a number")
    if val < min_val:
        raise ValueError(f"{field_name} must be greater than {min_val}")
    return val

def safe_decimal(val, default='0'):
    """Safely convert value to Decimal."""
    try:
        return Decimal(str(val or default))
    except InvalidOperation:
        return Decimal(default)

def parse_decimal(value, field_name, allow_zero=True):
    """Parse value to Decimal with validation."""
    try:
        d = Decimal(str(value or '0'))
        if not allow_zero and d <= 0:
            raise ValueError(f"{field_name} must be positive")
        return d
    except InvalidOperation:
        raise ValueError(f"{field_name} must be a valid number")

def validate_password(password):
    """Validate password meets policy: min 8 chars, 1 uppercase, 1 lowercase, 1 digit."""
    errors = []
    if len(password) < 8:
        errors.append("Password must be at least 8 characters")
    if not re.search(r'[A-Z]', password):
        errors.append("Password must contain at least one uppercase letter")
    if not re.search(r'[a-z]', password):
        errors.append("Password must contain at least one lowercase letter")
    if not re.search(r'\d', password):
        errors.append("Password must contain at least one digit")
    if errors:
        raise ValueError("; ".join(errors))
    return True

def validate_gstin(value):
    """Validate Indian GSTIN: 15-char alphanumeric format."""
    if not value:
        return True  # Optional field
    gstin_pattern = r'^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z]{1}[1-9A-Z]{1}[Z]{1}[A-Z0-9]{1}$'
    if not re.match(gstin_pattern, str(value).upper()):
        raise ValueError("GSTIN must be 15 characters (e.g., 27AABCM1234C1ZI)")
    return True

def validate_phone(value):
    """Validate Indian phone: 10 digits."""
    if not value:
        return True  # Optional
    digits = re.sub(r'\D', '', str(value))
    if len(digits) != 10 or not digits.isdigit():
        raise ValueError("Phone must be 10 digits")
    return True

def validate_positive_decimal(value, field_name):
    """Validate decimal value is positive."""
    try:
        val = Decimal(str(value))
    except (TypeError, ValueError, InvalidOperation):
        raise ValueError(f"{field_name} must be a number")
    if val <= 0:
        raise ValueError(f"{field_name} must be positive")
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
