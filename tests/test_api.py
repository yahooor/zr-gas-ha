"""Tests for zr_gas.api — signature generation."""

import hashlib

import pytest

from zr_gas.const import SIGN_SALT
from zr_gas.api import ZrGasAPI


class TestGenerateSignature:
    """Tests for ZrGasAPI._generate_signature(param, timestamp)."""

    def _md5(self, raw: str) -> str:
        return hashlib.md5(raw.encode("utf-8")).hexdigest()

    def test_known_values(self):
        api = ZrGasAPI(None)
        param = "test"
        timestamp = "1234567890"
        result = api._generate_signature(param, timestamp)
        expected = self._md5(f"{param}{SIGN_SALT}{timestamp}")
        assert result == expected
        # Also verify the raw string
        assert f"{param}{SIGN_SALT}{timestamp}" == "testyph12345678901234567890"

    def test_empty_param(self):
        api = ZrGasAPI(None)
        result = api._generate_signature("", "9999999999")
        expected = self._md5(f"yph12345678909999999999")
        assert result == expected

    def test_salt_value(self):
        assert SIGN_SALT == "yph1234567890"

    def test_chinese_param(self):
        api = ZrGasAPI(None)
        param = "用户123"
        ts = "1700000000000"
        result = api._generate_signature(param, ts)
        expected = self._md5(f"{param}{SIGN_SALT}{ts}")
        assert result == expected

    def test_different_params_different_signatures(self):
        api = ZrGasAPI(None)
        ts = "1234567890"
        assert api._generate_signature("param1", ts) != api._generate_signature("param2", ts)

    def test_different_timestamps_different_signatures(self):
        api = ZrGasAPI(None)
        param = "userId123"
        assert api._generate_signature(param, "1000") != api._generate_signature(param, "2000")

    def test_signature_is_32_chars_hex(self):
        api = ZrGasAPI(None)
        sig = api._generate_signature("test", "12345")
        assert len(sig) == 32
        assert all(c in "0123456789abcdef" for c in sig)
