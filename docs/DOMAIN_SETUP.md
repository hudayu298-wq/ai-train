# lianbanfit.top 接口域名

## 当前核验

2026-10-18 本机 DNS 查询：

| 域名 | 结果 |
|---|---|
| lianbanfit.top | A 记录为 113.45.193.50 |
| api.lianbanfit.top | A 记录为 113.45.193.50（用户添加后已验证） |

后续以实际 DNS 传播结果为准。用户已确认目前尚未备案。域名解析、证书签发与备案是独立事项。

## 推荐解析

在域名当前使用的权威 DNS 服务商控制台添加：

| 配置项 | 值 |
|---|---|
| 类型 | A |
| 主机记录 | api |
| 记录值 | 113.45.193.50 |
| TTL | 服务商默认值 |

App 接口地址计划使用 `https://api.lianbanfit.top`。根域名预留给后续官网。

## HTTPS 实施顺序

1. 确认实名认证、备案状态和计划开放范围，添加上述 DNS 记录。
2. 核实安全组与主机防火墙，开放 Caddy 使用的 80/443；不开放 API 8000 或数据库 5432。
3. 安装 Caddy，部署 `deploy/linux/Caddyfile`，验证配置后启动。
4. 验证域名解析、证书链、HTTP 跳转、登录与未授权请求返回、上传及 AI 请求。
5. 将 Flutter API_BASE 改为该 HTTPS 地址，重新构建并在手机移动网络验证。

准备脚本 `deploy/linux/prepare-https.sh` 会安装 Caddy、验证待启用配置，并保持 caddy/caddy-api 服务被 systemd mask 禁用，阻止安装包自动启动默认网站。配置位置为 `/etc/caddy/liftlab.Caddyfile.pending`。

实际进度：服务器已安装官方稳定版 Caddy 2.11.7，待启用配置校验通过；服务保持 masked，公网 80/443 未由 Caddy 监听，尚未签发证书。

华为云要求大陆节点上的网站或 App 备案后再开通访问，因此当前不启用公网反向代理，不改变 App 为尚不可用的 HTTPS 地址。此准备流程不会签发证书，也不能描述为已可用 HTTPS。

SSL 证书本身可以在备案前申请；若要提前申请，优先采用 DNS 验证。申请证书不替代备案，也不保证未备案业务能被云厂商接入。

备案通过后核实结果、DNS 和安全组，再将待启用配置安装为 `/etc/caddy/Caddyfile`，验证配置、取消 caddy.service 的 mask 并启动服务，最终验证证书链与登录/上传接口。保持 caddy-api.service 停用，只采用 Caddyfile 管理。

App 备案技术资料见 [APP_FILING_CHECKLIST.md](APP_FILING_CHECKLIST.md)。

参考：[Caddy 自动 HTTPS](https://caddyserver.com/docs/automatic-https)、[华为云备案域名要求](https://support.huaweicloud.com/icprb-icp/icp_01_0008.html)、[华为云备案接入要求](https://support.huaweicloud.com/icp_faq/icp_05_0145.html)、[证书申请与备案](https://support.huaweicloud.com/ccm_faq/ccm_01_0180.html)。
