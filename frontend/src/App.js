import React from "react";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { Toaster } from "sonner";

import { AuthProvider, useAuth } from "./contexts/AuthContext";
import { ThemeProvider } from "./contexts/ThemeContext";
import { DashboardSocketProvider } from "./contexts/WebSocketContext";
import AppShell from "./components/AppShell";

import LoginPage from "./pages/auth/LoginPage";
import SignupPage from "./pages/auth/SignupPage";
import AcceptInvitePage from "./pages/auth/AcceptInvitePage";
import DashboardPage from "./pages/DashboardPage";
import DevicesPage from "./pages/DevicesPage";
import DeviceDetailPage from "./pages/DeviceDetailPage";
import AlertsPage from "./pages/AlertsPage";
import SoftwarePolicyPage from "./pages/SoftwarePolicyPage";
import TeamPage from "./pages/TeamPage";
import OrgSettingsPage from "./pages/OrgSettingsPage";
import ProfilePage from "./pages/ProfilePage";
import AuditPage from "./pages/AuditPage";
import LandingPage from "./pages/LandingPage";
import DeviceGroupsPage from "./pages/DeviceGroupsPage";
import CommandHistoryPage from "./pages/CommandHistoryPage";

import "./App.css";

function ProtectedRoute({ children }) {
  const { isAuthenticated, initializing } = useAuth();
  if (initializing) {
    return (
      <div className="h-screen w-screen flex items-center justify-center">
        <div className="h-8 w-8 rounded-full border-2 border-primary/30 border-t-primary animate-spin" />
      </div>
    );
  }
  if (!isAuthenticated) return <Navigate to="/login" replace />;
  return children;
}

function PublicOnly({ children }) {
  const { isAuthenticated, initializing } = useAuth();
  if (initializing) return null;
  if (isAuthenticated) return <Navigate to="/app/dashboard" replace />;
  return children;
}

export default function App() {
  return (
    <ThemeProvider>
      <BrowserRouter>
        <AuthProvider>
          <DashboardSocketProvider>
            <Toaster theme="dark" position="top-right" richColors closeButton />
            <Routes>
              <Route path="/" element={<LandingPage />} />
              <Route
                path="/login"
                element={
                  <PublicOnly>
                    <LoginPage />
                  </PublicOnly>
                }
              />
              <Route
                path="/signup"
                element={
                  <PublicOnly>
                    <SignupPage />
                  </PublicOnly>
                }
              />
              <Route path="/invite/:token" element={<AcceptInvitePage />} />

              <Route
                path="/app"
                element={
                  <ProtectedRoute>
                    <AppShell />
                  </ProtectedRoute>
                }
              >
                <Route index element={<Navigate to="dashboard" replace />} />
                <Route path="dashboard" element={<DashboardPage />} />
                <Route path="devices" element={<DevicesPage />} />
                <Route path="devices/:deviceId" element={<DeviceDetailPage />} />
                <Route path="groups" element={<DeviceGroupsPage />} />
                <Route path="commands" element={<CommandHistoryPage />} />
                <Route path="alerts" element={<AlertsPage />} />
                <Route path="software" element={<SoftwarePolicyPage />} />
                <Route path="team" element={<TeamPage />} />
                <Route path="settings/organization" element={<OrgSettingsPage />} />
                <Route path="settings/profile" element={<ProfilePage />} />
                <Route path="audit" element={<AuditPage />} />
              </Route>

              <Route path="*" element={<Navigate to="/" replace />} />
            </Routes>
          </DashboardSocketProvider>
        </AuthProvider>
      </BrowserRouter>
    </ThemeProvider>
  );
}
