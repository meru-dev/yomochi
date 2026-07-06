"use client"
import { useState, useEffect, useRef } from "react"
import { useQueryClient } from "@tanstack/react-query"
import { api } from "@/lib/api/client"
import { keys } from "@/lib/query/keys"
import { parseSSEBuffer } from "@/features/chat/lib/parseSSE"
import type { SSEEvent } from "@/features/chat/lib/parseSSE"
import { useUIStore } from "@/lib/store/ui"


export interface ChatMessage {
  id: string
  role: "user" | "assistant"
  content: string
  context_quality?: string
  created_at?: string
  turn_id?: string
}

export function useStreamChat() {
  const qc = useQueryClient()
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [isStreaming, setIsStreaming] = useState(false)
  const [streamError, setStreamError] = useState<string | null>(null)
  const [historyLoaded, setHistoryLoaded] = useState(false)
  const abortRef = useRef<AbortController | null>(null)
  const { showToast } = useUIStore()

  useEffect(() => () => { abortRef.current?.abort() }, [])

  // Load history on mount
  useEffect(() => {
    if (historyLoaded) return
    ;(async () => {
      try {
        const { data, error } = await api.GET("/api/v1/chat/history", {
          params: { query: { limit: 40 } },
        })
        if (error) throw error
        const items = (data?.items ?? []).slice().reverse() as ChatMessage[]
        setMessages(items)
      } catch {
        // silently ignore history load errors
      } finally {
        setHistoryLoaded(true)
      }
    })()
  }, [historyLoaded])

  async function send(text: string): Promise<void> {
    if (isStreaming || !text.trim()) return

    setStreamError(null)
    setIsStreaming(true)

    const userId = crypto.randomUUID()
    const assistantId = crypto.randomUUID()

    const optimisticUser: ChatMessage = {
      id: userId,
      role: "user",
      content: text,
    }
    const optimisticAssistant: ChatMessage = {
      id: assistantId,
      role: "assistant",
      content: "",
    }

    setMessages((prev) => [...prev, optimisticUser, optimisticAssistant])

    const controller = new AbortController()
    abortRef.current = controller

    try {
      const response = await fetch("/api/v1/chat/stream", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: text }),
        credentials: "include",
        signal: controller.signal,
      })

      if (!response.ok) {
        // Remove optimistic messages on error
        setMessages((prev) =>
          prev.filter((m) => m.id !== userId && m.id !== assistantId)
        )
        let errorMsg = "Failed to send message."
        if (response.status === 429) {
          errorMsg = "Rate limit exceeded. Maximum 20 messages per minute."
        } else {
          try {
            const body = await response.json()
            errorMsg = body.detail ?? errorMsg
          } catch {
            // ignore parse error
          }
        }
        setStreamError(errorMsg)
        return
      }

      // Parse SSE stream
      const reader = response.body?.getReader()
      if (!reader) return

      function handleSSEEvent(event: SSEEvent) {
        if (event.type === "token") {
          setMessages((prev) =>
            prev.map((m) =>
              m.id === assistantId
                ? { ...m, content: m.content + event.content }
                : m
            )
          )
        } else if (event.type === "done") {
          setMessages((prev) =>
            prev.map((m) =>
              m.id === assistantId
                ? {
                    ...m,
                    turn_id: event.turn_id ?? m.turn_id,
                    context_quality: event.context_quality ?? m.context_quality,
                    created_at: event.created_at ?? m.created_at,
                  }
                : m
            )
          )
          if (event.save_failed) {
            showToast({
              message: "Message sent but not saved",
              meta: "won't appear in history",
              ttl: 6000,
            })
          }
          qc.invalidateQueries({ queryKey: keys.chat.history() })
        } else if (event.type === "error") {
          setStreamError(event.message)
          setMessages((prev) => prev.filter((m) => m.id !== assistantId))
        }
      }

      const decoder = new TextDecoder()
      let buffer = ""

      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        const { events, remainder } = parseSSEBuffer(buffer)
        buffer = remainder
        for (const event of events) {
          handleSSEEvent(event)
        }
      }
      buffer += decoder.decode()
      if (buffer) {
        const { events } = parseSSEBuffer(buffer)
        for (const event of events) {
          handleSSEEvent(event)
        }
      }
    } catch (err) {
      if (err instanceof Error && err.name === "AbortError") {
        return
      }
      setStreamError("Connection error. Please try again.")
      setMessages((prev) =>
        prev.filter((m) => m.id !== userId && m.id !== assistantId)
      )
    } finally {
      setIsStreaming(false)
      abortRef.current = null
    }
  }

  async function clearHistory(): Promise<void> {
    try {
      const { error } = await api.DELETE("/api/v1/chat/history")
      if (error) throw error
      setMessages([])
      qc.invalidateQueries({ queryKey: keys.chat.history() })
    } catch {
      // silently ignore or could set error
    }
  }

  return {
    messages,
    send,
    clearHistory,
    isStreaming,
    streamError,
    historyLoaded,
  }
}
