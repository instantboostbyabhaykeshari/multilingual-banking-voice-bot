"use client";

import { useEffect, useMemo, useState } from "react";

type Log = { kind: "customer" | "bot" | "nudge" | "system"; text: string; time: string };

const initialLogs: Log[] = [{ kind: "system", text: "Select a market and start a call.", time: "Now" }];

export default function Home() {
  const [market, setMarket] = useState("india");
  const [running, setRunning] = useState(false);
  const [logs, setLogs] = useState<Log[]>(initialLogs);
  const [error, setError] = useState("");

  const transcript = useMemo(() => logs.filter((x) => x.kind === "customer" || x.kind === "bot"), [logs]);
  const nudges = useMemo(() => logs.filter((x) => x.kind === "nudge"), [logs]);

  useEffect(() => {
    if (!running) return;
    const timer = setInterval(async () => {
      const response = await fetch("/api/call", { cache: "no-store" });
      if (!response.ok) return;
      const data = await response.json();
      if (data.lines?.length) {
        setLogs((old) => [...old, ...data.lines]);
        const systemError = data.lines.find((line: Log) => line.kind === "system");
        if (systemError) setError(systemError.text);
      }
      if (!data.running) setRunning(false);
    }, 700);
    return () => clearInterval(timer);
  }, [running]);

  async function start() {
    setError("");
    const response = await fetch("/api/call", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ market }) });
    const data = await response.json();
    if (!response.ok) return setError(data.error || "Could not start call");
    setLogs([{ kind: "system", text: `Call started for ${market}. Speak into the microphone.`, time: "Now" }]);
    setRunning(true);
  }

  async function stop() {
    await fetch("/api/call", { method: "DELETE" });
    setRunning(false);
    setLogs((old) => [...old, { kind: "system", text: "Call stopped.", time: "Now" }]);
  }

  return <main className="shell">
    <header className="topbar"><div><div className="eyebrow">ASSESSMENT MONITOR</div><h1>Native Voice Bot</h1></div><div className={`status ${running ? "live" : ""}`}><span />{running ? "Live call" : "Ready"}</div></header>
    <section className="controls"><label>Market<select value={market} onChange={(e) => setMarket(e.target.value)} disabled={running}><option value="india">India</option><option value="philippines">Philippines</option><option value="indonesia">Indonesia</option></select></label><div className="actions"><button className="primary" onClick={start} disabled={running}>Start call</button><button onClick={stop} disabled={!running}>Stop call</button></div></section>
    {error && <div className="error">{error}</div>}
    <section className="grid"><Panel title="Live transcript" subtitle="Customer and bot conversation"><div className="feed">{transcript.length ? transcript.map((log, i) => <div className={`message ${log.kind}`} key={i}><div className="messageHead"><b>{log.kind === "customer" ? "Customer" : "Bot"}</b><small>{log.time}</small></div><p>{log.text}</p></div>) : <Empty text="Transcript will appear during the call." />}</div></Panel><Panel title="Nudges" subtitle="Real-time recommendations"><div className="feed">{nudges.length ? nudges.map((log, i) => <div className="nudge" key={i}><span className="dot" /><p>{log.text}</p></div>) : <Empty text="No nudges yet." />}</div></Panel></section>
    <footer>Assessment prototype · Audio runs through the existing Python voice engine · Use headphones for interruption testing</footer>
  </main>;
}

function Panel({ title, subtitle, children }: { title: string; subtitle: string; children: React.ReactNode }) { return <article className="panel"><div className="panelTitle"><div><h2>{title}</h2><span>{subtitle}</span></div><span className="count">●</span></div>{children}</article>; }
function Empty({ text }: { text: string }) { return <div className="empty">{text}</div>; }
