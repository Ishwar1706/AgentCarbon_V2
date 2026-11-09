const M = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
export const DEFAULT_PERIOD = "2026-05";
export const periodLabel = (p) => {
  if (!p) return "";
  const [y, m] = p.split("-");
  return `${M[+m - 1]} ${y}`;
};
export const MONTHS = M;
export const ROLE_LABEL = {
  PLANT_OPERATOR: "Plant operator", AUDITOR: "Auditor", CREDIT_BUYER: "Credit buyer", ADMIN: "Admin",
};
