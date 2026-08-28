# VPS 部署

下面以 Ubuntu 22.04/24.04、域名 `briefing-api.example.com` 为例。GitHub Pages 是 HTTPS，所以 VPS API 也必须是 HTTPS。

## 1. 准备域名和服务器

先把一个域名或子域名的 A 记录指向 VPS 公网 IP。建议 VPS 至少 1 GB 内存。

```bash
sudo apt update
sudo apt install -y git python3 python3-venv caddy
sudo useradd --system --create-home --shell /usr/sbin/nologin briefing
sudo git clone https://github.com/Tan200051116/campus-briefing.git /opt/campus-briefing
sudo chown -R briefing:briefing /opt/campus-briefing
sudo -u briefing python3 -m venv /opt/campus-briefing/server/.venv
sudo -u briefing /opt/campus-briefing/server/.venv/bin/pip install -r /opt/campus-briefing/server/requirements.txt
```

## 2. 配置抓取间隔

```bash
sudo -u briefing cp /opt/campus-briefing/server/.env.example /opt/campus-briefing/server/.env
sudo nano /opt/campus-briefing/server/.env
```

常改的是：

```dotenv
SCRAPE_INTERVAL_MINUTES=30
LOCAL_TIMEZONE=Asia/Shanghai
QUIET_START_HOUR=22
QUIET_END_HOUR=8
OFFICIAL_FEED_URL=https://tan200051116.github.io/campus-briefing/official-events.json
ALLOWED_ORIGIN=https://tan200051116.github.io
```

程序按 `Asia/Shanghai` 判断日期，只保留今天及以后的宣讲。默认在北京时间 08:00–22:00 每 30 分钟检查一次，22:00–次日 08:00 暂停抓取。

就业网对部分境外 VPS 线路不可达，因此官网数据默认由 GitHub Actions 抓取并写入 `official-events.json`，VPS 再读取该文件。系统不再访问共享表格；已读状态和“我的宣讲”由每台设备的浏览器保存。GitHub Actions 同样只在北京时间 08:00–22:00 每半小时检查一次，只有数据变化时才提交文件。

## 3. 启动服务

```bash
sudo cp /opt/campus-briefing/server/campus-briefing.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now campus-briefing
sudo systemctl status campus-briefing
curl http://127.0.0.1:8765/api/status
```

首次同步通常需要几分钟。日志查看：

```bash
sudo journalctl -u campus-briefing -f
```

## 4. 开启 HTTPS

复制示例并把第一行换成你的真实域名：

```bash
sudo cp /opt/campus-briefing/server/Caddyfile.example /etc/caddy/Caddyfile
sudo nano /etc/caddy/Caddyfile
sudo systemctl reload caddy
curl https://你的域名/api/status
```

Caddy 会自动申请和续期 HTTPS 证书；需要 VPS 的 80、443 端口对公网开放。

## 5. 连接工作台

打开 GitHub Pages 上的“全部宣讲”，点“连接设置”，填写 `https://你的域名`。这个地址只保存在当前设备浏览器里。

## 修改间隔或更新代码

```bash
sudo nano /opt/campus-briefing/server/.env
sudo systemctl restart campus-briefing
```

更新仓库代码：

```bash
cd /opt/campus-briefing
sudo -u briefing git pull --ff-only
sudo -u briefing server/.venv/bin/pip install -r server/requirements.txt
sudo systemctl restart campus-briefing
```

## 故障判断

- `/api/status` 的 `errors.official`：学校就业网页结构或网络异常。
- 官网来源失败时，接口继续显示上一次完整同步的数据，不会把列表清空。
