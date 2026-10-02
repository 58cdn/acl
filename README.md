# acl

Clash Meta / Mihomo 的 SublinkPro 模板与经审阅的 ACL4SSR 规则快照。

## 使用与真实格式

`config/Clash.ini` **实际是 YAML**，历史扩展名保留以兼容已有链接；不是 subconverter 的 `[custom]` INI。上游 SublinkPro 的 `DecodeClash` 读取 YAML、合并订阅节点、展开 `__ALL_PROXIES__`。不要把本文件交给 INI 解析器，也不要把模板当作已经有节点的成品。

推荐私人配置入口：在 SublinkPro 中使用本仓库的
`https://raw.githubusercontent.com/58cdn/acl/master/config/Clash.private.yaml`。
该文件由基础模板与 `config/private.override.yaml` **真实合成**，仍保留订阅占位符，包含私域的 system DNS 策略。原 `Clash.ini` URL 仍是可转换基础模板，通过原生 rule-provider 引入私人域名及 Unity；私域 nameserver-policy 请使用完整私人入口。所有 `master` URL 需本 PR 合并后才发布，PR 期间请使用对应提交 SHA URL。

私人维护步骤：

1. 在 `config/private.override.yaml` 修改个人规则/DNS；Unity 域名在同层级的 `private/unity.list` 修改。
2. 执行 `python -m pip install -r requirements.txt`，再执行 `python scripts/build_private.py`。
3. 一起提交 canonical 文件、`private/direct.list`、`private/proxy.list`、`config/Clash.private.yaml` 与旧入口 `config/clash.override.yaml` 的生成更新。CI 会拒绝过期产物。

`private` 表示个人策略层，**不是访问控制**；本仓库内这些域名原本已公开。不要提交新凭据、真实订阅链接、节点密码或不应公开的内网信息。CI 只用保留地址段中的虚构节点。

## DNS 与 IPv6

- 使用 fake-ip，默认同时关闭顶层 `ipv6` 和 `dns.ipv6`。需要 IPv6 时用 `python scripts/prepare_template.py --private --ipv6 --output build/template.yaml`，同时启用两处开关并设置 `fake-ip-range6: fc00::/18`，把产物作为 SublinkPro 模板。只开布尔值而没有 IPv6 池，固定内核会对 fake-ip AAAA 返回空答案。固定内核默认还要求宿主接口存在 global-unicast IPv6 地址，否则会清空 IPv6 池，AAAA 仍为空；该开关不配置系统/TUN 路由，不保证节点或 ISP 的 IPv6 连通性，地址池与现网冲突时应先调整池。
- 常规解析与 `.cn` 策略使用阿里、腾讯两家国内 DoH；海外 fallback 的 Cloudflare/Google DoH 和 Cloudflare DoT 均显式加 `#自动选择`，强制通过只含代理测速组的出口。AI 域名走该 fallback；普通域名依照 fallback-filter 处理异常答案。这是国内解析器与海外代理 fallback 的分工，不按用户所在地自动选择，也不声称覆盖全部 DNS 污染形态。
- `default-nameserver` 使用国内 DNS 的 IP 引导加密解析器主机名，可能产生明文引导查询。`proxy-server-nameserver` 独立使用国内 DoH 解析代理节点，不能指回依赖该节点的代理 DNS，避免循环依赖。海外解析器经 `自动选择`，即使流量选择器手动设成 DIRECT 也不会自动改成 DNS 直连；代理全部故障时应报告解析失败。AI 域名指定 fallback 仅影响 DNS，不改变 AI 流量策略。
- 私人入口把 git.yun、open.yun 和 sa.linux.yun 交给 `system` DNS，并加入 fake-ip-filter。固定 Mihomo 的 Windows 实现枚举已启用且有网关的适配器 DNS，POSIX 实现读取 `/etc/resolv.conf`；它不是操作系统完整 split-DNS/Windows NRPT 调度器，也不保证枚举出 Tailscale/ZeroTier 的专用解析器。若 system 不可用，在 `config/private.override.yaml` 的相应 nameserver-policy 中填写你已核实的私域 DNS 地址（标量或列表），再生成。不要猜内网 IP，也不要指回 Mihomo 自己的 DNS 监听地址或形成转发环。fake-ip-filter 本身不负责 DNS 路由。
- 旧 `config/clash.override.yaml` 是专门生成的 Clash Party 覆盖入口：`fake-ip-filter+` 追加并保留 `*.lan`、`*.local`、localhost、`*.ts.net`。scalar `+.git.yun: system` 保留字面 `+`；只有数组型策略键转义为 `<+.git.yun>`，避免客户端误判为前插指令。不要直接用 canonical 文件代替旧覆盖入口。
- fallback-filter 只过滤保留/异常结果，不把整个 CGNAT 网段当污染；加密 DNS、节点可达性及私域解析仍取决于运行环境。不作“零泄漏”或国内/海外均可联网承诺。

