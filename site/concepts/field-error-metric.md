# 概念：场误差指标

环境用**一个**加权矢量均方根值衡量残差场。对残差矢量 `r_i` 和正权重 `w_i`：

```text
field_rms = sqrt(sum_i(w_i * (rx_i^2 + ry_i^2 + rz_i^2)) / sum_i(w_i))
```

几点必须理解：

- 这是对点做矢量模长的 RMS，不是对 `3N` 个标量分量做 RMS。
- 所有权重乘以同一个正常数，指标不变；相对权重才有意义。
- 奖励里的 `field_threshold_t`、`field_scale_t` 和 `field_weight` 都作用在这个单一指标上。
- 权重来自点集；均匀评估时所有权重取 1。

指标定义在[格式契约](../reference/format-contracts)里与打包布局一起冻结，改变它需要新的 ADR 和契约测试。
