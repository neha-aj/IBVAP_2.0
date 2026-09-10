import { useEffect, useState } from "react";
import PageHeader from "../components/layout/PageHeader";
import ActivityChart from "../components/analytics/ActivityChart";
import AlertChart from "../components/analytics/AlertChart";
import CameraAnalytics from "../components/analytics/CameraAnalytics";
import KpiCards from "../components/analytics/KpiCards";
import EventsByCameraChart from "../components/analytics/EventsByCameraChart";
import PpeComplianceChart from "../components/analytics/PpeComplianceChart";
import DirectionFlowChart from "../components/analytics/DirectionFlowChart";
import { analyticsService } from "../services/analyticsService";
import { cameraService } from "../services/cameraService";

export default function Analytics() {
  const [activityWeekly, setActivityWeekly] = useState([]);
  const [alertsByType, setAlertsByType] = useState([]);
  const [cameraUptime, setCameraUptime] = useState([]);
  const [eventsByCamera, setEventsByCamera] = useState([]);
  const [ppeCompliance, setPpeCompliance] = useState([]);
  const [dashboardStats, setDashboardStats] = useState(null);
  const [cameras, setCameras] = useState([]);
  const [directionFlow, setDirectionFlow] = useState([]);

  // Drill-down: clicking a bar in "Events by camera" narrows the PPE
  // compliance panel to that same camera (by name -- both endpoints key
  // on camera_name, not id).
  const [selectedCameraName, setSelectedCameraName] = useState(null);
  // Independent filter: which camera the direction-flow chart is scoped
  // to (by id -- that endpoint takes camera_id, unlike the two above).
  const [directionCameraId, setDirectionCameraId] = useState(null);

  useEffect(() => {
    let cancelled = false;
    analyticsService.getActivityWeekly().then((data) => !cancelled && setActivityWeekly(data));
    analyticsService.getAlertsByType().then((data) => !cancelled && setAlertsByType(data));
    analyticsService.getCameraUptime().then((data) => !cancelled && setCameraUptime(data));
    analyticsService.getEventsByCamera().then((data) => !cancelled && setEventsByCamera(data));
    analyticsService.getPpeCompliance().then((data) => !cancelled && setPpeCompliance(data));
    analyticsService.getDashboardStats().then((data) => !cancelled && setDashboardStats(data));
    cameraService.getAll().then((data) => !cancelled && setCameras(data));
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    analyticsService.getDirectionFlow(directionCameraId).then((data) => !cancelled && setDirectionFlow(data));
    return () => {
      cancelled = true;
    };
  }, [directionCameraId]);

  const totalEvents = eventsByCamera.reduce((sum, e) => sum + e.count, 0);
  const totalAlerts = alertsByType.reduce((sum, a) => sum + a.value, 0);
  const avgUptime = cameraUptime.length
    ? Math.round((cameraUptime.reduce((sum, c) => sum + c.value, 0) / cameraUptime.length) * 10) / 10
    : 0;
  const totalPpeViolations = ppeCompliance.reduce((sum, p) => sum + p.count, 0);

  return (
    <>
      <PageHeader
        title="Operational Analytics"
        subtitle="Aggregate surveillance activity across all sectors"
      />
      <div className="mb-5">
        <KpiCards
          totalEvents={totalEvents}
          totalAlerts={totalAlerts}
          avgUptime={avgUptime}
          ppeViolations={totalPpeViolations}
        />
      </div>
      <div className="grid gap-5 lg:grid-cols-2">
        <ActivityChart data={activityWeekly} />
        <AlertChart data={alertsByType} />
        <CameraAnalytics data={cameraUptime} todayStats={dashboardStats} />
        <DirectionFlowChart
          data={directionFlow}
          cameras={cameras}
          selectedCamera={directionCameraId}
          onSelectCamera={setDirectionCameraId}
        />
        <EventsByCameraChart
          data={eventsByCamera}
          selected={selectedCameraName}
          onSelect={setSelectedCameraName}
        />
        <PpeComplianceChart data={ppeCompliance} filterCamera={selectedCameraName} />
      </div>
    </>
  );
}