## 单 URL 测速与容错边界

Mihomo `url-test.url` 是单个字符串，没有 `urls` 数组。`自动选择` 是可见的手动端点选择器，下面三个 url-test 都使用同一订阅节点池：Cloudflare、Google `generate_204`、华为国内连接检测端点。国内 HTTP 204 只证明该端点可达，不能证明海外 AI 服务可达。

生成时可运行 `python scripts/prepare_template.py --private --probe --output build/template.yaml`：依次要求三个端点返回 HTTP 204，选择首个成功的测速组；输出失败端点记录，**全失败报错且不写产物**。不加 `--probe` 则保留确定的 CF 默认值，不能声称已完成探测。此探测发生在生成机器的已有网络路径上，不代表每条代理节点。

运行期每组按自己的单一端点测速。端点失效时可切换另外的可见组，或重新运行生成命令并刷新订阅；这里没有伪装成运行期多端点自动 OR/quorum 的外层 fallback。组全不可达时内核可能仍显示一个已选择节点，**显示节点名不代表健康**；应查看三个组的失败/延迟记录并人工处理，自动链中没有 DIRECT。

测速组采用 Mihomo `include-all-proxies: true` + `expected-status: 204`，`手动切换` 保留原 `__ALL_PROXIES__` 契约。原因是固定版本 SublinkPro 在看到 expected-status 时保留该组，不展开占位符；两者不能混用。空订阅/遗留占位符/策略名冲突在成品验证中被拒绝。客户端历史保存的手动选择可能覆盖默认项，首次使用请检查当前选择。

## 规则优先级

顺序为 CGNAT DIRECT → 私人/Unity → AI → 原 ACL4SSR 基础分类 → 中国 IP → 漏网策略。保留个人 ssh.git.yun、git.yun、open.yun、thh.cc、ToDesk、115、docs.qq、lib.ituohuang.com、sa.linux.yun、api.pub.dxx.cld.pub 直连，以及原个人代理域名和 Unity 安装依赖例外。

`100.64.0.0/10` 是共享地址/CGNAT 段，也被 Tailscale 常用；DIRECT 必须在宽泛代理前，但它不创建路由。其他使用 CGNAT 的服务也会受此例外影响。ZeroTier 地址由各网络配置决定，仓库没有提供可核实的专属网段，不把所有 ZeroTier 假定为这个段，也不修改本机或 VPS 的 VPN、DNS、路由。

Unity 的 unity.com、unity3d.com、unitychina.cn、plasticscm.com、packages.unity.com、upm-cdn.unity.com、download.packages.unity.com 及原依赖例外统一走 `节点选择`。`Ai平台` 覆盖 OpenAI/ChatGPT/Claude/Gemini/Copilot，默认 `节点选择`，放在 Bing/Microsoft DIRECT 前；DIRECT 仅为手动选项，没有自动 DIRECT 回退。用户如果手动把父组 `节点选择` 改成 DIRECT，也会影响 AI。

## 镜像、许可与每日同步

`rules/sources.json` 保留原 31 个 ACL4SSR 来源白名单，`rules/providers/` 提供 `classical` + `format: text` 镜像。`rules/snapshot.json` 记录单一上游提交、原始及发布 SHA256。许可见 `rules/ACL4SSR-LICENCE`（上游 CC BY-SA 4.0）；本地规范化包括 LF 换行和兼容性注释，保留来源归属。

Mihomo 不支持上游 ChinaMedia、ProxyMedia、Download 中的 9 条 `URL-REGEX`。这些原文在镜像中保留为注释，精确清单在 `rules/compatibility.json`；不把无效语法作为可用功能，也不扩大到整域替代 URL 路径规则。新增不支持语法必须人工审查。Surge.ini 未变，其既有上游规则仍按 Surge 语义使用。

`sync-rules.yml` 每日 03:17 UTC 取得一个上游 SHA，用限定来源、4 MiB 上限、单次/整批工作流时限、有界重试下载；拒绝重定向、空/HTML/乱码、非法 CIDR/规则。完整批次验证后才暂存替换；任何下载或校验失败不改旧快照，不提交。替换中发生文件系统故障时工作流失败，不 push；仓库发布是单一 Git 提交，不会发布半批数据。

