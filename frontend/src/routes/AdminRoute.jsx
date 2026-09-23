import { Navigate } from "react-router-dom";
import { useAuth } from "../hooks/useAuth";

// Wraps an admin-only page (currently just Cameras management). Only ever
// rendered inside ProtectedRoute's <Outlet/>, so `status` is already
// "authenticated" by the time this runs -- this adds just the role check.
// A non-admin who navigates straight to the URL is redirected, the same
// as if the nav link were never shown.
export default function AdminRoute({ children }) {
  const { user } = useAuth();
  if (user?.role !== "admin") return <Navigate to="/" replace />;
  return children;
}
