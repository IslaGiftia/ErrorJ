# ErrorJ Agent

独立的 ErrorJ QQ 助手服务。当前第一版支持：

- DeepSeek 闲聊
- 元件库存查询
- 收藏网站和链接查询
- 笔记搜索与读取
- 管理员待审核队列查询
- 审核操作二次确认

## 安全边界

- 仅允许配置中的 QQ 管理员私聊使用；群聊默认关闭。
- Agent 不直接连接数据库，只能调用错误酱内部工具 API。
- 内部 API 只接受本机请求、共享令牌和显式用户身份。
- 审核操作先生成一次性确认码，两分钟内回复 `确认 123456` 才执行。
- 当前笔记数据没有逐用户所有权字段，因此第一版只供管理员或拥有 `notes:view` 的用户使用。

## 本地启动

1. 复制 `.env.example` 为 `.env` 并填写配置。
2. 启动错误酱时设置相同的 `ERRORJIANG_AGENT_TOKEN`。
3. 运行：

```powershell
python -m errorjiang_agent
```

Agent 默认监听 `127.0.0.1:8011`，OneBot 事件地址为：

```text
http://127.0.0.1:8011/onebot/event/<ONEBOT_WEBHOOK_SECRET>
```

## OneBot / NapCat

- 事件上报方式：HTTP POST
- 事件地址：上方带密钥的地址
- HTTP API 地址：`http://127.0.0.1:3000`
- 如果配置了 `ONEBOT_ACCESS_TOKEN`，Agent 调用发送接口时会附带 Bearer Token

## 常用命令

- `帮助`
- `重置对话`
- `确认 123456`
