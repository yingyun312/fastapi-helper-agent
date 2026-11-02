import json
import re
from dataclasses import dataclass, field

from openai import AsyncOpenAI

from app.bm25 import tokenize
from app.chunker import fenced_code_spans
from app.config import Settings


@dataclass
class ModelReply:
    content: str = ""
    tool_calls: list[dict] = field(default_factory=list)
    usage: dict = field(default_factory=dict)

    def message(self):
        message = {"role": "assistant", "content": self.content or None}
        if self.tool_calls:
            message["tool_calls"] = self.tool_calls
        return message


class ChatModel:
    def __init__(self, settings: Settings, client=None):
        if client is None and not settings.deepseek_api_key.get_secret_value():
            raise ValueError("DEEPSEEK_API_KEY is required in live mode")
        self.settings = settings
        self.client = client or AsyncOpenAI(
            api_key=settings.deepseek_api_key.get_secret_value(),
            base_url=settings.llm_base_url,
            timeout=settings.llm_timeout,
            max_retries=0,
        )

    async def complete(self, messages, tools):
        options = {}
        if self.settings.llm_disable_thinking:
            options["extra_body"] = {"thinking": {"type": "disabled"}}
        result = await self.client.chat.completions.create(
            model=self.settings.llm_model,
            messages=messages,
            tools=tools,
            stream=False,
            temperature=0,
            max_tokens=1800,
            **options,
        )
        choice = result.choices[0]
        if choice.finish_reason not in {"stop", "tool_calls"}:
            raise ValueError("Incomplete model response")
        message = choice.message
        return ModelReply(
            message.content or "",
            [
                call.model_dump(include={"id", "type", "function"})
                for call in message.tool_calls or []
            ],
            result.usage.model_dump() if result.usage else {},
        )

    async def close(self):
        await self.client.close()


class DemoModel:
    """Exercise the same tool loop but return a quoted excerpt, never model-generated advice."""

    async def complete(self, messages, tools):
        last_user = max(i for i, message in enumerate(messages) if message["role"] == "user")
        outputs = [message for message in messages[last_user + 1 :] if message["role"] == "tool"]
        if not outputs:
            question = messages[last_user]["content"]
            community = re.search(
                r"\b(issue|issues|pull request|latest|today)\b|最新|今天|社区", question, re.I
            )
            name = "search_github_issues" if community else "search_docs"
            return ModelReply(
                tool_calls=[
                    {
                        "id": "demo_call",
                        "type": "function",
                        "function": {
                            "name": name,
                            "arguments": json.dumps({"query": question[:200]}),
                        },
                    }
                ]
            )
        evidence = json.loads(outputs[-1]["content"]).get("evidence", [])
        if not evidence:
            return ModelReply(content=json.dumps({"abstain": True, "answer": "", "citations": []}))
        candidates = []
        query_terms = set(tokenize(messages[last_user]["content"]))
        for source in evidence:
            text = source["text"]
            for start, end in reversed(fenced_code_spans(text)):
                text = text[:start] + "\n\n" + text[end:]
            for part in re.split(r"\n\s*\n", text.strip()):
                part = re.sub(r"\A(?:#{1,6}[^\n]*\n)+", "", part).strip()
                if (
                    len(part) >= 30
                    and "http" not in part
                    and "```" not in part
                    and not part.startswith(("#", "===", "!!!", "???"))
                ):
                    quote = part[:500]
                    score = len(query_terms & set(tokenize(quote)))
                    candidates.append((score, source, quote))
            if candidates:
                break
        if not candidates:
            return ModelReply(content=json.dumps({"abstain": True, "answer": "", "citations": []}))
        _, source, quote = max(candidates, key=lambda item: item[0])
        answer = "离线演示：以下是检索原文摘录，未经语言模型解释。\n\n" + quote
        # A single cited block makes the extractive nature and exact source explicit.
        answer = answer.replace("\n\n", "\n") + f" [{source['id']}]"
        return ModelReply(
            content=json.dumps(
                {
                    "abstain": False,
                    "answer": answer,
                    "citations": [{"id": source["id"], "quote": quote}],
                }
            )
        )

    async def close(self):
        pass
