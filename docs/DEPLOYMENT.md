# 部署与自动地址登记

## 本地私有配置

`setup_local.py` 创建 `work/local-config.json`。将其中 `allowed_origins` 设置为你的公开前端完整 origin（HTTPS 域名，不带路径）。访问口令、DeepSeek API 密钥、地址写入密钥是三个不同用途的秘密，不能混用。

## Cloudflare Worker + 静态资源

以下步骤在项目根目录执行，需要自己的 Cloudflare 账户与 Node.js/npm：

1. `npx wrangler@4 login`
2. 将 `wrangler.example.json` 复制成 `wrangler-auto-address.json`，设置唯一 Worker 名称。
3. `npx wrangler@4 kv namespace create ADDRESS_BOOK`，将返回的 namespace ID 填入配置的 `kv_namespaces[0].id`。
4. `python build_cloudflare.py`
5. `npx wrangler@4 deploy --config wrangler-auto-address.json`
6. 用实际部署域名更新 `work/local-config.json` 的 `allowed_origins`。
7. 将 `config/address-publisher.example.json` 复制为 `work/address-publisher.json`，将 endpoint 改成 `https://实际域名/api/backend-address`。
8. 生成一个独立的强随机字符串填入该文件的 `write_token`。执行 `npx wrangler@4 secret put ADDRESS_WRITE_TOKEN --config wrangler-auto-address.json`，在提示处粘贴同一个值。

随机值可在本机用 Python `secrets.token_urlsafe(32)` 生成。不要把实际值贴进 Issue、聊天或仓库。

Windows 安装 cloudflared 并加入 PATH 后，双击 `Start-Background.cmd`。默认在本机 8080 端口启动服务，创建临时 HTTPS 通道，并将地址发布到自己的 Worker。`Stop-Background.cmd` 只按保存的进程身份停止本项目服务。

手机始终访问你的固定 Worker 域名。页面自动获取最新地址，第一次填写访问口令后保存在浏览器。临时通道地址变化时无需手动复制；如果地址发布失败，检查日志与密钥配置。

后续网页更新运行 `Deploy-Website.cmd`。后台源码更新前先停止服务，备份 `work/`，仅替换源码和资源；不要用别人的 work 目录覆盖本机数据。重启会恢复排队任务，可能继续产生模型调用。

## 平台登录

仅在需要时使用 `login_platform.py`，执行 `python login_platform.py`，按提示选择平台并在弹出的浏览器中登录。登录资料保存在本机浏览器配置目录，不上传 GitHub。运行平台登录前停止后台，避免两个进程占用同一浏览器配置。

## Docker（可选）

复制 `.env.example` 为 `.env` 并填写密钥、访问口令、允许的网页 origin。执行 `docker compose up --build -d`。SQLite 数据使用持久卷。公网 HTTPS 需要另外配置通道/反向代理；Docker 文件不安装 Codex CLI，也不提供 Windows 图形界面登录自动化。

没有公网部署、没有配置 DeepSeek 时，也可以运行构建和离线测试。不要为了测试打包完整性提交私人视频或调用付费模型。
