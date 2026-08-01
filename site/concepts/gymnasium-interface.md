# 概念：Gymnasium 接口语义

导出的包通过标准 Gymnasium `reset/step` 接口消费，不包含任何训练代码。

## 观测

- `full_field`：所有评估点上的全场观测（残差场矢量，可选加外部场）。
- `basis`：用声明好的线性基对场做投影；基的矢量分量框架必须等于响应框架。
- `include_pose`：把当前位姿（平移与四元数）加进观测。

## 动作

`action_mode` 当前固定为 `current_delta`：动作是归一化的电流增量，硬件模型映射进合法区间（见[硬件投影](hardware-projection)）。

## 奖励

奖励由构建时声明的项组成：场误差（阈值、尺度、权重）、功率、电流变化、约束惩罚，以及可选的额定电流偏差。每一项都是物理声明，不是隐藏超参数。

## 终止与截断

- `terminated`：回合因非法动作且 `constraint_mode=terminate` 而结束。
- `truncated`：回合达到 `episode_length`（轨迹场景可配 `random_start`）。
- 其余情况下 `terminated`/`truncated` 为假，环境持续推进。

## info 中的证据

`info` 携带硬件约束证据（请求动作与实际动作、命中的边界）。观测形状、动作形状和奖励量纲应与算法假设一致；不一致时回到构建定义修改，而不是在环境外打补丁。
