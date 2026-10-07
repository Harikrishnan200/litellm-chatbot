import { useState } from "react";
import Chat from "./components/Chat.jsx";
import Inspector from "./components/Inspector.jsx";

export default function App() {
  const [messages, setMessages] = useState([]); // user + assistant messages
  const [selected, setSelected] = useState(null); // index of the answer whose details popup is open

  return (
    <div className="app">
      <header>
        <div className="logo">⚡</div>
        <div>
          <h1>SmartRoute</h1>
          <p>Fault-tolerant multi-provider LLM gateway</p>
        </div>
      </header>
      <Chat messages={messages} setMessages={setMessages} setSelected={setSelected} />
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
