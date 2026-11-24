"""Tests for zr_gas.sensor — _parse_timestamp helper."""

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from zr_gas.sensor import _parse_timestamp as _parse_timestamp_isolated


class TestParseTimestamp:
    def test_full_datetime(self):
        result = _parse_timestamp_isolated("2026-04-21 10:30:00")
        expected = datetime(2026, 4, 21, 10, 30, 0, tzinfo=ZoneInfo("Asia/Shanghai"))
        assert result == expected

    def test_date_only(self):
        result = _parse_timestamp_isolated("2026-04-21")
        expected = datetime(2026, 4, 21, 0, 0, 0, tzinfo=ZoneInfo("Asia/Shanghai"))
        assert result == expected

    def test_none_input(self):
        assert _parse_timestamp_isolated(None) is None

    def test_empty_string(self):
        assert _parse_timestamp_isolated("") is None

    def test_whitespace_only(self):
        assert _parse_timestamp_isolated("   ") is None

    def test_invalid_format(self):
        assert _parse_timestamp_isolated("not-a-date") is None

    def test_partial_date(self):
        assert _parse_timestamp_isolated("2026-04") is None

    def test_time_only(self):
        assert _parse_timestamp_isolated("10:30:00") is None

    def test_iso_format_with_T(self):
        """ISO format with T separator is not supported."""
        assert _parse_timestamp_isolated("2026-04-21T10:30:00") is None

    def test_datetime_with_whitespace(self):
        """Leading/trailing whitespace should be handled."""
        result = _parse_timestamp_isolated("  2026-04-21 10:30:00  ")
        expected = datetime(2026, 4, 21, 10, 30, 0, tzinfo=ZoneInfo("Asia/Shanghai"))
        assert result == expected

    def test_timezone_aware_result(self):
        """Result should always be timezone-aware."""
        result = _parse_timestamp_isolated("2026-01-01")
        assert result.tzinfo is not None

    def test_midnight_date(self):
        result = _parse_timestamp_isolated("2026-01-01 00:00:00")
        expected = datetime(2026, 1, 1, 0, 0, 0, tzinfo=ZoneInfo("Asia/Shanghai"))
        assert result == expected

    def test_end_of_day(self):
        result = _parse_timestamp_isolated("2026-12-31 23:59:59")
        expected = datetime(2026, 12, 31, 23, 59, 59, tzinfo=ZoneInfo("Asia/Shanghai"))
        assert result == expected

    def test_leap_year_date(self):
        result = _parse_timestamp_isolated("2024-02-29")
        expected = datetime(2024, 2, 29, 0, 0, 0, tzinfo=ZoneInfo("Asia/Shanghai"))
        assert result == expected

    def test_invalid_leap_year_date(self):
        """2025-02-29 is invalid (not a leap year)."""
        assert _parse_timestamp_isolated("2025-02-29") is None


def test_sensor_snapshot_pair_missing_values_and_zero():
    """Exercise real entity getters, including attributes for every sensor."""
    from types import SimpleNamespace

    from zr_gas.models import ZrGasDeviceData, ZrGasMeterSnapshot, ZrGasPayment
    from zr_gas.sensor import SENSOR_DESCRIPTIONS, ZrGasSensorEntity

    data = ZrGasDeviceData(
        source="mp",
        balance=0,
        cust_code="C01",
        cust_name="Example",
        cust_address="",
        monthly_usage=None,
        monthly_cost=None,
        period="",
        unit_price=None,
        max_gas=0,
        last_payment=0,
        last_record_time="2041-01-01",
        payment_history=[ZrGasPayment(amount=0, qty=None), ZrGasPayment()],
    )
    coordinator = SimpleNamespace(data=data)
    entities = {
        desc.key: ZrGasSensorEntity(coordinator, desc, "C01", "C01", "mp")
        for desc in SENSOR_DESCRIPTIONS
    }
    assert entities["qty_meter_balance"].native_value is None
    assert entities["meter_snapshot_time"].native_value is None
    assert entities["last_record_time"].native_value == datetime(
        2041, 1, 1, tzinfo=ZoneInfo("Asia/Shanghai")
    )
    assert entities["max_gas"].native_value == 0
    assert entities["last_payment"].native_value == 0
    assert entities["last_payment"].extra_state_attributes["payment_history"][0]["qty"] is None
    assert entities["last_payment"].extra_state_attributes["payment_history"][1]["amount"] is None
    as_of = datetime(2041, 2, 12, 4, 5, 6, tzinfo=ZoneInfo("Asia/Shanghai"))
    for volume in (0, 39.42):
        data.meter_snapshot = ZrGasMeterSnapshot(volume, as_of)
        assert entities["qty_meter_balance"].native_value == volume
        assert entities["meter_snapshot_time"].native_value == as_of
        assert entities["last_record_time"].native_value == datetime(
            2041, 1, 1, tzinfo=ZoneInfo("Asia/Shanghai")
        )
    assert len(entities) == 18
    for key, entity in entities.items():
        assert entity.extra_state_attributes["sensor_key"] == key
        assert entity._attr_unique_id == f"zr_gas_C01_{key}"
        assert entity.native_value is None or isinstance(
            entity.native_value, (int, float, str, datetime)
        )
    data.bills_degraded = True
    data.bill_missing_years = (2040,)
    for key in (
        "monthly_usage",
        "monthly_cost",
        "last_month_usage",
        "last_month_cost",
        "annual_usage",
        "annual_cost",
        "tier_remaining",
        "gas_price",
    ):
        assert entities[key].native_value is None
    attrs = entities["annual_usage"].extra_state_attributes
    assert attrs["history_complete"] is False and attrs["missing_years"] == [2040]


