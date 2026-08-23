export type Persona = {
  persona_id: string;
  name: string;
  role: "customer" | "support_agent" | "ops_admin";
  account_id: string | null;
  description: string;
};

export type ToolChip = {
  id: string;
  tool: string;
  args?: Record<string, unknown>;
  status: "running" | "done" | "error";
  resultPreview?: string;
};

export type TrustPayload = {
  confidence?: string;
  conflicts?: Array<{ claim?: string; sources?: unknown[]; note?: string }>;
  citations?: Array<{ type?: string; id?: string; note?: string; section?: string }>;
  flags?: string[];
  summary?: string;
  abstain?: boolean;
  agreement_override?: boolean;
  needs_confirmation?: boolean;
  recommend_escalation?: boolean;
};

export type ChatFinal = {
  thread_id: string;
  status: string;
  answer: string;
  awaiting_confirmation?: boolean;
  action_type?: string;
  pending_id?: string | null;
  draft?: Record<string, unknown>;
  interrupt?: Record<string, unknown>;
  tools_used?: Array<{ tool?: string; args?: Record<string, unknown>; result_preview?: string }>;
  trust?: TrustPayload;
};

export type ChatMessage = {
  id: string;
  role: "user" | "assistant" | "system";
  content: string;
  tools?: ToolChip[];
  trust?: TrustPayload;
  awaiting?: ChatFinal | null;
};
