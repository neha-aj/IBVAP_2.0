import { Navigate, Outlet, useLocation } from "react-router-dom";
import { useAuth } from "../hooks/useAuth";

export default function ProtectedRoute() {
  const { status } = useAuth();
  const location = useLocation();

  if (status === "loading") {
    return <div className="grid h-screen place-items-center bg-ink text-xs text-muted">Loading...</div>;
  }

  if (status === "unauthenticated") {
    return <Navigate to="/login" state={{ from: location }} replace />;
  }

  return <Outlet />;
}
