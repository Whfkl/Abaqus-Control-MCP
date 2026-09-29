# Abaqus Control MCP 2.0.0：工具契约

目标：保留原有六个工具，运行于 MCP `2026-07-28`，提高结果可信度。本文记录设计边界；使用方法以根目录 README 为准。

| 工具 | 主要契约 |
| --- | --- |
| `ping` | 检查当前 CAE 进程与会话。 |
| `run_python` | 只接收 `code`；表达式返回值或本次显式赋给 `result` 的值；stdout、stderr、异常和 `executionId` 同属本次调用。 |
| `set_workdir` | 只切换到已存在的绝对目录，返回前后路径。 |
| `monitor_job_status` | 列出作业，或合并 CAE/.log/.sta/.dat/.msg 的状态证据；文件独立终态需用 `since` 绑定本次提交时间。同一工具中的 `terminate=true` 请求 `job.kill()`，单独报告是否确认。 |
| `inspect_odb` | 只读元数据、指定场变量的 min/max、历史曲线；步骤时间明确分为起始、结束和持续时间。 |
| `capture_viewport` | PNG/TIFF 为 MCP 图片内容块；可选保存路径；文本不含 base64。SVG/EPS/PS 仅保存路径。 |

## 响应原则

- 每个桥接请求使用独立 UUID。插件的内核响应必须带回相同 `executionId`；客户端检查不匹配响应。
- `run_python` 的持久命名空间可保存用户变量，但每次运行前后清除 `result`。队列等待超时且尚未启动的请求会取消；已进入内核后超时，其结局为 `UNKNOWN`，不能自动重试。
- Python/Abaqus 异常以工具错误返回，包含原始异常文本、真实用户代码位置、精简调用链和有限的纠错建议。桥接内部保留完整 traceback，避免在工具响应中重复发送。
- 纠错候选按 key、成员、变量名和参数名分别匹配，最多返回三个；空 stdout/stderr、重复请求 ID 和整段 traceback 不进入默认 `run_python` 响应。
- GUI 插件默认不写请求日志。仅在 `ABAQUS_MCP_DEBUG=1` 时生成有大小上限的轮转日志；启动时清理旧版固定路径日志。
- 作业状态的 `COMPLETED / FAILED / TERMINATED` 只在有终态证据时返回；冲突和疑似旧文件返回 `UNKNOWN` 并说明来源。仅发出终止请求不代表已终止。
- ODB 向量默认统计模长，张量必须指定分量；历史序列有采样上限，并报告原始点数。
- 图片的 base64 仅用于桥接传输和 MCP 图片块，不存放在结构化 JSON 中。

## 尚待真实工程验证

- 正在运行的 CAE 插件需重启后才能加载新的插件代码；插件侧 ID 校验与新启动图案需在重启后验证。
- `terminate=true` 未对正在求解的专用测试作业执行破坏性验证；确认字段故意要求终态且无锁文件。
- 不同求解器和提交方式可能产生不同日志措辞；未知或冲突证据应保持 `UNKNOWN`，并用实际案例完善识别规则。
