import re

def clean_street_name(name: str) -> str:
    """Strip common Ukrainian road prefix/suffix helpers & parenthesized details."""
    if not name:
        return ""
    # Strip parenthesized text first (e.g. "Вишнева вулиця (Солом'янський р-н)" -> "Вишнева вулиця")
    name = re.sub(r'\s*\(.*?\)\s*', ' ', name)
    # Strip multiple spaces and trim edge spaces first so starting anchors work correctly
    name = re.sub(r'\s+', ' ', name).strip()
    # Strip common road type prefixes and suffixes
    name = re.sub(
        r'^(вулиця|вул\.|проспект|пр\.|провулок|пров\.|площа|майдан|бульвар|бул\.|шосе|дорога)\s+',
        '',
        name,
        flags=re.IGNORECASE
    )
    name = re.sub(
        r'\s+(вулиця|вул\.|проспект|пр\.|провулок|пров\.|площа|майдан|бульвар|бул\.|шосе|дорога)$',
        '',
        name,
        flags=re.IGNORECASE
    )
    return name.strip()

def normalize_house(h: str) -> str:
    """Normalize house number for exact matching (lowercase, no symbols/spaces, preserves Ukrainian letters)."""
    if not h:
        return ""
    return re.sub(r'[^a-zA-Zа-яА-ЯіїєґІЇЄҐ0-9]', '', h).lower()

def extract_numeric_part(house_str: str) -> int:
    """Extract first sequence of digits from a house number, default to 1."""
    if not house_str:
        return 1
    match = re.search(r'\d+', house_str)
    return int(match.group()) if match else 1
