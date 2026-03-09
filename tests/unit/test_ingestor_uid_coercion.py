"""Tests for ingestor UID type coercion (string/int mismatch fix).

Verifies that CSV files with integer FID columns are correctly matched
against string UIDs in the container after the coercion fix.
"""

import tempfile
from pathlib import Path

import numpy as np
import pandas as pd
from zarr.core.dtype import VariableLengthUTF8

from swimrs.container.components.ingestor import Ingestor
from swimrs.container.inventory import Inventory
from swimrs.container.provenance import ProvenanceLog
from swimrs.container.state import ContainerState
from swimrs.container.storage import MemoryStoreProvider


def _make_container_state(n_fields=5):
    """Create an in-memory ContainerState with string UIDs '1'..'N'."""
    provider = MemoryStoreProvider(mode="w")
    root = provider.open()

    uids = [str(i) for i in range(1, n_fields + 1)]

    # Create time index
    time_index = pd.date_range("2020-01-01", "2020-12-31", freq="D")

    time_grp = root.create_group("time")
    time_grp.create_array("daily", data=time_index.values.astype("datetime64[ns]"))

    # Create geometry/uid
    geom_grp = root.create_group("geometry")
    uid_arr = geom_grp.create_array("uid", shape=(n_fields,), dtype=VariableLengthUTF8())
    uid_arr[:] = uids

    # Create empty groups
    root.create_group("properties")
    root.create_group("remote_sensing")
    root.create_group("meteorology")
    root.create_group("snow")
    root.create_group("derived")

    provenance = ProvenanceLog()
    inventory = Inventory(root, uids)

    state = ContainerState(
        provider=provider,
        field_uids=uids,
        time_index=time_index,
        provenance=provenance,
        inventory=inventory,
        mode="w",
    )

    return state, uids


def test_ingest_soils_with_int_index():
    """Integer FID CSV + string UID container -> soil data ingested."""
    state, uids = _make_container_state(5)
    ingestor = Ingestor(state, container=None)

    with tempfile.TemporaryDirectory() as tmpdir:
        # Create CSV with integer FID column
        csv_path = Path(tmpdir) / "soils.csv"
        pd.DataFrame(
            {
                "FID": [1, 2, 3, 4, 5],  # integers, not strings
                "awc": [0.15, 0.16, 0.17, 0.18, 0.19],
                "clay": [25.0, 26.0, 27.0, 28.0, 29.0],
                "sand": [40.0, 41.0, 42.0, 43.0, 44.0],
                "ksat": [10.0, 11.0, 12.0, 13.0, 14.0],
            }
        ).to_csv(csv_path, index=False)

        ingestor.properties(soils_csv=str(csv_path), uid_column="FID")

    # Verify data was ingested (not all NaN)
    awc = np.asarray(state.root["properties/soils/awc"][:])
    assert not np.all(np.isnan(awc)), "AWC should not be all NaN after ingestion with int FIDs"
    assert np.sum(~np.isnan(awc)) == 5

    clay = np.asarray(state.root["properties/soils/clay"][:])
    assert np.sum(~np.isnan(clay)) == 5


def test_ingest_irrigation_with_int_index():
    """Integer FID CSV + string UID container -> irrigation data ingested."""
    state, uids = _make_container_state(5)
    ingestor = Ingestor(state, container=None)

    with tempfile.TemporaryDirectory() as tmpdir:
        csv_path = Path(tmpdir) / "irrigation.csv"
        pd.DataFrame(
            {
                "FID": [1, 2, 3, 4, 5],  # integers
                "irr_2020": [0.5, 0.6, 0.7, 0.8, 0.9],
                "irr_2021": [0.4, 0.5, 0.6, 0.7, 0.8],
            }
        ).to_csv(csv_path, index=False)

        ingestor.properties(irr_csv=str(csv_path), uid_column="FID")

    irr = np.asarray(state.root["properties/irrigation/irr"][:])
    assert not np.all(np.isnan(irr)), "Irrigation should not be all NaN with int FIDs"
    assert np.sum(~np.isnan(irr)) == 5


def test_ingest_lulc_with_int_index():
    """Integer FID CSV + string UID container -> LULC data ingested."""
    state, uids = _make_container_state(5)
    ingestor = Ingestor(state, container=None)

    with tempfile.TemporaryDirectory() as tmpdir:
        csv_path = Path(tmpdir) / "lulc.csv"
        pd.DataFrame(
            {
                "FID": [1, 2, 3, 4, 5],  # integers
                "modis_lc": [12, 12, 10, 7, 12],
            }
        ).to_csv(csv_path, index=False)

        ingestor.properties(
            lulc_csv=str(csv_path),
            uid_column="FID",
            lulc_column="modis_lc",
            extra_lulc_column=None,
        )

    lc = np.asarray(state.root["properties/land_cover/modis_lc"][:])
    assert not np.all(lc == -1), "LULC should not be all fill value with int FIDs"
    assert np.sum(lc != -1) == 5
