from finstock.models import derive_symbol


def test_derive_symbol_strips_t212_suffix():
    assert derive_symbol("AAPL_US_EQ", {}) == "AAPL"


def test_derive_symbol_uses_override_when_present():
    overrides = {"VOD_LON_EQ": "VOD.L"}
    assert derive_symbol("VOD_LON_EQ", overrides) == "VOD.L"
