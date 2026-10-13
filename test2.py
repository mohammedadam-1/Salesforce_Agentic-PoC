import httpx

response = httpx.post(
    "http://localhost:11434/api/show",
    json={"model": "qwen3:4b"},
    timeout=30,
)
response.raise_for_status()
data = response.json()

print({
    "thinking": data.get("thinking"),
    "capabilities": data.get("capabilities"),
})