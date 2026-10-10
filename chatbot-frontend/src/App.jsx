import { useEffect, useState } from "react";
import Chat from "./components/Chat.jsx";
import Inspector from "./components/Inspector.jsx";
import { loadHistory } from "./api.js";

const SESSION_KEY = "smartroute-session-id";

function getSessionId() {
  let sessionId = localStorage.getItem(SESSION_KEY);
  if (!sessionId) {
    sessionId = crypto.randomUUID?.() || `${Date.now()}-${Math.random().toString(36).slice(2)}`;
    localStorage.setItem(SESSION_KEY, sessionId);
  }
  return sessionId;
}

export default function App() {
  const [messages, setMessages] = useState([]); // user + assistant messages
  const [selected, setSelected] = useState(null); // index of the answer whose details popup is open
  const [sessionId] = useState(getSessionId);
  const [historyLoaded, setHistoryLoaded] = useState(false);

  useEffect(() => {
    loadHistory(sessionId)
      .then((history) => setMessages(history.map((message) => (
        { role: message.role, text: message.content, status: "done" }
      ))))
      .catch((error) => console.warn("Could not restore conversation history", error))
      .finally(() => setHistoryLoaded(true));
  }, [sessionId]);

  return (
    <div className="app">
      <header>
        <div className="logo">⚡</div>
        <div>
          <h1>SmartRoute</h1>
          <p>Fault-tolerant multi-provider LLM gateway</p>
        </div>
      </header>
      <Chat
        messages={messages}
        setMessages={setMessages}
        setSelected={setSelected}
        sessionId={sessionId}
        historyLoaded={historyLoaded}
      />
      {selected !== null && (
        <Inspector
          message={messages[selected]}
          history={messages.filter((m) => m.role === "assistant")}
          onClose={() => setSelected(null)}
        />
      )}
    </div>
  );
}
