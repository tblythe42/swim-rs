"""Tests for swimrs.container.schema module.

Tests cover:
- get_zarr_path(): all 5 category branches, optional segments
- validate_path(): all return branches
- list_all_paths(): structure and self-validation
- required_for_calibration() / required_for_forward_run(): lengths and propagation
- get_rooting_depth(): known codes, use_max, unknown fallback
"""

from swimrs.container.schema import (
    GLC10_TO_MODIS_ROOTING,
    ROOTING_DEPTH_BY_LULC,
    UNKNOWN_ROOTING_DEFAULT,
    SwimSchema,
    get_rooting_code,
    get_rooting_depth,
    is_cropland,
)


class TestGetZarrPath:
    """Tests for SwimSchema.get_zarr_path()."""

    def test_remote_sensing_full_path(self):
        """Remote sensing with all optional segments produces correct path."""
        path = SwimSchema.get_zarr_path(
            "remote_sensing", "etf", instrument="landsat", model="ssebop", mask="irr"
        )
        assert path == "remote_sensing/etf/landsat/ssebop/irr"

    def test_remote_sensing_no_model(self):
        """NDVI path omits model segment."""
        path = SwimSchema.get_zarr_path("remote_sensing", "ndvi", instrument="landsat", mask="irr")
        assert path == "remote_sensing/ndvi/landsat/irr"

    def test_remote_sensing_no_optional_segments(self):
        """Remote sensing with no optional segments returns category/parameter."""
        path = SwimSchema.get_zarr_path("remote_sensing", "ndvi")
        assert path == "remote_sensing/ndvi"

    def test_meteorology_with_source(self):
        """Meteorology path includes source before parameter."""
        path = SwimSchema.get_zarr_path("meteorology", "eto", source="gridmet")
        assert path == "meteorology/gridmet/eto"

    def test_meteorology_no_source(self):
        """Meteorology without source omits source segment."""
        path = SwimSchema.get_zarr_path("meteorology", "eto")
        assert path == "meteorology/eto"

    def test_properties_category(self):
        """Properties category produces category/parameter path."""
        path = SwimSchema.get_zarr_path("properties", "soils/awc")
        assert path == "properties/soils/awc"

    def test_derived_category(self):
        """Derived category produces category/parameter path."""
        path = SwimSchema.get_zarr_path("derived", "dynamics/ke_max")
        assert path == "derived/dynamics/ke_max"

    def test_snow_category(self):
        """Snow category produces category/parameter path."""
        path = SwimSchema.get_zarr_path("snow", "swe")
        assert path == "snow/swe"


class TestValidatePath:
    """Tests for SwimSchema.validate_path()."""

    def test_empty_path_returns_false(self):
        """Empty string is invalid."""
        assert SwimSchema.validate_path("") is False

    def test_remote_sensing_too_few_parts(self):
        """Remote sensing path with < 3 parts is invalid."""
        assert SwimSchema.validate_path("remote_sensing/ndvi") is False

    def test_remote_sensing_invalid_parameter(self):
        """Remote sensing with unknown parameter is invalid."""
        assert SwimSchema.validate_path("remote_sensing/bogus/landsat/irr") is False

    def test_remote_sensing_invalid_instrument(self):
        """Remote sensing with unknown instrument is invalid."""
        assert SwimSchema.validate_path("remote_sensing/ndvi/fake_instrument/irr") is False

    def test_remote_sensing_valid(self):
        """Valid remote sensing path passes."""
        assert SwimSchema.validate_path("remote_sensing/ndvi/landsat/irr") is True

    def test_meteorology_too_few_parts(self):
        """Meteorology path with < 3 parts is invalid."""
        assert SwimSchema.validate_path("meteorology/gridmet") is False

    def test_meteorology_invalid_source(self):
        """Meteorology with unknown source is invalid."""
        assert SwimSchema.validate_path("meteorology/fake_source/eto") is False

    def test_meteorology_valid(self):
        """Valid meteorology path passes."""
        assert SwimSchema.validate_path("meteorology/gridmet/eto") is True

    def test_properties_valid(self):
        """Properties path with >= 2 parts is valid."""
        assert SwimSchema.validate_path("properties/soils/awc") is True

    def test_derived_valid(self):
        """Derived category is valid with >= 1 part."""
        assert SwimSchema.validate_path("derived/dynamics/ke_max") is True

    def test_snow_valid(self):
        """Snow category is valid."""
        assert SwimSchema.validate_path("snow/snodas/swe") is True

    def test_unknown_category_returns_false(self):
        """Unknown top-level category is invalid."""
        assert SwimSchema.validate_path("unknown_category/foo") is False


class TestListAllPaths:
    """Tests for SwimSchema.list_all_paths()."""

    def test_non_empty(self):
        """list_all_paths returns a non-empty list."""
        paths = SwimSchema.list_all_paths()
        assert len(paths) > 0

    def test_contains_remote_sensing_sample(self):
        """list_all_paths includes remote sensing paths."""
        paths = SwimSchema.list_all_paths()
        assert "remote_sensing/ndvi/landsat/irr" in paths

    def test_contains_meteorology_sample(self):
        """list_all_paths includes meteorology paths."""
        paths = SwimSchema.list_all_paths()
        assert "meteorology/gridmet/eto" in paths

    def test_contains_properties_sample(self):
        """list_all_paths includes properties paths."""
        paths = SwimSchema.list_all_paths()
        assert any(p.startswith("properties/") for p in paths)

    def test_contains_snow_sample(self):
        """list_all_paths includes snow paths."""
        paths = SwimSchema.list_all_paths()
        assert any(p.startswith("snow/") for p in paths)

    def test_all_paths_validate(self):
        """Every path from list_all_paths passes validate_path."""
        paths = SwimSchema.list_all_paths()
        for path in paths:
            assert SwimSchema.validate_path(path), f"Path failed validation: {path}"


