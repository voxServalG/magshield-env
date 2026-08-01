# 操作指南：生成或导入采样区域

采样区域决定环境在哪些点上评估残差场。先想清楚物理边界、间距和框架，再打开向导或写构建定义。

## 生成式区域

构建定义支持四种生成式区域，全部使用规范 SI 单位（米）：

| 类型 | 关键字段 | 说明 |
|---|---|---|
| `box_cartesian` | `minimum_m`、`maximum_m`、`spacing_m` | 笛卡尔网格体 |
| `cylinder_cartesian` | `radius_m`、`height_m`、`spacing_m`、`axis`、`center_m` | 沿 x/y/z 轴的圆柱网格 |
| `sphere_cartesian` | `radius_m`、`spacing_m`、`center_m` | 球体内部网格 |
| `sphere_surface` | `radius_m`、`point_count`、`center_m` | 球面上的采样点（至少 4 个点） |

所有生成式区域都有 `frame` 字段（默认 `body`）。`spacing_m` 决定网格间距；`sphere_surface` 用点数而不是间距。

## 导入式区域

```yaml
region:
  kind: import
  path: points.csv
  frame: body
```

支持 CSV、HDF5 和 VTK 族点集。CSV 头部必须是 `point_id,x_m,y_m,z_m,weight`；HDF5 和 VTK 的布局见[参考：格式契约](../reference/format-contracts)。

## 进入下一步前的审查清单

1. **点数**：与你的评估预算和有限元网格一致。
2. **范围**：覆盖目标控制区域，没有意外的缺口或越界点。
3. **框架**：字符串拼写与后续响应、外场声明完全一致。
4. **顺序**：点 ID 顺序会被固化；之后所有通道文件都按这个顺序对齐。
5. **权重**：权重为正；均匀评估时全部取 1。

审查发现问题就回到源头修正，不要在响应文件里单独重排。
