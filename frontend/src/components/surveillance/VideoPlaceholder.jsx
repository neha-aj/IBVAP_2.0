import { useEffect, useRef, useState } from 'react';
import { CameraOff, Pause, Play } from 'lucide-react';
import DetectionOverlay from './DetectionOverlay';

// allowLocalFreeze: an operator-independent "let me look at this frame"
// toggle, separate from the camera-wide Pause Camera control (which needs
// the operator role and stops analysis for everyone -- see
// hooks/usePausedCameras.js). This one is purely client-side: it never
// calls the backend, so every role can use it, and it works the same way
// whether or not the camera itself is currently paused by an operator.
export default function VideoPlaceholder({ cameraName = 'CAMERA', detections = [], poses = [], streamUrl = null, className = '', fill = false, paused = false, allowLocalFreeze = false }) {
  const [streamFailed, setStreamFailed] = useState(false);
  const [frozenFrame, setFrozenFrame] = useState(null);
  const imgRef = useRef(null);
  const showStream = Boolean(streamUrl) && !streamFailed;
  const isFrozen = allowLocalFreeze && frozenFrame !== null;

  // A different camera/stream underneath us -- stop showing a stale frozen
  // frame from whatever was on screen before.
  useEffect(() => {
    setFrozenFrame(null);
  }, [streamUrl]);

  function toggleFreeze() {
    if (isFrozen) {
      setFrozenFrame(null);
      return;
    }
    const img = imgRef.current;
    if (!img || !img.complete || img.naturalWidth === 0) return;
    const canvas = document.createElement('canvas');
    canvas.width = img.naturalWidth;
    canvas.height = img.naturalHeight;
    canvas.getContext('2d').drawImage(img, 0, 0);
    try {
      // Capturing a still frame (rather than just hiding the <img>) so the
      // live multipart stream itself is dropped while frozen, instead of
      // still downloading in the background unseen. The stream is a
      // different origin than this dev server, so this only works because
      // of crossOrigin="anonymous" above plus the gateway's matching CORS
      // header on /stream/ -- without both, the canvas is tainted and this
      // throws instead of silently failing.
      setFrozenFrame(canvas.toDataURL('image/jpeg', 0.92));
    } catch {
      // Fails closed: stay live rather than show a broken frozen state.
    }
  }

  return (
    <div className={`relative overflow-hidden bg-[#070B10] ${fill ? 'h-full w-full' : 'aspect-video'} ${className}`}>
      {showStream ? (
        <img
          ref={imgRef}
          src={isFrozen ? frozenFrame : streamUrl}
          alt={`${cameraName} live feed`}
          className="absolute inset-0 h-full w-full object-cover"
          onError={() => setStreamFailed(true)}
          // Needed for canvas capture in toggleFreeze() below -- without
          // this, drawing a cross-origin frame taints the canvas and
          // exporting it throws, even though the gateway now sends the
          // matching CORS header. Harmless when allowLocalFreeze is off.
          crossOrigin={allowLocalFreeze ? 'anonymous' : undefined}
        />
      ) : (
        <div className="absolute inset-0 opacity-30" style={{ backgroundImage: 'linear-gradient(#202A36 1px, transparent 1px), linear-gradient(90deg, #202A36 1px, transparent 1px)', backgroundSize: '32px 32px' }} />
      )}
      <div className="absolute left-3 top-3 flex items-center gap-2 text-[10px] font-semibold tracking-wider text-primary">
        {paused ? (
          <span className="h-1.5 w-1.5 rounded-full bg-warning" />
        ) : (
          <span className="h-1.5 w-1.5 rounded-full bg-success" />
        )}
        {paused ? 'PAUSED' : 'LIVE'} <span className="text-secondary">{cameraName}</span>
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
      {/* A paused camera isn't being analysed, so any boxes still held from
          before the pause would be stale -- show none. Same reasoning for a
          locally frozen frame: it's a still image now, new detections from
          the live feed would no longer line up with it. */}
      {!paused && !isFrozen && <DetectionOverlay detections={detections} poses={poses} />}
      {paused && (
        <div className="pointer-events-none absolute inset-0 grid place-items-center bg-black/25">
          <div className="flex items-center gap-2 border border-warning/50 bg-ink/80 px-3 py-1.5 text-[11px] font-semibold tracking-[.14em] text-warning">
            <Pause size={13} /> PAUSED · ANALYSIS OFF
          </div>
        </div>
      )}
      {allowLocalFreeze && showStream && (
        <button
          type="button"
          onClick={toggleFreeze}
          className={`absolute bottom-3 right-3 flex items-center gap-1.5 border px-2.5 py-1.5 text-[11px] font-semibold ${
            isFrozen
              ? 'border-info/40 bg-info/10 text-info hover:bg-info/15'
              : 'border-line bg-ink/70 text-secondary hover:text-primary'
          }`}
          title={isFrozen ? 'Resume watching the live feed' : 'Freeze this frame for a closer look (only for you)'}
        >
          {isFrozen ? <Play size={12} /> : <Pause size={12} />}
          {isFrozen ? 'Resume' : 'Freeze'}
        </button>
      )}
      <div className="absolute bottom-3 left-3 font-mono text-[10px] text-secondary">
        {isFrozen ? 'FROZEN (LOCAL)' : paused ? 'PAUSED' : `LIVE · ${new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}`}
      </div>
    </div>
  );
}
