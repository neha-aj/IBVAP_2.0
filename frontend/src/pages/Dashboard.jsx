import { useEffect, useState } from "react";
import PageHeader from "../components/layout/PageHeader";
import StatCard from "../components/dashboard/StatCard";
import CameraStatus from "../components/dashboard/CameraStatus";
import RecentAlerts from "../components/dashboard/RecentAlerts";
import ActivityOverview from "../components/dashboard/ActivityOverview";
import { useCameras } from "../hooks/useCameras";
import { useAlerts } from "../hooks/useAlerts";
import { analyticsService } from "../services/analyticsService";

export default function Dashboard() {
  const { cameras } = useCameras();
  const { alerts } = useAlerts();
  const [stats, setStats] = useState(null);
  const [activity, setActivity] = useState([]);

  useEffect(() => {
    let cancelled = false;
    analyticsService.getDashboardStats().then((data) => !cancelled && setStats(data));
    analyticsService.getActivityOverview("today").then((data) => !cancelled && setActivity(data));
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <>
      <PageHeader
        title="Command Dashboard"
        subtitle="Real-time overview of border surveillance infrastructure"
      />
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-6">
        <StatCard
          label="Active Cameras"
          value={stats ? stats.activeCameras : "—"}
          detail={stats ? `of ${stats.totalCameras} deployed` : ""}
        />
        <StatCard
          label="Cameras Offline"
          value={stats ? stats.camerasOffline : "—"}
          detail="needs attention"
          accent="text-danger"
        />
        <StatCard
          label="Active Alerts"
          value={stats ? stats.activeAlerts : "—"}
          detail={stats ? `${stats.criticalAlerts} critical` : ""}
          accent="text-danger"
        />
        <StatCard
          label="People Detected"
          value={stats ? stats.peopleDetectedToday : "—"}
          detail="today"
        />
        <StatCard
          label="Vehicles Detected"
          value={stats ? stats.vehiclesDetectedToday : "—"}
          detail="today"
        />
        <StatCard
          label="Events Today"
          value={stats ? stats.eventsToday : "—"}
          detail={stats && stats.eventsTodayDeltaPct != null ? `${stats.eventsTodayDeltaPct > 0 ? "+" : ""}${stats.eventsTodayDeltaPct}% vs avg` : ""}
        />
      </div>
      <div className="mt-5 grid gap-5 xl:grid-cols-2">
        <ActivityOverview data={activity} />
        <div className="grid gap-5">
          <CameraStatus cameras={cameras} />
          <RecentAlerts alerts={alerts} />
        </div>
      </div>
    </>
  );
}
