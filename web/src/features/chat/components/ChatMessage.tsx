import type { ChatMessage as ChatMessageType } from "../hooks/useStreamChat"

const QUALITY_COLOR: Record<string, string> = {
  full: "text-[var(--income)]",
  partial: "text-[var(--text-3)]",
  none: "text-[var(--danger)]",
}

export function ChatMessage({
  message,
  isStreaming,
}: {
  message: ChatMessageType
  isStreaming: boolean
}) {
  const isUser = message.role === "user"
  const isEmpty = message.content === "" && !isStreaming

  return (
    <div className={`flex flex-col gap-1 ${isUser ? "items-end" : "items-start"}`}>
      <div
        className={`max-w-[80%] rounded-[var(--radius-md)] px-4 py-3 text-sm leading-relaxed whitespace-pre-wrap break-words ${
          isUser
            ? "bg-[var(--accent)] text-white"
            : "bg-[var(--surface)] text-[var(--text)] border border-[var(--rule)]"
        }`}
      >
        {isEmpty ? (
          <span className="opacity-40 text-xs">thinking…</span>
        ) : (
          <>
            {message.content}
            {!isUser && isStreaming && (
              <span className="inline-block w-[2px] h-[14px] ml-[2px] bg-[var(--accent)] animate-pulse align-middle" />
            )}
          </>
        )}
      </div>
      {!isUser && message.context_quality && (
        <span className={`text-[10px] font-mono px-1 ${QUALITY_COLOR[message.context_quality] ?? ""}`}>
          context: {message.context_quality}
        </span>
      )}
    </div>
  )
}
