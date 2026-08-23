"use client";

import { useEffect, useState } from "react";
import { fetchPersonas, loginPersona } from "@/lib/auth";
import type { Persona } from "@/lib/types";

const ROLE_LABEL: Record<string, string> = {
  customer: "Customer",
  support_agent: "Support agent",
  ops_admin: "Ops admin",
};

const PLAN_LABEL: Record<string, string> = {
  northstar: "Enterprise",
  lumenworks: "Growth",
  beacon: "Standard",
  axis: "Standard",
};

export default function HomePage() {
  const [apiReady, setApiReady] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [personas, setPersonas] = useState<Persona[]>([]);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    const apiUrl = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
    fetch(`${apiUrl}/health`)
      .then(async (res) => {
        if (!res.ok) throw new Error(`API returned ${res.status}`);
        setApiReady(true);
      })
      .catch((err: Error) => {
        setApiReady(false);
        setError(err.message);
      });

    fetchPersonas()
      .then(setPersonas)
      .catch(() => setPersonas([]));
  }, []);

  async function enter(personaId: string, href: string) {
    setBusy(true);
    try {
      await loginPersona(personaId);
      window.location.href = href;
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setBusy(false);
    }
  }

  const customers = personas.filter((p) => p.role === "customer");
  const internals = personas.filter((p) => p.role !== "customer");

  const customerList =
    customers.length > 0
      ? customers
      : ([
          {
            persona_id: "northstar",
            name: "Northstar User",
            role: "customer" as const,
            account_id: "ACCT-001",
            description: "",
          },
          {
            persona_id: "lumenworks",
            name: "LumenWorks User",
            role: "customer" as const,
            account_id: "ACCT-002",
            description: "",
          },
          {
            persona_id: "beacon",
            name: "Beacon User",
            role: "customer" as const,
            account_id: "ACCT-003",
            description: "",
          },
          {
            persona_id: "axis",
            name: "Axis User",
            role: "customer" as const,
            account_id: "ACCT-004",
            description: "",
          },
        ] satisfies Persona[]);

  const internalList =
    internals.length > 0
      ? internals
      : ([
          {
            persona_id: "maya",
            name: "Maya",
            role: "support_agent" as const,
            account_id: null,
            description: "",
          },
          {
            persona_id: "ops",
            name: "Ops Lead",
            role: "ops_admin" as const,
            account_id: null,
            description: "",
          },
        ] satisfies Persona[]);

  return (
    <main className="landing">
      <div className="landing-atmosphere" aria-hidden>
        <div className="landing-grid" />
        <div className="landing-orb landing-orb-a" />
        <div className="landing-orb landing-orb-b" />
      </div>

      <div className="landing-frame">
        <header className="landing-hero">
          <p className="brand-mark">ParcelPilot</p>
          <h1 className="brand-wordmark">Assist</h1>
          <p className="brand-line">
            Support that cites policy, shows its tools, and waits for your confirmation
            before changing anything.
          </p>
        </header>

        {!apiReady && (
          <p className="error-banner landing-error">
            Cannot reach the API. Start the backend on port 8000, then refresh.
          </p>
        )}
        {error && apiReady && <p className="error-banner landing-error">{error}</p>}

        <section className="enter-panel" aria-label="Choose how to enter">
          <div className="enter-block">
            <div className="enter-heading">
              <h2>Customer workspace</h2>
              <p>Each option signs you in as that account — you only see your own data.</p>
            </div>
            <div className="persona-cards">
              {customerList.map((p) => (
                <button
                  key={p.persona_id}
                  type="button"
                  className="persona-card"
                  disabled={busy || !apiReady}
                  onClick={() => void enter(p.persona_id, "/chat/customer")}
                >
                  <span className="persona-card-top">
                    <span className="persona-name">{p.name.replace(/ User$/, "")}</span>
                    <span className="persona-plan">
                      {PLAN_LABEL[p.persona_id] ?? "Account"}
                    </span>
                  </span>
                  <span className="persona-account">{p.account_id}</span>
                  <span className="persona-cta">Enter →</span>
                </button>
              ))}
            </div>
          </div>

          <div className="enter-divider" aria-hidden />

          <div className="enter-block">
            <div className="enter-heading">
              <h2>Internal workspace</h2>
              <p>Authorised ParcelPilot staff.</p>
            </div>
            <div className="persona-cards internal">
              {internalList.map((p) => (
                <button
                  key={p.persona_id}
                  type="button"
                  className="persona-card accent"
                  disabled={busy || !apiReady}
                  onClick={() => void enter(p.persona_id, "/chat/internal")}
                >
                  <span className="persona-card-top">
                    <span className="persona-name">{p.name}</span>
                    <span className="persona-plan">
                      {ROLE_LABEL[p.role] ?? p.role.replace(/_/g, " ")}
                    </span>
                  </span>
                  <span className="persona-cta">Enter →</span>
                </button>
              ))}
            </div>
          </div>
        </section>

        <p className="landing-footnote">Demo sign-in · no password</p>
      </div>
    </main>
  );
}
