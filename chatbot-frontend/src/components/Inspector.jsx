import { useEffect } from "react";
import { money, providerStyle } from "./helpers.js";

// Popup: shows exactly what the gateway did for one answer, plus session totals.
export default function Inspector({ message, history, onClose }) {
  useEffect(() => {
    const onKey = (e) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const total = history.reduce(
    (t, m) => ({
      requests: t.requests + 1,
      tokens: t.tokens + (m.stats ? (m.stats.prompt_tokens || 0) + (m.stats.completion_tokens || 0) : 0),
      cost: t.cost + (m.stats?.cost || 0),
      fallbacks: t.fallbacks + (m.meta?.fallbacks > 0 ? 1 : 0),
      cached: t.cached + (m.stats?.cached ? 1 : 0),
    }),
    { requests: 0, tokens: 0, cost: 0, fallbacks: 0, cached: 0 },
  );
  const meta = message?.meta;
  const stats = message?.stats;
  const attempts = message?.attempts ?? 0;

  return (
    <div className="overlay" onClick={onClose}>
    <aside className="inspector" onClick={(e) => e.stopPropagation()} role="dialog" aria-label="Request details">
      <button type="button" className="close" onClick={onClose} aria-label="Close">×</button>
      <h3>Request details</h3>
      {message?.blocked && (
        <div className="card">
          <b>Blocked by guardrail</b>
          <p className="muted">Reason: {message.blocked.reason}. The prompt was refused before routing, so no provider was called (0 tries, $0).</p>
          <p className="muted mono">Request ID {message.blocked.request_id}</p>
        </div>
      )}
      {message?.error && !meta && (
        <div className="card">
          <b>Request failed</b>
          <p className="muted">{message.error}{attempts ? ` (${attempts} tries)` : ""}</p>
        </div>
      )}

      {meta && (
        <>
          <div className="pipeline">
            <div className="step">
              <small>Router</small>
              <b>{meta.tier || "—"}</b>
              {meta.score !== "" && <span>score {Number(meta.score).toFixed(2)}</span>}
            </div>
            <div className="arrow">→</div>
            <div className="step">
              <small>Group</small>
              <b>{meta.route === "fallback" ? "fallback" : `${meta.route}-model`}</b>
              {meta.fallbacks > 0 && <span className="warn-text">primary failed</span>}
            </div>
            <div className="arrow">→</div>
            <div className="step" style={providerStyle(meta.provider)}>
              <small>Provider</small>
              <b>{meta.provider}</b>
            </div>
          </div>

          {message?.error && <p className="error">⚠ {message.error}</p>}
          <dl>
            <dt>Model</dt><dd>{meta.model}</dd>
            <dt>Tries</dt>
            <dd>
              {meta.attempts === 0 ? "0 (served from cache)" : `${meta.attempts} (${meta.retries} retry, ${meta.fallbacks} fallback)`}
            </dd>
            {stats && (
              <>
                <dt>Latency</dt><dd>{stats.latency}s</dd>
                <dt>Tokens</dt><dd>{stats.prompt_tokens} in · {stats.completion_tokens} out</dd>
                <dt>Billed</dt><dd>$0.00 <span className="muted">(free tier)</span></dd>
                <dt title="LiteLLM's estimate at public list prices. You are not charged.">List-price est.</dt>
                <dd>{money(stats.cost)}</dd>
                <dt>Cached</dt><dd>{stats.cached ? "yes" : "no"}</dd>
                {stats.recovered && (<><dt>Recovered by</dt><dd>{stats.recovered_by}</dd></>)}
                <dt>Request ID</dt><dd className="mono">{stats.request_id}</dd>
              </>
            )}
          </dl>
        </>
      )}

      <h3>This session</h3>
      <div className="totals">
        <div><b>{total.requests}</b><small>requests</small></div>
        <div><b>{total.tokens}</b><small>tokens</small></div>
        <div><b>{total.fallbacks}</b><small>fallbacks</small></div>
        <div><b>{total.cached}</b><small>cache hits</small></div>
      </div>
    </aside>
    </div>
  );
}
