"""Every entity translation key must resolve to a name in every shipped language.

A `_attr_translation_key` with no matching entry does not raise: Home Assistant
silently falls back to the device-class name, or to the device name alone, and
the entity shows up in the UI with the wrong label or no label at all. That is a
mute failure, and it is exactly the kind this suite exists to catch.

en.json is the canonical fallback, so a key missing there is a bug. The other
languages are checked for *shape* — no invented keys, no empty names — but are
allowed to be incomplete, since Home Assistant falls back to English per key.
"""

import ast
import json
from pathlib import Path

import pytest

COMPONENT = Path(__file__).parents[1] / "custom_components" / "samsungtv_smart"
TRANSLATIONS = COMPONENT / "translations"

# Platform module -> Home Assistant entity domain.
PLATFORMS = {
    "button.py": "button",
    "number.py": "number",
    "select.py": "select",
    "sensor.py": "sensor",
    "switch.py": "switch",
}

# Keys that resolve from something other than a literal in the class body.
# IP_CONTROL_PICTURE_SETTINGS drives five sliders from `setting.key`.
DYNAMIC_KEYS = {
    "number": {"contrast", "brightness", "sharpness", "color", "tint"},
}


def _declared_keys() -> dict[str, set[str]]:
    """Collect every translation key the integration assigns, by domain."""
    found: dict[str, set[str]] = {}
    for filename, domain in PLATFORMS.items():
        keys = set(DYNAMIC_KEYS.get(domain, set()))
        tree = ast.parse((COMPONENT / filename).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            target = None
            if isinstance(node, ast.Assign) and len(node.targets) == 1:
                target = node.targets[0]
            elif isinstance(node, ast.AnnAssign):
                target = node.target

            name = None
            if isinstance(target, ast.Name):
                name = target.id
            elif isinstance(target, ast.Attribute):
                name = target.attr
            if name != "_attr_translation_key":
                continue

            if isinstance(node.value, ast.Constant) and isinstance(
                node.value.value, str
            ):
                keys.add(node.value.value)
        found[domain] = keys
    return found


def _language(code: str) -> dict:
    return json.loads((TRANSLATIONS / f"{code}.json").read_text(encoding="utf-8"))


DECLARED = _declared_keys()
LANGUAGES = sorted(p.stem for p in TRANSLATIONS.glob("*.json"))


def test_the_integration_declares_translation_keys_at_all():
    """Guards the AST walk above: a rename that breaks it must not pass silently."""
    assert sum(len(keys) for keys in DECLARED.values()) >= 20


@pytest.mark.parametrize("domain", sorted(DECLARED))
def test_english_names_every_declared_key(domain):
    """en.json is the fallback for every other language, so it must be complete."""
    entity = _language("en").get("entity", {}).get(domain, {})
    missing = sorted(DECLARED[domain] - set(entity))
    assert not missing, f"en.json is missing entity.{domain}: {missing}"


@pytest.mark.parametrize("domain", sorted(DECLARED))
def test_spanish_names_every_declared_key(domain):
    """Spanish is maintained in full alongside English."""
    entity = _language("es").get("entity", {}).get(domain, {})
    missing = sorted(DECLARED[domain] - set(entity))
    assert not missing, f"es.json is missing entity.{domain}: {missing}"


@pytest.mark.parametrize("code", LANGUAGES)
def test_no_language_invents_a_key(code):
    """A key no entity declares is dead weight, usually a typo or a rename."""
    for domain, entries in _language(code).get("entity", {}).items():
        assert domain in DECLARED, f"{code}.json: unknown entity domain {domain!r}"
        unknown = sorted(set(entries) - DECLARED[domain])
        assert not unknown, f"{code}.json: entity.{domain} has unused keys {unknown}"


@pytest.mark.parametrize("code", LANGUAGES)
def test_every_name_is_a_non_empty_string(code):
    for domain, entries in _language(code).get("entity", {}).items():
        for key, value in entries.items():
            name = value.get("name")
            assert (
                isinstance(name, str) and name.strip()
            ), f"{code}.json: entity.{domain}.{key}.name is empty"


@pytest.mark.parametrize("code", LANGUAGES)
def test_translations_are_valid_json_and_utf8(code):
    _language(code)
