更新 ACL4SSR 固定提交快照、各规则文件 SHA256；来源与许可见 rules/snapshot.json 和 rules/ACL4SSR-LICENCE。

下载批次已通过非空、大小/超时、HTML、编码、规则语法和完整性校验；提交前执行真实 SublinkPro 生成及 Mihomo 配置加载检查。提交后另行触发验证工作流，检查 bot 分支上的 provider URL。

请人工审阅规则语义、上游来源与 CI 结果后决定是否合并。本 PR 不设置自动合并；测试不证明国内/海外的真实节点连通性。失败时旧 master 快照保留。
