import { apiBase, getToken } from "./auth";
import type { ChatFinal } from "./types";

export type StreamHandlers = {
  onStart?: (data: { thread_id: string }) => void;
  onToolStart?: (data: {
    tool: string;
    tool_call_id?: string;
    args?: Record<string, unknown>;
  }) => void;
  onToolEnd?: (data: {
    tool?: string;
    tool_call_id?: string;
    result_preview?: string;
  }) => void;
  onAssistantDelta?: (data: { text: string }) => void;
  onAwaiting?: (data: ChatFinal) => void;
  onFinal?: (data: ChatFinal) => void;
  onError?: (detail: string) => void;
};

async function readSseStream(
  response: Response,
  handlers: StreamHandlers,
): Promise<void> {
  if (!response.ok || !response.body) {
    const text = await response.text();
    throw new Error(text || `Stream failed (${response.status})`);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let eventName = "message";
  let dataLines: string[] = [];

  const flush = () => {
    if (!dataLines.length) return;
    const raw = dataLines.join("\n");
    dataLines = [];
    let payload: Record<string, unknown> = {};
    try {
      payload = JSON.parse(raw);
    } catch {
      payload = { detail: raw };
    }
    switch (eventName) {
      case "start":
        handlers.onStart?.(payload as { thread_id: string });
        break;
      case "tool_start":
        handlers.onToolStart?.(
          payload as {
            tool: string;
            tool_call_id?: string;
            args?: Record<string, unknown>;
          },
        );
        break;
      case "tool_end":
        handlers.onToolEnd?.(
          payload as {
            tool?: string;
            tool_call_id?: string;
            result_preview?: string;
          },
        );
        break;
      case "assistant_delta":
        handlers.onAssistantDelta?.(payload as { text: string });
        break;
      case "awaiting_confirmation":
        handlers.onAwaiting?.(payload as ChatFinal);
        break;
      case "final":
        handlers.onFinal?.(payload as ChatFinal);
        break;
      case "error":
        handlers.onError?.(String(payload.detail ?? "Stream error"));
        break;
      default:
        break;
    }
    eventName = "message";
  };

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const parts = buffer.split("\n");
    buffer = parts.pop() ?? "";
    for (const line of parts) {
      if (line.startsWith("event:")) {
        eventName = line.slice(6).trim();
      } else if (line.startsWith("data:")) {
        dataLines.push(line.slice(5).trim());
      } else if (line.trim() === "") {
        flush();
      }
    }
  }
  flush();
}

export async function streamChat(
  message: string,
  threadId: string | null,
  handlers: StreamHandlers,
): Promise<void> {
  const token = getToken();
  if (!token) throw new Error("Not logged in");

  const response = await fetch(`${apiBase()}/chat/stream`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
      Accept: "text/event-stream",
    },
    body: JSON.stringify({
      message,
      thread_id: threadId,
    }),
  });
  await readSseStream(response, handlers);
}

export async function streamResume(
  threadId: string,
  decision: "confirm" | "cancel",
  handlers: StreamHandlers,
): Promise<void> {
  const token = getToken();
  if (!token) throw new Error("Not logged in");

  const response = await fetch(`${apiBase()}/chat/resume/stream`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
      Accept: "text/event-stream",
    },
    body: JSON.stringify({ thread_id: threadId, decision }),
  });
  await readSseStream(response, handlers);
}
