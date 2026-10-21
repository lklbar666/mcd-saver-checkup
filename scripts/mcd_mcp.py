#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""麦当劳 MCP 客户端（JSON-RPC 2.0 over Streamable HTTP）

只做三件事：握手、列工具、调工具。不做任何字段假设——返回什么就打印什么。

用法：
  export MCD_MCP_TOKEN=xxxx
  python scripts/mcd_mcp.py --ping
  python scripts/mcd_mcp.py --tools
  python scripts/mcd_mcp.py --call query-meals '{"storeId":"..."}'
  python scripts/mcd_mcp.py --dump query-meals '{"storeId":"..."}' --out raw.json

说明：
  - Token 只从环境变量读取，不写入任何文件、不打印
  - Streamable HTTP 可能返回 application/json，也可能返回 text/event-stream（SSE），两种都解析
  - 若服务端下发 Mcp-Session-Id，后续请求自动带上
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

ENDPOINT = "https://mcp.mcd.cn"
PROTOCOL = "2025-06-18"


class McpError(RuntimeError):
    pass


class McpClient:
    def __init__(self, token: str, endpoint: str = ENDPOINT, timeout: int = 45):
        if not token:
            raise McpError("缺少 Token：请先 export MCD_MCP_TOKEN=...")
        self.token = token
        self.endpoint = endpoint.rstrip("/")
        self.timeout = timeout
        self.session_id: str | None = None
        self._id = 0

    # ---------------------------------------------------------------- 传输
    def _post(self, payload: dict) -> dict:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(self.endpoint, data=data, method="POST")
        req.add_header("Authorization", "Bearer " + self.token)
        req.add_header("Content-Type", "application/json")
        req.add_header("Accept", "application/json, text/event-stream")
        if self.session_id:
            req.add_header("Mcp-Session-Id", self.session_id)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                sid = r.headers.get("Mcp-Session-Id")
                if sid:
                    self.session_id = sid
                body = r.read().decode("utf-8", errors="replace")
                ctype = (r.headers.get("Content-Type") or "").lower()
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", errors="replace")[:500]
            raise McpError("HTTP %s：%s" % (e.code, detail)) from None
        except urllib.error.URLError as e:
            raise McpError("连接失败：%s" % e.reason) from None

        if "text/event-stream" in ctype or body.lstrip().startswith(("event:", "data:")):
            return self._parse_sse(body)
        try:
            return json.loads(body)
        except json.JSONDecodeError:
            raise McpError("返回既不是 JSON 也不是 SSE：%s" % body[:300]) from None

    @staticmethod
    def _parse_sse(body: str) -> dict:
        """从 SSE 里取出最后一个 data: 的 JSON。"""
        last = None
        for line in body.splitlines():
            line = line.strip()
            if line.startswith("data:"):
                chunk = line[5:].strip()
                if chunk and chunk != "[DONE]":
                    try:
                        last = json.loads(chunk)
                    except json.JSONDecodeError:
                        continue
        if last is None:
            raise McpError("SSE 里没有可解析的 data")
        return last

    def _rpc(self, method: str, params: dict | None = None) -> dict:
        self._id += 1
        payload = {"jsonrpc": "2.0", "id": self._id, "method": method}
        if params is not None:
            payload["params"] = params
        res = self._post(payload)
        if "error" in res:
            raise McpError("RPC 错误：%s" % json.dumps(res["error"], ensure_ascii=False))
        return res.get("result", {})

    # ---------------------------------------------------------------- 协议
    def initialize(self) -> dict:
        return self._rpc("initialize", {
            "protocolVersion": PROTOCOL,
            "capabilities": {},
            "clientInfo": {"name": "mcd-saver-checkup", "version": "0.1.0"},
        })

    def list_tools(self) -> list:
        return self._rpc("tools/list", {}).get("tools", [])

    def call(self, name: str, arguments: dict) -> dict:
        return self._rpc("tools/call", {"name": name, "arguments": arguments})


def extract_payload(result: dict) -> dict | None:
    """从 tools/call 的返回里取出业务 JSON。

    MCP 的返回是 {"content":[{"type":"text","text":"...说明...\n{json}"}]}，
    而且 text 里 JSON 之后可能还有内容，所以用 raw_decode 只取第一个完整对象。
    """
    text = "".join(b.get("text", "") for b in (result or {}).get("content", []) if isinstance(b, dict))
    dec = json.JSONDecoder()
    for anchor in ('{"success"', "{", "["):
        start = text.find(anchor)
        while start >= 0:
            try:
                obj, _ = dec.raw_decode(text[start:])
                return obj
            except json.JSONDecodeError:
                start = text.find(anchor, start + 1)
    return None


# -------------------------------------------------------------------- CLI
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="麦当劳 MCP 客户端")
    ap.add_argument("--ping", action="store_true", help="握手并打印服务端信息")
    ap.add_argument("--tools", action="store_true", help="列出全部工具")
    ap.add_argument("--call", nargs=2, metavar=("TOOL", "JSON_ARGS"), help="调用工具")
    ap.add_argument("--dump", nargs=2, metavar=("TOOL", "JSON_ARGS"), help="调用并把原始返回写文件")
    ap.add_argument("--out", default="raw.json")
    a = ap.parse_args(argv)

    token = os.environ.get("MCD_MCP_TOKEN", "").strip()
    try:
        c = McpClient(token)
        info = c.initialize()
        if a.ping or not any([a.tools, a.call, a.dump]):
            print("✓ 连接成功")
            print(json.dumps(info, ensure_ascii=False, indent=2)[:800])
        if a.tools:
            tools = c.list_tools()
            print("\n可用工具 %d 个：" % len(tools))
            for t in tools:
                print("  %-28s %s" % (t.get("name", "?"),
                                      (t.get("description") or "").split("\n")[0][:60]))
        if a.call:
            name, raw = a.call
            print(json.dumps(c.call(name, json.loads(raw)), ensure_ascii=False, indent=2))
        if a.dump:
            name, raw = a.dump
            res = c.call(name, json.loads(raw))
            Path(a.out).write_bytes(json.dumps(res, ensure_ascii=False, indent=2).encode("utf-8"))
            print("原始返回已写入 %s（%d 字节）" % (a.out, Path(a.out).stat().st_size))
    except McpError as e:
        print("✗ %s" % e, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
