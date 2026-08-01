# 教程：用导体路径构建动态几何环境

当评估区域会随位姿运动时，固定响应矩阵不再忠实描述物理。这时用导体路径构建**动态几何**环境：运行期按当前位姿实时计算有限段 Biot-Savart 响应。

## 路径文件

CSV 路径的头部固定为：

```text
channel_id,path_id,vertex_index,x_m,y_m,z_m,closed
```

每个 `(channel_id, path_id)` 唯一；顶点按电流方向排列；`closed` 表示路径是否闭合。VTP 则是 `PolyData`：内联 ASCII 的 `Points` 与 `Lines`（`connectivity`/`offsets`），`CellData` 每条线带 `channel_id`、`path_id` 和 `closed`。

## 通道几何 YAML

```yaml
schema_name: magshield_env.geometry_channels
schema_version: 1
channel_ids:
  - ch0
contributions:
  - rotation:
      - [1.0, 0.0, 0.0]
      - [0.0, 1.0, 0.0]
      - [0.0, 0.0, 1.0]
    translation_m: [0.0, 0.0, 0.0]
    allow_improper: false
    gain: 1.0
```

每个 `contribution` 把一个路径副本旋转、平移、缩放（`gain`）后叠加到通道响应上；`allow_improper` 控制是否允许镜像（行列式为负）的变换。

## 构建定义

```yaml
forward:
  kind: geometry
  paths: paths.csv
  channels: channels.yaml
  path_frame: body
  pose_source_frame: body
  pose_target_frame: body
  pose_cache_size: 64
```

`pose_source_frame` 必须等于采样点的坐标框架，`pose_target_frame` 必须等于 `path_frame`。每个位姿被解释为从点框架到路径框架的刚性变换。

## 运行期行为

- 每个运行时帧都需要一个位姿；没有位姿就无法求响应。
- 完全相同的位姿可以命中身份绑定缓存；未见过的位姿直接计算。
- 动态包必须包含完整导体几何；不存在固定矩阵回退。

详细物理语义见[概念：动态几何响应](../concepts/dynamic-geometry)。
