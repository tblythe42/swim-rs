"""Tests for swimrs.container.components.ingestor module.

Tests cover:
- _parse_single_csv(): date parsing for all instrument types (landsat, sentinel, ecostress)
- Edge cases: unknown instrument, non-date columns, empty CSVs, single-field CSVs
"""

import pandas as pd
import pytest

from swimrs.container.components.ingestor import _parse_single_csv


@pytest.fixture
def known_uids():
    return {"US-FPe", "FR-Aur", "AU-DaS"}


class TestParseSingleCsvLandsat:
    """Date parsing for Landsat instrument (suffix YYYYMMDD after underscore)."""

    def test_basic_landsat_parsing(self, tmp_path, known_uids):
        """Landsat columns like lc08_042030_20210118 parse date from last segment."""
        csv = tmp_path / "etf_US-FPe_irr_2021.csv"
        csv.write_text("sid,lc08_042030_20210118,lc08_042030_20210307\nUS-FPe,0.45,0.82\n")
        result = _parse_single_csv(csv, "sid", "landsat", known_uids, None)
        assert len(result) == 1
        s = result[0]
        assert s.name == "US-FPe"
        assert len(s) == 2
        assert pd.Timestamp("2021-01-18") in s.index
        assert pd.Timestamp("2021-03-07") in s.index
        assert s[pd.Timestamp("2021-01-18")] == pytest.approx(0.45)
        assert s[pd.Timestamp("2021-03-07")] == pytest.approx(0.82)

    def test_landsat_skips_non_date_cols(self, tmp_path, known_uids):
        """Non-date columns like system:index are skipped."""
        csv = tmp_path / "etf.csv"
        csv.write_text("sid,system:index,lc08_042030_20210118\nUS-FPe,abc,0.5\n")
        result = _parse_single_csv(csv, "sid", "landsat", known_uids, None)
        assert len(result) == 1
        assert len(result[0]) == 1

    def test_landsat_multiple_fields(self, tmp_path, known_uids):
        """Multiple rows yield multiple Series."""
        csv = tmp_path / "etf.csv"
        csv.write_text("sid,lc08_042030_20210118\nUS-FPe,0.5\nFR-Aur,0.7\n")
        result = _parse_single_csv(csv, "sid", "landsat", known_uids, None)
        assert len(result) == 2
        names = {s.name for s in result}
        assert names == {"US-FPe", "FR-Aur"}


class TestParseSingleCsvSentinel:
    """Date parsing for Sentinel instrument (prefix YYYYMMDD before underscore)."""

    def test_basic_sentinel_parsing(self, tmp_path, known_uids):
        """Sentinel columns like 20210118T... parse date from first 8 chars."""
        csv = tmp_path / "ndvi.csv"
        csv.write_text("sid,20210118T100000_S2A,20210307T100000_S2A\nFR-Aur,0.3,0.6\n")
        result = _parse_single_csv(csv, "sid", "sentinel", known_uids, None)
        assert len(result) == 1
        s = result[0]
        assert s.name == "FR-Aur"
        assert pd.Timestamp("2021-01-18") in s.index
        assert pd.Timestamp("2021-03-07") in s.index


