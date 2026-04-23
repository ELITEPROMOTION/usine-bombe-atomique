import { Navigate, Outlet, useLocation } from "react-router-dom";
import { useAuth } from "@/stores/authStore";

export function AuthGuard() {
  const token = useAuth((s) => s.token);
  const loc = useLocation();
  if (!token) return <Navigate to="/login" replace state={{ from: loc.pathname }} />;
  return <Outlet />;
}
