import { RecurringList } from "@/features/recurring/components/RecurringList"
import { FeatureErrorBoundary } from "@/components/FeatureErrorBoundary"

export default function RecurringPage() {
  return (
    <main className="max-w-2xl mx-auto px-4 py-8">
      <FeatureErrorBoundary feature="Recurring">
        <RecurringList />
      </FeatureErrorBoundary>
    </main>
  )
}
