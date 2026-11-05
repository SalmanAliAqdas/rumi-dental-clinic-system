import re
import phonenumbers
from django.core.exceptions import ValidationError

def normalize_phone(value):
    """Validate a complete phone and return E.164. Bare national input uses PK."""
    value = value.strip()
    if not re.fullmatch(r'[+\d\s().-]+', value):
        raise ValidationError('Enter a valid phone number; include +country code for international numbers.')
    if value.startswith('00'):
        value = '+' + value[2:]
    try:
        number = phonenumbers.parse(value, 'PK')
    except phonenumbers.NumberParseException:
        raise ValidationError('Enter a valid phone number.')
    if not phonenumbers.is_valid_number(number):
        raise ValidationError('Enter a valid phone number.')
    return phonenumbers.format_number(number, phonenumbers.PhoneNumberFormat.E164)

def partial_phone(value):
    if not re.fullmatch(r'[+\d\s().-]+', value):
        return ''
    digits = re.sub(r'\D', '', value)
    if digits.startswith('00'):
        digits = digits[2:]
    elif digits.startswith('0'):
        digits = '92' + digits[1:]
    return digits
