import { describe, it, expect } from "vitest"
import { parseSSEBuffer } from "./parseSSE"

describe("parseSSEBuffer", () => {
  it("returns empty events and full string for partial chunk (no double newline)", () => {
    const { events, remainder } = parseSSEBuffer('data: {"type":"token"')
    expect(events).toEqual([])
    expect(remainder).toBe('data: {"type":"token"')
  })

  it("parses a single token event", () => {
    const { events, remainder } = parseSSEBuffer('data: {"type":"token","content":"hello"}\n\n')
    expect(events).toHaveLength(1)
    expect(events[0]).toEqual({ type: "token", content: "hello" })
    expect(remainder).toBe("")
  })

  it("parses multiple events in one buffer", () => {
    const input =
      'data: {"type":"token","content":"a"}\n\n' +
      'data: {"type":"token","content":"b"}\n\n'
    const { events } = parseSSEBuffer(input)
    expect(events).toHaveLength(2)
    expect(events[0]).toEqual({ type: "token", content: "a" })
    expect(events[1]).toEqual({ type: "token", content: "b" })
  })

  it("retains partial trailing chunk as remainder", () => {
    const input =
      'data: {"type":"token","content":"a"}\n\n' +
      'data: {"type":"token"'
    const { events, remainder } = parseSSEBuffer(input)
    expect(events).toHaveLength(1)
    expect(remainder).toBe('data: {"type":"token"')
  })

  it("parses done event with metadata", () => {
    const input = 'data: {"type":"done","turn_id":"t1","context_quality":"good","created_at":"2026-01-01"}\n\n'
    const { events } = parseSSEBuffer(input)
    expect(events[0]).toEqual({
      type: "done",
      turn_id: "t1",
      context_quality: "good",
      created_at: "2026-01-01",
    })
  })

  it("parses error event", () => {
    const input = 'data: {"type":"error","message":"something went wrong"}\n\n'
    const { events } = parseSSEBuffer(input)
    expect(events[0]).toEqual({ type: "error", message: "something went wrong" })
  })

  it("skips chunks without data: prefix", () => {
    const input = "event: ping\n\ndata: {\"type\":\"token\",\"content\":\"x\"}\n\n"
    const { events } = parseSSEBuffer(input)
    expect(events).toHaveLength(1)
    expect(events[0]).toEqual({ type: "token", content: "x" })
  })

  it("skips malformed JSON silently", () => {
    const input = "data: not-json\n\ndata: {\"type\":\"token\",\"content\":\"ok\"}\n\n"
    const { events } = parseSSEBuffer(input)
    expect(events).toHaveLength(1)
    expect(events[0]).toEqual({ type: "token", content: "ok" })
  })

  it("returns empty events and empty remainder for empty string", () => {
    const { events, remainder } = parseSSEBuffer("")
    expect(events).toEqual([])
    expect(remainder).toBe("")
  })
})
