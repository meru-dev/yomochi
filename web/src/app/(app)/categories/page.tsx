import { CategoriesView } from "@/features/categories/components/CategoriesView"
import { FeatureErrorBoundary } from "@/components/FeatureErrorBoundary"
export default function CategoriesPage() { return <FeatureErrorBoundary feature="Categories"><CategoriesView /></FeatureErrorBoundary> }
