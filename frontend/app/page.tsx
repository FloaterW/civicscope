import { CivicDashboard } from "@/components/CivicDashboard";
import { ErrorBoundary } from "@/components/ErrorBoundary";

export default function Home() {
  return (
    <ErrorBoundary>
      <CivicDashboard />
    </ErrorBoundary>
  );
}
