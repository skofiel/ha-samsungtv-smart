"""Global fixtures for integration_blueprint integration."""

# Fixtures allow you to replace functions with a Mock object. You can perform
# many options via the Mock to reflect a particular behavior from the original
# function that you want to see without going through the function's actual logic.
# Fixtures can either be passed into tests as parameters, or if autouse=True, they
# will automatically be used across all tests.
#
# Fixtures that are defined in conftest.py are available across all tests. You can also
# define fixtures within a particular test file to scope them locally.
#
# pytest_homeassistant_custom_component provides some fixtures that are provided by
# Home Assistant core. You can find those fixture definitions here:
# https://github.com/MatthewFlamm/pytest-homeassistant-custom-component/blob/master/pytest_homeassistant_custom_component/common.py
#
# See here for more info: https://docs.pytest.org/en/latest/fixture.html (note that
# pytest includes fixtures OOB which you can use as defined on this page)
import sys
from types import ModuleType
from unittest.mock import patch

import pytest

pytest_plugins = "pytest_homeassistant_custom_component"


def _install_pysmartthings_stub() -> None:
    """Install a complete ``pysmartthings`` stub before any test module loads.

    ``pysmartthings`` is supplied at runtime by Home Assistant's own SmartThings
    integration (this integration only declares it under ``after_dependencies``),
    so it is deliberately absent from requirements_test.txt and the component
    modules that import it need a stand-in here.

    It has to live in the root conftest, which pytest imports before collecting
    any test module. Several test modules used to install their own stub behind
    an ``if "pysmartthings" not in sys.modules`` guard, and three of them only
    defined ``SmartThings``. Whichever module pytest imported first won, so
    ``tests/api/test_smartthings_hue_sync.py`` installed the incomplete stub and
    ``tests/test_ipcontrol_channel_coordinator.py`` then failed to import
    ``sensor.py`` ("cannot import name 'Attribute'"), aborting collection for
    the whole suite. One complete stub, installed first, makes the result
    independent of collection order.
    """
    if "pysmartthings" in sys.modules:
        return

    module = ModuleType("pysmartthings")

    class _Names:
        """Resolve any attribute to its own name.

        The integration only ever passes these through to the SmartThings REST
        API as strings (``Capability.SWITCH`` -> ``"SWITCH"``), and deliberately
        avoids depending on enum members that move between library versions.
        """

        def __getattr__(self, name):
            return name

    module.Attribute = _Names()
    module.Capability = _Names()
    module.Command = _Names()
    module.SmartThings = object
    sys.modules["pysmartthings"] = module


_install_pysmartthings_stub()


# This fixture enables loading custom integrations in all tests.
# Remove to enable selective use of this fixture
@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    yield


# This fixture is used to prevent HomeAssistant from attempting to create and dismiss persistent
# notifications. These calls would fail without this fixture since the persistent_notification
# integration is never loaded during a test.
@pytest.fixture(name="skip_notifications", autouse=True)
def skip_notifications_fixture():
    """Skip notification calls."""
    with patch("homeassistant.components.persistent_notification.async_create"), patch(
        "homeassistant.components.persistent_notification.async_dismiss"
    ):
        yield
