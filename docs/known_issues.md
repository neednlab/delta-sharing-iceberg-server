## 已知问题
1. Control Plane中的Admin URL未启用身份认证，当前仅限本机(localhost)访问。符合MVP预期设计，暂时无需做安全增强
2. Iceberg Manifest文件下载时使用串行逻辑，如果Manifest文件数量较多，可能存在潜在性能问题。符合MVP预期设计，暂时无需优化
3. API未设计限流控制，考虑部署时由云服务层承担包括网络限流，DDos攻击防护等职责。符合MVP预期设计，暂时无需优化