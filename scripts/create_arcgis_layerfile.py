"""Build a relative-path ArcGIS Pro .lyrx containing every Shapefile in one directory."""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

try:
    import arcpy
except ImportError as exc:
    raise SystemExit("Run with ArcGIS Pro's Python, where arcpy is available") from exc


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True, help="directory with converted .shp files")
    parser.add_argument("--output", type=Path, help="new .lyrx file; defaults to all_layers.lyrx inside input")
    args = parser.parse_args()
    source = args.input.resolve()
    shapefiles = sorted(source.glob("*.shp"))
    if not shapefiles:
        parser.error("No Shapefiles found")
    destination = (args.output or source / "all_layers.lyrx").resolve()
    if destination.suffix.lower() != ".lyrx":
        parser.error("Output must end in .lyrx")
    if destination.exists():
        parser.error("Output layer file already exists; choose another path to preserve it")
    if destination.parent != source:
        parser.error("Place the layer file in the Shapefile directory so relative connections remain valid")

    pieces = []
    with tempfile.TemporaryDirectory(prefix="mapgis_lyrx_") as stage:
        stage_dir = Path(stage)
        for index, shp in enumerate(shapefiles):
            describe = arcpy.Describe(str(shp))
            if describe.shapeType not in ("Point", "Polyline", "Polygon"):
                raise ValueError(f"Unexpected shape type: {shp}")
            view = arcpy.management.MakeFeatureLayer(str(shp), f"mapgis_layer_{index}").getOutput(0)
            temp_layer = stage_dir / f"{index:03d}.lyrx"
            arcpy.management.SaveToLayerFile(view, str(temp_layer), "ABSOLUTE")
            arcpy.management.Delete(view)
            document = json.loads(temp_layer.read_text(encoding="utf-8"))
            if len(document["layers"]) != 1 or len(document["layerDefinitions"]) != 1:
                raise ValueError(f"Unexpected ArcGIS layer document: {temp_layer}")
            definition = document["layerDefinitions"][0]
            definition["name"] = shp.stem
            definition["featureTable"]["dataConnection"]["workspaceConnectionString"] = "DATABASE=."
            field_names = {field.name for field in arcpy.ListFields(str(shp))}
            if describe.shapeType == "Point" and {"TEXT", "PT_TYPE"} <= field_names:
                definition["labelVisibility"] = True
                classes = definition.get("labelClasses", [])
                for label in classes:
                    label["expression"] = "$feature.TEXT"
                    label["whereClause"] = "PT_TYPE = 0 AND TEXT <> ''"
                    label["visibility"] = True
            else:
                definition["labelVisibility"] = False
            pieces.append((document, definition))
        result = {key: value for key, value in pieces[0][0].items() if key not in ("layers", "layerDefinitions")}
        result["layers"] = [item[0]["layers"][0] for item in pieces]
        result["layerDefinitions"] = [item[1] for item in pieces]
        if len(set(result["layers"])) != len(shapefiles):
            raise ValueError("Layer URI collision; cannot build combined layer file")
        destination.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    opened = arcpy.mp.LayerFile(str(destination))
    layers = opened.listLayers()
    if len(layers) != len(shapefiles) or any(layer.isBroken for layer in layers):
        raise ValueError(f"Generated layer file has broken connections: {destination}")
    print(f"Created {destination} with {len(layers)} readable layers")
    return 0


if __name__ == "__main__":
    sys.exit(main())
