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
import ConfirmDialog from "../components/common/ConfirmDialog";
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

  const [deleteError, setDeleteError] = useState("");
  const [cameraPendingDelete, setCameraPendingDelete] = useState(null);
  const [deleting, setDeleting] = useState(false);
  const [thermalBusy, setThermalBusy] = useState(false);
  const [notice, setNotice] = useState(null);

  const filteredCameras = useMemo(() => {
    return cameras.filter((camera) => {
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
  }, [cameras, search, status, sector]);

  function handleAddCamera() {
    setEditingCamera(null);
    setShowForm(true);
  }

  function handleEditCamera() {
    if (!selectedCamera) return;

    setEditingCamera(selectedCamera);
    setShowForm(true);
  }

  async function changeGeneratedThermal(enable) {
    if (!selectedCamera) return;
    setThermalBusy(true);
    setNotice(null);
    try {
      const updated = enable
        ? await cameraService.generateThermal(selectedCamera.id)
        : await cameraService.removeGeneratedThermal(selectedCamera.id);
      await refetch();
      setSelectedCamera(updated);
      setNotice({
        tone: "info",
        text: enable
          ? "Thermal view enabled -- it appears on Live Surveillance within a few seconds."
          : "Thermal view removed.",
      });
    } catch (err) {
      setNotice({ tone: "danger", text: err.detail || err.message || "Couldn't change the thermal view." });
    } finally {
      setThermalBusy(false);
    }
  }

  async function confirmDeleteCamera() {
    const camera = cameraPendingDelete;
    if (!camera) return;
    setDeleting(true);
    setDeleteError("");
    try {
      await cameraService.delete(camera.id);
      if (selectedCamera?.id === camera.id) setSelectedCamera(null);
      await refetch();
      setCameraPendingDelete(null);
    } catch (err) {
      setDeleteError(err.detail || err.message || `Failed to delete ${camera.name}.`);
    } finally {
      setDeleting(false);
    }
  }

  async function handleSaveCamera(formData) {
    if (editingCamera) {
      const updated = await cameraService.update(editingCamera.id, {
        name: formData.name,
        location: formData.location,
        sector: formData.sector || undefined,
      });
      setSelectedCamera((current) => (current?.id === updated.id ? updated : current));
      await refetch();
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

      // Optional extra: give a plain video camera a simulated thermal view.
      // Failing here must not undo the camera that was just created, so it
      // surfaces as a notice rather than an error on the form.
      if (formData.type === "file" && formData.generateThermal && formData.file) {
        try {
          await cameraService.generateThermal(created.id);
        } catch (err) {
          setNotice({
            tone: "danger",
            text: `Camera created, but the thermal view couldn't be generated: ${err.detail || err.message}`,
          });
        }
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

      {notice && (
        <div
          role="status"
          className={`mb-3 flex items-center justify-between border px-3 py-2 text-xs ${
            notice.tone === "danger" ? "border-danger/40 bg-danger/10 text-danger" : "border-info/40 bg-info/10 text-info"
          }`}
        >
          <span>{notice.text}</span>
          <button type="button" onClick={() => setNotice(null)} className="ml-3 font-semibold hover:text-primary">
            Dismiss
          </button>
        </div>
      )}

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
            {cameras.filter((c) => c.status === "online").length} Online
          </Badge>

          <Badge tone="warning">
            {cameras.filter((c) => c.status === "warning").length} Warning
          </Badge>

          <Badge tone="offline">
            {cameras.filter((c) => c.status === "offline").length} Offline
          </Badge>
        </div>
      </div>

      {deleteError && (
        <p className="mb-3 border border-danger/40 bg-danger/10 px-3 py-2 text-xs text-danger">
          {deleteError}
        </p>
      )}

      {isLoading ? (
        <div className="panel p-10 text-center text-xs text-muted">Loading cameras...</div>
      ) : error ? (
        <div className="panel p-10 text-center text-xs text-danger">Failed to load cameras.</div>
      ) : (
        <CameraTable
          cameras={filteredCameras}
          onSelect={setSelectedCamera}
          onEdit={(camera) => {
            setSelectedCamera(camera);
            setEditingCamera(camera);
            setShowForm(true);
          }}
          onDelete={setCameraPendingDelete}
        />
      )}

      {selectedCamera && (
        <CameraConfig
            camera={selectedCamera}
            onClose={() => setSelectedCamera(null)}
            onEdit={handleEditCamera}
            onDelete={() => setCameraPendingDelete(selectedCamera)}
            onConfigureDetection={() => setShowDetectionConfig(true)}
            onConfigureFence={() => setShowFenceConfig(true)}
            onConfigureCalibration={() => setShowCalibrationConfig(true)}
            onGenerateThermal={() => changeGeneratedThermal(true)}
            onRemoveThermal={() => changeGeneratedThermal(false)}
            thermalBusy={thermalBusy}
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

      {cameraPendingDelete && (
        <ConfirmDialog
          open
          title={`Delete "${cameraPendingDelete.name}"?`}
          message={`This permanently removes ${cameraPendingDelete.id} and stops its stream. This cannot be undone.`}
          confirmLabel={deleting ? "Deleting..." : "Delete"}
          onConfirm={confirmDeleteCamera}
          onCancel={() => setCameraPendingDelete(null)}
        />
      )}
    </div>
  );
}
