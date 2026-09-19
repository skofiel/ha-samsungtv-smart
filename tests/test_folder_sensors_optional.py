"""The frame_art folder sensors are opt-in.

They mirror Home Assistant's platform:folder format so folder-gallery-card can
consume them directly. Most installs do not use that card, and what they see
instead is three entities on the TV's device page reporting the size in MB of a
local thumbnail cache — 0.0 MB until artwork is downloaded.

They stay available for anyone who wants them; they are just no longer created
enabled. Entities that already exist keep whatever state the registry holds, so
this only changes fresh installs.
"""

from custom_components.samsungtv_smart.sensor import (
    FrameArtFolderSensor,
    FrameArtMetadataSensor,
    FrameArtSensor,
)


def _enabled_default(entity_class) -> bool:
    """Read the property Home Assistant actually consults.

    `_attr_entity_registry_enabled_default` is not a plain class attribute:
    Home Assistant's CachedProperties metaclass turns every `_attr_*` into a
    descriptor, so reading it off the class hands back the descriptor rather
    than the value. The public property on an instance is the real answer.
    """
    return object.__new__(entity_class).entity_registry_enabled_default


def test_the_folder_sensors_are_not_enabled_by_default():
    assert _enabled_default(FrameArtFolderSensor) is False


def test_the_artwork_sensors_are_still_enabled_by_default():
    """Only the folder-size trio is opt-in; the artwork sensors are the point."""
    for entity_class in (FrameArtSensor, FrameArtMetadataSensor):
        assert _enabled_default(entity_class) is True
