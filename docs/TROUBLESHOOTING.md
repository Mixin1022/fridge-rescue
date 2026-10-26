# 故障排查

| 现象 | 首先检查 | 处理方式 |
| --- | --- | --- |
| Failed to fetch | 本机 /api/health、后台进程、通道、DNS、allowed_origins | 先恢复服务，再确认登记地址；不是直接重设口令 |
| 401 | 网站访问口令 | 使用 work/access-token.txt，不用 DeepSeek 密钥 |
| 缺少有效原文编号 | deepseek-candidate.json、evidence-repair.json | 仅明确匹配时恢复缺失编号，步骤语义仍需复核 |
| 缺少帖子正文 | 视频是否提示参考内文；识别依据是否含 post_text | 使用带正文的原帖链接，或手动补充图文 |
| 空食谱 | 模型 ingredients/steps 是否为空 | 不允许空内容进入复核或假装成功 |
| 绘图额度用尽 | art-task/codex.log | 等额度恢复后从断点继续，不重复上传视频 |
| 图像裁切或步骤不对应 | render-plan、自检报告、原始独立 PNG | 保留证据并报错，不用隐藏提示代替修复 |
| 首页无法自动播放视频 | 手机浏览器媒体策略 | 使用轻量动态图降级；系统策略不能强制绕过 |

重试可能调用付费文字 API或消耗绘图额度。已保存且输入规则一致的阶段才会复用。不要在公开 Issue 附密钥、带签名的完整链接、cookies 或整个 work 文件夹；使用匿名示例与脱敏日志。
