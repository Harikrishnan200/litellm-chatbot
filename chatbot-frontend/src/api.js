const API_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";
const API_KEY = import.meta.env.VITE_API_KEY || "";

// Sends the message and calls the callbacks as server-sent events arrive:
//   onMeta  - who is answering (provider, model, router tier, retries, fallbacks)
//   onToken - next piece of the answer
//   onDone  - final stats (latency, tokens, cost, cached, recovered)
//   onBlocked - the safety guardrail refused the prompt
//   onError - everything failed
// We use fetch (not EventSource) because EventSource cannot send POST bodies or headers.
export async function streamChat(message, { onMeta, onToken, onDone, onBlocked, onError }) {
  const response = await fetch(`${API_URL}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-API-Key": API_KEY },
    body: JSON.stringify({ message }),
  });

  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    onError(body.detail || `Request failed (${response.status})`, response.status);
    return;
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    // Events are separated by a blank line. Keep any incomplete tail in the buffer.
    const events = buffer.split("\n\n");
    buffer = events.pop();
    for (const raw of events) {
      if (!raw.startsWith("data: ")) continue;
      const event = JSON.parse(raw.slice(6));
      if (event.type === "meta") onMeta(event);
      else if (event.type === "token") onToken(event.text);
      else if (event.type === "done") onDone(event);
      else if (event.type === "blocked") onBlocked(event);
      else if (event.type === "error") onError(event.message, 200, event);
    }
  }
}
