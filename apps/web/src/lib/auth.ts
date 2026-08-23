import type { Persona } from "./types";

const TOKEN_KEY = "pp_access_token";
const PERSONA_KEY = "pp_persona";

export function apiBase(): string {
  return process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
}

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(TOKEN_KEY);
}

export function getStoredPersona(): Persona | null {
  if (typeof window === "undefined") return null;
  const raw = localStorage.getItem(PERSONA_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as Persona;
  } catch {
    return null;
  }
}

export function storeSession(token: string, persona: Persona): void {
  localStorage.setItem(TOKEN_KEY, token);
  localStorage.setItem(PERSONA_KEY, JSON.stringify(persona));
}

export function clearSession(): void {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(PERSONA_KEY);
}

export async function fetchPersonas(): Promise<Persona[]> {
  const res = await fetch(`${apiBase()}/auth/personas`);
  if (!res.ok) throw new Error(`Failed to load personas (${res.status})`);
  return res.json();
}

export async function loginPersona(personaId: string): Promise<{ token: string; persona: Persona }> {
  const res = await fetch(`${apiBase()}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ persona_id: personaId }),
  });
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(detail || `Login failed (${res.status})`);
  }
  const body = await res.json();
  const user = body.user;
  const persona: Persona = {
    persona_id: user?.persona_id ?? personaId,
    name: user?.name ?? personaId,
    role: user?.role ?? "customer",
    account_id: user?.account_id ?? null,
    description: user?.description ?? "",
  };
  storeSession(body.access_token, persona);
  return { token: body.access_token, persona };
}