class TestRequiredPaths:
    """Tests for required_for_calibration() and required_for_forward_run()."""

    def test_calibration_default_returns_known_length(self):
        """Calibration with defaults returns a non-empty list."""
        paths = SwimSchema.required_for_calibration()
        assert len(paths) > 0

    def test_calibration_requires_both_irr_masks(self):
        """Calibration requires both irr and inv_irr masks for NDVI and ETf."""
        paths = SwimSchema.required_for_calibration()
        irr_paths = [p for p in paths if "/irr" in p and "/inv_irr" not in p]
        inv_irr_paths = [p for p in paths if "/inv_irr" in p]
        assert len(irr_paths) > 0
        assert len(inv_irr_paths) > 0

    def test_calibration_propagates_model(self):
        """Non-default model propagates into calibration paths."""
        paths = SwimSchema.required_for_calibration(model="ptjpl")
        assert any("ptjpl" in p for p in paths)
        assert not any("ssebop" in p for p in paths)

    def test_calibration_propagates_met_source(self):
        """Non-default met_source propagates into calibration paths."""
        paths = SwimSchema.required_for_calibration(met_source="era5")
        met_paths = [p for p in paths if "meteorology" in p]
        assert all("era5" in p for p in met_paths)

    def test_forward_run_default_returns_known_length(self):
        """Forward run with defaults returns a non-empty list."""
        paths = SwimSchema.required_for_forward_run()
        assert len(paths) > 0

    def test_forward_run_propagates_mask(self):
        """Non-default mask propagates into forward run paths."""
        paths = SwimSchema.required_for_forward_run(mask="no_mask")
        rs_paths = [p for p in paths if "remote_sensing" in p]
        assert all("no_mask" in p for p in rs_paths)

    def test_forward_run_fewer_than_calibration(self):
        """Forward run requires fewer paths than calibration."""
        cal = SwimSchema.required_for_calibration()
        fwd = SwimSchema.required_for_forward_run()
        assert len(fwd) < len(cal)


class TestGetRootingDepth:
    """Tests for get_rooting_depth()."""

    def test_known_cropland_code(self):
        """LULC 12 (cropland) returns expected depth."""
        depth = get_rooting_depth(12)
        assert depth == ROOTING_DEPTH_BY_LULC[12].max_depth

    def test_use_max_false(self):
        """use_max=False returns mean depth instead of max."""
        depth_max = get_rooting_depth(12, use_max=True)
        depth_mean = get_rooting_depth(12, use_max=False)
        assert depth_mean < depth_max
        assert depth_mean == ROOTING_DEPTH_BY_LULC[12].mean_depth

    def test_unknown_code_falls_back_to_grassland(self):
        """Unknown LULC code falls back to UNKNOWN_ROOTING_DEFAULT (grassland)."""
        depth = get_rooting_depth(999)
        expected_depth = get_rooting_depth(UNKNOWN_ROOTING_DEFAULT)
        assert depth == expected_depth

    def test_all_known_codes_return_positive_depth(self):
        """All known LULC codes return positive rooting depth."""
        for code in ROOTING_DEPTH_BY_LULC:
            depth = get_rooting_depth(code)
            assert depth > 0, f"Code {code} has non-positive depth"


class TestIsCropland:
    """Tests for is_cropland()."""

    def test_glc10_cropland(self):
        assert is_cropland(10, "glc10") is True

    def test_glc10_non_cropland(self):
        for code in [20, 30, 40, 50, 60, 70, 80, 90, 100]:
            assert is_cropland(code, "glc10") is False, f"GLC10 {code} should not be cropland"

    def test_modis_cropland_codes(self):
        for code in [12, 13, 14]:
            assert is_cropland(code, "modis") is True, f"MODIS {code} should be cropland"

    def test_modis_non_cropland(self):
        for code in [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 16]:
            assert is_cropland(code, "modis") is False, f"MODIS {code} should not be cropland"

    def test_invalid_code(self):
        assert is_cropland(-1, "glc10") is False
        assert is_cropland(-1, "modis") is False


class TestGetRootingCode:
    """Tests for get_rooting_code()."""

    def test_glc10_cropland_maps_to_modis_12(self):
        assert get_rooting_code(10, "glc10") == 12

    def test_glc10_forest_maps_to_modis_4(self):
        assert get_rooting_code(20, "glc10") == 4

    def test_glc10_grassland_maps_to_modis_10(self):
        assert get_rooting_code(30, "glc10") == 10

    def test_glc10_unknown_defaults_to_grassland(self):
        assert get_rooting_code(999, "glc10") == UNKNOWN_ROOTING_DEFAULT

    def test_modis_known_code_returned_as_is(self):
        assert get_rooting_code(12, "modis") == 12
        assert get_rooting_code(1, "modis") == 1

    def test_modis_unknown_defaults_to_grassland(self):
        assert get_rooting_code(999, "modis") == UNKNOWN_ROOTING_DEFAULT

    def test_all_glc10_keys_have_valid_modis_mapping(self):
        for glc_code, modis_code in GLC10_TO_MODIS_ROOTING.items():
            assert modis_code in ROOTING_DEPTH_BY_LULC, (
                f"GLC10 {glc_code} maps to MODIS {modis_code} which has no rooting depth"
            )
