# Ask Opus

另一个基于 MCP 的 Claude Code Advisor。通过让轻量级大模型向更聪明的大模型提问，从而节省后者的账单。

## 安装

```bash
# 克隆仓库
git clone https://github.com/xiaoheiCat/ask-opus
cd ask-opus

# 复制并编辑配置文件
cp config.json.anthropic-apikey.example config.json
# 或
cp config.json.anthropic-authtoken.example config.json
# 或
cp config.json.openai.example config.json

# 编辑 config.json，填入你的 API 密钥和模型信息
```

## 配置

`config.json` 示例：

```json
{
  "provider": "anthropic",                     // openai / anthropic
  "base_url": "https://api.anthropic.com",     // AI 提供商的 Base URL
  "model": "claude-opus-4-7",                  // 某个更聪明的大模型，取决于你的提供商
  "api_key": "your-api-key",                   // 认证方式 1: openai / anthropic 均可用；与 authToken 冲突
  "authToken": "your-auth-token"               // 认证方式 2: 仅 anthropic 可用；与 api_key 冲突
}
```

## 使用

编辑受支持的 MCP 客户端的配置文件以启用 Ask Opus。以下提供了一个示例：

```json
{
  "mcpServers": {
    "ask-opus": {
      "command": "python3",
      "args": [
        "/path/to/ask-opus/ask-opus.py"
      ]
    }
  }
}
```

或者使用 `uv`：

```json
{
  "mcpServers": {
    "ask-opus": {
      "command": "uv",
      "args": [
        "run",
        "/path/to/ask-opus/ask-opus.py"
      ]
    }
  }
}
```
