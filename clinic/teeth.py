from django.core.exceptions import ValidationError

ADULT_ROWS = [list(map(str, [*range(18, 10, -1), *range(21, 29)])), list(map(str, [*range(48, 40, -1), *range(31, 39)]))]
PRIMARY_ROWS = [list(map(str, [*range(55, 50, -1), *range(61, 66)])), list(map(str, [*range(85, 80, -1), *range(71, 76)]))]
TEETH = tuple(tooth for row in ADULT_ROWS + PRIMARY_ROWS for tooth in row)

def validate_teeth(value):
    if not isinstance(value, list) or len(value) > 52 or any(not isinstance(t, str) or t not in TEETH for t in value) or len(value) != len(set(value)):
        raise ValidationError('Select valid, unique two-digit adult or primary FDI tooth identifiers.')
