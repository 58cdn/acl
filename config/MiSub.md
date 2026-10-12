# MiSub 使用说明

使用 [`MiSub.ini`](MiSub.ini) 配合 **MiSub 内置转换引擎 + Clash/Mihomo 输出**。
这是将此前 `58cdn-MiSub-example.ini` 整理进仓库的真正 `[custom]` INI 模板，
保留原示例的 11 个远程规则文件和 5 个策略组，不是原生 Clash YAML，也不包含代理节点。

## 推荐：填写远程模板 URL

合并到 `master` 后，填写以下 Raw 地址，不要填写 GitHub 的 `/blob/` 网页地址：

```text
https://raw.githubusercontent.com/58cdn/acl/master/config/MiSub.ini
```

在 MiSub 的 **设置 → 服务设置 → 订阅转换** 区域填写：

| 设置项 | 值 |
| --- | --- |
| 转换引擎 | 内置引擎（`builtin`），不是第三方转换 |
| 模板/配置模式 | 自定义 URL（`custom`），不是本地自定义规则模板 |
| 模板配置/远程模板地址 | 上面的 Raw URL |

保存设置。编辑要使用的订阅组，让模板和转换引擎跟随全局设置，再保存订阅组。
已有订阅组如果配置了自己的模板或第三方引擎，会覆盖全局选择，需一并检查。
只希望单个订阅组使用时，在该组的转换设置中选择内置引擎、自定义 URL，并填写相同地址。
不同版本的中文标签可能略有差异，以下是全局设置字段的对应关系（仅作说明，无需手动编辑数据库）：

```json
{
  "transformConfigMode": "custom",
  "transformConfig": "https://raw.githubusercontent.com/58cdn/acl/master/config/MiSub.ini",
  "subconverter": { "engineMode": "builtin" }
}
```

保留/添加正常的上游节点订阅或手动节点，然后复制 MiSub 生成的 **Clash/Mihomo 订阅链接**到客户端。
不要把本模板 URL 加到“节点订阅源”，也不要把它直接作为含节点的成品导入客户端。
`base64`、`nodes` 或仅节点输出 `list=true` 不会带上完整分流规则。

## 规则与策略组

规则顺序：CGNAT 直连 → 私人直连/代理与 Unity → AI → 局域网/放行 → 广告拒绝 → Telegram/GFW → 中国域名/IP → 漏网策略。

| 远程规则 | 策略 |
| --- | --- |
| `private/direct.list` | DIRECT |
| `private/proxy.list`、`private/unity.list` | 节点选择 |
| `rules/providers/AI.list`、`OpenAi.list` | Ai平台 |
| `rules/providers/LocalAreaNetwork.list`、`UnBan.list` | DIRECT |
| `rules/providers/BanAD.list` | REJECT |
| `rules/providers/Telegram.list`、`ProxyGFWlist.list` | 节点选择 |
| `rules/providers/ChinaDomain.list` | DIRECT |

五个模板策略组为 `节点选择`、`手动切换`、`自动选择`、`Ai平台`、`漏网之鱼`。
`手动切换` 和 `自动选择` 使用 MiSub 支持的 `.*` 匹配节点，不依赖 SublinkPro 的 `__ALL_PROXIES__`。
自动选择使用一个 Cloudflare 检测 URL，间隔 300 秒、容差 50；没有三端点自动容错语义。
`节点选择` 默认指向自动选择，AI 和漏网组默认指向节点选择；其中的 DIRECT 是手动选项。
MiSub 自身可能额外生成 DNS 出口组，不能用“输出必须恰好五个组”判断成功。

## 兼容边界

- 本模板只整理此前的精选示例，不等同于 `Clash.private.yaml` 的全量规则和设置。没有复制私人 DNS、监听端口、局域网访问或三个测速组。
- 私人域名的 DIRECT 规则不负责 DNS 解析，也不创建 VPN/系统路由。需要私域解析时，在 MiSub 的 DNS 配置中使用自己已核实的解析器，不能猜内网 DNS 地址。
- 当前不引用 `ChinaCompanyIp.list`：MiSub 的 INI→Clash 渲染器按文件名推断 `ipcidr`，而本仓库此文件是带 `IP-CIDR,` 前缀的 classical text。不要未经验证把它加回来。
- 原 `Clash.ini` 名称虽然以 `.ini` 结尾，正文实际是 YAML；不能替代这里的 `MiSub.ini`。`Clash.private.yaml` 中的占位符也不是本模板的写法。
- 当前 MiSub INI 渲染对附加参数（例如规则的 `no-resolve`）并非完整透传；本模板不承诺原生 YAML 的逐字段等价。
- 此次只为 Clash/Mihomo 输出提供配置说明和结构回归，不声称 Surge/Sing-Box 等其他客户端已经实测兼容。
- `master` 地址会跟随仓库更新，模板和规则缓存可能延迟生效。模板变更后应刷新 MiSub/客户端订阅并检查最终输出；仅换模板 URL 的版本不等于冻结其内部所有规则 URL。
- 仓库是公开的。不要提交真实节点、订阅 Token、密码或其他凭据。

## 检查方法

本模板的离线结构回归：

```bash
python -m unittest discover -s tests -p 'test_misub_template.py' -v
```

仓库完整回归继续使用原来的 `python -m unittest discover -s tests -v` 与 CI。
新增测试检查格式、策略引用、规则顺序、节点匹配方式和远程 URL 白名单，不代替 MiSub 或客户端的实际运行。
仓库原有 SublinkPro/Mihomo CI 主要验证原生 YAML，不能将其成功当成 MiSub 端到端验证成功。

实际使用时检查 MiSub 最终生成的 YAML：`proxies` 有节点；手动/自动组有节点；不残留 `__ALL_PROXIES__`；
存在指向本仓库的 `rule-providers`；最后是 `MATCH,漏网之鱼`。随后由实际客户端完成配置加载和联网验证。

实现依据（2026-10-12 核对 `58cdn/MiSub` 的 `main`，线上部署可能不同步）：
[模板选择 UI](https://github.com/58cdn/MiSub/blob/main/src/components/settings/sections/ServiceSettings/TransformCard.vue)、
[INI 解析](https://github.com/58cdn/MiSub/blob/main/functions/modules/subscription/template-parsers/ini-template-parser.js)、
[Clash 渲染](https://github.com/58cdn/MiSub/blob/main/functions/modules/subscription/template-renderers/render-clash.js)。
