import { InsightsIndexPage } from "@/features/insights/components/InsightsIndexPage"
import { FeatureErrorBoundary } from "@/components/FeatureErrorBoundary"

export default function InsightsRoot() {
  return <FeatureErrorBoundary feature="Insights"><InsightsIndexPage /></FeatureErrorBoundary>
}
