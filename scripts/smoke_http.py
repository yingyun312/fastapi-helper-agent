"""Verify running localhost services through real HTTP, including SSE framing."""

import json

import httpx


def main():
    with httpx.Client(timeout=30) as client:
        health = client.get("http://127.0.0.1:8000/health")
        health.raise_for_status()
        ui = client.get("http://127.0.0.1:8501/_stcore/health")
        ui.raise_for_status()
        events, current = [], ""
        with client.stream(
            "POST",
            "http://127.0.0.1:8000/chat",
            json={"message": "How to declare a path parameter?"},
        ) as response:
            response.raise_for_status()
            assert response.headers["content-type"].startswith("text/event-stream")
            for line in response.iter_lines():
                if line.startswith("event: "):
                    current = line[7:]
                elif line.startswith("data: "):
                    events.append((current, json.loads(line[6:])))
        assert events[0][0] == "meta" and events[-1][0] == "done"
        assert any(event == "step" for event, _ in events)
        assert events[-1][1]["sources"]
        assert (
            "".join(data["text"] for event, data in events if event == "token")
            == events[-1][1]["answer"]
        )
        print(
            json.dumps(
                {
                    "backend": health.json(),
                    "frontend_health": ui.status_code,
                    "events": [event for event, _ in events],
                    "abstained": events[-1][1]["abstained"],
                },
                indent=2,
            )
        )


if __name__ == "__main__":
    main()
