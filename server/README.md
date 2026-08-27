# VPS 部署

下面以 Ubuntu 22.04/24.04、域名 `briefing-api.example.com` 为例。GitHub Pages 是 HTTPS，所以 VPS API 也必须是 HTTPS。

## 1. 准备域名和服务器

先把一个域名或子域名的 A 记录指向 VPS 公网 IP。建议 VPS 至少 1 GB 内存；安装 Chromium 时可临时加 1–2 GB swap。

```bash
sudo apt update
sudo apt install -y git python3 python3-venv caddy
sudo useradd --system --create-home --shell /usr/sbin/nologin briefing
sudo git clone https://github.com/Tan200051116/campus-briefing.git /opt/campus-briefing
sudo chown -R briefing:briefing /opt/campus-briefing
sudo -u briefing python3 -m venv /opt/campus-briefing/server/.venv
sudo -u briefing /opt/campus-briefing/server/.venv/bin/pip install -r /opt/campus-briefing/server/requirements.txt
sudo /opt/campus-briefing/server/.venv/bin/playwright install-deps chromium
sudo -u briefing /opt/campus-briefing/server/.venv/bin/playwright install chromium
```

## 2. 配置抓取间隔

```bash
sudo -u briefing cp /opt/campus-briefing/server/.env.example /opt/campus-briefing/server/.env
sudo nano /opt/campus-briefing/server/.env
```

常改的是：

```dotenv
SCRAPE_INTERVAL_MINUTES=60
LOCAL_TIMEZONE=Asia/Shanghai
ALLOWED_ORIGIN=https://tan200051116.github.io
MY_NAME=谭睿
KDOCS_URL=在这里粘贴金山共享表格链接
```

`KDOCS_URL` 只填写在 VPS 的 `.env` 中，不要提交到公开仓库。程序按 `Asia/Shanghai` 判断日期，只保留今天及以后的宣讲。`SCRAPE_INTERVAL_MINUTES` 改成 30 就是每 30 分钟抓取一次。为避免给学校网站造成压力，程序最低按 5 分钟执行，建议 30–120 分钟。

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
- `/api/status` 的 `errors.kdocs`：共享表格权限、标签名或复制方式异常。
- 如果周标签改名，在 `.env` 的 `KDOCS_SHEETS` 中用英文逗号写全新的标签名。
- 任一来源失败时，接口继续显示上一次完整同步的数据，不会把列表清空。
