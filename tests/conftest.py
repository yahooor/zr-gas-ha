"""Shared fixtures and path setup for zr_gas unit tests."""

import importlib
import sys
import types
from pathlib import Path

# ── Path setup ────────────────────────────────────────────────────────
# Add custom_components to sys.path so we can import zr_gas.models etc.
_CC_DIR = str(Path(__file__).resolve().parent.parent / "custom_components")
if _CC_DIR not in sys.path:
    sys.path.insert(0, _CC_DIR)


# ── Mock homeassistant before any submodule import ────────────────────
# zr_gas/__init__.py imports homeassistant, but zr_gas.models and
# zr_gas.const are pure Python.  We mock the bare minimum so that
# importing the package doesn't crash.

def _setup_ha_mocks():
    """Create minimal homeassistant mock modules so zr_gas can be imported."""
    ha = types.ModuleType("homeassistant")
    ha.__path__ = []  # make it look like a package
    sys.modules["homeassistant"] = ha

    submods = {
        "homeassistant.config_entries": types.ModuleType("homeassistant.config_entries"),
        "homeassistant.const": types.ModuleType("homeassistant.const"),
        "homeassistant.core": types.ModuleType("homeassistant.core"),
        "homeassistant.exceptions": types.ModuleType("homeassistant.exceptions"),
        "homeassistant.helpers": types.ModuleType("homeassistant.helpers"),
        "homeassistant.helpers.aiohttp_client": types.ModuleType("homeassistant.helpers.aiohttp_client"),
        "homeassistant.helpers.issue_registry": types.ModuleType("homeassistant.helpers.issue_registry"),
        "homeassistant.helpers.update_coordinator": types.ModuleType("homeassistant.helpers.update_coordinator"),
        "homeassistant.util": types.ModuleType("homeassistant.util"),
        "homeassistant.util.dt": types.ModuleType("homeassistant.util.dt"),
        "homeassistant.components": types.ModuleType("homeassistant.components"),
        "homeassistant.components.sensor": types.ModuleType("homeassistant.components.sensor"),
        "homeassistant.helpers.entity_platform": types.ModuleType("homeassistant.helpers.entity_platform"),
    }
    for name, mod in submods.items():
        sys.modules[name] = mod

    # Wire up parent references
    ha.config_entries = submods["homeassistant.config_entries"]
    ha.const = submods["homeassistant.const"]
    ha.core = submods["homeassistant.core"]
    ha.exceptions = submods["homeassistant.exceptions"]
    ha.helpers = submods["homeassistant.helpers"]
    ha.util = submods["homeassistant.util"]
    ha.components = submods["homeassistant.components"]

    submods["homeassistant.helpers"].aiohttp_client = submods["homeassistant.helpers.aiohttp_client"]
    submods["homeassistant.helpers"].issue_registry = submods["homeassistant.helpers.issue_registry"]
    submods["homeassistant.helpers"].update_coordinator = submods["homeassistant.helpers.update_coordinator"]
    submods["homeassistant.helpers"].entity_platform = submods["homeassistant.helpers.entity_platform"]
    submods["homeassistant.util"].dt = submods["homeassistant.util.dt"]
    submods["homeassistant.components"].sensor = submods["homeassistant.components.sensor"]

    # Provide dt utilities
    from datetime import datetime
    from zoneinfo import ZoneInfo
    dt_mod = submods["homeassistant.util.dt"]
    dt_mod.DEFAULT_TIME_ZONE = ZoneInfo("Asia/Shanghai")
    dt_mod.now = lambda: datetime.now(tz=dt_mod.DEFAULT_TIME_ZONE)

    # Provide Platform enum-like
    const_mod = submods["homeassistant.const"]
    const_mod.Platform = type("Platform", (), {"SENSOR": "sensor", "BUTTON": "button"})
    const_mod.UnitOfVolume = type("UnitOfVolume", (), {"CUBIC_METERS": "m³"})

    # Provide SensorDeviceClass, SensorEntity, etc.
    sensor_mod = submods["homeassistant.components.sensor"]
    sensor_mod.SensorDeviceClass = type("SensorDeviceClass", (), {
        "MONETARY": "monetary",
        "GAS": "gas",
        "TIMESTAMP": "timestamp",
    })
    sensor_mod.SensorEntity = type("SensorEntity", (), {})
    sensor_mod.SensorEntityDescription = type("SensorEntityDescription", (), {})
    sensor_mod.SensorStateClass = type("SensorStateClass", (), {
        "TOTAL": "total",
    })

    # Provide ConfigEntry, UpdateFailed, etc.
    submods["homeassistant.config_entries"].ConfigEntry = type("ConfigEntry", (), {})
    submods["homeassistant.core"].HomeAssistant = type("HomeAssistant", (), {})
    submods["homeassistant.exceptions"].ConfigEntryAuthFailed = type("ConfigEntryAuthFailed", (Exception,), {})
    # DataUpdateCoordinator[T] must be subscriptable (generic syntax)
    class _GenericBase:
        def __class_getitem__(cls, item):
            return cls
    submods["homeassistant.helpers.update_coordinator"].DataUpdateCoordinator = type(
        "DataUpdateCoordinator", (_GenericBase,), {}
    )
    submods["homeassistant.helpers.update_coordinator"].UpdateFailed = type("UpdateFailed", (Exception,), {})
    submods["homeassistant.helpers.entity_platform"].AddEntitiesCallback = type("AddEntitiesCallback", (), {})
    submods["homeassistant.helpers.aiohttp_client"].async_get_clientsession = lambda hass: None
    submods["homeassistant.helpers.issue_registry"].async_create_issue = lambda *a, **k: None
    submods["homeassistant.helpers.issue_registry"].async_delete_issue = lambda *a, **k: None
    submods["homeassistant.helpers.issue_registry"].IssueSeverity = type("IssueSeverity", (), {"WARNING": "warning"})
    submods["homeassistant.helpers"].CoordinatorEntity = type("CoordinatorEntity", (), {})

_setup_ha_mocks()

import pytest

from zr_gas.models import TierConfig


@pytest.fixture
def tier_config_default():
    """Default TierConfig matching Zhangjiajie residential gas pricing."""
    return TierConfig()


@pytest.fixture
def tier_config_custom():
    """Custom TierConfig with non-default values."""
    return TierConfig(
        tier_2_start=300.0,
        tier_3_start=1200.0,
        tier_1_price=2.50,
        tier_2_price=3.00,
        tier_3_price=4.00,
        tier_cycle_start_md="07-01",
    )