有变化后先做真实生成与内核检查，提交到 `bot/sync-rules-<SHA>`，开 PR 并显式触发验证，不直接写 master/main，不 force、不自动 merge。已有 bot 分支不覆盖，需检查已有 PR。GitHub 默认 GITHUB_TOKEN 创建的 PR 不保证触发普通 PR 事件，所以不能省略同步 job 内部验证或显式 dispatch。

**当前平台前提**：仓库 Actions 已启用；自动创建同步 PR 尚待首次有变更的实际运行验证。REST 返回 `can_approve_pull_request_reviews: false` 仅足以说明不允许批准 review，不能单独证明 PR 创建被禁用。若创建实际失败，job 将保留准确错误并报告阻塞；脚本不会更改设置、扩大凭据权限或配置 PAT。`actions: write` 仅用于 dispatch 验证，`pull-requests: write` 不等于审批/合并授权。此任务不静默扩大权限。

手动刷新：取得 ACL4SSR 的完整提交 SHA 后执行 `python scripts/sync_rules.py --revision <SHA>`，审阅 diff、运行验证、通过 PR 合并。回滚通过新的 PR 恢复旧快照/模板，客户端缓存按 provider interval 或手动刷新生效。

## 验证与证据

本地快速检查：`python scripts/validate.py` 和 `python -m unittest discover -s tests -v`。完整 CI 固定 SublinkPro 提交，直接执行其 `DecodeClash`，输出基础、私人覆盖、IPv6 三种含虚构节点的成品。每种均做结构/顺序回归与官方 Mihomo v1.19.31 `-t`；还展开全部 provider 条目后再次交给真实内核解析，避免只校验惰性 provider 声明。工具版本/校验值在 `ci/tools.json`。另下载并校验固定 Clash Party 的原始 `deepMerge`，在真实生成结果上测试旧覆盖合并、全部原 fake-ip-filter 和字面策略键，再做两次内核 `-t`。DNS 行为测试仅启动临时 loopback DNS 子进程，关闭代理端口/TUN/外部控制器和外部 DNS，查询 A/AAAA 验证默认关闭与 IPv6 地址池，并保留缺池/关闭两组负向对照。仅测试子进程使用上游 `SKIP_SYSTEM_IPV6_CHECK=true`，隔离 CI runner 是否有 global-unicast IPv6 的差异，非空 AAAA 断言不跳过；这不证明生产宿主通过接口检查，也不修改系统 DNS、路由或 VPN。

合并前验证 **PR HEAD SHA** 上 34 个 provider URL 的 HTTP 响应、规则内容和逐字节快照一致性，明确映射到未来发布 URL；不会把 master 尚未存在的新文件 404 当作成功。master push 后再验证全部真正发布 URL。`validation-evidence` artifact 保存虚构成品和 URL 证据，Action 结果以具体 SHA 的运行页为准。

这些检查证明语法、生成契约、规则内容和加载结构，**不证明**国内/海外实际联网、真实订阅节点、DNS 无泄漏、平台地域访问或本机 VPN 路由效果。

官方依据：[SublinkPro loader](https://github.com/ZeroDeng01/sublinkPro/blob/11479dacf0a73ec0e43e1ee7e811ad31136e46f9/node/protocol/clash.go)、[Mihomo DNS](https://wiki.metacubex.one/config/dns/)、[固定内核 DNS 出口](https://github.com/MetaCubeX/mihomo/blob/v1.19.31/tunnel/dns_dialer.go)、[固定内核 fake-ip 中间件](https://github.com/MetaCubeX/mihomo/blob/v1.19.31/dns/middleware.go)、[IPv6 宿主检查](https://github.com/MetaCubeX/mihomo/blob/v1.19.31/config/utils.go)、[Clash Party merge](https://github.com/mihomo-party-org/clash-party/blob/f528f65762dd4db818414923c60bd8522b64e972/src/main/utils/merge.ts)、[代理组字段](https://wiki.metacubex.one/config/proxy-groups/)、[url-test](https://wiki.metacubex.one/config/proxy-groups/url-test/)、[rule-provider](https://wiki.metacubex.one/config/rule-providers/)、[固定内核规则解析器](https://github.com/MetaCubeX/mihomo/blob/v1.19.31/rules/parser.go)。
