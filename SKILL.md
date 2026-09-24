---
name: mapgis-to-shp
description: Use when converting MapGIS 6.x .wt/.wl/.wp layers to Shapefile, including geological maps with blank or inactive attribute records, invalid polygons, Chinese labels, or CGCS2000 coordinate assignment.
---

# MapGIS 转 Shapefile

本 skill 处理 MapGIS 6.x/6.7 原生 `.wt`（点）、`.wl`（线）、`.wp`（面）。`.mpj` 是工程索引，不是独立几何文件。根据请求选中源目录并清点要素文件；将输出写到另一个新目录，保留源数据。先检查各文件头的投影代码、椭球代码、比例尺和坐标范围，区分图面排版坐标与真实经纬度。

优先使用开源 [mapgis2shp](https://github.com/leecugb/mapgis2shp) 的 `pymapgis.Reader`；本 skill 在 `vendor/pymapgis` 中保留已验证的 2.2.1 版本及 Apache-2.0 许可证，脚本可直接加载，无需依赖临时仓库。此 skill 的 [批量转换脚本](scripts/mapgis_to_shp.py) 以其解析结果为基础，补充文字点的 `TEXT` 字段、原图符号参数、删除记录过滤、缺失属性标记、面有效性处理及逐层核验。所需 Python 包：`geopandas`、`shapely`、`pyproj`、`numpy` 及 GeoPandas 的 Shapefile 读写后端。若本机依赖尚缺，在适用的独立 Python 环境中安装；不要改写用户的 ArcGIS Pro 默认 Python 环境。代码来源和固定版本见 [mapgis2shp](https://github.com/leecugb/mapgis2shp)；文字参数解析参考 [ConvertMapGIS](https://github.com/BenChao1998/ConvertMapGIS)。

示例：

```powershell
python scripts/mapgis_to_shp.py --input "E:\地质图\K4929\MAPGIS" --output "E:\地质图\K4929\MAPGIS_SHP_CGCS2000" --assign-crs 4490
```

当用户明确要求修复几何无效的面，包括修复后面积可能明显变化的情况，添加 `--repair-invalid-polygons`，并使用新的输出目录。默认只接受面积变化很小的自动修复；明显变化仍会中止，以免不知情地改变地质界线。

```powershell
python scripts/mapgis_to_shp.py --input "E:\地质图\J4806\MAPGIS" --output "E:\地质图\J4806\MAPGIS_SHP_几何修复版" --assign-crs 4490 --repair-invalid-polygons
```

几何有效、但对应属性记录未激活的要素仍应转换；原属性字段置空，`ATTR_OK=0` 标记缺失，`SRC_REC` 保留原始记录号。正常属性记录为 `ATTR_OK=1`。不能把未激活记录中的零值或乱码当作真实属性。输出清单的 `missing_attribute_records` 统计此类要素。若解析器本身无法建立几何与记录的对应关系，停止并报告，不能猜测补齐。

修复前后的记录写入 `polygon_repair_details.json/.csv`：源图层、`SRC_REC`、面积和边界变化及是否属于明显面积变化。无效原面计算的面积仅用于诊断，并非可靠的地质面积；对明显变化的面应在 ArcGIS Pro 中对照原图复核。没有用户修复授权时，不自动开启允许明显变化的选项。

`--assign-crs 4490` 仅为已有经纬度数据定义 CGCS2000 地理坐标系（EPSG:4490），不进行坐标基准转换。只有用户要求这一坐标系、且文件的投影代码为 0、坐标范围合理时才指定；文件椭球索引或来源若暗示其他基准，应说明定义参考系和真正的基准转换是两件事。图面坐标或坐标系不明时省略此参数，保留未知空间参考，不臆造 `.prj`。若用户要求真正重投影，先明确并验证原始坐标系及转换参数，再使用可信 GIS 工具转换。

转换后核对：源文件与输出图层数、有效要素数、原始字段和值（缺失属性除外）、中文注记、坐标范围、`.prj` 的 EPSG、空/无效几何；脚本在输出中写出清单与细节。ArcGIS Pro 可用时，还应按其几何规则检查。若必须做 ArcGIS 容差修复，先备份已转换的 SHP，在副本上修复，再核对要素数、原始属性及最大边界/面积变化，确认可接受后再采用。修复记录和备份随交付保存。MapGIS 的色号、线型号、子图号是样式库索引，Shapefile 只能保存这些编号和点位，不能声称完整复刻原图符号或文字排版。

在安装了 ArcGIS Pro 的本机，可用其 Python 执行 [图层文件脚本](scripts/create_arcgis_layerfile.py)：`python scripts/create_arcgis_layerfile.py --input "<SHP输出目录>"`。它生成相对路径的 `all_layers.lyrx`，一次加载所有 SHP，并为 `TEXT` 文字点设置基础标注；这是便捷预览，仍需另行核对原图符号与字体。

向用户提供输出目录、图层及要素数、ArcGIS Pro 加载方法、坐标系定义与基准转换的状态，以及几何修复的实际验证结果。运行估时：本机数十个普通图幅图层的格式转换通常为数分钟，ArcGIS 原生几何检查及修复视复杂面数量另需数分钟；以实际文件体量和进度调整估时。
