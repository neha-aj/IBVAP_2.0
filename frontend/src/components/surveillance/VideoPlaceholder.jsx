import { useState } from 'react';
import { CameraOff } from 'lucide-react';
import DetectionOverlay from './DetectionOverlay';

export default function VideoPlaceholder({ cameraName = 'CAMERA', detections = [], streamUrl = null, className = '', fill = false }) {
  const [streamFailed, setStreamFailed] = useState(false);
  const showStream = Boolean(streamUrl) && !streamFailed;

  return (
    <div className={`relative overflow-hidden bg-[#070B10] ${fill ? 'h-full w-full' : 'aspect-video'} ${className}`}>
      {showStream ? (
        <img
          src={streamUrl}
          alt={`${cameraName} live feed`}
          className="absolute inset-0 h-full w-full object-cover"
          onError={() => setStreamFailed(true)}
        />
      ) : (
        <div className="absolute inset-0 opacity-30" style={{ backgroundImage: 'linear-gradient(#202A36 1px, transparent 1px), linear-gradient(90deg, #202A36 1px, transparent 1px)', backgroundSize: '32px 32px' }} />
      )}
      <div className="absolute left-3 top-3 flex items-center gap-2 text-[10px] font-semibold tracking-wider text-primary">
        <span className="h-1.5 w-1.5 rounded-full bg-success" />LIVE <span className="text-secondary">{cameraName}</span>
      </div>
      {!showStream && (
        <div className="absolute inset-0 grid place-items-center text-center">
          <div>
            <CameraOff size={26} className="mx-auto text-muted" />
            <p className="mt-3 text-[11px] font-semibold tracking-[.18em] text-secondary">LIVE VIDEO FEED</p>
            <p className="mt-1 text-[11px] text-muted">
              {streamFailed ? 'Stream unavailable' : 'Awaiting stream connection'}
            </p>
          </div>
        </div>
      )}
      <DetectionOverlay detections={detections} />
      <div className="absolute bottom-3 left-3 font-mono text-[10px] text-secondary">
        LIVE · {new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
      </div>
    </div>
  );
}
