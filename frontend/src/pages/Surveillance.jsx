import { useMemo, useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { UserRound, CarFront } from "lucide-react";
import PageHeader from "../components/layout/PageHeader";
import SurveillanceToolbar from "../components/surveillance/SurveillanceToolbar";
import CameraGrid from "../components/surveillance/CameraGrid";
import DetectionSummary from "../components/surveillance/DetectionSummary";
import ActiveEvents from "../components/surveillance/ActiveEvents";
import CameraDetails from "../components/surveillance/CameraDetails";
import { useCameras } from "../hooks/useCameras";
import { useDetections } from "../hooks/useDetections";
import { usePoses } from "../hooks/usePoses";
import { useCameraDailyCounts } from "../hooks/useCameraDailyCounts";

export default function Surveillance() {
  const { cameras } = useCameras();
  const cameraIds = useMemo(() => cameras.map((c) => c.id), [cameras]);
  const { detections } = useDetections(cameraIds);
  const { posesByCamera } = usePoses(cameraIds);
  const dailyCounts = useCameraDailyCounts();
  const [searchParams] = useSearchParams();
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("all");
  const [detection, setDetection] = useState("all");
  const [view, setView] = useState("grid");
  const [selectedCamera, setSelectedCamera] = useState(null);

  useEffect(() => {
    const cameraId = searchParams.get("camera");

    if (!cameraId) return;

    const camera = cameras.find((item) => item.id === cameraId);

    if (camera) {
      setSelectedCamera(camera);
    }
  }, [searchParams, cameras]);

  const filteredCameras = useMemo(() => {
    return cameras.filter((camera) => {
      const matchesSearch =
        camera.name.toLowerCase().includes(search.toLowerCase()) ||
        camera.id.toLowerCase().includes(search.toLowerCase()) ||
        camera.location.toLowerCase().includes(search.toLowerCase());

      const matchesStatus =
        status === "all" || camera.status === status;

      const cameraDetections = detections.filter(
        (item) => item.cameraId === camera.id
      );

      const matchesDetection =
        detection === "all" ||
        cameraDetections.some((item) => item.type === detection) ||
        (detection === "intrusion" && camera.alert === "Fence Intrusion") ||
        (detection === "anpr" && camera.alert === "ANPR");

      return matchesSearch && matchesStatus && matchesDetection;
    });
  }, [cameras, detections, search, status, detection]);

  const selectedDetections = selectedCamera
    ? detections.filter((item) => item.cameraId === selectedCamera.id)
    : [];

  const visibleIds = new Set(filteredCameras.map((c) => c.id));
  const visibleDetections = detections.filter((item) => visibleIds.has(item.cameraId));
  const totalPeople = visibleDetections.filter((d) => d.type === "person").length;
  const totalVehicles = visibleDetections.filter((d) => d.type === "vehicle").length;

  return (
    <div>
      <PageHeader
        title="Live Surveillance"
        description="Monitor connected border surveillance cameras"
      />

      <div className="mt-5">
        <SurveillanceToolbar
          search={search}
          setSearch={setSearch}
          status={status}
          setStatus={setStatus}
          detection={detection}
          setDetection={setDetection}
          view={view}
          setView={setView}
        />
      </div>

      <div className="mt-5">
        <div className="mb-3 flex items-center justify-between">
          <div>
            <p className="eyebrow">Connected Cameras</p>
            <p className="mt-1 text-xs text-secondary">
              {filteredCameras.length} of {cameras.length} cameras
            </p>
          </div>

          <div className="flex items-center gap-4 text-xs text-secondary">
            <span className="flex items-center gap-1.5"><UserRound size={14} className="text-info" /> {totalPeople} people</span>
            <span className="flex items-center gap-1.5"><CarFront size={14} className="text-info" /> {totalVehicles} vehicles</span>
          </div>
        </div>

        <CameraGrid
          cameras={filteredCameras}
          detections={detections}
          posesByCamera={posesByCamera}
          dailyCounts={dailyCounts}
          selectedCamera={selectedCamera}
          onSelect={setSelectedCamera}
          view={view}
        />
      </div>

      {selectedCamera && (
        <div className="mt-5 grid gap-4 lg:grid-cols-2">
          <DetectionSummary
            camera={selectedCamera}
            detections={selectedDetections}
          />

          <ActiveEvents camera={selectedCamera} />

          <div className="lg:col-span-2">
            <CameraDetails camera={selectedCamera} />
          </div>
        </div>
      )}
    </div>
  );
}
