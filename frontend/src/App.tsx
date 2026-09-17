import { Skeleton } from "antd";
import { Suspense, lazy } from "react";
import { Navigate, Route, Routes } from "react-router-dom";

import { AppShell } from "@/app/AppShell";
import { ErrorBoundary } from "@/app/ErrorBoundary";

/**
 * Chart-heavy pages load on demand.
 *
 * ECharts is most of the bundle, and somebody who opens the record list should
 * not download a charting library to read it. The split follows an `import()`
 * the bundler can see, which is the only safe way to do it.
 */
const DashboardPage = lazy(() => import("@/pages/DashboardPage"));
const ExplorerPage = lazy(() => import("@/pages/ExplorerPage"));
const RecordPage = lazy(() => import("@/pages/RecordPage"));
const SavedSearchesPage = lazy(() => import("@/pages/SavedSearchesPage"));
const StatisticsPage = lazy(() => import("@/pages/StatisticsPage"));
const PipelinePage = lazy(() => import("@/pages/PipelinePage"));

export default function App() {
  return (
    <AppShell>
      <ErrorBoundary>
        <Suspense fallback={<Skeleton active paragraph={{ rows: 8 }} />}>
          <Routes>
            <Route path="/" element={<DashboardPage />} />
            <Route path="/records" element={<ExplorerPage />} />
            <Route path="/records/:recordId" element={<RecordPage />} />
            <Route path="/searches" element={<SavedSearchesPage />} />
            <Route path="/statistics" element={<StatisticsPage />} />
            <Route path="/pipeline" element={<PipelinePage />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </Suspense>
      </ErrorBoundary>
    </AppShell>
  );
}
