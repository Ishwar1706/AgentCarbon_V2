import React, { createContext, useCallback, useContext, useEffect, useState } from "react";
import { api, setToken, setUnauthorizedHandler } from "../api/client.js";
import { DEFAULT_PERIOD } from "../../lib/periods.js";

const Ctx = createContext(null);
export const useAuth = () => useContext(Ctx);
const DATA_ROLES = ["PLANT_OPERATOR", "AUDITOR"];

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [ready, setReady] = useState(false);
  const [companies, setCompanies] = useState([]);
  const [companyId, setCompanyId] = useState(localStorage.getItem("ac_company") || "");
  const [period, setPeriodState] = useState(localStorage.getItem("ac_period") || DEFAULT_PERIOD);
  const [cal, setCal] = useState(null);

  const setPeriod = (p) => { setPeriodState(p); localStorage.setItem("ac_period", p); };
  const logout = useCallback(() => { setToken(""); setUser(null); setCompanies([]); setCal(null); }, []);

  useEffect(() => {
    setUnauthorizedHandler(logout);
    api.get("/auth/me").then(setUser).catch(() => setToken("")).finally(() => setReady(true));
  }, [logout]);

  useEffect(() => {
    if (!user || !DATA_ROLES.includes(user.role)) return;
    api.get("/companies").then((list) => {
      setCompanies(list);
      const own = user.role === "PLANT_OPERATOR" ? user.company_id : null;
      setCompanyId((cur) => own || (list.some((c) => c.company_id === cur) ? cur : list[0]?.company_id || ""));
    }).catch(() => {});
  }, [user]);

  useEffect(() => { if (companyId) localStorage.setItem("ac_company", companyId); }, [companyId]);

  const year = +period.slice(0, 4);
  const refreshCalendar = useCallback(() => {
    if (!user || !companyId || !DATA_ROLES.includes(user.role)) return;
    api.get("/calendar", { company_id: companyId, year }).then(setCal).catch(() => setCal(null));
  }, [user, companyId, year]);
  useEffect(() => { refreshCalendar(); }, [refreshCalendar]);

  const login = async (email, password) => {
    const data = await api.login(email, password);
    setToken(data.access_token);
    setUser(data.user);
  };
  const company = companies.find((c) => c.company_id === companyId);
  const monthInfo = cal?.months?.find((m) => m.period === period) || null;
  return (
    <Ctx.Provider value={{ user, ready, login, logout, companies, companyId, setCompanyId, company,
                           period, setPeriod, monthInfo, refreshCalendar }}>
      {children}
    </Ctx.Provider>
  );
}
