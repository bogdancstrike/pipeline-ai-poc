import "@fontsource-variable/inter";
import "./index.css";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { App as AntApp } from "antd";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";

import App from "@/App";
import { ApiError } from "@/api/client";
import { AppearanceProvider } from "@/theme/AppearanceProvider";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      // A record list is read far more often than it changes, and refetching
      // on window focus makes a table somebody is reading jump under them.
      refetchOnWindowFocus: false,
      staleTime: 30_000,
      retry: (failureCount, error) => {
        // Retrying a 404 will not make the record exist, and retrying a bad
        // filter will not make it valid. A 503 is worth one more try: it is
        // usually PostgreSQL still starting.
        if (error instanceof ApiError && error.status < 500) return false;
        return failureCount < 2;
      },
    },
  },
});

const container = document.getElementById("root");
if (!container) throw new Error("#root is missing from index.html");

createRoot(container).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <AppearanceProvider>
        {/* AntApp supplies the message/notification/modal contexts that the
            static `message.*` helpers cannot theme. */}
        <AntApp notification={{ maxCount: 3, placement: "bottomRight" }}>
          <BrowserRouter>
            <App />
          </BrowserRouter>
        </AntApp>
      </AppearanceProvider>
    </QueryClientProvider>
  </StrictMode>,
);
