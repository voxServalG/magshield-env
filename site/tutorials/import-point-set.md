# 教程：导入测量点集

测量点集是评估区域的最常见来源。v0.1 只接受规范 SI 源文件，所有数值必须是有限的 float64。

## CSV 点集

CSV 的头部和列顺序是固定的：

```text
point_id,x_m,y_m,z_m,weight
```

`point_id` 非空且唯一；坐标和权重有限；权重必须为正。坐标单位是米，坐标框架在构建定义的 `region.frame` 里显式声明——CSV 文件本身不写框架。

```yaml
region:
  kind: import
  path: points.csv
  frame: body
```

## HDF5 与 VTK 族变体

- HDF5 根数据集为 `point_ids`、`points_m`、`weights`，根属性为 `coordinate_frame` 和 `length_unit=m`。
- VTK 族把坐标存为网格点，点数据 `weight` 附在点上；身份用标量 `point_id`，或无损的 `point_id_utf8` 加 `point_id_length` 组合；框架仍由构建定义声明。

精确布局见[参考：格式契约](../reference/format-contracts)。

## 导入前检查清单

1. 坐标已经确定性转换为米，转换过程留在包外作为溯源记录。
2. 点 ID 唯一且稳定——后续所有响应文件都按这个 ID 顺序对齐。
3. 权重为正；如果你只想均匀评估，所有权重取 1 即可。
4. 框架字符串拼写一致；框架是精确身份，不是描述文字。

导入后先在向导或 `inspect_build` 里审查点数、范围、顺序和权重，再进入正向模型步骤。
