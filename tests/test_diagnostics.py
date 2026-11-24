"""Device diagnostics use the registry identifiers without exporting personal data."""

import asyncio
import json
from datetime import timedelta
from types import SimpleNamespace

import pytest
from zr_gas.const import DOMAIN, SOURCE_MP, SOURCE_PAY
from zr_gas.diagnostics import async_get_device_diagnostics
from zr_gas.models import ZrGasDeviceData


@pytest.mark.parametrize("source, as_mapping", [(SOURCE_MP, False), (SOURCE_PAY, True)])
def test_device_diagnostics_reads_only_own_identifier_and_never_exports_private_values(
    source, as_mapping
):
    private = "synthetic-do-not-export"
    entry = SimpleNamespace(
        entry_id="entry",
        title=private,
        data={"access_token": private, "user_id": private, "customers": [{"account": private}]},
        options={"extra": private},
        version=2,
        minor_version=1,
    )
    data = ZrGasDeviceData(source, 0.0, private, private, private, 0.0, 0.0, "204011", 0.0)
    data.meter_no = data.card_no = data.bar_code = private
    data.bills_degraded = True
    coordinator = SimpleNamespace(
        name=private,
        source=source,
        cust_name=private,
        cust_code=private,
        last_update_success=True,
        update_interval=timedelta(hours=6),
        data=data,
    )
    hass = SimpleNamespace(data={DOMAIN: {"entry": {"coordinators": {private: coordinator}}}})
    value = f"pay_{private}" if source == SOURCE_PAY else private
    identifiers = [("other_domain", "not-a-customer"), (DOMAIN, value)]
    device = (
        {"identifiers": identifiers} if as_mapping else SimpleNamespace(identifiers=identifiers)
    )

    result = asyncio.run(async_get_device_diagnostics(hass, entry, device))

    assert result["entry"] == {"version": 2, "minor_version": 1}
    assert result["coordinator"]["source"] == source
    assert result["coordinator"]["last_update_success"] is True
    assert result["data"]["bills_degraded"] is True
    assert result["data"]["monthly_stats_count"] == 0
    assert private not in json.dumps(result)


def test_diagnostics_does_not_select_a_foreign_integration_identifier():
    entry = SimpleNamespace(entry_id="entry", version=2, minor_version=1)
    other = SimpleNamespace(data=None)
    hass = SimpleNamespace(data={DOMAIN: {"entry": {"coordinators": {"customer": other}}}})
    device = SimpleNamespace(identifiers={("other_domain", "customer")})

    result = asyncio.run(async_get_device_diagnostics(hass, entry, device))

    assert result == {"entry": {"version": 2, "minor_version": 1}}
