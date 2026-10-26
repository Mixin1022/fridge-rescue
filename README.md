# Fridge Rescue · 料理便签

## 项目简介与使用逻辑

这是一个手机上使用的料理便签 Web App：把喜欢的视频或图文食谱整理成带食材插图、用量说明和完整步骤图的便签，再用冰箱里已有的食材寻找适合做的菜。

首页提供两个入口：

### ① 冰箱里有啥？——用现有食材找菜谱

**输入手头食材 → 选择菜系（或不限）→ 查看已收录食谱的匹配结果 → 打开完整便签。**

这里查找的是自己的菜谱库。拍照目前用于预览，食材仍需手动确认。

### ② 给菜谱库加餐——把喜欢的食谱收进来

**提交分享链接、上传视频或补充图文 → 后台识别与整理 → 复核并生成插图 → 查看完整便签 → 选择收录或报错。**

- 上传完成后可以离开页面、继续添加其他任务；电脑后台需要保持运行。
- 每个任务分别显示处理阶段、耗时、失败原因和待确认问题；失败后可以从有效断点继续。
- 便签上方展示食材、名称和原文明示用量，下方完整展开步骤，以简要注释和弧形箭头说明顺序，不需逐步点开。
- **结果不会自动收录。** 用户满意后保存；不满意则报错并说明原因。未收录的便签不进入菜谱库，后台保留记录。

首次使用需连接自己的小厨房并输入访问口令；成功后当前浏览器会记住口令，后台地址变化时自动更新。清除网站数据或更换设备后需重新填写。

识别或复核仍可能出错，缺少的用量和步骤不能凭空补造；疑问应明确展示，由用户决定是否收录。

详细页面流程见 [Web App 完整使用说明](docs/PRODUCT_FLOW.md)。

## 项目组成

前端使用原生 HTML/CSS/JavaScript；Python + SQLite 后台运行在自己的电脑或服务器；Cloudflare Worker 托管网页并登记动态后台地址。本仓库包含源码、素材、测试和部署说明，私人菜谱及密钥保留在自己的运行环境中。

## 已包含的功能

- 视频链接、本地视频和图文输入；字幕 OCR、语音识别及视频帖正文合并。
- DeepSeek 整理、原文编号校验、独立复核、局部修正和疑问标记。
- 两个任务并行推进，下载/识别/绘图分别限制共享资源竞争，阶段断点与耗时记录。
- Codex 插图分批生成、自检、独立素材排版；完整食材注释和蛇形步骤图。
- 用户选择收录或报错；未收录内容不进入食谱库，后台保留记录。
- 手机任务列表、失败原因、历史恢复记录、浏览器端口令记忆。
- 静音循环视频与轻量动态图降级；自动获取变化的后台地址。

## 快速开始（Windows）

准备 Python 3.12、FFmpeg（加入 PATH）；需要远程访问时再安装 cloudflared，需要部署时安装 Node.js/npm。

1. 解压或克隆仓库到任意目录，双击 `Install-Windows.cmd`。它安装依赖、Chromium，并生成本机访问口令；不调用模型。
2. 将 `config/deepseek-config.example.json` 复制为 `work/deepseek-config.json`，填写自己的密钥和账户可用模型名称。不要提交该文件。
3. 前台运行：

```powershell
.\.venv\Scripts\python.exe run_pc_backend.py
```

4. 打开 `http://127.0.0.1:8080`。网站访问口令保存在 `work/access-token.txt`，不是 DeepSeek 密钥。
5. 手机 HTTPS、自动地址登记见 [部署说明](docs/DEPLOYMENT.md)。首次填写口令后保存在同一网站、同一浏览器；清除网站数据后需要重填。

不用安装脚本时：

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m playwright install chromium
.\.venv\Scripts\python.exe setup_local.py
```

Linux/macOS 可用 `python3 -m venv .venv`，其余 Python 命令对应 `.venv/bin/python`；Windows 后台启动器不适用于其他系统。

## 绘图

默认不启用自动绘图。需另行安装并登录 Codex CLI，且该执行环境确实具有原生图像生成能力。普通 CLI 安装不保证可绘图；不能把 ChatGPT Windows 窗口自动化视为已实现。

准备好后，启动后台前设置 `FRIDGE_CODEX_ART=1`，或自行创建 `work/codex-art-enabled.txt`。图像生成会消耗相应账户额度。失败不会切换付费图片 API。请先用一个非私密示例实测；没有图片能力时仍可检查文字结果和错误信息。

## 测试与构建

```powershell
.\.venv\Scripts\python.exe scripts/test.py
node tests-js/test_autoconnect_motion.cjs
node tests-js/test_current_job.cjs
node tests-js/test_refresh_race.cjs
.\.venv\Scripts\python.exe build_cloudflare.py
.\.venv\Scripts\python.exe scripts/check_release.py
```

构建生成 `cloudflare-pages/` 和 `fridge-rescue-cloudflare.zip`。它们不应提交 Git。已启用地址登记的 Worker 必须连同 `address_worker.mjs` 一起部署，不能用静态 ZIP 覆盖。

## 目录

| 路径 | 用途 |
| --- | --- |
| `cloud_server.py` / `cloud_store.py` / `cloud_worker.py` | HTTP API、数据库、持久队列 |
| `pipeline_*.py` | 获取、阶段缓存、断点、任务编排 |
| `deepseek_recipe.py` / `recipe_*review*.py` | 文字整理及复核 |
| `codex_recipe_art.py` / `art_batches.py` | 原生绘图与批次恢复 |
| `app_template.html` / `cloud_client.js` / `*.css` | 前端模板、状态与视觉 |
| `assets/` / `pwa/` | 图片、视频、图标和离线壳 |
| `address_worker.mjs` / `publish_address.py` | 地址登记服务与发布客户端 |
| `config/` / `wrangler.example.json` | 无密钥配置示例 |
| `test_*.py` / `tests-js/` | 回归测试 |
| `work/` | 本机运行时数据，不进入 Git 或源码包 |

## 使用边界

识别依据可能缺失或有错，模型复核不是准确性保证。缺少正文时不能凭常识补全步骤；无用量不虚构用量。登录、平台风控、网络、模型额度均可能导致任务失败。电脑休眠或关闭后，本机后台与临时通道不能持续提供服务。

本项目是单用户私人服务，不是已加固的公共多租户系统。查看 [安全说明](SECURITY.md)、[架构](docs/ARCHITECTURE.md)、[验证记录](docs/VALIDATION.md) 和 [故障排查](docs/TROUBLESHOOTING.md)。

## 上传 GitHub

建议先创建空的私有仓库，在本目录执行：

```sh
git init
git add .
git status
git commit -m "Initial Fridge Rescue source release"
git branch -M main
git remote add origin https://github.com/YOUR_NAME/YOUR_REPO.git
git push -u origin main
```

也可以将源码文件夹内容上传到 GitHub。不要上传个人运行目录、密钥或浏览器登录资料。是否公开及采用何种开源许可由项目所有者决定，见 [许可说明](LICENSE-NOTICE.md)。
