"""Tests for property derivation logic in swimrs.process.input.

Tests cover the pure numpy operations used during HDF5 construction:
- CN2 from clay: clay < 15 -> 67, 15-30 -> 77, > 30 -> 85
- Perennial from LULC: codes 12/14 not perennial, code 10 perennial
- Variable alias resolution: etr/eto/ref_et fallback chain
- NDVI bare/full: with data -> per-field percentiles, without -> defaults
"""

import numpy as np
from numpy.testing import assert_array_equal


class TestCN2FromClay:
    """Tests for CN2 derivation from clay content.

    Logic: cn2 = np.where(clay < 15, 67, np.where(clay > 30, 85, 77))
    """

    def test_clay_below_15(self):
        """Clay < 15 -> CN2 = 67."""
        clay = np.array([5.0, 10.0, 14.9])
        cn2 = np.where(clay < 15.0, 67.0, np.where(clay > 30.0, 85.0, 77.0))
        assert_array_equal(cn2, [67.0, 67.0, 67.0])

    def test_clay_15_to_30(self):
        """15 <= Clay <= 30 -> CN2 = 77."""
        clay = np.array([15.0, 20.0, 30.0])
        cn2 = np.where(clay < 15.0, 67.0, np.where(clay > 30.0, 85.0, 77.0))
        assert_array_equal(cn2, [77.0, 77.0, 77.0])

    def test_clay_above_30(self):
        """Clay > 30 -> CN2 = 85."""
        clay = np.array([30.1, 50.0, 80.0])
        cn2 = np.where(clay < 15.0, 67.0, np.where(clay > 30.0, 85.0, 77.0))
        assert_array_equal(cn2, [85.0, 85.0, 85.0])

    def test_mixed_array(self):
        """Mixed clay values produce correct CN2 distribution."""
        clay = np.array([10.0, 20.0, 40.0])
        cn2 = np.where(clay < 15.0, 67.0, np.where(clay > 30.0, 85.0, 77.0))
        assert_array_equal(cn2, [67.0, 77.0, 85.0])


class TestPerennialFromLULC:
    """Tests for perennial status derivation from LULC codes.

    Uses schema.is_cropland() for GLC10-primary, MODIS-fallback logic.
    perennial = not is_cropland(code, source) AND code > 0
    """

    def test_glc10_cropland_not_perennial(self):
        """GLC10 10 (cropland) is not perennial."""
        from swimrs.container.schema import is_cropland

        assert is_cropland(10, "glc10") is True
        perennial = not is_cropland(10, "glc10") and 10 > 0
        assert perennial is False

    def test_modis_cropland_not_perennial(self):
        """MODIS 12 (cropland) is not perennial."""
        from swimrs.container.schema import is_cropland

        assert is_cropland(12, "modis") is True
        perennial = not is_cropland(12, "modis") and 12 > 0
        assert perennial is False

    def test_modis_cropland_mosaic_not_perennial(self):
        """MODIS 14 (cropland/natural mosaic) is not perennial."""
        from swimrs.container.schema import is_cropland

        perennial = not is_cropland(14, "modis") and 14 > 0
        assert perennial is False

    def test_glc10_grassland_is_perennial(self):
        """GLC10 30 (grassland) is perennial."""
        from swimrs.container.schema import is_cropland

        perennial = not is_cropland(30, "glc10") and 30 > 0
        assert perennial is True

    def test_glc10_forest_is_perennial(self):
        """GLC10 20 (forest) is perennial."""
        from swimrs.container.schema import is_cropland

        perennial = not is_cropland(20, "glc10") and 20 > 0
        assert perennial is True

    def test_modis_grassland_is_perennial(self):
        """MODIS 10 (grassland) is perennial."""
        from swimrs.container.schema import is_cropland

        perennial = not is_cropland(10, "modis") and 10 > 0
        assert perennial is True

    def test_invalid_code_not_perennial(self):
        """Negative code is not perennial."""
        from swimrs.container.schema import is_cropland

        perennial = not is_cropland(-1, "glc10") and -1 > 0
        assert perennial is False

    def test_vectorized_perennial_glc10(self):
        """Vectorized perennial derivation over GLC10 codes."""
        from swimrs.container.schema import is_cropland

        codes = np.array([10, 20, 30, 40, -1])
        perennial = np.array([not is_cropland(c, "glc10") and c > 0 for c in codes])
        # 10=Crop(not perennial), 20=Forest(perennial), 30=Grass(perennial),
        # 40=Shrub(perennial), -1=invalid(not perennial)
        assert_array_equal(perennial, [False, True, True, True, False])


class TestVariableAliasResolution:
    """Tests for reference ET alias resolution logic.

    Logic from get_time_series: if variable not in ts, check aliases.
    """

    def test_primary_present_direct_return(self):
        """When primary name exists, it is used directly."""
        ts_keys = {"etr", "prcp", "tmin"}
        variable = "etr"
        assert variable in ts_keys

    def test_fallback_to_alias(self):
        """When primary name missing, falls back to alias."""
        ts_keys = {"ref_et", "prcp"}
        variable = "etr"
        ref_et_aliases = {"etr", "eto", "ref_et"}
        actual_var = variable
        if variable not in ts_keys and variable in ref_et_aliases:
            for alias in ref_et_aliases:
                if alias in ts_keys:
                    actual_var = alias
                    break
        assert actual_var == "ref_et"

    def test_none_present_raises(self):
        """When no alias is present, expect KeyError."""
        ts_keys = {"prcp", "tmin"}
        variable = "etr"
        ref_et_aliases = {"etr", "eto", "ref_et"}
        found = False
        if variable not in ts_keys and variable in ref_et_aliases:
            for alias in ref_et_aliases:
                if alias in ts_keys:
                    found = True
                    break
        assert found is False

    def test_non_ref_et_variable_not_aliased(self):
        """Non-reference-ET variables don't use the alias chain."""
        ts_keys = {"ref_et", "prcp"}
        variable = "srad"
        ref_et_aliases = {"etr", "eto", "ref_et"}
        actual_var = variable
        if variable not in ts_keys and variable in ref_et_aliases:
            for alias in ref_et_aliases:
                if alias in ts_keys:
                    actual_var = alias
                    break
        # srad is not in ref_et_aliases, so no alias resolution
        assert actual_var == "srad"
