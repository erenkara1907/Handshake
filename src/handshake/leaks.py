import re

THOUSAND = 1000
GROUP_SIZE = 3
SEPARATOR = r"[,. ]?"
LEFT_GUARD = r"(?<![\d,.])"
RIGHT_GUARD = r"(?![\d,.]?\d)(?!\w)"


def _grouped_digits(value: int) -> str:
    digits = str(value)
    head_len = len(digits) % GROUP_SIZE or GROUP_SIZE
    groups = [digits[:head_len]] + [
        digits[i : i + GROUP_SIZE] for i in range(head_len, len(digits), GROUP_SIZE)
    ]
    return SEPARATOR.join(groups)


def mentions_number(text: str, value: int) -> bool:
    """True when `value` appears as a standalone number (8000, 8,000, 8k) in text."""
    forms = [_grouped_digits(value)]
    if value > 0 and value % THOUSAND == 0:
        forms.append(f"{value // THOUSAND}k")
    pattern = re.compile(f"{LEFT_GUARD}(?:{'|'.join(forms)}){RIGHT_GUARD}", re.IGNORECASE)
    return pattern.search(text) is not None
