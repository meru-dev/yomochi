import { TransactionsView } from "@/features/transactions/components/TransactionsView"
import { FeatureErrorBoundary } from "@/components/FeatureErrorBoundary"
export default function TransactionsPage() { return <FeatureErrorBoundary feature="Transactions"><TransactionsView /></FeatureErrorBoundary> }
