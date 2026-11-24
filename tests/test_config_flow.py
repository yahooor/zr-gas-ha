"""Exercise real config-flow transitions with lightweight HA framework doubles."""

import importlib
import sys
from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest


class AlreadyConfigured(Exception):
    """Represent the HA control-flow exception raised during discovery."""


@pytest.fixture
def flow_module(monkeypatch):
    import homeassistant.config_entries as entries
    import homeassistant.core as core

    class ConfigFlow:
        def __init_subclass__(cls, **kwargs):
            super().__init_subclass__()

    monkeypatch.setattr(entries, "ConfigFlow", ConfigFlow, raising=False)
    monkeypatch.setattr(entries, "OptionsFlow", object, raising=False)
    monkeypatch.setattr(core, "callback", lambda value: value, raising=False)
    flow_result = ModuleType("homeassistant.data_entry_flow")
    flow_result.FlowResult = dict
    flow_result.FlowResultType = SimpleNamespace(CREATE_ENTRY="create_entry")
    monkeypatch.setitem(sys.modules, "homeassistant.data_entry_flow", flow_result)
    # Schema construction is not under test; HA owns voluptuous validation.
    monkeypatch.setitem(sys.modules, "voluptuous", MagicMock())
    sys.modules.pop("zr_gas.config_flow", None)
    module = importlib.import_module("zr_gas.config_flow")
    yield module
    sys.modules.pop("zr_gas.config_flow", None)


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ["token", "sms_code"])
async def test_already_configured_abort_is_not_relabelled_as_connection_error(flow_module, method):
    flow = flow_module.ZrGasConfigFlow()
    flow.hass = SimpleNamespace()
    api = SimpleNamespace(check_token=AsyncMock(), login_with_sms=AsyncMock())
    flow._api = api
    flow.async_step_discover = AsyncMock(side_effect=AlreadyConfigured("already_configured"))
    flow.async_show_form = MagicMock()
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(flow_module, "ZrGasMpApi", MagicMock(return_value=api))
        with pytest.raises(AlreadyConfigured, match="already_configured"):
            if method == "token":
                await flow.async_step_token({"access_token": "synthetic", "user_id": "test"})
            else:
                await flow.async_step_sms_code({"sms_code": "synthetic"})
    flow.async_show_form.assert_not_called()


@pytest.mark.asyncio
async def test_discovery_closes_login_session_before_duplicate_abort(flow_module):
    from zr_gas.models import ZrGasCustomer

    flow = flow_module.ZrGasConfigFlow()
    api = SimpleNamespace(
        user_id="test",
        get_bind_gas_cust_list=AsyncMock(return_value=[ZrGasCustomer("C01", "Example")]),
        close_login_session=AsyncMock(),
    )
    flow._api = api
    flow.async_set_unique_id = AsyncMock()

    def abort_if_configured():
        api.close_login_session.assert_awaited_once()
        raise AlreadyConfigured("already_configured")

    flow._abort_if_unique_id_configured = abort_if_configured
    with pytest.raises(AlreadyConfigured):
        await flow.async_step_discover()
    flow.async_set_unique_id.assert_awaited_once_with("mp_test")
