#!/usr/bin/env python3
import sys
import json
import os
import time
import uuid
import urllib.request
import urllib.error

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")
SESSION_PATH = os.path.join(BASE_DIR, "session.json")

SESSION_TTL = 30 * 24 * 60 * 60
LONG_CONTEXT_TURNS = 15

SYSTEM_PROMPT = (
    "你是一位耐心、专业、善于启发学生的老师 AI。"
    "你的任务是帮助向你提问的学生 AI 真正理解问题，而不是直接替学生 AI 完成任务。"
    "请像教新手一样讲清楚核心原理、关键步骤和思考方式。"
    "回答应当清晰、简洁、点到为止。"
    "必要时可以给出简短示例，但不要过度展开。"
)


def load_json(path, default):
    if not os.path.exists(path):
        return default
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def load_config():
    cfg = load_json(CONFIG_PATH, {})

    for k in ("provider", "base_url", "model"):
        if not cfg.get(k):
            raise ValueError(f"config.json 缺少字段: {k}")

    provider = cfg["provider"].lower()
    if provider not in ("anthropic", "openai"):
        raise ValueError("provider 必须是 anthropic 或 openai")

    if provider == "openai" and not cfg.get("api_key"):
        raise ValueError("openai 需要 api_key")

    if provider == "anthropic" and not (cfg.get("api_key") or cfg.get("authToken")):
        raise ValueError("anthropic 需要 api_key 或 authToken")

    cfg["provider"] = provider
    cfg["base_url"] = cfg["base_url"].rstrip("/")
    return cfg


def load_sessions():
    sessions = load_json(SESSION_PATH, {})
    now = int(time.time())

    cleaned = {}
    for sid, s in sessions.items():
        updated = s.get("metadata", {}).get("updated_at", 0)
        if now - updated <= SESSION_TTL:
            cleaned[sid] = s

    if cleaned != sessions:
        save_json(SESSION_PATH, cleaned)

    return cleaned


def count_turns(messages):
    return sum(1 for m in messages if m.get("role") == "user")


def post_json(url, headers, payload):
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise RuntimeError(e.read().decode("utf-8", errors="replace"))
    except Exception as e:
        raise RuntimeError(str(e))


def call_anthropic(cfg, messages):
    url = cfg["base_url"] + "/v1/messages"

    headers = {
        "Content-Type": "application/json",
    }

    if cfg.get("api_key"):
        headers["x-api-key"] = cfg["api_key"]
    else:
        headers["Authorization"] = "Bearer " + cfg["authToken"]

    payload = {
        "model": cfg["model"],
        "system": SYSTEM_PROMPT,
        "messages": [
            {"role": m["role"], "content": m["content"]}
            for m in messages if m["role"] in ("user", "assistant")
        ],
    }

    res = post_json(url, headers, payload)

    content = res.get("content", [])
    return "".join(
        p.get("text", "")
        for p in content
        if isinstance(p, dict)
    ).strip()


def call_openai(cfg, messages):
    url = cfg["base_url"] + "/chat/completion"

    headers = {
        "Content-Type": "application/json",
        "Authorization": "Bearer " + cfg["api_key"],
    }

    payload = {
        "model": cfg["model"],
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            *[
                {"role": m["role"], "content": m["content"]}
                for m in messages if m["role"] in ("user", "assistant")
            ],
        ],
    }

    res = post_json(url, headers, payload)
    return res["choices"][0]["message"]["content"].strip()


def call_model(cfg, messages):
    if cfg["provider"] == "anthropic":
        return call_anthropic(cfg, messages)
    return call_openai(cfg, messages)


def ask_opus(args):
    question = args.get("question")
    session_id = args.get("sessionId")

    if not question:
        raise ValueError("缺少 question")

    cfg = load_config()
    sessions = load_sessions()
    now = int(time.time())

    if session_id and session_id in sessions:
        session = sessions[session_id]
    else:
        session_id = str(uuid.uuid4())
        session = {
            "metadata": {
                "created_at": now,
                "updated_at": now,
            },
            "messages": [],
        }
        sessions[session_id] = session

    session["messages"].append({
        "role": "user",
        "content": question,
        "ts": now,
    })

    answer = call_model(cfg, session["messages"])

    now = int(time.time())
    session["messages"].append({
        "role": "assistant",
        "content": answer,
        "ts": now,
    })

    session["metadata"]["updated_at"] = now
    save_json(SESSION_PATH, sessions)

    turns = count_turns(session["messages"])

    result = {
        "answer": answer,
        "sessionId": session_id,
        "turns": turns,
    }

    if turns > LONG_CONTEXT_TURNS:
        result["notice"] = (
            "当前会话轮数较多，继续追加上下文可能影响回答质量与成本控制。"
            "如果接下来的问题与当前话题关联不强，建议省略 sessionId 以开启新的会话。"
        )

    return result


def get_session(args):
    sid = args.get("sessionId")
    if not sid:
        raise ValueError("缺少 sessionId")

    sessions = load_sessions()
    if sid not in sessions:
        raise ValueError("session 不存在")

    return {
        "sessionId": sid,
        **sessions[sid],
    }


def list_session(_):
    sessions = load_sessions()
    out = []

    for sid, s in sessions.items():
        meta = s.get("metadata", {})
        out.append({
            "sessionId": sid,
            "created_at": meta.get("created_at"),
            "updated_at": meta.get("updated_at"),
            "turns": count_turns(s.get("messages", [])),
        })

    out.sort(key=lambda x: x["updated_at"] or 0, reverse=True)
    return {"sessions": out}


TOOLS = [
    {
        "name": "ask_opus",
        "description": "遇到复杂的架构或者难以解决的棘手问题时，向 Opus —— 一个更聪明的 Teacher AI 求助。\n传入 sessionId 可继续上次的对话，不传入则为开启一段新的对话。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "question": {"type": "string"},
                "sessionId": {"type": "string"},
            },
            "required": ["question"],
        },
    },
    {
        "name": "get_session",
        "description": "获取与 Opus 的会话详情",
        "inputSchema": {
            "type": "object",
            "properties": {
                "sessionId": {"type": "string"},
            },
            "required": ["sessionId"],
        },
    },
    {
        "name": "list_session",
        "description": "列出与 Opus 的会话",
        "inputSchema": {
            "type": "object",
            "properties": {},
        },
    },
]


def ok(i, r):
    return {"jsonrpc": "2.0", "id": i, "result": r}


def err(i, msg):
    return {"jsonrpc": "2.0", "id": i, "error": {"code": -32000, "message": msg}}


def handle(req):
    i = req.get("id")
    m = req.get("method")
    p = req.get("params") or {}

    try:
        if m == "initialize":
            return ok(i, {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "ask-opus", "version": "1.0.0"},
            })

        if m == "tools/list":
            return ok(i, {"tools": TOOLS})

        if m == "tools/call":
            name = p.get("name")
            args = p.get("arguments") or {}

            if name == "ask_opus":
                data = ask_opus(args)
            elif name == "get_session":
                data = get_session(args)
            elif name == "list_session":
                data = list_session(args)
            else:
                raise ValueError("未知工具")

            return ok(i, {
                "content": [{
                    "type": "text",
                    "text": json.dumps(data, ensure_ascii=False),
                }]
            })

        return err(i, "未知方法")

    except Exception as e:
        return err(i, str(e))


def main():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue

        try:
            req = json.loads(line)
            res = handle(req)
        except Exception as e:
            res = err(None, str(e))

        print(json.dumps(res, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()