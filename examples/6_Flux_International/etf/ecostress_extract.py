import json
import multiprocessing
import os
import re
from collections import defaultdict
from datetime import datetime

import geopandas as gpd
import rasterio
from rasterio.warp import transform_bounds
from rasterstats import zonal_stats
from shapely.geometry import Polygon, mapping, shape


def _worker_process_sid_date_values(sid, polygon_geometry_mapping, tiff_files_for_aid):
    date_to_value = {}
    date_pattern = re.compile(r"doy(\d{4})(\d{3})")

    for tiff_file_path in tiff_files_for_aid:
        filename = os.path.basename(tiff_file_path)
        date_match = date_pattern.search(filename)
        if date_match:
            year_str, doy_str = date_match.groups()
            # Removed try-except for date parsing and zonal_stats
            date_obj = datetime.strptime(f"{year_str}-{doy_str}", "%Y-%j")
            date_key = date_obj.strftime("%Y-%m-%d")

            stats_result = zonal_stats(
                polygon_geometry_mapping,
                tiff_file_path,
                stats=["count", "mean", "std", "min", "max"],
                geojson_out=False,
            )
            if (
                stats_result
                and stats_result[0]
                and "count" in stats_result[0]
                and stats_result[0]["count"] > 0
            ):
                date_to_value[date_key] = stats_result[0]

    return {sid: date_to_value}


def process_geospatial_data_with_aid(
    shapefile_path,
    tiff_directory,
    sid_field,
    num_workers,
    debug=False,
    aid_filename_pattern=r"_aid(\d+)\.tif$",
    tiff_name_contains=None,
):
    gdf = gpd.read_file(shapefile_path, engine="fiona")
    if gdf.crs and gdf.crs.to_epsg() != 4326:
        gdf = gdf.to_crs(epsg=4326)

    all_tiff_files = [
        os.path.join(tiff_directory, f)
        for f in os.listdir(tiff_directory)
        if f.endswith(".tif") and (tiff_name_contains is None or tiff_name_contains in f)
    ]

    aid_regex = re.compile(aid_filename_pattern)

    aid_to_representative_geom = {}
    processed_aids_for_geom = set()
    for tiff_file in all_tiff_files:
        match = aid_regex.search(os.path.basename(tiff_file))
        if match:
            aid_val = match.group(1)
            if aid_val not in processed_aids_for_geom:
                with rasterio.open(tiff_file) as src:
                    b = src.bounds
                    if src.crs and src.crs.to_epsg() != 4326:
                        left, bottom, right, top = transform_bounds(
                            src.crs, "EPSG:4326", b.left, b.bottom, b.right, b.top
                        )
                    else:
                        left, bottom, right, top = b.left, b.bottom, b.right, b.top
                    aid_to_representative_geom[aid_val] = Polygon(
                        [(left, bottom), (right, bottom), (right, top), (left, top)]
                    )
                processed_aids_for_geom.add(aid_val)

    sid_to_aid_map = {}
    for _, poly_row in gdf.iterrows():
        polygon_geom = poly_row.geometry
        current_sid = poly_row[sid_field]
        for aid_val, representative_geom in aid_to_representative_geom.items():
            if polygon_geom.intersects(representative_geom):
                sid_to_aid_map[current_sid] = aid_val
                break

    aid_to_all_filepaths = defaultdict(list)
    for tiff_file in all_tiff_files:
        match = aid_regex.search(os.path.basename(tiff_file))
        if match:
            aid_val = match.group(1)
            aid_to_all_filepaths[aid_val].append(tiff_file)

    tasks = []
    aid_to_raster_crs = {}
    sid_aid_geom_cache = {}
    for current_sid, mapped_aid in sid_to_aid_map.items():
        polygon_series = gdf[gdf[sid_field] == current_sid]
        if not polygon_series.empty:
            polygon_geom_for_sid = polygon_series.geometry.iloc[0]
            files_for_this_aid = aid_to_all_filepaths.get(mapped_aid, [])
            if files_for_this_aid:
                raster_crs = aid_to_raster_crs.get(mapped_aid)
                if raster_crs is None:
                    first_tif = files_for_this_aid[0]
                    with rasterio.open(first_tif) as src:
                        raster_crs = src.crs
                    aid_to_raster_crs[mapped_aid] = raster_crs
                cache_key = (current_sid, mapped_aid)
                polygon_geom_mapping = sid_aid_geom_cache.get(cache_key)
                if polygon_geom_mapping is None:
                    polygon_geom_mapping = mapping(polygon_geom_for_sid)
                    if raster_crs and gdf.crs and raster_crs != gdf.crs:
                        poly_gs = gpd.GeoSeries([shape(polygon_geom_mapping)], crs=gdf.crs).to_crs(
                            raster_crs
                        )
                        polygon_geom_mapping = mapping(poly_gs.iloc[0])
                    sid_aid_geom_cache[cache_key] = polygon_geom_mapping
                tasks.append((current_sid, polygon_geom_mapping, files_for_this_aid))

    final_results = {}
    if not tasks:
        return final_results

    if debug:
        processed_results = []
        for i, t in enumerate(tasks):
            d = _worker_process_sid_date_values(*t)
            processed_results.append(d)
            print(i, t[0], len(d[t[0]]))

    else:
        with multiprocessing.Pool(processes=num_workers) as pool:
            processed_results = pool.starmap(_worker_process_sid_date_values, tasks)

    for res_dict in processed_results:
        final_results.update(res_dict)

    return final_results


if __name__ == "__main__":
    multiprocessing.freeze_support()

    project = "6_Flux_International"
    root = "/data/ssd2/swim"
    data_dir_ = os.path.join(root, project, "data")

    ecostress_ = os.path.join(data_dir_, "ecostress")
    chips_dir = os.path.join(ecostress_, "chips")

    shapefile_ = os.path.join(data_dir_, "gis", "flux_intl_150m_30DEC2025.shp")

    FEATURE_ID = "sid"
    aid_pattern = r"_aid(\d+)_.*\.tif$"

    output_data = process_geospatial_data_with_aid(
        shapefile_path=shapefile_,
        tiff_directory=chips_dir,
        sid_field=FEATURE_ID,
        num_workers=10,
        debug=False,
        aid_filename_pattern=aid_pattern,
        tiff_name_contains="ECO_L3T_JET.002_ETdaily",
    )
    if output_data:
        output_json_path = os.path.join(ecostress_, "ecostress_extract_31DEC2025.json")
        with open(output_json_path, "w") as f:
            json.dump(output_data, f, indent=2)
        print(f"wrote {output_json_path}")
    pass

# ========================= EOF ====================================================================
