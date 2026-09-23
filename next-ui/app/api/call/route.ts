import { NextRequest, NextResponse } from "next/server";
import { spawn, ChildProcessWithoutNullStreams } from "node:child_process";
import path from "node:path";

export const runtime = "nodejs";
type Event = { kind: "customer" | "bot" | "nudge" | "system"; text: string; time: string };
type Store = { process: ChildProcessWithoutNullStreams | null; lines: Event[]; running: boolean; stdoutRemainder: string; stderrRemainder: string };
const state = globalThis as typeof globalThis & { voiceCall?: Store };
const store: Store = state.voiceCall ?? (state.voiceCall = { process: null, lines: [], running: false, stdoutRemainder: "", stderrRemainder: "" });

function parseLine(line: string): Event | null {
  const time = new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  if (line.startsWith("[Customer transcript]")) return { kind: "customer", text: line.replace(/^\[Customer transcript\]\s*/, ""), time };
  if (line.startsWith("[Bot transcript]")) return { kind: "bot", text: line.replace(/^\[Bot transcript\]\s*/, ""), time };
  if (line.startsWith("[LIVE NUDGE]")) return { kind: "nudge", text: line, time };
  if (line.startsWith("  ") && line.includes("confidence=")) return { kind: "nudge", text: line.trim(), time };
  if (line.startsWith("[Nudge classifier error]") || line.startsWith("[Nudges paused") || line.startsWith("Live call failed") || line.startsWith("GEMINI_API_KEY") || line.startsWith("No input transcription")) return { kind: "system", text: line, time };
  return null;
}

function addOutput(chunk: string, stream: "stdout" | "stderr") {
  const key = stream === "stdout" ? "stdoutRemainder" : "stderrRemainder";
  const combined = store[key] + chunk;
  const parts = combined.split(/\r?\n/);
  store[key] = parts.pop() ?? "";
  for (const line of parts) {
    if (!line.trim()) continue;
    const event = stream === "stdout" ? parseLine(line) : { kind: "system" as const, text: line.trim(), time: new Date().toLocaleTimeString() };
    if (event) store.lines.push(event);
  }
}

export async function POST(request: NextRequest) {
  if (store.running) return NextResponse.json({ error: "A call is already running" }, { status: 409 });
  const { market = "india" } = await request.json();
  if (!["india", "philippines", "indonesia"].includes(market)) return NextResponse.json({ error: "Invalid market" }, { status: 400 });
  const root = path.resolve(process.cwd(), "..");
  const python = process.platform === "win32" ? path.join(root, "venv", "Scripts", "python.exe") : path.join(root, "venv", "bin", "python");
  const child = spawn(python, ["-u", path.join(root, "app.py"), market], { cwd: root, env: { ...process.env, PYTHONUNBUFFERED: "1" } });
  store.process = child; store.lines = []; store.stdoutRemainder = ""; store.stderrRemainder = ""; store.running = true;
  child.stdout.on("data", (chunk: Buffer) => addOutput(chunk.toString(), "stdout"));
  child.stderr.on("data", (chunk: Buffer) => addOutput(chunk.toString(), "stderr"));
  child.on("error", (error) => { store.lines.push({ kind: "system", text: `Python process error: ${error.message}`, time: new Date().toLocaleTimeString() }); store.running = false; store.process = null; });
  child.on("close", (code) => { if (store.stdoutRemainder) addOutput("\n", "stdout"); if (store.stderrRemainder) addOutput("\n", "stderr"); if (code && store.running) store.lines.push({ kind: "system", text: `Voice process stopped with exit code ${code}.`, time: new Date().toLocaleTimeString() }); store.running = false; store.process = null; });
  return NextResponse.json({ ok: true });
}

export async function GET() {
  const lines = store.lines.splice(0);
  return NextResponse.json({ running: store.running, lines });
}
export async function DELETE() { if (store.process && !store.process.killed) store.process.kill(); store.running = false; return NextResponse.json({ ok: true }); }
