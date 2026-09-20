import { useEffect, useState } from 'react';
import { createPortal } from 'react-dom';
import { Pause, Play, X } from 'lucide-react';
import VideoPlaceholder from './VideoPlaceholder';
import ZoomPanViewport from './ZoomPanViewport';
import Badge from '../common/Badge';
import StatusDot from '../common/StatusDot';

// Full-size viewer opened by a camera tile's expand button: the same live
// feed + detection overlay as the tile, but large and zoomable. For a 'dual'
// camera a tab switches between its RGB and thermal halves (the tile shows
// both side by side; here each gets the whole frame).
export default function CameraViewerModal({
  camera,
  detections = [],
  poses = [],
  streamUrl,
  thermalStreamUrl,
  thermalIsGenerated = false,
  paused = false,
  onTogglePause,
  onClose,
}) {
  const isDual = camera.type === 'dual';
  const [modality, setModality] = useState('rgb');
  const showingThermal = isDual && modality === 'thermal';

  useEffect(() => {
    function onKeyDown(event) {
      if (event.key === 'Escape') onClose();
    }
    window.addEventListener('keydown', onKeyDown);
    // Stop the page behind the modal scrolling while it's open.
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      window.removeEventListener('keydown', onKeyDown);
      document.body.style.overflow = previousOverflow;
    };
  }, [onClose]);

  // Portaled to <body> and click-isolated: React synthetic events bubble
  // through portals to the tile's own onClick (which selects the camera),
  // which must not fire from interacting with this modal.
  return createPortal(
    <div
      role="dialog"
      aria-modal="true"
      aria-label={`${camera.name} live view`}
      className="fixed inset-0 z-50 grid place-items-center bg-black/80 p-4"
      onClick={(e) => {
        e.stopPropagation();
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div className="panel flex max-h-full w-full max-w-6xl flex-col overflow-hidden">
        <div className="flex items-center justify-between gap-3 border-b border-line p-3">
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <StatusDot status={camera.status} />
              <h2 className="truncate text-sm font-semibold text-primary">{camera.name}</h2>
              {paused && <Badge tone="high">Paused</Badge>}
            </div>
            <p className="mt-0.5 truncate font-mono text-[10px] text-muted">
              {camera.id} · {camera.location}
            </p>
          </div>

          <div className="flex items-center gap-2">
            {isDual && (
              <div className="flex border border-line text-[11px] font-semibold">
                {['rgb', 'thermal'].map((m) => (
                  <button
                    key={m}
                    type="button"
                    onClick={() => setModality(m)}
                    className={`px-3 py-1.5 uppercase ${modality === m ? 'bg-info/15 text-info' : 'text-secondary hover:text-primary'}`}
                  >
                    {m}
                  </button>
                ))}
              </div>
            )}
            <button
              type="button"
              onClick={onTogglePause}
              className={`flex items-center gap-1.5 border px-3 py-1.5 text-xs font-semibold ${
                paused
                  ? 'border-success/40 bg-success/10 text-success hover:bg-success/15'
                  : 'border-line bg-panelSecondary text-secondary hover:text-primary'
              }`}
            >
              {paused ? <Play size={13} /> : <Pause size={13} />}
              {paused ? 'Resume' : 'Pause'}
            </button>
            <button
              type="button"
              aria-label="Close live view"
              onClick={onClose}
              className="p-2 text-muted hover:bg-panelSecondary hover:text-primary"
            >
              <X size={16} />
            </button>
          </div>
        </div>

        <div className="flex min-h-0 flex-1 justify-center bg-[#070B10] p-3">
          {/* Largest 16:9 frame that fits both the modal width and the
              viewport height. */}
          <div className="w-full" style={{ maxWidth: 'calc((100vh - 200px) * 16 / 9)' }}>
            <ZoomPanViewport className="aspect-video w-full">
              <VideoPlaceholder
                fill
                cameraName={showingThermal ? (thermalIsGenerated ? 'THERMAL (SIMULATED)' : 'THERMAL') : camera.id}
                detections={showingThermal && !thermalIsGenerated ? [] : detections}
                poses={showingThermal ? [] : poses}
                streamUrl={showingThermal ? thermalStreamUrl : streamUrl}
                paused={paused}
              />
            </ZoomPanViewport>
          </div>
        </div>

        {paused && (
          <p className="border-t border-line px-3 py-2 text-[11px] text-warning">
            Paused — the view is frozen and this camera is not being analysed. No detections or alerts are generated until you resume.
          </p>
        )}
      </div>
    </div>,
    document.body
  );
}
