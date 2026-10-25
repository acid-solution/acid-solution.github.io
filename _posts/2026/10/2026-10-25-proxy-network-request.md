---
title: "一次网络请求的代理之旅：串起机场、DNS、代理协议与翻墙原理"
date: 2026-10-25 17:00:00 +0800
categories: [计算机网络]
tags: [proxy, dns, networking, mihomo]
description: "跟着一次 HTTPS 请求，理解代理、机场、DNS、分流、代理协议与网络排障。附按讲述顺序排列的可跳转术语索引。"
permalink: /posts/proxy-network-request/
toc: true
math: false
---

打开代理软件，导入订阅，选一个节点，然后访问网站。这几个操作背后，至少有三个问题：请求怎么进入代理，代理怎么找到远端节点，节点又怎么替我们访问网站？

把这条路径弄清楚，许多看起来零散的名词就有了位置。机场提供服务，订阅提供配置，系统代理决定应用把连接交给谁，DNS 帮助寻找地址，分流规则决定出口，代理协议约定本机和节点如何通信。

这篇文章跟着一次访问向前走：在电脑上开启代理，用浏览器打开 `https://www.example.com/articles/proxy`。我们先追踪一种常见情况：浏览器使用本机 HTTP 代理，客户端选择远端节点，目标网站使用基于 TCP 的 HTTPS。TUN、SOCKS5 和其他分支会在相关位置展开。

文中的域名与端口用于说明原理。实际访问可能命中缓存、复用已有连接，省略部分步骤；分流与 DNS 也可能相互触发，下面按便于理解的逻辑顺序讲述。

<span id="term-index"></span>

## 本文涉及的知识点

下面按正文讲述顺序排列。第一次阅读可以直接往下看，需要查某个名词时再从这里跳转。

