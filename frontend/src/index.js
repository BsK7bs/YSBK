import React from "react";
import ReactDOM from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import "@/index.css";
import App from "@/App";

// Prevent unhandled promise rejections (e.g., clipboard denials) from surfacing
// as the CRA error overlay, which would block the entire UI.
if (typeof window !== "undefined") {
  window.addEventListener("unhandledrejection", (event) => {
    // Silently swallow — individual handlers should already toast when needed.
    // Keep a console warning for developers.
    // eslint-disable-next-line no-console
    console.warn("Unhandled promise rejection:", event.reason);
    event.preventDefault();
  });
}

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 60_000,
      refetchOnWindowFocus: false,
    },
  },
});

const root = ReactDOM.createRoot(document.getElementById("root"));
root.render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <App />
    </QueryClientProvider>
  </React.StrictMode>,
);
