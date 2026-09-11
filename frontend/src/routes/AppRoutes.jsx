import { Routes, Route, Navigate } from "react-router-dom";
import DashboardLayout from "../layouts/DashboardLayout";
import ProtectedRoute from "./ProtectedRoute";
import Login from "../pages/Login";
import Dashboard from "../pages/Dashboard";
import Surveillance from "../pages/Surveillance";
import Cameras from "../pages/Cameras";
import Alerts from "../pages/Alerts";
import Events from "../pages/Events";
import Evidence from "../pages/Evidence";
import Analytics from "../pages/Analytics";
import LicensePlates from "../pages/LicensePlates";
import PersonSearch from "../pages/PersonSearch";
import Settings from "../pages/Settings";

const page = (Component) => (
  <DashboardLayout>
    <Component />
  </DashboardLayout>
);

export default function AppRoutes() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />

      <Route element={<ProtectedRoute />}>
        <Route path="/" element={page(Dashboard)} />
        <Route path="/surveillance" element={page(Surveillance)} />
        <Route path="/cameras" element={page(Cameras)} />
        <Route path="/alerts" element={page(Alerts)} />
        <Route path="/events" element={page(Events)} />
        <Route path="/evidence" element={page(Evidence)} />
        <Route path="/analytics" element={page(Analytics)} />
        <Route path="/anpr" element={page(LicensePlates)} />
        <Route path="/reid" element={page(PersonSearch)} />
        <Route path="/settings" element={page(Settings)} />
      </Route>

      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
