"""Batch-convert MapGIS 6.x WT/WL/WP files to Shapefile without touching sources."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "vendor"))

import geopandas as gpd
import numpy as np
import shapely

try:
    import pymapgis
    import pymapgis.reader as reader_module
except ImportError as exc:
    raise SystemExit("Missing mapgis2shp. Install mapgis2shp==2.2.1 in this Python environment.") from exc

if pymapgis.__version__ != "2.2.1":
    raise SystemExit(f"Expected mapgis2shp 2.2.1; found {pymapgis.__version__}")

TYPES = {".wt": "point", ".wl": "line", ".wp": "polygon"}
FIELD_ALIASES = {"ID": "ORIG_ID", "长度": "ORIG_LEN", "面积": "ORIG_AREA", "周长": "ORIG_PERI"}


def at(buf: bytes, fmt: str, offset: int):
    return struct.unpack_from("<" + fmt, buf, offset)[0]


def fields_to_shp(frame: gpd.GeoDataFrame):
    """Return an ASCII, unique, <=10-byte field schema and reversible mapping."""
    used = set()
    mapping = {}
    for source in frame.columns:
        if source == "geometry":
            continue
        candidate = FIELD_ALIASES.get(source, source)
        candidate = re.sub(r"[^A-Za-z0-9_]", "_", candidate).upper()[:10]
        if not candidate or candidate[0].isdigit():
            candidate = "F_" + candidate[:8]
        base = candidate
        index = 1
        while candidate in used:
            suffix = str(index)
            candidate = base[: 10 - len(suffix)] + suffix
            index += 1
        used.add(candidate)
        mapping[source] = candidate
    return frame.rename(columns=mapping), mapping


def inactive_attribute_ids(raw: bytes, attr_base: int, record_length: int, ids: list[int]) -> list[int]:
    """Find geometries whose matching MapGIS attribute slot is not active."""
    if record_length <= 0:
        return list(ids)
    return [i for i in ids if attr_base + i * record_length >= len(raw) or raw[attr_base + i * record_length] != 1]


def repair_polygon(geom, allow_material: bool):
    """Repair an invalid polygon and return its diagnostic area/bounds change."""
    if geom.is_valid:
        return geom, None
    fixed = shapely.make_valid(geom, method="structure", keep_collapsed=False)
    if fixed.geom_type not in ("Polygon", "MultiPolygon") or fixed.is_empty or not fixed.is_valid:
        raise ValueError("Polygon repair failed")
    change = abs(fixed.area - geom.area)
    material = change > max(1e-7, abs(geom.area) * 1e-5)
    if material and not allow_material:
        raise ValueError("Polygon repair materially changed area")
    return fixed, {
        "original_area": float(geom.area), "repaired_area": float(fixed.area),
        "absolute_area_change": float(change),
        "relative_area_change": float(change / geom.area) if geom.area else None,
        "original_bounds": list(geom.bounds), "repaired_bounds": list(fixed.bounds),
        "material_area_change": material,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True, help="MapGIS file or directory")
    parser.add_argument("--output", type=Path, required=True, help="new output directory")
    parser.add_argument("--assign-crs", type=int, help="assign an EPSG code to existing longitude/latitude; no datum transform")
    parser.add_argument("--repair-invalid-polygons", action="store_true", help="allow polygon repair even when its area changes materially; writes a per-feature report")
    args = parser.parse_args()
    source = args.input.resolve()
    files = [source] if source.is_file() else sorted(p for p in source.rglob("*") if p.is_file())
    files = [p for p in files if p.suffix.lower() in TYPES]
    if not files:
        parser.error("No .wt/.wl/.wp files found")
    destination = args.output.resolve()
    if destination == source or source in destination.parents:
        parser.error("Output must be outside source directory")
    if destination.exists():
        parser.error("Output directory already exists; choose a new path to preserve prior results")

    headers = []
    for path in files:
        raw = path.read_bytes()
        if raw[:8] not in (b"WMAP`D22", b"WMAP`D21", b"WMAP`D23"):
            parser.error(f"Unexpected MapGIS signature: {path}")
        proj = raw[109]
        ellipsoid = raw[110]
        scale = at(raw, "d", 143)
        if args.assign_crs and proj != 0:
            parser.error(f"{path.name}: CRS assignment is limited to already geographic coordinates (projection code 0)")
        if args.assign_crs and scale == 0:
            parser.error(f"{path.name}: coordinate scale/header is unset; inspect whether this is a map-layout layer before assigning a geographic CRS")
        headers.append((path, proj, ellipsoid, scale))

    # In MapGIS geographic files, the header's 1:200000 display scale must
    # not multiply the already-decimal-degree geometry coordinates.
    original_read_crs = reader_module._read_crs

    def raw_geographic_crs(handle):
        handle.seek(109)
        if handle.read(1) == b"\x00":
            return None, 1.0
        return original_read_crs(handle)

    reader_module._read_crs = raw_geographic_crs
    destination.mkdir(parents=True)
    report = []
    repair_details = []
    name_counts = {}
    for path, proj, ellipsoid, scale in headers:
        reader_module._PolygonTopologyBuilder._ENDPOINT_MATCH_TOL = 1e-10 if proj == 0 and scale != 0 else 1e-5
        raw = path.read_bytes()
        start = at(raw, "i", 12)
        sections = [struct.unpack_from("<ii", raw, start + 10 * i) for i in range(10)]
        kind = TYPES[path.suffix.lower()]
        reader = pymapgis.Reader(path, make_valid=False)
        original = reader.geodataframe
        if kind == "polygon":
            sec_start, sec_size = sections[8]
            size = 40
            ids = [i for i in range(1, sec_size // size) if raw[sec_start + i * size] == 1]
            if ids != reader._polygon_active_ids:
                raise ValueError(f"Polygon topology and active records disagree: {path}")
            frame = original.copy().reset_index(drop=True)
        else:
            sec_start, sec_size = sections[0]
            size = 93 if kind == "point" else 57
            ids = [i for i in range(1, sec_size // size) if raw[sec_start + i * size] == 1]
            if len(original) != sec_size // size - 1:
                raise ValueError(f"Geometry slot count mismatch: {path}")
            frame = original.iloc[[i - 1 for i in ids]].copy().reset_index(drop=True)
        if len(frame) != len(ids):
            raise ValueError(f"Geometry and attribute count mismatch: {path}")
        attr_start, _ = sections[9 if kind == "polygon" else 2]
        field_count, _, record_length = struct.unpack_from("<hih", raw, attr_start + 322)
        attr_base = attr_start + 348 + 39 * field_count
        inactive_ids = inactive_attribute_ids(raw, attr_base, record_length, ids)
        if inactive_ids:
            # Inactive attribute bytes are not trustworthy values. Keep their
            # geometry and mark the attribute fields as genuinely missing.
            attribute_columns = [column for column in original.columns if column != "geometry"]
            if attribute_columns:
                frame.loc[[j for j, i in enumerate(ids) if i in set(inactive_ids)], attribute_columns] = None
        frame.insert(0, "SRC_REC", ids)
        frame.insert(1, "SRC_FILE", path.name)
        frame.insert(2, "ATTR_OK", [0 if i in set(inactive_ids) else 1 for i in ids])
        extra = []
        for i in ids:
            rec = raw[sec_start + i * size : sec_start + (i + 1) * size]
            if kind == "point":
                n, offset = struct.unpack_from("<hi", rec, 1)
                text_start, text_size = sections[1]
                if n < 0 or offset < 0 or offset + n > text_size:
                    raise ValueError(f"Point text index out of range: {path}:{i}")
                text = raw[text_start + offset : text_start + offset + n].decode("gb18030").rstrip("\0") if n else ""
                point_type = rec[31]
                if point_type not in (0, 1):
                    raise ValueError(f"Unsupported point kind {point_type}: {path}:{i}")
                extra.append({
                    "PT_TYPE": point_type, "TEXT": text,
                    "SYM_NO": at(rec, "i", 33) if point_type == 1 else 0,
                    "HEIGHT": at(rec, "f", 37 if point_type == 1 else 33),
                    "WIDTH": at(rec, "f", 41 if point_type == 1 else 37),
                    "ANGLE": at(rec, "f", 45), "COLOR_IDX": at(rec, "i", 75),
                    "LAYER_NO": at(rec, "h", 83),
                })
            elif kind == "line":
                extra.append({
                    "LINE_TYPE": at(rec, "h", 22), "COLOR_IDX": at(rec, "i", 26),
                    "LINE_W": at(rec, "f", 30), "LAYER_NO": at(rec, "h", 47),
                })
            else:
                extra.append({
                    "FILL_COLOR": at(rec, "i", 9), "PATTERN": at(rec, "h", 13),
                    "PAT_COLOR": at(rec, "i", 25),
                })
        for column in extra[0] if extra else []:
            frame[column] = [row[column] for row in extra]
        repairs = []
        if kind == "polygon":
            for j, geom in enumerate(frame.geometry):
                if geom.is_valid:
                    continue
                try:
                    fixed, detail = repair_polygon(geom, args.repair_invalid_polygons)
                except ValueError as exc:
                    raise ValueError(f"{exc}: {path}:{ids[j]}") from exc
                frame.at[j, "geometry"] = fixed
                repairs.append(ids[j])
                repair_details.append({"source": str(path), "source_record": ids[j], **detail})
        if frame.is_empty.any() or not frame.is_valid.all() or not np.isfinite(frame.total_bounds).all():
            raise ValueError(f"Empty, invalid, or non-finite geometry: {path}")
        if proj == 0:
            bounds = frame.total_bounds
            if args.assign_crs and not (-180 <= bounds[0] <= 180 and -90 <= bounds[1] <= 90 and -180 <= bounds[2] <= 180 and -90 <= bounds[3] <= 90):
                raise ValueError(f"Coordinate range is not longitude/latitude: {path}")
            if args.assign_crs:
                frame = frame.set_crs(epsg=args.assign_crs)
            else:
                frame = frame.set_crs(None, allow_override=True)
        elif args.assign_crs:
            raise ValueError(f"Projected source cannot be assigned a geographic CRS: {path}")
        shp_frame, mapping = fields_to_shp(frame)
        for column in shp_frame.columns:
            if column == "geometry":
                continue
            if shp_frame[column].dtype.kind in "OUS":
                max_bytes = shp_frame[column].fillna("").astype(str).map(lambda x: len(x.encode("utf-8"))).max()
                if max_bytes > 254:
                    raise ValueError(f"Shapefile would truncate {column} ({max_bytes} UTF-8 bytes): {path}")
        relative = path.relative_to(source) if source.is_dir() else Path(path.name)
        root_name = "_".join(relative.with_suffix("").parts)
        target_name = re.sub(r"[^A-Za-z0-9_-]", "_", root_name) + "_" + kind
        name_counts[target_name] = name_counts.get(target_name, 0) + 1
        if name_counts[target_name] > 1:
            target_name += f"_{name_counts[target_name]}"
        target = destination / (target_name + ".shp")
        shp_frame.to_file(target, driver="ESRI Shapefile", encoding="UTF-8", index=False)
        opened = gpd.read_file(target)
        if len(opened) != len(shp_frame) or opened.is_empty.any() or not opened.is_valid.all():
            raise ValueError(f"Shapefile verification failed: {target}")
        if not np.allclose(opened.total_bounds, shp_frame.total_bounds, atol=1e-10, rtol=0):
            raise ValueError(f"Coordinate bounds changed: {target}")
        if (opened.crs.to_epsg() if opened.crs else None) != (shp_frame.crs.to_epsg() if shp_frame.crs else None):
            raise ValueError(f"Projection check failed: {target}")
        for column in shp_frame.columns:
            if column == "geometry":
                continue
            if shp_frame[column].dtype.kind in "OUS":
                if not shp_frame[column].fillna("").astype(str).str.strip().equals(opened[column].fillna("").astype(str).str.strip()):
                    raise ValueError(f"Text changed in {column}: {target}")
            elif not np.allclose(shp_frame[column].to_numpy(float), opened[column].to_numpy(float), atol=1e-12, rtol=1e-12, equal_nan=True):
                raise ValueError(f"Numeric attribute changed in {column}: {target}")
        with (destination / (target_name + "_attributes.csv")).open("w", encoding="utf-8-sig", newline="") as handle:
            shp_frame.drop(columns="geometry").to_csv(handle, index=False)
        report.append({
            "source": str(path), "shp": target.name, "type": kind,
            "features": len(frame), "deleted_slots": sec_size // size - 1 - len(ids),
            "polygon_repairs": len(repairs), "missing_attribute_records": len(inactive_ids),
            "epsg": opened.crs.to_epsg() if opened.crs else None,
            "bounds": opened.total_bounds.tolist(), "projection_code": proj,
            "ellipsoid_code": ellipsoid, "header_scale": scale,
            "source_sha256": hashlib.sha256(raw).hexdigest(), "field_names": mapping,
        })
        print(f"{path.name}: {len(frame)} {kind} -> {target.name}", flush=True)
    with (destination / "conversion_manifest.json").open("w", encoding="utf-8") as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2)
    with (destination / "conversion_manifest.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        columns = ("source", "shp", "type", "features", "deleted_slots", "polygon_repairs", "missing_attribute_records", "epsg")
        writer.writerow(columns)
        writer.writerows([row[key] for key in columns] for row in report)
    with (destination / "polygon_repair_details.json").open("w", encoding="utf-8") as handle:
        json.dump(repair_details, handle, ensure_ascii=False, indent=2)
    with (destination / "polygon_repair_details.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        columns = ("source", "source_record", "original_area", "repaired_area", "absolute_area_change", "relative_area_change", "original_bounds", "repaired_bounds", "material_area_change")
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows(repair_details)
    print(f"Completed {len(report)} layers and {sum(row['features'] for row in report)} features")
    return 0


if __name__ == "__main__":
    sys.exit(main())
