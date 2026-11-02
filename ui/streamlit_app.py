import json
import os
from uuid import uuid4

import httpx
import streamlit as st

st.set_page_config(page_title="FastAPI 社区答疑", page_icon="📚", layout="wide")
st.title("FastAPI 社区答疑")
st.caption("官方文档 · 社区搜索 · 可追溯引用")
backend = os.environ.get("CHAT_API_URL", "http://127.0.0.1:8000").rstrip("/")

if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid4())
    st.session_state.messages = []

with st.sidebar:
    st.subheader("对话")
    if st.button("开始新对话", use_container_width=True):
        st.session_state.session_id = str(uuid4())
        st.session_state.messages = []
        st.rerun()
    try:
        status = httpx.get(backend + "/health", timeout=3)
        status.raise_for_status()
        mode = status.json()["mode"]
        st.info(
            "离线演示：词汇向量 + 原文摘录，无真实模型调用。" if mode == "demo" else "真实服务模式"
        )
        st.caption("索引版本：" + status.json()["index_version"][:12])
    except Exception:
        st.warning("后端尚未就绪，请按 README 完成入库并启动服务。")
    st.caption("英文文档的离线演示请用英文提问；真实模型可以把中文问题改写为英文检索词。")
    st.write("示例：How to declare a path parameter?")


def show_details(message):
    if message.get("sources"):
        with st.expander(f"参考来源（{len(message['sources'])}）"):
            for source in message["sources"]:
                st.markdown(f"**[{source['id']}]** [{source['title']}]({source['url']})")
                st.caption(
                    f"{source['heading']} · 版本 {source['version'][:12]} · {source['kind']}"
                )
                st.text(source.get("quote", source["text"]))
    if message.get("steps"):
        with st.expander("工具执行记录"):
            for step in message["steps"]:
                st.json(step)
    if message.get("result"):
        result = message["result"]
        st.caption(
            f"耗时 {result['elapsed_ms']:.0f} ms · 缓存 {'命中' if result['cache_hit'] else '未命中'} · {result['reason']}"
        )
        if result.get("usage"):
            with st.expander("调用用量"):
                st.json(result["usage"])


for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])
        show_details(message)

if question := st.chat_input("输入 FastAPI 问题"):
    st.session_state.messages.append({"role": "user", "content": question})
    with st.chat_message("user"):
        st.markdown(question)
    with st.chat_message("assistant"):
        text_area, progress = st.empty(), st.empty()
        message = {"role": "assistant", "content": "", "sources": [], "steps": []}
        event, completed = "", False
        try:
            with httpx.stream(
                "POST",
                backend + "/chat",
                json={"message": question, "session_id": st.session_state.session_id},
                timeout=180,
            ) as response:
                response.raise_for_status()
                for line in response.iter_lines():
                    if line.startswith("event: "):
                        event = line[7:]
                    elif line.startswith("data: "):
                        data = json.loads(line[6:])
                        if event == "token":
                            message["content"] += data["text"]
                            text_area.markdown(message["content"])
                        elif event == "sources":
                            message["sources"] = data
                        elif event == "step":
                            message["steps"].append(data)
                            progress.caption(
                                f"{data.get('tool', data['stage'])} · {data['status']}"
                            )
                        elif event == "done":
                            message["result"], completed = data, True
                        elif event == "error":
                            raise RuntimeError(data["code"])
            if not completed:
                raise RuntimeError("stream_incomplete")
        except Exception:
            st.error("本轮未完成，请检查后端连接后重试。")
            message["content"] = message["content"] or "本轮请求失败，未获得完整回答。"
        progress.empty()
        show_details(message)
        st.session_state.messages.append(message)
