"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import {
  clearSession,
  getStoredPersona,
  getToken,
  loginPersona,
} from "@/lib/auth";
import { streamChat, streamResume } from "@/lib/stream";
import type { ChatFinal, ChatMessage, Persona, ToolChip } from "@/lib/types";

type Mode = "customer" | "internal";

const CUSTOMER_IDS = new Set(["northstar", "lumenworks", "beacon", "axis"]);
const INTERNAL_IDS = new Set(["maya", "ops"]);

const ROLE_LABEL: Record<string, string> = {
  customer: "Customer",
  support_agent: "Support agent",
  ops_admin: "Ops admin",
};

function formatRole(role: string): string {
  return ROLE_LABEL[role] ?? role.replace(/_/g, " ");
}

function uid(): string {
  return `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

function formatDraft(draft: Record<string, unknown> | undefined): string {
  if (!draft) return "Review the proposed action.";
  return Object.entries(draft)
    .filter(([, v]) => v != null && v !== "")
    .map(([k, v]) => `${k}: ${String(v)}`)
    .join("\n");
}

export function ChatApp({ mode }: { mode: Mode }) {
  const [persona, setPersona] = useState<Persona | null>(null);
  const [ready, setReady] = useState(false);
  const [threadId, setThreadId] = useState<string | null>(null);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [liveTools, setLiveTools] = useState<ToolChip[]>([]);
  const [pending, setPending] = useState<ChatFinal | null>(null);
  const bottomRef = useRef<HTMLDivElement | null>(null);

  const allowed = useMemo(
    () => (mode === "customer" ? CUSTOMER_IDS : INTERNAL_IDS),
    [mode],
  );

  useEffect(() => {
    const stored = getStoredPersona();
    const token = getToken();
    if (stored && token && allowed.has(stored.persona_id)) {
      setPersona(stored);
    }
    setReady(true);
  }, [allowed]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, liveTools, pending, busy]);

  async function ensureLogin(): Promise<Persona> {
    if (persona && getToken()) return persona;
    const defaultId = mode === "customer" ? "northstar" : "maya";
    const { persona: p } = await loginPersona(defaultId);
    setPersona(p);
    return p;
  }

  function upsertToolStart(data: {
    tool: string;
    tool_call_id?: string;
    args?: Record<string, unknown>;
  }) {
    setLiveTools((prev) => {
      const id = data.tool_call_id || `${data.tool}-${prev.length}`;
      const next = prev.filter((t) => t.id !== id);
      next.push({
        id,
        tool: data.tool,
        args: data.args,
        status: "running",
      });
      return next;
    });
  }

  function upsertToolEnd(data: {
    tool?: string;
    tool_call_id?: string;
    result_preview?: string;
  }) {
    setLiveTools((prev) =>
      prev.map((t) => {
        if (data.tool_call_id && t.id === data.tool_call_id) {
          return { ...t, status: "done", resultPreview: data.result_preview };
        }
        if (!data.tool_call_id && data.tool && t.tool === data.tool && t.status === "running") {
          return { ...t, status: "done", resultPreview: data.result_preview };
        }
        return t;
      }),
    );
  }

  async function sendMessage(text: string) {
    const trimmed = text.trim();
    if (!trimmed || busy) return;
    setError(null);
    setBusy(true);
    setLiveTools([]);
    setPending(null);
    setInput("");
    setMessages((m) => [...m, { id: uid(), role: "user", content: trimmed }]);

    const assistantId = uid();
    let toolsSnapshot: ToolChip[] = [];

    try {
      await ensureLogin();
      await streamChat(trimmed, threadId, {
        onStart: (data) => setThreadId(data.thread_id),
        onToolStart: (data) => {
          upsertToolStart(data);
          toolsSnapshot = [
            ...toolsSnapshot.filter((t) => t.id !== (data.tool_call_id || data.tool)),
            {
              id: data.tool_call_id || data.tool,
              tool: data.tool,
              args: data.args,
              status: "running",
            },
          ];
        },
        onToolEnd: (data) => {
          upsertToolEnd(data);
          toolsSnapshot = toolsSnapshot.map((t) =>
            (data.tool_call_id && t.id === data.tool_call_id) ||
            (!data.tool_call_id && t.tool === data.tool && t.status === "running")
              ? { ...t, status: "done" as const, resultPreview: data.result_preview }
              : t,
          );
        },
        onAwaiting: (data) => {
          setThreadId(data.thread_id);
          setPending(data);
          setMessages((m) => [
            ...m,
            {
              id: assistantId,
              role: "assistant",
              content: data.answer,
              tools: toolsSnapshot,
              trust: data.trust,
              awaiting: data,
            },
          ]);
          setLiveTools([]);
        },
        onFinal: (data) => {
          setThreadId(data.thread_id);
          setMessages((m) => [
            ...m,
            {
              id: assistantId,
              role: "assistant",
              content: data.answer,
              tools: toolsSnapshot.length
                ? toolsSnapshot
                : (data.tools_used || []).map((t, i) => ({
                    id: `${t.tool}-${i}`,
                    tool: t.tool || "tool",
                    args: t.args,
                    status: "done" as const,
                    resultPreview: t.result_preview,
                  })),
              trust: data.trust,
            },
          ]);
          setLiveTools([]);
        },
        onError: (detail) => setError(detail),
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  async function resolvePending(decision: "confirm" | "cancel") {
    if (!pending?.thread_id || busy) return;
    setBusy(true);
    setError(null);
    setLiveTools([]);
    const assistantId = uid();
    let toolsSnapshot: ToolChip[] = [];
    try {
      await streamResume(pending.thread_id, decision, {
        onStart: (data) => setThreadId(data.thread_id),
        onToolStart: (data) => {
          upsertToolStart(data);
          toolsSnapshot = [
            ...toolsSnapshot,
            {
              id: data.tool_call_id || data.tool,
              tool: data.tool,
              args: data.args,
              status: "running",
            },
          ];
        },
        onToolEnd: upsertToolEnd,
        onAwaiting: (data) => {
          setPending(data);
          setMessages((m) => [
            ...m,
            {
              id: assistantId,
              role: "assistant",
              content: data.answer,
              tools: toolsSnapshot,
              trust: data.trust,
              awaiting: data,
            },
          ]);
        },
        onFinal: (data) => {
          setPending(null);
          setMessages((m) => [
            ...m,
            {
              id: assistantId,
              role: "assistant",
              content: data.answer,
              tools: toolsSnapshot,
              trust: data.trust,
            },
          ]);
          setLiveTools([]);
        },
        onError: (detail) => setError(detail),
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  function logout() {
    clearSession();
    setPersona(null);
    setMessages([]);
    setThreadId(null);
    setPending(null);
  }

  if (!ready) {
    return <main className="chat-shell">Loading…</main>;
  }

  if (!persona) {
    return (
      <main className="chat-shell">
        <header className="chat-hero">
          <p className="brand-kicker">ParcelPilot</p>
          <h1 className="brand-title">Assist</h1>
          <p className="brand-sub">
            {mode === "customer"
              ? "Account-scoped support — ask about orders, fees, and SLAs."
              : "Internal investigation — cross-account tools with confirmation gates."}
          </p>
        </header>
        <PersonaGate
          mode={mode}
          onPick={async (id) => {
            const { persona: p } = await loginPersona(id);
            setPersona(p);
          }}
        />
        <p className="chat-meta">
          <a href="/">← Home</a>
        </p>
      </main>
    );
  }

  return (
    <main className="chat-shell">
      <header className="chat-hero compact">
        <div>
          <p className="brand-kicker">ParcelPilot Assist</p>
          <h1 className="brand-title sm">{mode === "customer" ? "Customer" : "Internal"} chat</h1>
          <p className="brand-sub">
            {persona.name}
            {persona.account_id
              ? ` · ${persona.account_id}`
              : ` · ${formatRole(persona.role)}`}
          </p>
        </div>
        <div className="hero-actions">
          <a href="/">Home</a>
          <button type="button" className="linkish" onClick={logout}>
            Switch persona
          </button>
        </div>
      </header>

      <section className="transcript" aria-live="polite">
        {messages.length === 0 && (
          <p className="empty-hint">
            Ask a question — tool chips appear live while the agent works.
          </p>
        )}
        {messages.map((msg) => (
          <article key={msg.id} className={`bubble ${msg.role}`}>
            <div className="bubble-label">{msg.role === "user" ? "You" : "Assist"}</div>
            {msg.tools && msg.tools.length > 0 && <ToolChipRow tools={msg.tools} />}
            <div className={`bubble-body ${msg.role === "assistant" ? "md" : ""}`}>
              {msg.role === "assistant" ? (
                <ReactMarkdown remarkPlugins={[remarkGfm]}>{msg.content}</ReactMarkdown>
              ) : (
                msg.content
              )}
            </div>
            {msg.awaiting?.draft && (
              <pre className="draft-inline">{formatDraft(msg.awaiting.draft)}</pre>
            )}
            {msg.trust && <TrustBlock trust={msg.trust} />}
          </article>
        ))}

        {busy && liveTools.length > 0 && (
          <div className="live-tools">
            <div className="bubble-label">Working</div>
            <ToolChipRow tools={liveTools} live />
          </div>
        )}
        {busy && liveTools.length === 0 && (
          <p className="thinking">Thinking…</p>
        )}
        <div ref={bottomRef} />
      </section>

      {error && <p className="error-banner">{error}</p>}

      <div className="composer-dock">
        {pending && (
          <div className="confirm-bar" role="region" aria-label="Confirm pending action">
            <div className="confirm-bar-copy">
              <span className="confirm-bar-label">
                {(pending.action_type || "action").replace(/_/g, " ")}
              </span>
              <span className="confirm-bar-hint">Confirm to apply, or cancel to discard</span>
            </div>
            <div className="confirm-bar-actions">
              <button
                type="button"
                className="btn-secondary btn-compact"
                disabled={busy}
                onClick={() => void resolvePending("cancel")}
              >
                Cancel
              </button>
              <button
                type="button"
                className="btn-primary btn-compact"
                disabled={busy}
                onClick={() => void resolvePending("confirm")}
              >
                Confirm
              </button>
            </div>
          </div>
        )}

        <form
          className="composer"
          onSubmit={(e) => {
            e.preventDefault();
            void sendMessage(input);
          }}
        >
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder={
              pending
                ? "Confirm or cancel above, or ask something else…"
                : mode === "customer"
                  ? "e.g. Can I cancel ORD-1001 without a fee?"
                  : "e.g. Check SLA on TKT-501 and escalate if breached"
            }
            disabled={busy}
            aria-label="Message"
          />
          <button type="submit" disabled={busy || !input.trim() || !!pending}>
            Send
          </button>
        </form>
      </div>
    </main>
  );
}

function PersonaGate({
  mode,
  onPick,
}: {
  mode: Mode;
  onPick: (id: string) => Promise<void>;
}) {
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const options =
    mode === "customer"
      ? [
          ["northstar", "Northstar (ACCT-001)"],
          ["lumenworks", "LumenWorks (ACCT-002)"],
          ["beacon", "Beacon (ACCT-003)"],
          ["axis", "Axis (ACCT-004)"],
        ]
      : [
          ["maya", "Maya — Support agent"],
          ["ops", "Ops Lead — Ops admin"],
        ];

  return (
    <div className="persona-gate">
      <p>Choose a demo persona to continue:</p>
      <div className="persona-grid">
        {options.map(([id, label]) => (
          <button
            key={id}
            type="button"
            disabled={busy}
            onClick={async () => {
              setBusy(true);
              setErr(null);
              try {
                await onPick(id);
              } catch (e) {
                setErr(e instanceof Error ? e.message : String(e));
              } finally {
                setBusy(false);
              }
            }}
          >
            {label}
          </button>
        ))}
      </div>
      {err && <p className="error-banner">{err}</p>}
    </div>
  );
}

function ToolChipRow({ tools, live }: { tools: ToolChip[]; live?: boolean }) {
  if (!tools.length) return null;
  const running = tools.some((t) => t.status === "running");
  const label = live
    ? running
      ? `tools called (${tools.length})…`
      : `tools called (${tools.length})`
    : `tools called (${tools.length})`;

  return (
    <details className={`tools-called ${live ? "live" : ""}`} open={live && running ? true : undefined}>
      <summary className="tools-called-summary">
        <span className="tools-called-label">{label}</span>
        <span className="tools-called-arrow" aria-hidden="true" />
      </summary>
      <ul className="tools-called-list">
        {tools.map((t, i) => (
          <li key={t.id} className={t.status} title={JSON.stringify(t.args ?? {})}>
            <span className="tools-called-index">{i + 1}.</span>
            <span className="tools-called-name">{t.tool}</span>
            {t.status === "running" && <span className="tools-called-status">running</span>}
          </li>
        ))}
      </ul>
    </details>
  );
}

function TrustBlock({ trust }: { trust: NonNullable<ChatMessage["trust"]> }) {
  const conflicts = trust.conflicts || [];
  const citations = trust.citations || [];
  const hasBadges =
    trust.abstain || trust.agreement_override || trust.recommend_escalation;
  if (!hasBadges && !conflicts.length && !citations.length) return null;
  return (
    <div className="trust-block">
      {trust.abstain && <span className="badge warn">abstain</span>}
      {trust.agreement_override && <span className="badge ok">agreement override</span>}
      {trust.recommend_escalation && <span className="badge warn">recommend escalation</span>}
      {conflicts.length > 0 && (
        <div className="conflict-callout">
          <strong>Conflict</strong>
          <ul>
            {conflicts.map((c, i) => (
              <li key={i}>{c.claim || c.note || JSON.stringify(c)}</li>
            ))}
          </ul>
        </div>
      )}
      {citations.length > 0 && (
        <div className="citations">
          {citations.slice(0, 6).map((c, i) => (
            <span key={i} className="cite">
              {c.type}:{c.id}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}
