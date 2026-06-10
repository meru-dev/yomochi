import { ChatView } from "@/features/chat/components/ChatView"
import { FeatureErrorBoundary } from "@/components/FeatureErrorBoundary"

export default function ChatPage() {
  return <FeatureErrorBoundary feature="Chat"><ChatView /></FeatureErrorBoundary>
}
