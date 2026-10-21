# auto-net

> 校园网自动认证 · 掉线自动重连 · 开机自启动开关

[![CI](https://github.com/aths-7/auto-net/actions/workflows/ci.yml/badge.svg)](https://github.com/aths-7/auto-net/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.8%2B-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Deps](https://img.shields.io/badge/dependencies-0-brightgreen.svg)](#)

一个**只用 Python 标准库**的校园网自动登录工具。开机后静默认证，中途掉线自动重连，不需要常驻托盘、不需要装一堆依赖，也永远不碰管理员权限。

Python 包名 / 命令叫 `campusnet`，仓库叫 `auto-net` —— 名字对不上是我起名时的锅，不影响用。

支持三种国内最常见的认证协议，一个配置文件切换：

| 适配器 | 说明 | 典型 portal |
| --- | --- | --- |
| `srun` | 深澜 Srun（多数高校在用） | `http://10.x.x.x` |
| `eportal` | 锐捷 ePortal | `https://10.x.x.x/eportal/` |
| `drcom` | Dr.COM 城市热点（宿舍宽带） | `http://10.x.x.x` |
| `custom` | 自定义 URL 模板 | 你自己填 |

---

## 快速开始

```bash
git clone git@github.com:aths-7/auto-net.git
cd auto-net

# 1. 写配置（交互式，会问你 portal / 账号 / 密码）
python -m campusnet init

# 2. 认证一次，确认能通
python -m campusnet login

# 3. 常驻守护：每 30 秒检查一次，掉线自动重连
python -m campusnet daemon

# 4. 开机自启动（可随时关掉）
python -m campusnet autostart on
```

只想临时用、不想装包？直接在仓库根目录跑 `python -m campusnet ...` 就行，零依赖。

想全局使用：

```bash
pip install -e .
campusnet status
```

---

## 命令一览

| 命令 | 作用 |
| --- | --- |
| `campusnet init` | 交互式生成/更新 `~/.campusnet/config.json` |
| `campusnet login [--force]` | 认证一次；默认已在线就跳过 |
| `campusnet logout` | 主动下线 |
| `campusnet status` | 联网状态 + 配置摘要 + 自启动状态 |
| `campusnet daemon` | 常驻守护，掉线重连（`--once` 只跑一轮） |
| `campusnet autostart on\|off\|status` | 开机自启动开关 |
| `campusnet doctor` | 排障：探测网络、猜 portal 地址、检查配置完整性 |
| `campusnet config <key> [value]` | 读/写单个配置项，支持 `daemon.interval` 这种点号路径 |

---

## 自启动是怎么实现的

不写系统目录、不要管理员权限、随时可逆：

| 平台 | 位置 |
| --- | --- |
| Windows | `HKCU\Software\Microsoft\Windows\CurrentVersion\Run`（用 `winreg` 写，不调 `reg.exe`） |
| Linux | `~/.config/systemd/user/campusnet.service`，没 systemd 就退回 `~/.config/autostart/` |
| macOS | `~/Library/LaunchAgents/com.campusnet.autologin.plist` |

Windows 上会优先调用同目录的 `pythonw.exe` 并在 `~/.campusnet/` 生成一个自带 `sys.path` 修补的启动脚本 —— 这样开机时不会弹黑窗口，也不依赖当前工作目录。

先看要写什么，再决定要不要写：

```bash
campusnet autostart on --dry-run
```

---

## 配置文件

默认在 `~/.campusnet/config.json`，可用 `-c` / 环境变量 `CAMPUSNET_CONFIG` 指定。
**推荐把密码放环境变量**，配置文件里就只留账号：

```bash
export CAMPUSNET_PASSWORD='your-password'   # Windows: setx CAMPUSNET_PASSWORD "xxx"
```

### 通用项

| 键 | 默认 | 说明 |
| --- | --- | --- |
| `provider` | `srun` | `srun` / `eportal` / `drcom` / `custom` |
| `portal` | — | portal 根地址，**不要**带 `/eportal/` 之类的路径 |
| `username` | — | 账号 |
| `password` | — | 密码（可被 `CAMPUSNET_PASSWORD` 覆盖） |
| `client_ip` | 自动探测 | 认证时上报的本机 IP |
| `use_proxy` | `false` | 内网 portal 一定不要走代理 |
| `verify_tls` | `false` | 校园网自签证书，默认不校验 |
| `timeout` | `8` | 单请求超时（秒） |
| `check.urls` | 3 个 generate_204 | 判断在线的探测地址 |
| `daemon.interval` | `30` | 守护轮询间隔（秒） |
| `daemon.max_backoff` | `300` | 失败后退避上限（秒） |
| `daemon.startup_delay` | `0` | 开机后延迟启动，等网络就绪 |

### 深澜 `srun`

| 键 | 说明 |
| --- | --- |
| `srun.ac_id` | 认证组 ID，抓包里 `ac_id=` 后面的数字 |
| `srun.os` / `srun.name` | 上报的客户端类型，一般不用改 |

### 锐捷 `eportal`

| 键 | 说明 |
| --- | --- |
| `eportal.encrypt` | `plain` 或 `rc4`；开了 `passwordEncrypt=true` 的学校选 `rc4` |
| `eportal.rc4_key` | RC4 密钥；留空则自动从 portal 页面 JS 里抠 |
| `eportal.query_string` | 留空则自动从 portal 首页/重定向里取 |
| `eportal.service` | 服务名，如 `internet` |

### Dr.COM `drcom`

| 键 | 默认 | 说明 |
| --- | --- | --- |
| `drcom.key` | `123456` | 表单里 `0MKKey` 的值 |
| `drcom.success_marker` | `Dr.COMWebLoginID_3` | 成功页特征 |

### 自定义 `custom`

```json
{
  "provider": "custom",
  "custom": {
    "login_url": "{portal}/api/login",
    "method": "POST",
    "body": "user={username_q}&pw={password_q}",
    "success_regex": "\"code\":\\s*0",
    "headers": {"X-Requested-With": "XMLHttpRequest"}
  }
}
```

可用占位符：`{portal}` `{username}` `{password}` `{client_ip}`，以及 URL 编码版 `{username_q}` `{password_q}`。

---

## 怎么知道自己是哪种认证

```bash
campusnet doctor
```

它会探测当前网络，如果被劫持到登录页，会直接把 portal 地址打出来：

```
网络: 离线
猜测 portal 地址: https://10.21.8.7
  当前配置的是: http://10.0.0.55
  如果这个猜测更靠谱：campusnet config portal https://10.21.8.7
```

再看登录页长什么样：

- 网址里有 `srun_portal` / `cgi-bin/get_challenge` → `srun`
- 网址里有 `/eportal/InterFace.do` → `eportal`
- 页面提示装 Dr.COM 客户端、表单里有 `0MKKey` → `drcom`
- 都不是 → `custom`，F12 抓一次登录请求填进模板

---

## 常见问题

**服务跑起来了但一直重连？**
先 `campusnet login --force` 手动跑一次看报错。密码错、`ac_id` 填错、多设备同时在线的学校（同一账号只能一台设备）都会表现为「认证成功但马上掉线」。

**登录成功却上不了网？**
`campusnet status` 看探测结果。有的学校认证后还要再点「选择运营商」或绑定 MAC，这属于 portal 侧的额外步骤，本工具不管。

**想让它在后台跑、看不到窗口？**
Windows 上直接把 `autostart on` 打开就行（用 `pythonw.exe`，无窗口）。临时后台跑：

```powershell
Start-Process pythonw -ArgumentList "-m","campusnet","daemon","--quiet" -WindowStyle Hidden
```

Linux 上 `systemctl --user status campusnet` 看状态，`journalctl --user -u campusnet -f` 看日志。

**会不会被学校判定为异常行为？**
默认 30 秒轮询、失败指数退避到最长 5 分钟。别把 `daemon.interval` 改成 1 秒去撞 portal，那不是自动化，那是压力测试。

**密码明文存在配置文件里安全吗？**
文件权限已收到 `0600`，但明文就是明文。更稳妥的做法是只把密码放环境变量 `CAMPUSNET_PASSWORD`，别写进 json。

---

## 开发与测试

```bash
python -m unittest discover -s tests -t . -v
```

57 个用例，覆盖 RC4 已知向量、深澜 xencode 往返、chksum 拼接、JSONP 解析、各适配器对本地假 portal 的完整登录流程、联网检测、配置读写、自启动命令拼装。全部离线运行，不需要连真实校园网。

```
campusnet/
├── cli.py           命令分发、配置向导、doctor
├── config.py        配置读写 + 默认值 + 环境变量覆盖
├── crypto.py        RC4 / 深澜 xencode / md5 / sha1
├── http.py          urllib 会话（cookie、忽略 TLS、绕过代理）
├── netcheck.py      captive portal 探测
├── daemon.py        守护循环 + 单实例锁 + 指数退避
├── autostart.py     Windows 注册表 / systemd / launchd
└── providers/       srun / eportal / drcom / custom
```

加一个适配器的方式：继承 `providers.base.BaseProvider`，实现 `login()` 返回 `LoginResult`，然后在 `providers/__init__.py` 的 `REGISTRY` 里注册。

---

## 免责声明

仅供个人在自有账号上使用。请遵守所在学校的网络使用规定；因滥用导致的账号封禁与作者无关。

## License

MIT
