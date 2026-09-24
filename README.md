# MapGIS 转 Shapefile Skill

把 MapGIS 6.x/6.7 的 `.wt`（点）、`.wl`（线）、`.wp`（面）批量转换为 ArcGIS Pro 可读取的 Shapefile。既可作为 Codex skill 使用，也可直接运行 Python 脚本。适合地质图分幅、图例和经纬度图层；`.mpj` 是工程索引，不作为独立图层转换。

## 能做什么

- 批量转换文件或文件夹，保留原始 MapGIS 文件，输出到新的独立目录。
- 保留中文属性、文字点的 `TEXT` 字段及可读取的原图符号参数；过滤已删除的几何记录。
- 保留几何存在但属性记录未激活的要素：原属性置空，`ATTR_OK=0` 标记，`SRC_REC` 保留原始记录号。
- 修复无效面，并记录修复前后的面积与边界变化；对变化较大的面提供显式开关和逐条报告。
- 回读核验 Shapefile 的要素数、几何有效性、坐标范围、属性及坐标系，生成转换清单。

**不包含**：地图样式的完整复刻、自动判定原始坐标基准、北京54到 CGCS2000 等坐标基准转换。Shapefile 中保存的是可提取的符号编号，不是 MapGIS 的完整样式库。

## 环境要求

- 已在 Windows x64、Python 3.12.3 上验证；测试组合见 [requirements.txt](requirements.txt)。
- Git（用于克隆仓库）。
- ArcGIS Pro *不是转换所必需*；只有可选的 `.lyrx` 图层文件生成步骤需要 ArcGIS Pro 的 `arcpy`。
- 仓库已经包含所需的 `pymapgis` 2.2.1 源码，无需另行安装该解析器。

请使用独立 Python 虚拟环境，不要改动 ArcGIS Pro 自带的 Python 环境。

## Windows 部署

在 PowerShell 中运行。若 `%USERPROFILE%\.codex\skills\mapgis-to-shp` 已存在，先检查并备份，不要直接克隆覆盖。

```powershell
$skillsDir = Join-Path $env:USERPROFILE '.codex\skills'
New-Item -ItemType Directory -Path $skillsDir -Force | Out-Null
git clone https://github.com/RenXiaokai1999/mapgis-to-shp-skill.git (Join-Path $skillsDir 'mapgis-to-shp')
Set-Location (Join-Path $skillsDir 'mapgis-to-shp')
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

安装后，Codex 可通过 [SKILL.md](SKILL.md) 识别该 skill。未使用 Codex 时，在仓库目录直接运行下面的命令即可。若 `py -3.12` 不可用，请先安装 Python 3.12 x64，或将命令改为你已确认的 Python 3.12 可执行文件路径。

## 转换示例

以下命令均在仓库根目录运行。将输入、输出路径改成自己的实际路径；`--output` 必须是尚不存在的目录。

**仅转换，不指定未知坐标系：**

```powershell
.\.venv\Scripts\python.exe .\scripts\mapgis_to_shp.py --input 'E:\地质图\某图幅\MAPGIS' --output 'E:\地质图\某图幅\MAPGIS_SHP'
```

**已核实原坐标值为经纬度，且要将其定义为 CGCS2000 地理坐标系：**

```powershell
.\.venv\Scripts\python.exe .\scripts\mapgis_to_shp.py --input 'E:\地质图\某图幅\MAPGIS' --output 'E:\地质图\某图幅\MAPGIS_SHP_CGCS2000' --assign-crs 4490
```

**用户明确要求修复无效面，允许修复后面积明显变化：**

```powershell
.\.venv\Scripts\python.exe .\scripts\mapgis_to_shp.py --input 'E:\地质图\某图幅\MAPGIS' --output 'E:\地质图\某图幅\MAPGIS_SHP_几何修复版' --assign-crs 4490 --repair-invalid-polygons
```

`--input` 可以是单个 `.wt/.wl/.wp` 文件，也可以是包含这些文件的目录。未加 `--repair-invalid-polygons` 时，脚本仅接受面积变化很小的自动修复；若变化明显会中止，避免不知情地改变面边界。开启后也应对照原图复核报告，不能把“几何有效”直接视为地质边界正确。

### 坐标系特别提醒

`--assign-crs 4490` **只写入 CGCS2000（EPSG:4490）的坐标系定义，不会移动坐标，也不是坐标基准转换**。只有确认源数据的经纬度数值适合按 CGCS2000 使用时才指定；仅凭坐标值看起来像经纬度，不能判断其原始基准。源坐标系不明时省略参数，先查来源资料或控制点。脚本还会拒绝为文件头显示为投影坐标的图层直接指定地理坐标系。

## 输出与核验

每个图层输出一组 `.shp/.shx/.dbf` 等文件；指定坐标系且核验通过时包含 `.prj`。同一输出目录还会有：

| 文件 | 用途 |
| --- | --- |
| `conversion_manifest.json/.csv` | 各图层来源、要素数、修复数、缺失属性数、坐标范围、EPSG 和源文件校验值 |
| `*_attributes.csv` | 转换后属性表的独立副本 |
| `polygon_repair_details.json/.csv` | 每个修复面的原记录号、修复前后面积和边界、明显变化标记 |

在输出 Shapefile 中，`SRC_REC` 是 MapGIS 原始记录号，`SRC_FILE` 是原始文件名，`ATTR_OK=0` 表示对应属性记录未激活。原面本身无效时，它计算出来的面积只适合作诊断参考；面积变化明显的修复应在 GIS 中逐条核对。

可在 ArcGIS Pro 中直接加载 `.shp`。如果需要一次性加载所有图层，可在安装了 ArcGIS Pro 的电脑上，打开 **ArcGIS Pro Python Command Prompt**，切换到仓库目录，再用其中的 `python` 运行：

```powershell
python .\scripts\create_arcgis_layerfile.py --input 'E:\地质图\某图幅\MAPGIS_SHP_CGCS2000'
```

这会生成相对路径的 `all_layers.lyrx`，并为 `TEXT` 文字点设置基础标注；仍需自行核对原图符号与字体。

## 常见问题

- **输出目录已存在：**脚本拒绝覆盖。换一个新目录；若上次转换中途失败，先检查已生成的部分文件，不要直接当作完整成果。
- **属性记录未激活：**几何继续输出，原属性字段为空，并以 `ATTR_OK=0` 标识；不把源文件中的占位零值当作真实属性。
- **修复后面积变化：**先看 `polygon_repair_details.csv`，必要时在 ArcGIS Pro 中叠加源图核查。`--repair-invalid-polygons` 是允许继续转换，不代表自动确认地质解释正确。
- **图层没有 `.prj`：**若未核实源坐标系且未指定 `--assign-crs`，保留未知空间参考是有意行为，不能凭猜测补写。

## 来源与许可

本仓库不包含地质图原始数据或转换成果。第三方 `pymapgis` 来源于 [leecugb/mapgis2shp](https://github.com/leecugb/mapgis2shp)，其 Apache-2.0 许可证保存在 [vendor/LICENSE](vendor/LICENSE)。本仓库其他文件目前未单独声明许可证；公开可浏览、下载不等于自动授予修改或再分发权利。
