import pandas as pd

PLACES = {
    "city",
    "town",
    "village",
    "hamlet",
    "isolated_dwelling",
}

RESIDENTIAL = {
    "residential",
    "apartments",
    "dormitory",
    "house",
    "detached",
    "semidetached_house",
    "terrace",
    "bungalow",
    "farm",
}

OFFICE_VALUES = {
    "financial",
    "government",
    "company",
    "it",
    "telecommunication",
    "energy_supplier",
    "insurance",
    "employment_agency",
    "logistics",
    "research",
    "yes",
    "lawyer",
    "notary",
    "accountant",
    "architect",
    "estate_agent",
    "tax_advisor",
    "consulting",
    "advertising_agency",
    "surveyor",
    "ngo",
    "association",
    "charity",
    "foundation",
    "religion",
    "political_party",
}

FOOD_SHOPS = {
    "convenience",
    "grocery",
    "greengrocer",
    "butcher",
    "bakery",
    "pastry",
    "deli",
    "confectionery",
    "beverages",
    "alcohol",
    "seafood",
    "farm",
    "dairy",
    "kiosk",
    "general",
    "frozen_food",
    "tea",
    "coffee",
    "cheese",
    "nuts",
    "spices",
    "health_food",
}

LARGE_RETAIL = {
    "supermarket",
    "department_store",
    "mall",
    "wholesale",
}

PERSONAL_SERVICES = {
    "beauty",
    "hairdresser",
    "massage",
    "tattoo",
    "laundry",
    "dry_cleaning",
    "tailor",
    "optician",
}

FOOD_SERVICES = {
    "restaurant",
    "cafe",
    "fast_food",
    "food_court",
}

WILDCARD_TAGS = {
    "office",
    "shop",
    "industrial",
}

def get_osm_tags(buildings=True):
    """
    Возвращает набор тегов для загрузки объектов.

    Набор соответствует rules.yaml.
    """
    tags = {
        "amenity": ["bank", "atm", *sorted(FOOD_SERVICES)],
        "office": True,
        "shop": True,
        "place": sorted(PLACES),
        "building": sorted(RESIDENTIAL),
        "man_made": "works",
        "industrial": True,
        "landuse": "industrial",
    }

    return tags

NAME_KEYS = {"name", "alt_name", "official_name", "short_name", "old_name"}
KEEP_LANGS = {"ru", "en"}

def keep_tag(key, value):
    """Оставляет только заполненные свойства и нужные языки названий."""
    if value is None:
        return False

    if not isinstance(value, (list, dict)) and pd.isna(value):
        return False
    
    if isinstance(value, str) and not value.strip():
        return False

    # Удаляем name:de, alt_name:fr и подобные языковые варианты,
    # оставляя name:ru, name:en, alt_name:ru и т. д.
    for name_key in NAME_KEYS:
        prefix = f"{name_key}:"
        if key.startswith(prefix):
            language = key[len(prefix):].split(":")[0].split("-")[0]
            return language in KEEP_LANGS
    return True

def pick_name(t, osm_id):
    for key in ("name:ru", "name", "official_name:ru", "official_name"):
        v = t.get(key)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return f"Район OSM {osm_id}"