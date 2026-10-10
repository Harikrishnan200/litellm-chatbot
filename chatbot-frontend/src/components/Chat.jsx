import { useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { streamChat } from "../api.js";
import { providerStyle, statusText } from "./helpers.js";

// Each example is expected to land in a different router tier.
const EXAMPLES = [
  "What is the capital of Japan?",
  "Write a Python function to reverse a linked list",
  "Compare REST and gRPC, analyze the trade-offs step by step, then recommend one",
];

export default function Chat({ messages, setMessages, setSelected, sessionId, historyLoaded }) {
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const bottom = useRef(null);

  useEffect(() => {
    bottom.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  // Change the last (assistant) message while events stream in.
  function updateLast(change) {
    setMessages((all) => all.map((m, i) => (i === all.length - 1 ? { ...m, ...change(m) } : m)));
  }

  async function send(text) {
    text = text.trim();
    if (!text || busy || !historyLoaded) return;
    setInput("");
    setBusy(true);
    setMessages((all) => [...all, { role: "user", text }, { role: "assistant", text: "", status: "routing" }]);

    try {
      await streamChat(text, sessionId, {
        onMeta: (meta) => updateLast(() => ({ meta, status: "thinking" })),
        onToken: (t) => updateLast((m) => ({ text: m.text + t, status: "streaming" })),
        onDone: (stats) => updateLast(() => ({ stats, status: "done" })),
        onBlocked: (event) => updateLast(() => ({ blocked: event, status: "blocked" })),
        onError: (msg, code, event) =>
          updateLast(() => ({ error: msg, status: "error", attempts: event?.attempts })),
      });
    } catch (err) {
      console.error(err);
      updateLast(() => ({ error: "Something went wrong talking to the server.", status: "error" }));
    }
    setBusy(false);
  }

  return (
    <section className="chat">
      <div className="messages">
        {!historyLoaded && messages.length === 0 && <div className="empty"><p>Loading conversation…</p></div>}
        {historyLoaded && messages.length === 0 && (
          <div className="empty">
            <h2>Ask anything</h2>
            <p>Each prompt is scored and routed to a different model. Try one:</p>
            {EXAMPLES.map((e) => (
              <button key={e} className="example" onClick={() => send(e)}>{e}</button>
            ))}
          </div>
        )}
        {messages.map((m, i) =>
          m.role === "user" ? (
            <div key={i} className="bubble user">{m.text}</div>
          ) : (
            <div key={i} className="bubble assistant">
              {m.meta && (
                <div className="chips">
                  <span className="chip" style={providerStyle(m.meta.provider)}>{m.meta.provider}</span>
                  <span className="chip plain">{m.meta.model.split("/").slice(1).join("/") || m.meta.model}</span>
                  {m.meta.fallbacks > 0 && <span className="chip warn">fallback</span>}
                  {m.stats?.cached && <span className="chip good">cached</span>}
                  {m.stats?.recovered && <span className="chip warn">recovered mid-stream</span>}
                </div>
              )}
              {m.text ? (
                <div className="markdown"><ReactMarkdown remarkPlugins={[remarkGfm]}>{m.text}</ReactMarkdown></div>
              ) : (
                m.status === "done" ? (
                  <div className="muted">The model returned an empty answer. Try rephrasing.</div>
                ) : (
                  !["error", "blocked"].includes(m.status) && <div className="status"><span className="dots"><i /><i /><i /></span>{statusText(m)}</div>
                )
              )}
              {m.blocked && (
                <div className="blocked">
                  <b>🛡 Blocked by guardrail</b>
                  <p>{m.blocked.message} Reason: <code>{m.blocked.reason}</code>. It was never sent to any AI provider.</p>
                </div>
              )}
              {m.error && <div className="error">⚠ {m.error}</div>}
              {(m.stats?.latency !== undefined || m.status === "error" || m.status === "blocked") && (
                <button type="button" className="foot" onClick={() => setSelected(i)}>
                  {m.stats?.latency !== undefined && `${m.stats.latency}s · ${m.stats.prompt_tokens + m.stats.completion_tokens} tokens · `}
                  View details ›
                </button>
              )}
            </div>
          ),
        )}
        <div ref={bottom} />
      </div>
      <form onSubmit={(e) => { e.preventDefault(); send(input); }}>
        <input value={input} onChange={(e) => setInput(e.target.value)} placeholder="Message SmartRoute…" maxLength={4000} disabled={!historyLoaded} />
        <button disabled={busy || !historyLoaded || !input.trim()}>{busy ? "…" : "Send"}</button>
      </form>
    </section>
  );
}
