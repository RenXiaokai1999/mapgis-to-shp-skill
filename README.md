# MapGIS 转 Shapefile Skill

用于批量转换 MapGIS 6.x 的 `.wt`（点）、`.wl`（线）、`.wp`（面）为 Shapefile，保留中文属性与文字点，并核验输出。支持保留属性记录未激活但几何有效的要素，以及按需修复无效面。详细使用约定见 [SKILL.md](SKILL.md)。

## 安装

将本仓库克隆到 Codex 的个人 skills 目录，目录名保持 `mapgis-to-shp`。另在独立 Python 环境中安装 `geopandas`、`shapely`、`pyproj`、`numpy` 和 GeoPandas 的 Shapefile 读写后端；不要改动 ArcGIS Pro 自带的 Python 环境。仓库内已包含 `pymapgis` 2.2.1 的已验证源码。

## 命令行示例

```powershell
python scripts/mapgis_to_shp.py --input "E:\地质图\某图幅\MAPGIS" --output "E:\地质图\某图幅\MAPGIS_SHP" --assign-crs 4490 --repair-invalid-polygons
```

- `--assign-crs 4490` 只为已有经纬度定义 CGCS2000 地理坐标系，不进行北京54等坐标基准到 CGCS2000 的转换。来源坐标系不明时不要使用该参数。
- `--repair-invalid-polygons` 允许无效面修复后面积明显变化。修复细节写入 `polygon_repair_details.json/.csv`，明显变化的面应对照原图复核。
- 原属性记录未激活的要素保留几何、原属性置空，并以 `ATTR_OK=0` 标记。输出必须指定不存在的新目录，避免覆盖原始或既有结果。

## 验证

```powershell
python -m unittest discover -s tests -v
```

仓库不包含任何地质图原始文件或转换成果。第三方 `pymapgis` 来源于 [leecugb/mapgis2shp](https://github.com/leecugb/mapgis2shp)，其 Apache-2.0 许可证保存在 `vendor/LICENSE`。本仓库其他文件目前未单独声明许可证；公开可浏览不等于自动授予再分发或修改权利。
