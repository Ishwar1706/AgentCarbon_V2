import React, { createContext, useContext, useEffect, useState, useCallback } from "react";
import { api, setToken, setUnauthorizedHandler } from "../api/client.js";

const Ctx = createContext(null);
export const useAuth = () => useContext(Ctx);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [ready, setReady] = useState(false);
  const [companies, setCompanies] = useState([]);
  const [companyId, setCompanyId] = useState(localStorage.getItem("ac_company") || "");

  const logout = useCallback(() => {
    setToken("");
    setUser(null);
    setCompanies([]);
  }, []);

  useEffect(() => {
    setUnauthorizedHandler(logout);
    api.get("/auth/me").then(setUser).catch(() => setToken("")).finally(() => setReady(true));
  }, [logout]);

  useEffect(() => {
    if (!user) return;
    api.get("/companies").then((list) => {
      setCompanies(list);
      const own = user.role === "PLANT_OPERATOR" ? user.company_id : null;
      setCompanyId((cur) => own || (list.some((c) => c.company_id === cur) ? cur : list[0]?.company_id || ""));
    }).catch(() => {});
  }, [user]);

  useEffect(() => { if (companyId) localStorage.setItem("ac_company", companyId); }, [companyId]);

  const login = async (email, password) => {
    const data = await api.login(email, password);
    setToken(data.access_token);
    setUser(data.user);
  };
  const company = companies.find((c) => c.company_id === companyId);
  return (
    <Ctx.Provider value={{ user, ready, login, logout, companies, companyId, setCompanyId, company }}>
      {children}
    </Ctx.Provider>
  );
}
