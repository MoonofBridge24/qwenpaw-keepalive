
# -*- coding: utf-8 -*-

import json
import os
import sys
import uuid
import urllib.request
import urllib.error

PLATFORM = "https://platform.agentscope.io"

# 要发送给 QwenPaw 的命令
COMMAND = "测试消息请回复1"

# 当前聊天会话 ID
SESSION_ID = "1794787411260-uacrycw"

# 固定配置
USER_ID = "default"
AGENT_ID = "default"
CHANNEL = "console"


def req(url, method="GET", headers=None, data=None, timeout=30):
    h = {"User-Agent": "Mozilla/5.0"}
    if headers:
        h.update(headers)

    body = json.dumps(data, ensure_ascii=False).encode("utf-8") if data is not None else None

    if body is not None:
        h.setdefault("Content-Type", "application/json")

    r = urllib.request.Request(
        url,
        data=body,
        headers=h,
        method=method
    )

    try:
        with urllib.request.urlopen(r, timeout=timeout) as resp:
            return resp.status, resp.read().decode("utf-8", errors="replace")

    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", errors="replace")

    except Exception as e:
        print(f"    request error: {e}")
        return 0, ""


def console_chat(sid, token):
    """通过 console/chat 发送命令"""

    url = f"https://{sid}.qwenpaw.platform.agentscope.io/api/console/chat"

    message_id = str(uuid.uuid4())

    payload = {
        "input": [
            {
                "role": "user",
                "type": "message",
                "content": [
                    {
                        "type": "text",
                        "text": COMMAND,
                        "status": "created"
                    }
                ],
                "metadata": {
                    "qwenpaw_client_message_id": message_id
                }
            }
        ],
        "session_id": SESSION_ID,
        "user_id": USER_ID,
        "channel": CHANNEL,
        "stream": True,
        "request_context": {
            "approval_level": "AUTO",
            "session_id": SESSION_ID,
            "user_id": USER_ID,
            "channel": CHANNEL,
            "agent_id": AGENT_ID
        }
    }

    headers = {
        "accept": "*/*",
        "content-type": "application/json",
        "x-agent-id": AGENT_ID,
        "Cookie": f"qwenpaw_console_token={token}",
        "Origin": f"https://{sid}.qwenpaw.platform.agentscope.io",
        "Referer": (
            f"https://{sid}.qwenpaw.platform.agentscope.io/"
            "chat/ad4293ee-1d3b-4da7-9155-c3d67ef7584a"
        )
    }

    code, body = req(
        url,
        method="POST",
        headers=headers,
        data=payload,
        timeout=90
    )

    print(f"    console/chat: HTTP {code}")

    if body:
        # SSE 响应可能比较长，只输出前 1000 个字符
        print(f"    response: {body[:1000]}")

    return code == 200


def keepalive(account, password):
    # 1. 登录
    code, body = req(
        f"{PLATFORM}/api/v1/auth/login",
        "POST",
        data={
            "account": account,
            "password": password
        }
    )

    if code != 200:
        print(f"login failed: HTTP {code}")
        return False

    try:
        at = json.loads(body).get("data", {}).get("accessToken")
    except Exception:
        at = None

    if not at:
        print("login failed: accessToken unavailable")
        return False

    auth = {
        "Authorization": f"Bearer {at}",
        "accept": "application/json"
    }

    print("login successful")

    # 2. 获取全部沙箱
    code, body = req(
        f"{PLATFORM}/api/v1/app/list",
        "GET",
        headers=auth
    )

    if code != 200:
        print(f"list sandbox failed: HTTP {code}")
        return False

    try:
        items = json.loads(body).get("data") or []

        if isinstance(items, dict):
            items = items.get("list") or []

    except Exception:
        print("invalid sandbox list response")
        return False

    if not items:
        print("no sandbox found")
        return False

    print(f"found {len(items)} sandbox(s)")

    # 3. 逐台处理
    results = []

    for it in items:
        sid = it.get("id") or it.get("appId")

        if not sid:
            continue

        print(f"\n[{sid[:13]}...]")

        # 3.1 官方 heartbeat
        c, _ = req(
            f"{PLATFORM}/api/v1/app/heartbeat",
            "POST",
            headers=auth,
            data={"appId": sid}
        )

        print(f"  heartbeat: HTTP {c}")

        # 3.2 获取 console_token
        c2, b2 = req(
            f"{PLATFORM}/api/v1/qwenpaw/{sid}",
            "GET",
            headers=auth
        )

        if c2 != 200:
            print(f"  get console_token failed: HTTP {c2}")
            results.append(False)
            continue

        try:
            ct = json.loads(b2).get("data", {}).get("console_token")
        except Exception:
            ct = None

        if not ct:
            print("  console_token unavailable")
            results.append(False)
            continue

        # 3.3 发送命令
        success = console_chat(sid, ct)

        results.append(success)

    # 4. 汇总
    print("\n========== Summary ==========")

    success_count = sum(results)
    total = len(results)

    print(f"Success: {success_count}/{total}")

    return total > 0 and success_count == total


if __name__ == "__main__":
    account = os.environ.get("QP_ACCOUNT", "")
    password = os.environ.get("QP_PASSWORD", "")

    if not account or not password:
        print("QP_ACCOUNT / QP_PASSWORD required")
        sys.exit(2)

    sys.exit(0 if keepalive(account, password) else 1)
