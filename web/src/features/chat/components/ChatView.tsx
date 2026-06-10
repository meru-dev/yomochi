"use client"
import { useEffect, useRef } from "react"
import { PageHead } from "@/components/shell/PageHead"
import { useStreamChat } from "../hooks/useStreamChat"
import { ChatMessage } from "./ChatMessage"
import { ChatInput } from "./ChatInput"

export function ChatView() {
  const { messages, send, clearHistory, isStreaming, streamError, historyLoaded } = useStreamChat()
  const scrollRef = useRef<HTMLDivElement>(null)
  const bottomRef = useRef<HTMLDivElement>(null)
  const stickToBottomRef = useRef(true)

  function handleScroll() {
    const el = scrollRef.current
    if (!el) return
    const distanceFromBottom = el.scrollHeight - el.scrollTop - el.clientHeight
    // 80px tolerance so smooth-scroll deceleration doesn't flip the flag mid-animation.
    stickToBottomRef.current = distanceFromBottom < 80
  }

  useEffect(() => {
    if (!stickToBottomRef.current) return
    bottomRef.current?.scrollIntoView({ behavior: "smooth" })
  }, [messages])

  return (
    <div className="flex flex-col h-[calc(100dvh-120px)] max-w-3xl mx-auto">
      <PageHead
        crumb="chat"
        title="Chat"
        subtitle="Ask anything about your finances"
        actions={
          messages.length > 0 && (
            <button
              onClick={clearHistory}
              disabled={isStreaming}
              className="text-xs text-[var(--text-3)] hover:text-[var(--danger)] transition-colors disabled:opacity-40"
            >
              clear history
            </button>
          )
        }
      />

      <div
        ref={scrollRef}
        onScroll={handleScroll}
        className="flex-1 overflow-y-auto flex flex-col gap-4 pb-4 pr-1"
      >
        {!historyLoaded && (
          <p className="text-sm text-[var(--text-3)] text-center pt-8">Loading…</p>
        )}
        {historyLoaded && messages.length === 0 && !isStreaming && (
          <div className="flex flex-col items-center justify-center flex-1 gap-3 text-center">
            <span className="text-3xl">✦</span>
            <p className="text-sm text-[var(--text-2)]">Ask about your spending, trends, or categories.</p>
            <p className="text-xs text-[var(--text-3)]">e.g. &ldquo;How much did I spend on food last month?&rdquo;</p>
          </div>
        )}
        {messages.map((m, i) => {
          const isLastAssistant =
            m.role === "assistant" && i === messages.length - 1 && isStreaming
          return (
            <ChatMessage key={m.id} message={m} isStreaming={isLastAssistant} />
          )
        })}
        {streamError && (
          <p className="text-sm text-[var(--danger)] text-center py-2">{streamError}</p>
        )}
        <div ref={bottomRef} />
      </div>

      <ChatInput onSend={send} disabled={isStreaming} />
    </div>
  )
}