class TestParseSingleCsvEcostress:
    """Date parsing for ECOSTRESS instrument (suffix YYYYMMDD after underscore)."""

    def test_basic_ecostress_parsing(self, tmp_path, known_uids):
        """ECOSTRESS columns like ETF_20210118 parse date from last segment."""
        csv = tmp_path / "etf_US-FPe_no_mask_2021.csv"
        csv.write_text("sid,ETF_20210115,ETF_20210203,ETF_20210415\nUS-FPe,0.32,0.41,0.95\n")
        result = _parse_single_csv(csv, "sid", "ecostress", known_uids, None)
        assert len(result) == 1
        s = result[0]
        assert s.name == "US-FPe"
        assert len(s) == 3
        assert pd.Timestamp("2021-01-15") in s.index
        assert pd.Timestamp("2021-02-03") in s.index
        assert pd.Timestamp("2021-04-15") in s.index
        assert s[pd.Timestamp("2021-04-15")] == pytest.approx(0.95)

    def test_ecostress_multiple_sites(self, tmp_path, known_uids):
        """Multiple rows in one CSV produce multiple Series."""
        csv = tmp_path / "etf.csv"
        csv.write_text("sid,ETF_20210115,ETF_20210203\nUS-FPe,0.3,0.4\nAU-DaS,0.8,0.9\n")
        result = _parse_single_csv(csv, "sid", "ecostress", known_uids, None)
        assert len(result) == 2
        names = {s.name for s in result}
        assert names == {"US-FPe", "AU-DaS"}

    def test_ecostress_filters_by_fields_set(self, tmp_path, known_uids):
        """Only returns fields in the fields_set allowlist."""
        csv = tmp_path / "etf.csv"
        csv.write_text("sid,ETF_20210115\nUS-FPe,0.3\nAU-DaS,0.8\n")
        result = _parse_single_csv(csv, "sid", "ecostress", known_uids, {"AU-DaS"})
        assert len(result) == 1
        assert result[0].name == "AU-DaS"

    def test_ecostress_skips_unknown_uids(self, tmp_path, known_uids):
        """Fields not in known_uids are silently skipped."""
        csv = tmp_path / "etf.csv"
        csv.write_text("sid,ETF_20210115\nUNKNOWN-SITE,0.5\n")
        result = _parse_single_csv(csv, "sid", "ecostress", known_uids, None)
        assert len(result) == 0

    def test_ecostress_single_field_csv(self, tmp_path, known_uids):
        """Single-field CSV where the first column header IS the field ID."""
        csv = tmp_path / "etf.csv"
        csv.write_text("US-FPe,ETF_20210115,ETF_20210203\n,0.3,0.4\n")
        result = _parse_single_csv(csv, "sid", "ecostress", known_uids, None)
        assert len(result) == 1
        assert result[0].name == "US-FPe"

    def test_ecostress_handles_nan_values(self, tmp_path, known_uids):
        """NaN values in data are preserved in the output Series."""
        csv = tmp_path / "etf.csv"
        csv.write_text("sid,ETF_20210115,ETF_20210203\nUS-FPe,,0.4\n")
        result = _parse_single_csv(csv, "sid", "ecostress", known_uids, None)
        assert len(result) == 1
        s = result[0]
        assert pd.isna(s[pd.Timestamp("2021-01-15")])
        assert s[pd.Timestamp("2021-02-03")] == pytest.approx(0.4)

    def test_ecostress_sorted_by_date(self, tmp_path, known_uids):
        """Output Series is sorted by date even if CSV columns are not."""
        csv = tmp_path / "etf.csv"
        csv.write_text("sid,ETF_20210415,ETF_20210115,ETF_20210203\nUS-FPe,0.9,0.3,0.5\n")
        result = _parse_single_csv(csv, "sid", "ecostress", known_uids, None)
        s = result[0]
        assert list(s.index) == [
            pd.Timestamp("2021-01-15"),
            pd.Timestamp("2021-02-03"),
            pd.Timestamp("2021-04-15"),
        ]
        # Values follow the sorted order
        assert s.iloc[0] == pytest.approx(0.3)
        assert s.iloc[1] == pytest.approx(0.5)
        assert s.iloc[2] == pytest.approx(0.9)

    def test_ecostress_deduplicates_dates(self, tmp_path, known_uids):
        """Duplicate dates are resolved by taking the max value."""
        csv = tmp_path / "etf.csv"
        csv.write_text("sid,ETF_20210115,PTJPL_20210115\nUS-FPe,0.3,0.5\n")
        result = _parse_single_csv(csv, "sid", "ecostress", known_uids, None)
        s = result[0]
        assert len(s) == 1
        assert s.iloc[0] == pytest.approx(0.5)


class TestParseSingleCsvEdgeCases:
    """Edge cases common across instrument types."""

    def test_empty_csv_returns_empty(self, tmp_path, known_uids):
        """An empty CSV returns an empty list."""
        csv = tmp_path / "empty.csv"
        csv.write_text("")
        result = _parse_single_csv(csv, "sid", "ecostress", known_uids, None)
        assert result == []

    def test_no_data_columns_returns_empty(self, tmp_path, known_uids):
        """CSV with only metadata columns returns empty list."""
        csv = tmp_path / "meta.csv"
        csv.write_text("sid,system:index,.geo\nUS-FPe,abc,{}\n")
        result = _parse_single_csv(csv, "sid", "landsat", known_uids, None)
        assert result == []

    def test_unknown_instrument_returns_empty(self, tmp_path, known_uids):
        """Unrecognized instrument yields no parsed dates, returns empty."""
        csv = tmp_path / "etf.csv"
        csv.write_text("sid,ETF_20210115\nUS-FPe,0.3\n")
        result = _parse_single_csv(csv, "sid", "unknown_sat", known_uids, None)
        assert result == []

    def test_nonexistent_file_returns_empty(self, tmp_path, known_uids):
        """Missing file returns empty list (no exception)."""
        csv = tmp_path / "does_not_exist.csv"
        result = _parse_single_csv(csv, "sid", "ecostress", known_uids, None)
        assert result == []
