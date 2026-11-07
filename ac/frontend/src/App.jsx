import React from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import { useAuth } from "./state/AuthContext.jsx";
import Shell from "./components/Shell.jsx";
import Login from "./pages/Login.jsx";
import Overview from "./pages/Overview.jsx";
import Sensors from "./pages/Sensors.jsx";
import Trust from "./pages/Trust.jsx";
import Claims from "./pages/Claims.jsx";
import Verification from "./pages/Verification.jsx";
import Evidence from "./pages/Evidence.jsx";
import Audit from "./pages/Audit.jsx";
import Admin from "./pages/Admin.jsx";
import { Loading } from "./components/UI.jsx";

export default function App() {
  const { user, ready } = useAuth();
  if (!ready) return <Loading text="Starting AgentCarbon…" />;
  if (!user) return <Login />;
  return (
    <Routes>
      <Route element={<Shell />}>
        <Route index element={user.role === "ADMIN" ? <Navigate to="/admin" replace /> : <Overview />} />
        <Route path="sensors" element={<Sensors />} />
        <Route path="trust" element={<Trust />} />
        <Route path="claims" element={<Claims />} />
        <Route path="verify" element={<Verification />} />
        <Route path="evidence" element={<Evidence />} />
        <Route path="audit" element={<Audit />} />
        <Route path="admin" element={<Admin />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}
