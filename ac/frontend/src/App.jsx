import React from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import { useAuth } from "./state/AuthContext.jsx";
import Shell from "./components/Shell.jsx";
import Login from "./pages/Login.jsx";
import Overview from "./pages/Overview.jsx";
import Sensors from "./pages/Sensors.jsx";
import Trust from "./pages/Trust.jsx";
import MonthlyRequest from "./pages/MonthlyRequest.jsx";
import InfoRequests from "./pages/InfoRequests.jsx";
import Verification from "./pages/Verification.jsx";
import Audit from "./pages/Audit.jsx";
import Credits from "./pages/Credits.jsx";
import Admin from "./pages/Admin.jsx";
import { Loading } from "./components/UI.jsx";

export default function App() {
  const { user, ready } = useAuth();
  if (!ready) return <Loading text="Starting AgentCarbon…" />;
  if (!user) return <Login />;
  const home = user.role === "ADMIN" ? <Admin /> : user.role === "CREDIT_BUYER" ? <Credits /> : <Overview />;
  const operator = user.role === "PLANT_OPERATOR", auditor = user.role === "AUDITOR";
  const dataRole = operator || auditor;
  return (
    <Routes>
      <Route element={<Shell />}>
        <Route index element={home} />
        {dataRole && <Route path="sensors" element={<Sensors />} />}
        {dataRole && <Route path="trust" element={<Trust />} />}
        {dataRole && <Route path="inbox" element={<InfoRequests />} />}
        {operator && <Route path="request" element={<MonthlyRequest />} />}
        {auditor && <Route path="verify" element={<Verification />} />}
        {auditor && <Route path="audit" element={<Audit />} />}
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}
