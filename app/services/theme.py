"""Theme helpers.

Turns the school's configured brand colours into the CSS custom properties
Bootstrap derives its utilities from.  Kept separate from the templates so the
hex handling is testable and so the future theme engine has one place to grow.
"""

import re

_HEX_RE = re.compile(r'^#?([0-9a-fA-F]{3}|[0-9a-fA-F]{6})$')


def normalize_hex(value):
    """Return a canonical ``#rrggbb`` string, or None when unusable."""
    if not isinstance(value, str):
        return None
    match = _HEX_RE.match(value.strip())
    if not match:
        return None
    digits = match.group(1)
    if len(digits) == 3:
        digits = ''.join(ch * 2 for ch in digits)
    return '#' + digits.lower()


def hex_to_rgb_triplet(value):
    """``'#0d6efd'`` -> ``'13,110,253'``; None when the value is not a hex colour.

    Bootstrap builds many utilities from ``--bs-primary-rgb`` (focus rings,
    ``*-subtle`` backgrounds, ``*-emphasis`` text).  Those only follow the
    school's brand colour when this triplet matches the chosen hex.
    """
    normalized = normalize_hex(value)
    if not normalized:
        return None
    digits = normalized[1:]
    return '%d,%d,%d' % (int(digits[0:2], 16),
                         int(digits[2:4], 16),
                         int(digits[4:6], 16))


def hex_to_rgba(value, alpha):
    """``('#0d6efd', 0.12)`` -> ``'rgba(13,110,253,0.12)'``; None when unusable."""
    triplet = hex_to_rgb_triplet(value)
    if not triplet:
        return None
    try:
        alpha_value = max(0.0, min(1.0, float(alpha)))
    except (TypeError, ValueError):
        return None
    return 'rgba(%s, %s)' % (triplet, ('%g' % alpha_value))


def brand_palette(primary, secondary=None):
    """CSS values for the brand colours, or None when the hex is unusable.

    Returns only the values the templates need, each already guarded so an
    unset/garbage colour simply leaves Bootstrap's defaults in place.
    """
    primary_hex = normalize_hex(primary)
    if not primary_hex:
        return None
    palette = {
        'primary': primary_hex,
        'primary_rgb': hex_to_rgb_triplet(primary_hex),
        'primary_subtle': hex_to_rgba(primary_hex, 0.12),
        'primary_border_subtle': hex_to_rgba(primary_hex, 0.32),
    }
    secondary_hex = normalize_hex(secondary)
    if secondary_hex:
        palette.update({
            'secondary': secondary_hex,
            'secondary_rgb': hex_to_rgb_triplet(secondary_hex),
            'secondary_subtle': hex_to_rgba(secondary_hex, 0.12),
            'secondary_border_subtle': hex_to_rgba(secondary_hex, 0.32),
        })
    return palette