@pytest.mark.parametrize("source,prefix", [("mp", "zr_gas_"), ("pay", "zr_gas_pay_")])
def test_qa_preserves_legacy_sensor_keys_unique_ids_and_statistics(source, prefix):
    """保留旧17项的统计类别和标识，仅增加独立快照时间。"""
    from types import SimpleNamespace

    from homeassistant.components.sensor import SensorStateClass
    from zr_gas.sensor import SENSOR_DESCRIPTIONS, ZrGasSensorEntity

    legacy_keys = {
        "balance",
        "monthly_usage",
        "monthly_cost",
        "owe_money",
        "award_money",
        "gas_price",
        "max_gas",
        "last_record",
        "qty_meter_balance",
        "purch_times",
        "last_record_time",
        "last_payment",
        "last_month_usage",
        "last_month_cost",
        "annual_cost",
        "tier_remaining",
        "annual_usage",
    }
    total_keys = {"last_record", "qty_meter_balance", "purch_times", "annual_usage"}
    descriptions = {description.key: description for description in SENSOR_DESCRIPTIONS}
    assert len(SENSOR_DESCRIPTIONS) == 18
    assert set(descriptions) == legacy_keys | {"meter_snapshot_time"}
    for key, description in descriptions.items():
        expected_class = SensorStateClass.TOTAL if key in total_keys else None
        assert description.state_class == expected_class
        entity = ZrGasSensorEntity(SimpleNamespace(data=None), description, "C01", "C01", source)
        assert entity._attr_unique_id == f"{prefix}C01_{key}"


@pytest.mark.parametrize("has_snapshot", [False, True])
@pytest.mark.parametrize("crm_time", ["2040-01-02", None, "invalid"])
def test_qa_reading_and_cutoff_are_independent_without_cross_fallback(crm_time, has_snapshot):
    """CRM抄表时间和快照截止时间来源独立；任一缺失不借用另一个。"""
    from types import SimpleNamespace

    from zr_gas.models import ZrGasDeviceData, ZrGasMeterSnapshot
    from zr_gas.sensor import SENSOR_DESCRIPTIONS, ZrGasSensorEntity

    cutoff = datetime(2041, 2, 12, 4, 5, 6, tzinfo=ZoneInfo("Asia/Shanghai"))
    data = ZrGasDeviceData(
        source="mp",
        balance=0,
        cust_code="C01",
        cust_name="Example",
        cust_address="",
        monthly_usage=None,
        monthly_cost=None,
        period="",
        unit_price=None,
        last_record=0,
        last_record_time=crm_time,
        meter_snapshot=ZrGasMeterSnapshot(0, cutoff) if has_snapshot else None,
    )
    entities = {
        description.key: ZrGasSensorEntity(
            SimpleNamespace(data=data), description, "C01", "C01", "mp"
        )
        for description in SENSOR_DESCRIPTIONS
    }
    expected_reading = (
        datetime(2040, 1, 2, tzinfo=ZoneInfo("Asia/Shanghai")) if crm_time == "2040-01-02" else None
    )
    assert entities["last_record_time"].native_value == expected_reading
    assert entities["last_record_time"].extra_state_attributes["last_record"] == 0
    assert entities["last_record"].extra_state_attributes["last_record_time"] == crm_time
    assert entities["meter_snapshot_time"].native_value == (cutoff if has_snapshot else None)
    assert entities["qty_meter_balance"].native_value == (0 if has_snapshot else None)
    assert entities["meter_snapshot_time"].extra_state_attributes["data_source"] == (
        "queryLatestMeterInfo.dataTime"
    )
