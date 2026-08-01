# 教程：导入有限元结果

有限元求解器算出的磁场逐通道导入。**一个通道一个文件**，每个文件覆盖全部评估点、包含三分量，并且是规范 SI 单位。

## 每通道 CSV 格式

```text
point_id,bx_T,by_T,bz_T
```

`point_id` 必须与采样区域的点 ID 完全一致（顺序也要一致），`bx_T/by_T/bz_T` 是特斯拉单位的三分量。通道标识和分量坐标框架在构建定义中声明：

```yaml
forward:
  kind: finite_element
  channel_files:
    - field_ch0.csv
    - field_ch1.csv
  channel_ids:
    - ch0
    - ch1
  coordinate_tolerance_m: 0.0
```

`channel_ids` 与 `channel_files` 一一对应，且顺序会被固化进 manifest。

## 坐标容差

`coordinate_tolerance_m` 是显式的坐标匹配容差，默认 0。有限元网格点与评估点不可能重排；如果你确实需要按坐标容差匹配，必须显式声明，且每个点只能无歧义地对应到一个评估点。重排一个文件而不重排所有依赖文件是常见错误来源。

## HDF5 与 VTK 变体

- HDF5 字段：数据集 `point_ids`（`[N]`）和 `field_T_per_A`（`[N,3]`），根属性 `channel_id`、`coordinate_frame`、`field_unit=T/A`。
- VTK 族字段：点数据 `field_T_per_A`（`[N,3]`），点身份来自网格点，通道和框架在导入时声明。

## 导出前的纪律

1. 在权威点集上重新导出所有通道，保持点顺序一致。
2. 非 SI 导出先在受控的预处理步骤里确定性转换，并保留原始文件与转换记录。
3. 不要平均、插值或丢弃任何通道。

完成后，在硬件和场景步骤里使用完全相同的通道标识和顺序。
