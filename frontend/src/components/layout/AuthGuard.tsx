import { Navigate, Outlet, useLocation } from "react-router-dom";
import { useAuth } from "@/stores/authStore";

interface Props {
  /**
   * Si fourni, restreint l'access aux tokens dont le claim `iss`
   * matche. Permet de separer admin (`uba-studio/admin`) et client
   * (`uba-studio/client`). Cf. ADR-32 + ADR-33.
   */
  requiredIssuer?: "uba-studio/admin" | "uba-studio/client";
  /**
   * Path de redirection si le token est present mais invalid issuer.
   * Defaut : `/`.
   */
  fallbackPath?: string;
}

function decodeJwtIss(token: string): string | null {
  try {
    const parts = token.split(".");
    if (parts.length !== 3) return null;
    const payload = JSON.parse(atob(parts[1].replace(/-/g, "+").replace(/_/g, "/")));
    return typeof payload.iss === "string" ? payload.iss : null;
  } catch {
    return null;
  }
}

export function AuthGuard({ requiredIssuer, fallbackPath = "/" }: Props = {}) {
  const token = useAuth((s) => s.token);
  const loc = useLocation();

  if (!token) {
    return <Navigate to="/login" replace state={{ from: loc.pathname }} />;
  }

  if (requiredIssuer) {
    const iss = decodeJwtIss(token);
    if (iss !== requiredIssuer) {
      return <Navigate to={fallbackPath} replace />;
    }
  }

  return <Outlet />;
}