- **出发前，认清参与者：** [代理](#proxy) · [VPN](#vpn) · [翻墙与 GFW](#circumvention) · [客户端](#client) · [内核](#core) · [机场](#airport) · [订阅](#subscription) · [节点](#node) · [VPS](#vps)
- **第 1 站，明确访问目标：** [URL](#url) · [域名](#domain) · [IP、IPv4 与 IPv6](#ip) · [端口](#port) · [HTTP](#http) · [HTTPS](#https)
- **第 2 站，把请求交给本机代理：** [回环地址](#loopback) · [监听端口](#listen) · [系统代理、WinINET 与 WinHTTP](#system-proxy) · [代理环境变量](#environment-proxy) · [程序代理设置](#app-proxy) · [HTTP 代理](#http-proxy) · [CONNECT](#connect) · [SOCKS5](#socks5) · [mixed-port](#mixed-port) · [TUN](#tun) · [透明代理](#transparent-proxy)
- **第 3 站，决定流量去向：** [入站与出站](#inbound-outbound) · [分流规则](#rules) · [域名规则](#domain-rule) · [IP 规则、CIDR 与 GEOIP](#ip-rule) · [规则模式与全局模式](#proxy-mode) · [DIRECT 与 REJECT](#direct-reject) · [代理组](#proxy-group) · [select](#select) · [url-test](#url-test) · [fallback 代理组](#fallback-group) · [load-balance](#load-balance)
- **第 4 站，寻找连接地址：** [DNS](#dns) · [解析器](#resolver) · [DNS 缓存与 TTL](#dns-cache) · [A、AAAA 与 CNAME](#dns-records) · [引导解析](#bootstrap) · [DNS 污染](#dns-poisoning) · [DoH](#doh) · [DoT](#dot) · [DNSSEC](#dnssec) · [mihomo 的 DNS 配置](#mihomo-dns) · [fake-ip](#fake-ip) · [redir-host](#redir-host) · [域名嗅探](#sniffing)
- **第 5 站，建立到节点的通信通道：** [TCP](#tcp) · [UDP](#udp) · [QUIC](#quic) · [隧道](#tunnel) · [TLS](#tls) · [证书](#certificate) · [ClientHello](#clienthello) · [SNI](#sni) · [ECH](#ech) · [协议指纹、JA3 与 JA4](#fingerprint) · [主动探测](#active-probing) · [Shadowsocks](#shadowsocks) · [VMess](#vmess) · [Trojan](#trojan) · [VLESS](#vless) · [REALITY](#reality) · [uTLS](#utls) · [Hysteria2](#hysteria2) · [拥塞控制与 Brutal](#congestion) · [Salamander](#salamander)
- **第 6 站，沿线路抵达出口：** [路由器、运营商与路由](#route) · [入口、中转与落地](#relay) · [出口 IP](#exit-ip) · [延迟、带宽与丢包](#performance)
- **第 7 站，访问目标网站：** [远端 DNS](#remote-dns) · [CDN](#cdn) · [端到端 HTTPS](#https-end-to-end) · [HTTP 状态码](#http-status) · [IP 风控](#ip-reputation)
- **第 8 站，响应返回之后：** [响应与连接复用](#response) · [隐私边界与 DNS 泄漏](#privacy)
- **遇到问题时：** [按链路排障](#troubleshooting) · [Windows 检查命令](#windows-checks) · [端口保留与绑定失败](#port-reservation)

<span id="overview"></span>

## 先看一眼整条路径

准备阶段，我们获得访问远端节点所需的信息：

```text
机场或自建服务器的维护者
        ↓ 提供配置
订阅 / 手动填写的节点信息
        ↓ 导入
本机代理客户端
```

实际访问时，数据沿这些角色传递：

```text
浏览器：我要访问 www.example.com:443
        ↓ 本机 HTTP 代理
本机客户端：接收连接，匹配规则，选择节点
        ↓ 必要时解析节点域名，建立到节点的通信通道
远端代理节点：接收目标地址，连接目标网站
        ↓ 必要时解析目标域名
目标网站：处理 HTTPS 请求，返回响应
        ↑ 响应经节点、本机客户端返回浏览器
```

DNS 负责在需要时寻找地址，代理负责转交连接和数据。它们会协作，但职责不同。下面从这次访问开始前的准备工作说起。

## 出发前：软件、服务和节点，分别是什么

<span id="proxy"></span>

**代理（Proxy）**的基本意思是：由一个中间角色代你与另一端通信。浏览器可以直接连接网站，也可以先连接代理，由代理建立后续连接并转发数据。

代理有很多用途，包括企业网络接入、缓存、访问控制和转发。我们讨论的是用户访问外部服务时使用的正向代理。

<span id="vpn"></span>

**VPN（Virtual Private Network，虚拟专用网络）**通常通过隧道把设备接入另一个网络，并配合路由决定哪些流量进入隧道。企业远程办公就是常见用途。HTTP、SOCKS 代理则通过应用或代理协议接收连接请求。两类工具在使用体验上可能接近，具体工作层次和接管范围需要看实现。

一些代理软件在手机上借助系统的 VPN 接口接收流量。界面出现“VPN”图标，只能说明它使用了相应系统接口，不能据此判断远端采用什么代理协议。

<span id="circumvention"></span>

**翻墙**是对绕过网络访问限制的一种俗称，描述的是用途。**GFW**是讨论中国大陆跨境网络过滤体系时常用的称呼。DNS 应答干扰、IP 或端口阻断、依据握手和流量特征实施限制，都可能影响访问；一次超时本身无法证明发生了哪一种干预。

<span id="client"></span>
<span id="core"></span>

我们安装的**代理客户端**通常包含图形界面和**代理内核**。界面负责导入订阅、展示节点和修改设置；内核负责接收连接、匹配规则、解析地址以及转发数据。mihomo 是一种代理内核，多个图形客户端可以使用它。

这也解释了为什么“窗口还开着”和“代理正常工作”是两回事：界面存在，并不能证明内核已成功监听端口或连接节点。

<span id="airport"></span>
<span id="subscription"></span>

**机场**是代理服务提供方的一种俗称，并非标准网络协议。它一般维护一批节点，向用户提供账号、流量额度和配置。

**订阅**是客户端获取、更新这些配置的一种方式。订阅链接可能返回节点列表，也可能包含规则、代理组和 DNS 设置，具体取决于服务与格式。导入订阅，相当于把连接所需的信息交给客户端。

订阅链接常带有身份令牌，应像账号凭据一样保存。文章截图和公开配置需要使用示例值。

<span id="node"></span>
<span id="vps"></span>

**节点**是客户端中一个可选的代理连接配置，通常包括服务器地址、端口、协议和认证参数。一个节点名称不一定对应一台独占服务器，服务端还可能有负载均衡、中转或多个出口。

**VPS（Virtual Private Server，虚拟专用服务器）**是可以自行部署服务的一类虚拟服务器。自建代理时，你负责维护服务器和配置；购买机场服务时，这些工作主要由服务提供方承担。两种方式都需要一个能接收连接并转发流量的远端角色。

到这里，我们已经有了客户端，也有了至少一个节点配置。现在打开浏览器。

## 第 1 站：浏览器先明确自己要访问谁

<span id="url"></span>

输入地址：

```text
https://www.example.com/articles/proxy
└──┬──┘ └──────┬──────┘└──────┬──────┘
  协议          主机名          路径
```

这是一条 **URL**，用于描述资源的位置与访问方式。

<span id="domain"></span>

其中 `www.example.com` 是一个**域名**。域名便于人和应用识别服务；建立网络连接时，负责连接的一方通常还要获得对应的 IP 地址。这一步会在后面的 DNS 环节完成。

<span id="ip"></span>

**IP 地址**用于网络寻址，常见格式包括 IPv4 和 IPv6，例如示意地址 `192.0.2.10` 与 `2001:db8::10`。一台设备可以有多个地址，一个域名也可能对应多个地址。

<span id="port"></span>

同一个 IP 上可以运行多个网络服务。**端口**配合地址及传输协议帮助区分通信端点。HTTPS 通常使用端口 `443`，因此上面的 URL 在连接目标这一层可以理解成 `www.example.com:443`。

<span id="http"></span>
<span id="https"></span>

**HTTP**约定客户端和服务器怎样表达请求与响应，例如请求哪个路径、返回什么状态码和内容。**HTTPS**通过 TLS 保护 HTTP 通信，提供传输中的机密性、完整性和身份验证；TLS 与证书稍后再讲。

浏览器现在知道自己想访问什么，但它已经配置了本机代理，因此接下来先与本机代理通信。

## 第 2 站：请求怎样进入本机代理

<span id="loopback"></span>
<span id="listen"></span>

假设客户端在 `127.0.0.1:7890` 提供代理服务。`127.0.0.1` 是 IPv4 的**回环地址**，指向本机；**监听端口** `7890` 表示客户端正在这里等待连接。

浏览器连接这个地址，数据先到同一台电脑上的代理进程。`7890` 只是示例，必须与客户端实际监听的端口一致。

### 应用怎么知道代理地址

<span id="system-proxy"></span>

一种方式是**系统代理**。客户端把代理地址写入操作系统提供的设置，支持该机制的程序读取并使用它。

在 Windows 上，常会遇到 **WinINET** 和 **WinHTTP** 两套相关接口与配置。不同程序、不同网络库的使用方式存在差异，不能仅凭“系统代理已开启”推断每个进程都会走代理。WinHTTP 也支持由应用进行自动代理发现等配置。[Microsoft：WinHTTP 自动代理](https://learn.microsoft.com/en-us/windows/win32/winhttp/winhttp-autoproxy-support)

<span id="environment-proxy"></span>

另一种方式是**代理环境变量**，常见名称包括 `HTTP_PROXY`、`HTTPS_PROXY`、`ALL_PROXY` 和 `NO_PROXY`。支持哪些变量、大小写如何处理、哪个设置优先，都由程序或网络库决定。

例如，`HTTPS_PROXY=http://127.0.0.1:7890` 通常表示访问 HTTPS 目标时使用这个 HTTP 代理。变量名里的 HTTPS 描述目标流量；代理地址里的 `http://` 描述如何连接代理，二者并不矛盾。[curl：代理环境变量](https://everything.curl.dev/usingcurl/proxies/env.html)

<span id="app-proxy"></span>

程序还可能有**自带代理设置**，例如 Git 的 `http.proxy`。系统代理、环境变量和软件配置同时存在时，应查看该程序的优先级规则。图形界面和后台进程也可能使用不同网络库，所以“浏览器能访问，命令行工具失败”并不奇怪。

### 交给代理时，说的是什么协议

<span id="http-proxy"></span>
<span id="connect"></span>

在本例中，浏览器使用 **HTTP 代理**访问 HTTPS 网站，通常先发送一条 **CONNECT** 请求：

```http
CONNECT www.example.com:443 HTTP/1.1
Host: www.example.com:443
```

它表达的意思是：“请建立通向这个目标的隧道，随后双向转发数据。”代理成功建立相应通道并返回成功响应后，浏览器才能在其中继续与网站通信。CONNECT 中可以使用主机名；代理也可能把请求交给下一层代理。[RFC 9110：CONNECT](https://www.rfc-editor.org/rfc/rfc9110.html#section-9.3.6)

因此，这种方式允许浏览器把目标域名交给代理，浏览器无需先为建立这条目标连接解析出真实 IP。不过，浏览器仍可能因预解析、其他请求或自身 DNS 策略发起 DNS 查询。

访问普通 HTTP 网站时，HTTP 代理还可以直接接收带完整目标 URL 的 HTTP 请求。CONNECT 是其中用于建立隧道的一种机制。

<span id="socks5"></span>

**SOCKS5**是另一种代理协议，支持在请求中携带 IPv4 地址、IPv6 地址或域名。应用传 IP 时，目标地址通常已经在此前解析；应用传域名时，可以把解析交给后续代理。SOCKS5 本身并不自动提供整条链路的数据加密。[RFC 1928：SOCKS5](https://www.rfc-editor.org/rfc/rfc1928.html)

<span id="mixed-port"></span>

**mixed-port**是部分客户端提供的混合监听端口，可以在同一个端口接收 HTTP 和 SOCKS 代理连接。它让多个程序共用一个入口，各程序仍需要选择自己支持的代理协议。[mihomo：代理端口](https://wiki.metacubex.one/config/inbound/port/)

### 应用不支持代理时：TUN 与透明代理

<span id="tun"></span>
<span id="transparent-proxy"></span>

**TUN**提供虚拟网络接口，可以结合系统路由，把原本准备发往网络的 IP 数据包交给代理程序处理。应用不一定需要主动配置 HTTP 或 SOCKS 代理，因此它能接管一些不读取代理设置的程序。

**透明代理**强调应用无需主动配合即可被转发。TUN 是常见实现方式之一，路由器上也有其他实现方式。它们的接管范围仍取决于路由、协议支持、排除项和权限，不能只凭一个开关认定全部流量已经进入代理。[mihomo：TUN 配置](https://wiki.metacubex.one/config/inbound/tun/)

先记住这个分支：显式代理可以直接收到域名，而接管 IP 数据包时，客户端最初可能只有目标 IP。后面讲 fake-ip 时，就会用到这个区别。

本例继续沿 HTTP CONNECT 这条路走。请求已经进入客户端，接下来轮到客户端选择去向。

## 第 3 站：客户端决定这次连接往哪里走

<span id="inbound-outbound"></span>

从内核的角度，接收应用流量的入口叫**入站（Inbound）**，把流量送往下一段的方式叫**出站（Outbound）**。HTTP、SOCKS、TUN 可以承担入站角色；直连或某种远端代理可以承担出站角色。

这也说明，本机使用 HTTP 代理，并不意味着本机到远端节点也使用 HTTP。两段连接可以采用不同协议。

<span id="rules"></span>
<span id="domain-rule"></span>

客户端通过**分流规则**选择出站。例如：

```yaml
rules:
  - DOMAIN-SUFFIX,example.com,网页代理
  - GEOIP,CN,DIRECT
  - MATCH,默认代理
```

这里假设“网页代理”和“默认代理”已经定义。常见的**域名规则**包括：`DOMAIN` 匹配完整域名，`DOMAIN-SUFFIX` 匹配域名及其子域名，`DOMAIN-KEYWORD` 匹配域名中的关键词。

<span id="ip-rule"></span>

**IP 规则**根据目标地址判断。`IP-CIDR` 使用 **CIDR** 表示的网段，例如 `192.0.2.0/24`；`GEOIP` 则依据 IP 地理归属数据库匹配。数据库存在更新与精度限制，IP 归属也不能完整代表一个服务的身份。

mihomo 的规则按从上到下的优先级处理，`MATCH` 常用作最后的兜底。某些 IP 规则需要先解析目标域名，所以 DNS 可能在分流过程中提前参与。[mihomo：路由规则](https://wiki.metacubex.one/config/rules/)

<span id="proxy-mode"></span>
<span id="direct-reject"></span>

**规则模式**按照配置逐条判断；**全局模式**通常把进入内核的连接交给全局选择的代理策略。全局模式决定进入内核后如何处理，系统代理或 TUN 等设置决定流量能否先进入内核。

**DIRECT**表示由本机直接建立后续连接；**REJECT**表示拒绝这次连接。它们也是分流结果，不是远端服务器。

### 代理组怎样选出具体节点

<span id="proxy-group"></span>

规则还可以指向一个**代理组**，再由组内策略选择节点。

<span id="select"></span>
<span id="url-test"></span>
<span id="fallback-group"></span>
<span id="load-balance"></span>

| 类型 | 选择方式 | 应当怎样理解结果 |
|---|---|---|
| **select** | 用户手动选择 | 使用你选中的成员 |
| **url-test** | 根据指定测试地址的响应时间自动选择 | 测得快，表示到该测试地址的表现好 |
| **fallback** | 按配置顺序选择可用成员 | 前面的成员恢复后，可能切回前面的成员 |
| **load-balance** | 按算法分配不同连接 | 可以采用一致性哈希、轮询等方式，并非只能轮流选 |

url-test 的 `tolerance` 可以减少因小幅延迟变化造成的切换。测试成功也只代表相应测试成功，不能证明所有网站都可用，更不能直接等同于下载带宽。[mihomo：自动选择](https://wiki.metacubex.one/config/proxy-groups/url-test/)、[自动回退](https://wiki.metacubex.one/config/proxy-groups/fallback/)、[负载均衡](https://wiki.metacubex.one/config/proxy-groups/load-balance/)

切换成员会影响后续连接的出口；已有连接如何处理取决于实现。网站是否要求重新登录，还与会话和风控策略有关。

本例中，`www.example.com` 命中了“网页代理”，组内选中一个配置地址为 `node.example.net:443` 的节点。下一步是找到这个节点并建立连接。

## 第 4 站：DNS 在需要地址时参与

<span id="dns"></span>
<span id="resolver"></span>

**DNS（Domain Name System，域名系统）**保存和查询域名相关的信息。对这次访问来说，我们最关心的是：给定域名，怎样找到能够连接的 IP 地址？

负责完成或转交查询的组件称为**解析器**。应用可能把问题交给系统，系统再交给路由器或公共递归解析服务；代理客户端也可能使用自己的解析器。递归解析服务在需要时向相应权威服务器获取记录。

<span id="dns-cache"></span>

为避免反复查询，应用、系统和递归解析服务都可能保存 **DNS 缓存**。记录的 **TTL（生存时间）**约束缓存可使用的时长，因此并非每次访问都会重新进行完整查询。[RFC 1034：DNS 的概念与设施](https://www.rfc-editor.org/rfc/rfc1034.html)

<span id="dns-records"></span>

常见记录中，**A**提供 IPv4 地址，**AAAA**提供 IPv6 地址，**CNAME**把一个名称指向另一个名称。一次域名解析可能经过别名，也可能获得多个地址；“域名对应一个永远不变的 IP”并不符合普遍情况。[RFC 1035：DNS 记录格式](https://www.rfc-editor.org/rfc/rfc1035.html)、[RFC 3596：IPv6 DNS 扩展](https://www.rfc-editor.org/rfc/rfc3596.html)

### 这次访问里，有三类域名需要分清

<span id="bootstrap"></span>

第一类是**节点域名** `node.example.net`。本机要连接节点，必须先有节点地址。本例假设没有可用缓存，也没有其他代理通道，因此通过当前网络能够直接访问的解析路径获取地址。

第二类是**目标网站域名** `www.example.com`。它可以由本机解析，也可以随代理请求交给远端节点解析。我们继续追踪后一种情况。

第三类是**DNS 服务自身的域名**。如果选择的解析服务地址是 `https://dns.example.net/dns-query`，连接它之前仍需要知道 `dns.example.net` 的地址。这种为解析服务先寻找地址的过程，常称为**引导解析（Bootstrap）**。

这里容易出现循环依赖：要连接代理，先解析节点；要解析节点，又把 DNS 请求安排给尚未连接的同一个代理。解决办法是让启动所需的地址获取有一条独立可用的路径，例如可访问的解析器、已有缓存或预设地址。

### DNS 污染，干扰的是地址查询

<span id="dns-poisoning"></span>

传统 DNS 常使用 UDP 53，也支持 TCP 53。未加密的查询可能被沿途设备观察；缺少经过验证的数据来源时，伪造或篡改应答可能让解析器接受错误记录，这类问题常被称为 **DNS 污染**。

“抢在真实应答之前返回错误答案”是一种直观模型，但解析器仍会检查查询标识、地址、端口等信息，不能简单理解为任意应答谁先到就信谁。[RFC 5452：抵御伪造 DNS 应答](https://www.rfc-editor.org/rfc/rfc5452.html)

DNS 查询异常和网站连接失败是两个环节。即使获得了正确地址，连接仍可能被限制；反过来，不同解析器返回不同 IP，也可能只是缓存、地域调度或 CDN 造成，不能单凭这一点断定污染。

<span id="doh"></span>
<span id="dot"></span>

**DoH（DNS over HTTPS）**通过 HTTPS 传输 DNS 查询；**DoT（DNS over TLS）**通过专门的 TLS 连接传输，默认使用 TCP 853。正确验证服务端身份时，它们可以保护客户端到所选解析服务之间的查询内容，降低沿途窃听和篡改风险。[RFC 8484：DoH](https://www.rfc-editor.org/rfc/rfc8484.html)、[RFC 7858：DoT](https://www.rfc-editor.org/rfc/rfc7858.html)

使用加密 DNS 仍需要信任所选解析服务，而且该服务必须可达。某个网络下某次测试失败，不能推导出所有境外加密 DNS 都不可用；使用 DoH 也不会自动让目标网站变得可连接。

<span id="dnssec"></span>

**DNSSEC**通过数字签名验证 DNS 数据的来源与完整性。它不负责隐藏查询内容，也不保证查询一定成功。DoH、DoT 保护传输通道，DNSSEC验证有相应签名与信任链支持的数据，侧重点不同。[RFC 4033：DNSSEC](https://www.rfc-editor.org/rfc/rfc4033.html)

### 为什么客户端里有好几个 DNS 配置项

<span id="mihomo-dns"></span>

以 mihomo 为例，这些配置处理不同需求：

| 配置项 | 主要职责 |
|---|---|
| `default-nameserver` | 为 DNS 服务自身的域名获取地址 |
| `nameserver` | 默认域名解析 |
| `nameserver-policy` | 为指定域名选择解析服务 |
| `proxy-server-nameserver` | 解析代理节点域名 |
| `direct-nameserver` | 解析直连出站所需的域名 |
| `fallback` / `fallback-filter` | 按筛选条件决定何时采用后备解析结果 |

没有填写 `proxy-server-nameserver` 时，节点域名会按其他相关 DNS 配置处理，并非必然失败。需要检查的是它最终走到了哪条解析路径，以及这条路径是否存在前面说的循环依赖。

另一个容易读反的配置是 `fallback-filter.geoip-code: CN`：按官方说明，符合该国家代码的主解析结果直接采用，其他结果转而采用后备结果；域名等其他筛选条件还可能改变处理分支。这是配置中的筛选策略，不是证明某个答案真实与否的通用算法。[mihomo：DNS 配置](https://wiki.metacubex.one/config/dns/)

### 接回 TUN 分支：fake-ip 为什么返回“假地址”

<span id="fake-ip"></span>

第 2 站提到，应用直接使用 HTTP CONNECT 时可以提交域名，但 TUN 接收到的 IP 数据包可能只带目标 IP。为了保留“这个连接原本想访问哪个域名”的信息，客户端可以使用 **fake-ip**。

假设应用的 DNS 查询交给了代理内核，内核为某个域名分配一个合成地址：

```text
应用查询：www.example.com 的地址是什么？
内核回答：198.18.0.7
内核同时保存：198.18.0.7 ↔ www.example.com

应用连接：198.18.0.7:443
连接进入内核后，内核查表恢复：www.example.com:443
随后按规则决定怎样建立真实的后续连接
```

这个地址在内核管理的映射中代表目标域名。内核不需要先把它当作网站真实 IP 发往公网。fake-ip 减少了部分场景对预先获取目标真实地址的依赖，但后续直连、IP 规则或远端连接仍可能需要真实解析。

<span id="redir-host"></span>

**redir-host**是 mihomo 的另一种 DNS 处理模式，向应用返回实际解析地址。它与 fake-ip 的主要区别在于返回及关联地址的方式，解析结果是否可靠仍取决于上游和路径。TUN 也可以与返回真实地址的方案配合，fake-ip 并非 TUN 唯一的工作条件。[mihomo：DNS 处理模式](https://wiki.metacubex.one/config/dns/#enhanced-mode)

<span id="sniffing"></span>

客户端还可以尝试**域名嗅探（Sniffing）**：从支持的协议内容中读取主机名，例如 HTTP 请求信息或 TLS 握手。它受到协议、加密方式和实现支持的限制，不能保证从任意 IP 连接恢复域名。[mihomo：域名嗅探](https://wiki.metacubex.one/config/sniff/)

回到本例：本机获得了节点地址，同时仍保留目标域名 `www.example.com`，准备交给节点。现在可以真正连接节点了。

## 第 5 站：本机怎样与节点建立通信通道

### 先分清传输协议和代理协议

<span id="tcp"></span>

**TCP**提供可靠、有序的字节流。建立连接时会进行握手，传输中通过确认、重传和拥塞控制等机制处理丢包与网络负载。应用拿到的是连续字节流，而不是每一个原始数据包。

<span id="udp"></span>

**UDP**提供数据报传输，本身不保证送达、顺序和重传。建立在 UDP 之上的协议可以自行实现这些能力，因此使用 UDP 不代表上层业务必然不可靠。

<span id="quic"></span>

**QUIC**就是一种基于 UDP 的安全传输协议，提供连接、可靠流和多路复用等机制。HTTP/3 使用 QUIC；Hysteria2 也在 QUIC 上实现代理业务，但二者提供的应用功能不同。[RFC 9000：QUIC](https://www.rfc-editor.org/rfc/rfc9000.html)

TCP、UDP 描述基础传输方式；HTTP CONNECT、SOCKS5、VLESS 等描述代理通信的不同约定。理解一个节点配置时，要同时看它使用什么代理协议、怎样承载，以及由谁提供加密。

<span id="tunnel"></span>

**隧道**可以理解为：把本来要传给目标的数据装进另一段通信通道，到另一端再取出、转发。我们常说的加密代理隧道，通常还会对本机与远端节点之间的数据进行保护。隧道这个词本身并不承诺加密。

### 加密了内容，为什么仍有握手特征

<span id="tls"></span>
<span id="certificate"></span>

**TLS**用于建立受保护的通信会话。客户端与服务端协商参数，验证身份，并获得用于保护后续通信的密钥。常见 Web 场景中，**证书**把服务端公钥与域名等身份信息关联起来，由客户端依据受信任的证书体系等条件验证。[RFC 8446：TLS 1.3](https://www.rfc-editor.org/rfc/rfc8446.html)

<span id="clienthello"></span>
<span id="sni"></span>

客户端发起 TLS 握手时发送的消息叫 **ClientHello**，里面包含支持的协议版本、密码套件和扩展等信息。**SNI（Server Name Indication）**是其中可携带服务器名称的一种扩展，使同一个地址上的服务能够根据名称选择相应配置。

普通 TLS 握手中的 ClientHello 不会因为后续内容加密而自动隐藏。因此，保护了网页内容，并不意味着网络上的观察者连握手里的域名信息也看不到。

<span id="ech"></span>

**ECH（Encrypted Client Hello）**用于加密内部 ClientHello，保护其中的 SNI 等敏感字段。它需要客户端、服务端及配置分发等条件配合；它也无法单独消除 IP、明文 DNS 或流量形态暴露的信息。[RFC 9849：ECH](https://www.rfc-editor.org/rfc/rfc9849.html)

<span id="fingerprint"></span>

协议实现还会在扩展顺序、参数选择等方面留下差异。把这些差异归纳起来，就形成了**协议指纹**。**JA3**、**JA4**是常见的相关指纹名称，用来辅助识别和分析通信实现。观察者也可能结合连接时长、包长、节奏等信号判断流量；单个指纹不是某种用途的确定证明。[JA3 项目](https://github.com/salesforce/ja3)、[JA4 项目](https://github.com/FoxIO-LLC/ja4)

<span id="active-probing"></span>

**主动探测**则更进一步：观察者主动向服务器发起连接，发送测试数据，根据回应判断它可能提供什么服务。代理协议在设计认证失败时的行为、握手外观和转发策略时，可能会考虑这种风险。

因此，一个代理方案需要分别回答：内容如何保密，用户如何认证，对外表现出什么协议特征，以及被错误或未知请求访问时怎样回应。

### 把常见代理协议放回这段连接

<span id="shadowsocks"></span>

**Shadowsocks**通过双方约定的密钥等参数建立加密代理通信，转交目标地址和数据。它存在不同代际，Shadowsocks 2022 对加密、重放保护等做了改进，不能用早期版本的特征概括所有实现。加密保障也不等于通信外观与普通 HTTPS 相同。[Shadowsocks 2022 规范](https://shadowsocks.org/doc/sip022.html)

<span id="vmess"></span>

**VMess**是 V2Ray 生态中的代理通信协议，包含用户认证与数据保护机制。它也有版本和认证方式的变化，官方文档已将传统 MD5 认证标为弃用。实际连接外观还要结合所使用的承载方式及 TLS 等配置判断。[V2Fly：VMess 协议](https://www.v2fly.org/developer/protocols/vmess.html)

<span id="trojan"></span>

**Trojan**先建立真正的 TLS 连接，再在其中传递认证和代理请求；对不符合代理认证等条件的流量，可以按设计转交给普通服务。这有助于让未经授权的访问得到普通服务的回应，但不能据此保证无法识别。具体部署也未必使用某种固定语言或固定 Web 服务器。[Trojan 协议说明](https://github.com/trojan-gfw/trojan/blob/master/docs/protocol.md)

<span id="vless"></span>

**VLESS**负责代理请求、认证及相关转发约定。在常见的 `encryption: none` 配置中，需要另行关注 TLS、REALITY 等安全层。是否启用 VLESS 自身的其他加密能力，还要看版本与配置，因此读节点名称时，应该把整套组合一起看。[Project X：传输配置](https://xtls.github.io/en/config/transport.html)

<span id="reality"></span>

**REALITY**是常与 VLESS 组合使用的安全与握手机制。它通过特定认证设计、目标站点相关的握手外观及对未通过认证连接的处理，降低某些探测和识别风险。

这里有个常见误解：它不能简单解释成“转发真实网站握手，拿到真实证书，再偷偷换密钥”。官方说明中，合法代理连接收到的是可验证的**临时可信证书**；收到目标网站的真实证书，对应转发等另一类情况。认证客户端与未认证访问的处理需要分开理解。[REALITY 官方说明](https://github.com/XTLS/REALITY/blob/main/README.en.md)

<span id="utls"></span>

**uTLS**允许调整和模拟 ClientHello 特征，例如接近某种浏览器的握手样式。选择浏览器指纹只能影响相应握手行为，不会让整个代理程序的全部网络行为都变成浏览器，也不保证无法识别。[uTLS 项目说明](https://github.com/refraction-networking/utls)

<span id="hysteria2"></span>

**Hysteria2**在 QUIC 上承载 TCP、UDP 代理业务，并设计了认证和 HTTP/3 伪装等机制。它通常需要网络能够有效传输 UDP；使用什么端口由配置决定，并不要求高位端口。[Hysteria2 协议规范](https://v2.hysteria.network/docs/developers/Protocol/)

<span id="congestion"></span>

**拥塞控制**决定发送方怎样根据网络情况调整发送。Hysteria2 支持的策略包括 **Brutal** 等。Brutal 按协商的带宽目标工作，并可对丢包进行补偿；带宽参数设置过高可能反过来造成拥塞和不稳定，不能概括成“丢包也永远不减速”。[Hysteria2：带宽与拥塞配置](https://v2.hysteria.network/docs/advanced/Full-Client-Config/#bandwidth)

<span id="salamander"></span>

**Salamander**是 Hysteria2 的一种可选混淆机制，会改变数据包的外观。混淆与传输加密承担不同任务，也会带来新的可观察特征和部署条件。启用它不等于自动获得更好的所有网络兼容性。[Hysteria2：混淆配置](https://v2.hysteria.network/docs/advanced/Full-Client-Config/#obfuscation)

这些方案没有脱离网络条件的统一排名。协议版本、客户端实现、服务器配置、链路质量和过滤策略都会影响结果。比较协议时，应明确比较的是连接成功率、吞吐量、延迟、资源开销还是特定探测下的表现。

无论选中哪一种，客户端到节点的通道建立后，都要把“连接 `www.example.com:443`”这个目标交给节点，随后转发相应数据。接下来看看这段通道实际经过的路。

## 第 6 站：协议之外，还有实际线路

<span id="route"></span>

数据离开本机后，通常经过本地网络、**路由器**、**运营商（ISP）**及后续网络。**路由**决定数据包接下来向哪一段网络转交。节点在地图上离你近，不代表实际路径一定短；切换校园网、家庭宽带和手机热点，也会改变这段路径。

<span id="relay"></span>

服务提供方常把线路中的角色称为**入口**、**中转**与**落地**：入口接收用户侧连接，中转负责继续转交，落地通常指最终向目标网站发起连接的一端。这些称呼并非统一协议标准，具体含义应结合服务说明。

一条线路可能是：

```text
本机 → 运营商网络 → 远端节点 → 目标网站
```

也可能是：

```text
本机 → 入口服务器 → 中转链路 → 落地服务器 → 目标网站
```

多经过一台机器可能增加开销，也可能借助更好的互联改善整体体验。因此，“有中转就一定慢”和“有专线标签就一定快”都需要实际证据。

<span id="exit-ip"></span>

目标网站在这条连接上看到的源地址通常是最终出口或其 NAT 的公网地址，也就是**出口 IP**。它可能与客户端配置里最初连接的入口 IP 不同。选择标注某个地区的节点，通常是在选择一套包含相应出口的服务配置，不能仅凭名字验证真实路径。

<span id="performance"></span>

**延迟**描述通信等待时间，常见测速值反映某种往返或测试请求耗时；**带宽**描述一定时间内能传输多少数据；**丢包**描述部分数据包未成功到达的情况。

低延迟适合频繁交互，但不能保证大文件下载快。页面加载还涉及多个连接、服务器处理和资源请求；整条代理路径的吞吐也会受到最窄或最拥堵环节限制。排查时，把“本机到节点”和“节点到网站”分别观察，比只盯着一个测速数字更有用。

现在，数据已经抵达能代表我们访问外部网站的节点。轮到节点建立后半段连接。

## 第 7 站：节点连接网站，浏览器建立 HTTPS

<span id="remote-dns"></span>

节点收到的目标是 `www.example.com:443`。本例中它收到的是域名，因此通过自己可用的解析路径获取目标地址，这就是这里所说的**远端 DNS 解析**。如果本机此前已解析并发送 IP，远端就可能直接使用该 IP。

把目标解析交给远端，可以避免这一步依赖本机获取的目标地址。但远端解析仍然依赖节点所在网络与上游解析服务，不能仅凭“发生在远端”就保证所有答案正确。

<span id="cdn"></span>

节点解析到的也可能是网站的 **CDN（Content Delivery Network，内容分发网络）**地址。CDN 通过分布式节点提供内容或转发服务，解析和接入调度可能结合查询来源、网络位置等信息。同一个网站从不同出口访问，可能被分配到不同服务节点，这也是不同代理线路体验有差异的原因之一。

### 网站的 HTTPS，和代理隧道是两条安全边界

<span id="https-end-to-end"></span>

节点建立到网站的后续连接，在本机代理完成 CONNECT 的相应成功响应后，浏览器才开始在通道里与目标网站进行 TLS 握手。这里按普通转发、不进行 HTTPS 解密检查的场景说明。

逻辑关系可以画成：

```text
浏览器                                                    目标网站
  │                                                          │
  └──────── 浏览器与网站之间的 HTTPS / TLS ────────────────────┘
         这段 TLS 数据经下面的代理连接转发

浏览器 → 本机客户端 ═════ 受保护的代理通道 ═════ 远端节点 → 网站
                         本机到节点
```

浏览器到网站的 TLS 用来保护网页内容与登录数据；本机到节点的代理安全层，用来保护这一段代理通信。即使节点处理掉外层代理封装，浏览器与网站之间的 TLS 数据仍然是加密的。具体协议可以优化封装方式，不能把所有实现都理解为每个字节必然重复加密。

浏览器会验证网站证书及域名等条件，再在 TLS 中发送 HTTP 请求。示意请求可能是：

```http
GET /articles/proxy HTTP/1.1
Host: www.example.com
```

网站解密并处理请求，代理节点负责转发。HTTPS 保护的是这段 HTTP 内容，不会自动隐去节点连接了什么 IP、何时连接、传输多少等信息。[RFC 8446：TLS 安全目标](https://www.rfc-editor.org/rfc/rfc8446.html#section-1)

### 收到状态码，说明到了哪一步

<span id="http-status"></span>

网站或它前面的 CDN、网关可能返回 HTTP 响应：

| 状态码 | 常见含义 | 对排查有什么帮助 |
|---|---|---|
| `200` | 请求成功 | 已收到相应 HTTP 服务的成功响应，仍可核对内容 |
| `204` | 成功，但无响应正文 | 常用于连通性测试接口 |
| `301` / `302` | 重定向 | 还需要检查后续地址能否访问 |
| `401` | 缺少有效身份凭据 | 对方已回应，需要检查认证 |
| `403` | 拒绝请求 | 可能涉及访问策略、账号、地区或 IP 等原因 |
| `429` | 请求过多等限流情形 | 需要结合响应和服务规则判断 |
| `5xx` | 服务端或网关一类错误 | 可能由目标服务、CDN 或中间代理产生 |

这些是 HTTP 层的回应。还应确认回应来自本机代理、上游代理，还是目标服务。例如 CONNECT 阶段的 `200` 只表示隧道阶段成功，不能拿它当作目标网页已经返回 `200`。[RFC 9110：状态码](https://www.rfc-editor.org/rfc/rfc9110.html#section-15)

有些工具显示的 `000` 不是 HTTP 状态码。对 curl 来说，这通常意味着没有取得相应 HTTP 响应码，需要继续看退出码和错误信息；原因可能发生在解析、连接、TLS 或代理阶段。[curl 使用手册](https://curl.se/docs/manpage.html)

<span id="ip-reputation"></span>

目标服务还可能根据**出口 IP 的信誉、网络归属和共享使用情况进行风控**。同一个出口被很多用户使用时，也可能共同受到某些限流或验证策略影响。不过，一次 `403` 不能直接证明该 IP 被封，仍需结合响应说明、账号与对照测试判断。

到这里，这次请求已经得到了 HTTP 层面的结果。接下来，响应沿代理连接逐段返回。

## 第 8 站：响应返回后，谁知道了什么

<span id="response"></span>

响应的逻辑方向是：

```text
目标网站 → 远端节点 → 本机客户端 → 浏览器
```

各段连接负责把数据继续传给上一端。这里说的是连接中的转发方向，互联网实际经过的逐跳路由未必与去程完全相同。

浏览器收到 HTML 后，通常还要请求样式、脚本、图片等资源，因此“打开一个网页”会产生多次请求。**连接复用**允许多个请求使用已有连接，代理实现也可能复用到节点的通道。这就是为什么后续请求不一定重新进行前面所有握手。

<span id="privacy"></span>

理解代理时，还需要区分不同观察者所处的位置：

| 观察者 | 在这类配置中通常能了解什么 |
|---|---|
| 本地网络与运营商 | 本机连接的节点或入口 IP、端口、通信时间、流量规模，以及未被保护的 DNS 或握手信息 |
| 被使用的 DNS 解析服务 | 发送给它的域名查询；它看到哪个客户端来源，取决于查询路径 |
| 代理服务提供方 | 用户侧连接、所转发的目标地址及流量元数据；目标以域名提交时，通常也能知道该域名 |
| 目标网站及其前置服务 | 出口 IP、到达它的请求内容，以及登录账号、Cookie 等应用信息 |

表中能力取决于具体协议、日志、DNS 路径和加密配置。普通代理转发下，代理节点无法仅凭转发就读出有效 HTTPS 会话里的完整网页内容，但它仍掌握一定的目标与通信信息。

尤其要分清两种握手：目标网站的 TLS 握手可以被装进本机到节点的受保护通道；而代理通道自己的握手如果携带明文 SNI，沿途仍可能看见这个外层名称。离开节点后，节点到目标网站这一段也有自己的网络观察范围。

**DNS 泄漏**通常指原本希望经过受保护路径的域名查询，却从其他路径发出，向预期之外的观察者暴露了访问意图。浏览器自己的加密 DNS、系统解析、代理内核 DNS 与 TUN 接管范围可能相互影响，需要沿查询实际路径检查。

所以，使用代理改变了连接出口和部分观察边界，账号、Cookie、浏览器特征等仍能帮助网站识别用户。评价隐私效果时，先明确自己希望对谁隐藏哪些信息，再看当前配置能覆盖哪一段。

<span id="troubleshooting"></span>

## 附录一：沿着链路排查“为什么连不上”

看到“连接失败”，先确认失败发生在哪一段，再选择检查方法。

| 现象 | 优先检查 | 还不能直接下什么结论 |
|---|---|---|
| 本机代理端口无法连接 | 内核是否启动、监听是否成功、应用填写的地址是否正确 | 不能据此判断远端节点失效 |
| 浏览器可用，某个命令行工具失败 | 工具读取的代理配置、环境变量与绕过设置 | 不能据此判断所有程序都已走代理 |
| 所有节点同时超时 | 公共依赖：DNS、本地网络、配置、账号和共同入口 | 不能直接判定全部节点 IP 被封 |
| 某个节点失败，其他正常 | 节点地址、端口、认证、协议与服务器状态 | 一次 TCP 失败不能确定是封锁还是服务离线 |
| 换手机热点后恢复 | 原网络的路由、DNS、UDP 可达性及访问策略 | 不能据此确定原网络限制了哪种协议 |
| 收到 `403` 或 `429` | 响应来源、目标服务策略、账号与出口情况 | 不能直接归因于代理软件或单个 IP |
| 延迟低但下载慢 | 带宽、负载、丢包、限速以及节点到目标的路径 | 延迟测试不能替代吞吐测试 |

一次只改变一个条件，例如保留节点和配置，只切换网络；或者保留网络，只换节点。这样结果才有助于缩小范围。客户端日志里的域名、命中规则、所选出站和错误阶段，往往比连续重启更能提供线索。

同时保留三个检查目标：**流量进没进本机代理，代理连没连上节点，节点有没有获得目标服务的回应。** 前一段成功，才继续判断后一段。

<span id="windows-checks"></span>

## 附录二：Windows 上几项有用的检查

以下以 PowerShell 为例，端口 `7890` 需要替换成客户端实际值。这些命令用于检查，不会修改代理或系统网络配置。

### 1. 系统代理填写了什么，内核有没有监听

```powershell
Get-ItemProperty -LiteralPath 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Internet Settings' -ErrorAction Stop |
    Select-Object ProxyEnable, ProxyServer, ProxyOverride

netsh winhttp show proxy

Get-NetTCPConnection -State Listen -ErrorAction Stop |
    Where-Object LocalPort -eq 7890 |
    Select-Object LocalAddress, LocalPort, OwningProcess
```

前两项反映不同的代理配置；最后一项查看对应 TCP 端口是否在监听。地址和进程也要一起核对，端口有监听只能证明本地入口存在，不能证明远端连接成功。

### 2. 显式使用代理，再与直连对照

使用 `curl.exe` 可以明确调用 curl，避免某些 PowerShell 环境把 `curl` 当成其他命令的别名。选择自己想测试的 HTTPS 地址：

```powershell
$probeUrl = 'https://www.example.com/'

# 指定本机代理；显式绕过列表不包含本例目标域名
curl.exe --proxy 'http://127.0.0.1:7890' --noproxy 'localhost,127.0.0.1' --connect-timeout 10 --max-time 20 --output NUL --write-out 'target_http=%{http_code} connect_http=%{http_connect}\n' $probeUrl
$LASTEXITCODE

# 直连对照：忽略代理设置
curl.exe --noproxy '*' --connect-timeout 10 --max-time 20 --output NUL --write-out 'target_http=%{http_code}\n' $probeUrl
$LASTEXITCODE
```

`http_code`反映目标 HTTP 传输取得的响应码；`http_connect`反映 CONNECT 阶段的代理响应码；`$LASTEXITCODE` 是外部程序退出码。结合 curl 的错误文字判断失败阶段。测试地址本身是否允许直连、是否需要认证，也会影响结果。[curl 使用手册](https://curl.se/docs/manpage.html)

### 3. 分开检查目标解析与节点端口

```powershell
# 观察 Windows 这条查询路径上的结果
Resolve-DnsName -Name 'www.example.com' -Type A -ErrorAction Stop

# 必须先把示例 IP 替换为实际节点 IP，再检查相应 TCP 端口
Test-NetConnection -ComputerName '192.0.2.10' -Port 443 -InformationLevel Detailed
```

`192.0.2.10` 是文档示意地址。纯 IP 测 TCP 端口，可以暂时排除本次测试中的节点域名解析，但不能检验认证、代理协议或 UDP 服务；TCP 失败也不直接证明 IP 被封。Windows 的 DNS 查询结果同样不能代表浏览器或内核使用的所有解析路径。

<span id="port-reservation"></span>

### 4. 客户端启动了，为什么端口没有监听

可能原因包括另一个进程占用端口、系统排除端口范围、权限问题、内核启动失败，以及虚拟网络接口或服务依赖异常。先查看启动日志，再检查：

```powershell
netsh interface ipv4 show excludedportrange protocol=tcp
netsh interface ipv4 show dynamicport tcp
netsh interface ipv6 show excludedportrange protocol=tcp
```

**排除端口范围**与**动态端口范围**是不同概念。现代 Windows 默认动态端口范围通常是 `49152–65535`，本机设置可以不同；不能推导出低于 `1024` 的端口永远不会被保留或受到限制。[Microsoft：动态端口范围](https://learn.microsoft.com/en-us/troubleshoot/windows-client/networking/tcp-ip-port-exhaustion-troubleshooting)

Windows 的 `10013 / WSAEACCES` 表示访问权限被拒绝，端口保留可能是原因之一，其他独占绑定等情形也可能触发它，不能只看错误码就唯一定位原因。[Microsoft：Windows Sockets 错误码](https://learn.microsoft.com/en-us/windows/win32/winsock/windows-sockets-error-codes-2)

选用一个当前允许、没有冲突的端口后，还要同步核对系统代理、环境变量和程序自己的代理地址。若同时安装多个客户端，也应确认当前究竟由哪个内核接收应用连接。

理解这条路径后，配置项就能对应到具体问题：入口设置让请求进入客户端，规则决定去向，DNS 提供所需地址，协议建立到节点的通道，线路承载数据，出口替你访问目标。下次遇到“连不上”，就从第一个尚未被验证的环节开始检查。

---

技术资料与项目文档核对日期：2026 年 10 月 25 日。涉及具体软件的配置语义，应结合所用内核、版本和客户端的合并规则阅读。

[返回术语索引](#term-index)
