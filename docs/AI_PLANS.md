# AI训练计划

保存画像 → 训练页“根据画像生成 AI 计划” → 查看制定理由、训练安排、热身、恢复和调整建议 → 调整草稿 → 确认保存。

生成只创建草稿，不覆盖已保存计划；确认保存产生新版本。画像或RM发生变化后，旧AI草稿需重新生成。

当前动作范围：平板杠铃卧推、高杠杠铃深蹲、传统杠铃硬拉。缺少确认且90天内的RM时，对应重量置空，显示“重量待确认”。已有伤病或训练限制时，当前三项负重动作的自动生成会被阻止，需先确认可训练范围。AI输出必须满足动作范围、训练日数量和RM上限，否则返回错误，不替换为静态模板。

## 配置模型服务

复制根目录 `.env.example` 为 `.env`，填写服务商提供的配置：

```dotenv
AI_API_KEY=你的API密钥
AI_BASE_URL=服务商的API基础地址
AI_MODEL=你的账户可用模型ID
```

使用支持 `/chat/completions` 及 `response_format={"type":"json_object"}` 的服务。OpenAI基础地址为 `https://api.openai.com/v1`；其他服务以官方文档为准。模型ID不固定，按账户实际权限配置。

配置每次调用都会读取，无需重启才能读取新密钥。密钥仅存于电脑后端；手机不会获取。`.env`已被Git忽略。不要将密钥提交到代码库或写进Flutter代码。

接口：`GET /api/ai/status` 返回配置状态；`POST /api/plans/generate` 根据已保存画像和RM返回草稿；`POST /api/plans` 确认保存（包括generation_id）。

测试使用模拟服务返回，不产生模型费用。真实生成需要有效API密钥、余额及网络；ChatGPT订阅和API计费分开。目前没有真实模型联调结果。

参考： https://api-docs.deepseek.com/api/create-chat-completion/ ， https://developers.openai.com/api/docs/quickstart 。
