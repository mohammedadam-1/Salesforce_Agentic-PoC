import json
import time
import httpx

payload = {
    "model": "qwen3:4b",
    "messages": [{"role": "user", "content": "Reply only OK"}],
    "stream": True,
    "keep_alive": "10m",
    "options": {"num_ctx": 4096},
}

started = time.perf_counter()

try:
    with httpx.stream(
        "POST",
        "http://localhost:11434/api/chat",
        json=payload,
        timeout=httpx.Timeout(120, connect=10),
    ) as response:
        response.raise_for_status()

        for line in response.iter_lines():
            if not line:
                continue

            chunk = json.loads(line)
            if "error" in chunk:
                raise RuntimeError(chunk["error"])

            message = chunk.get("message", {})
            print(
                message.get("thinking", "") + message.get("content", ""),
                end="",
                flush=True,
            )

            if chunk.get("done"):
                print("\n", {
                    "elapsed_seconds": round(
                        time.perf_counter() - started, 2
                    ),
                    "done_reason": chunk.get("done_reason"),
                    "eval_count": chunk.get("eval_count"),
                })
                break

except httpx.ReadTimeout:
    print("\nTimed out waiting for the next response data.")