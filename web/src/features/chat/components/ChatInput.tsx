"use client"
import { useRef, useState, useEffect, Suspense } from "react"
import { useSearchParams } from "next/navigation"

function ChatInputInner({
  onSend,
  disabled,
}: {
  onSend: (text: string) => void
  disabled: boolean
}) {
  const searchParams = useSearchParams()
  const prefill = searchParams.get("q") ?? ""
  const [text, setText] = useState(prefill)
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  useEffect(() => {
    textareaRef.current?.focus()
  }, [])

  function submit() {
    const trimmed = text.trim()
    if (!trimmed || disabled) return
    onSend(trimmed)
    setText("")
  }

  function onKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault()
      submit()
    }
  }

  return (
    <div className="flex gap-3 items-end border-t border-[var(--rule)] pt-4">
      <textarea
        ref={textareaRef}
        value={text}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={onKeyDown}
        disabled={disabled}
        placeholder="Ask about your finances…"
        rows={1}
        className="flex-1 resize-none rounded-[var(--radius-md)] border border-[var(--rule)] bg-[var(--surface)] px-4 py-3 text-sm text-[var(--text)] placeholder-[var(--text-3)] focus:outline-none focus:border-[var(--accent)] disabled:opacity-50 overflow-hidden"
        style={{ maxHeight: "120px", overflowY: text.split("\n").length > 4 ? "auto" : "hidden" }}
        onInput={(e) => {
          const t = e.currentTarget
          t.style.height = "auto"
          t.style.height = `${Math.min(t.scrollHeight, 120)}px`
        }}
        maxLength={500}
      />
      <button
        onClick={submit}
        disabled={disabled || !text.trim()}
        className="px-5 py-3 rounded-[var(--radius-md)] bg-[var(--accent)] text-white text-sm font-medium disabled:opacity-40 hover:opacity-90 transition-opacity shrink-0"
      >
        {disabled ? "…" : "Send"}
      </button>
    </div>
  )
}

export function ChatInput(props: { onSend: (text: string) => void; disabled: boolean }) {
  return (
    <Suspense fallback={null}>
      <ChatInputInner {...props} />
    </Suspense>
  )
}
