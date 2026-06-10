import { DashboardView } from "@/features/dashboard/components/DashboardView"
import { FeatureErrorBoundary } from "@/components/FeatureErrorBoundary"
export default function DashboardPage() { return <FeatureErrorBoundary feature="Dashboard"><DashboardView /></FeatureErrorBoundary> }
