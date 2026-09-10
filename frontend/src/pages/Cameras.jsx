import { useMemo, useState } from "react";
import { Plus } from "lucide-react";

import PageHeader from "../components/layout/PageHeader";
import CameraFilters from "../components/cameras/CameraFilters";
import CameraTable from "../components/cameras/CameraTable";
import CameraConfig from "../components/cameras/CameraConfig";
import DetectionConfig from "../components/cameras/DetectionConfig";
import VirtualFenceConfig from "../components/cameras/VirtualFenceConfig";
import CalibrationConfig from "../components/cameras/CalibrationConfig";
import CameraForm from "../components/cameras/CameraForm";
import Badge from "../components/common/Badge";
import { useCameras } from "../hooks/useCameras";
import { cameraService } from "../services/cameraService";

export default function Cameras() {
  const { cameras, isLoading, error, refetch } = useCameras();

  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("all");
  const [sector, setSector] = useState("all");

  const [selectedCamera, setSelectedCamera] = useState(null);

  const [showForm, setShowForm] = useState(false);
  const [editingCamera, setEditingCamera] = useState(null);

  const [showDetectionConfig, setShowDetectionConfig] = useState(false);
  const [showFenceConfig, setShowFenceConfig] = useState(false);
  const [showCalibrationConfig, setShowCalibrationConfig] = useState(false);

  // Local cosmetic overlay for edits -- camera-service does have a real
  // PUT /cameras/{id}, but wiring it wasn't part of this pass; edits show
  // immediately here without persisting server-side.
  const [localEdits, setLocalEdits] = useState({});
  const displayedCameras = cameras.map((camera) => ({ ...camera, ...localEdits[camera.id] }));

  const filteredCameras = useMemo(() => {
    return displayedCameras.filter((camera) => {
      const query = search.toLowerCase();

      const matchesSearch =
        camera.name.toLowerCase().includes(query) ||
        camera.id.toLowerCase().includes(query) ||
        camera.location.toLowerCase().includes(query);

      const matchesStatus =
        status === "all" || camera.status === status;

      const matchesSector =
        sector === "all" || camera.sector === sector;

      return matchesSearch && matchesStatus && matchesSector;
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cameras, localEdits, search, status, sector]);

  function handleAddCamera() {
    setEditingCamera(null);
    setShowForm(true);
  }

  function handleEditCamera() {
    if (!selectedCamera) return;

    setEditingCamera(selectedCamera);
    setShowForm(true);
  }

  async function handleSaveCamera(formData) {
    if (editingCamera) {
      setLocalEdits((current) => ({
        ...current,
        [editingCamera.id]: { name: formData.name, location: formData.location, sector: formData.sector },
      }));
      setSelectedCamera((current) =>
        current ? { ...current, name: formData.name, location: formData.location, sector: formData.sector } : null
      );
    } else {
      // M11: 'thermal'/'dual' are upload-based too (see CameraForm's own
      // UPLOAD_BASED_TYPES comment) -- no sourceUrl sent up front for any
      // of them, filled in by the upload call(s) below instead.
      const isUploadBased = formData.type === "file" || formData.type === "thermal" || formData.type === "dual";
      const created = await cameraService.create({
        name: formData.name,
        location: formData.location,
        sector: formData.sector || undefined,
        type: formData.type,
        sourceUrl: isUploadBased ? undefined : formData.sourceUrl,
      });

      if (isUploadBased && formData.file) {
        await cameraService.uploadVideo(created.id, formData.file, formData.type === "dual" ? "rgb" : undefined);
      }
      if (formData.type === "dual" && formData.thermalFile) {
        await cameraService.uploadVideo(created.id, formData.thermalFile, "thermal");
      }

      await refetch();
      setSelectedCamera(created);
    }

    setShowForm(false);
    setEditingCamera(null);
  }

  return (
    <div>
      <PageHeader
        title="Camera Management"
        subtitle="Inventory and health of deployed surveillance devices"
        action={
          <button
            onClick={handleAddCamera}
            className="flex items-center gap-2 border border-info bg-info/10 px-3 py-2 text-xs font-semibold text-info hover:bg-info/15"
          >
            <Plus size={15} />
            Add Camera
          </button>
        }
      />

      <CameraFilters
        search={search}
        setSearch={setSearch}
        status={status}
        setStatus={setStatus}
        sector={sector}
        setSector={setSector}
      />

      <div className="mb-3 flex items-center justify-between">
        <div>
          <p className="text-xs font-semibold text-primary">
            {filteredCameras.length} Cameras
          </p>

          <p className="mt-1 text-[11px] text-muted">
            Select a camera to view configuration details
          </p>
        </div>

        <div className="flex items-center gap-2">
          <Badge tone="online">
            {displayedCameras.filter((c) => c.status === "online").length} Online
          </Badge>

          <Badge tone="warning">
            {displayedCameras.filter((c) => c.status === "warning").length} Warning
          </Badge>

          <Badge tone="offline">
            {displayedCameras.filter((c) => c.status === "offline").length} Offline
          </Badge>
        </div>
      </div>

      {isLoading ? (
        <div className="panel p-10 text-center text-xs text-muted">Loading cameras...</div>
      ) : error ? (
        <div className="panel p-10 text-center text-xs text-danger">Failed to load cameras.</div>
      ) : (
        <CameraTable cameras={filteredCameras} onSelect={setSelectedCamera} />
      )}

      {selectedCamera && (
        <CameraConfig
            camera={selectedCamera}
            onClose={() => setSelectedCamera(null)}
            onEdit={handleEditCamera}
            onConfigureDetection={() => setShowDetectionConfig(true)}
            onConfigureFence={() => setShowFenceConfig(true)}
            onConfigureCalibration={() => setShowCalibrationConfig(true)}
        />
        )}

        {showDetectionConfig && selectedCamera && (
            <DetectionConfig
                camera={selectedCamera}
                onClose={() => setShowDetectionConfig(false)}
            />
        )}

        {showFenceConfig && selectedCamera && (
            <VirtualFenceConfig
                camera={selectedCamera}
                onClose={() => setShowFenceConfig(false)}
            />
        )}

        {showCalibrationConfig && selectedCamera && (
            <CalibrationConfig
                camera={selectedCamera}
                onClose={() => setShowCalibrationConfig(false)}
            />
        )}

      {showForm && (
        <CameraForm
          camera={editingCamera}
          onSave={handleSaveCamera}
          onClose={() => {
            setShowForm(false);
            setEditingCamera(null);
          }}
        />
      )}
    </div>
  );
}
