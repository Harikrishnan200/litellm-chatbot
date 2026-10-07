// Small shared helpers for the UI.
const COLORS = { groq: "#f97316", gemini: "#3b82f6", openrouter: "#a855f7" };

export function providerStyle(provider) {
  const color = COLORS[provider] || "#64748b";
  return { background: color + "26", color, borderColor: color + "66" };
}

// What the assistant bubble says while no text has arrived yet.
export function statusText(m) {
  if (m.status === "routing") return "Scoring prompt and routing…";
  if (m.status === "thinking") return `${m.meta.provider} accepted the request, waiting for first token…`;
  return "";
}

export function money(value) {
  if (!value) return "$0.00";
  return value < 0.01 ? `$${value.toFixed(6)}` : `$${value.toFixed(4)}`;
}
