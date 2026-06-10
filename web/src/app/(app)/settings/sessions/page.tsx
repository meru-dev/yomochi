import { FeatureErrorBoundary } from "@/components/FeatureErrorBoundary"
import { SessionsView } from "@/features/users/components/SessionsView"

export default function SessionsPage() {
  return (
    <FeatureErrorBoundary feature="Sessions">
      <SessionsView />
    </FeatureErrorBoundary>
  )
}
