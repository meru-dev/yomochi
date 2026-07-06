export type SSEEvent =
  | { type: "token"; content: string }
  | { type: "done"; turn_id?: string; context_quality?: string; created_at?: string; save_failed?: boolean }
  | { type: "error"; message: string }

export function parseSSEBuffer(buffer: string): { events: SSEEvent[]; remainder: string } {
  const chunks = buffer.split("\n\n")
  const remainder = chunks.pop() ?? ""
  const events: SSEEvent[] = []

  for (const chunk of chunks) {
    const line = chunk.trim()
    if (!line.startsWith("data:")) continue
    const jsonStr = line.slice("data:".length).trim()
    if (!jsonStr) continue

    let parsed: Record<string, unknown>
    try {
      parsed = JSON.parse(jsonStr)
    } catch {
      continue
    }

    const type = parsed.type as string
    if (type === "token") {
      events.push({ type: "token", content: (parsed.content as string) ?? "" })
    } else if (type === "done") {
      events.push({
        type: "done",
        turn_id: parsed.turn_id as string | undefined,
        context_quality: parsed.context_quality as string | undefined,
        created_at: parsed.created_at as string | undefined,
        save_failed: parsed.save_failed as boolean | undefined,
      })
    } else if (type === "error") {
      events.push({ type: "error", message: (parsed.message as string) ?? "An error occurred." })
    }
  }

  return { events, remainder }
}
