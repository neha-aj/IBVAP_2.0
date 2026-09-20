import { useCallback, useEffect, useRef, useState } from 'react';
import { Minus, Plus, RotateCcw } from 'lucide-react';

const MIN_ZOOM = 1;
const MAX_ZOOM = 8;
const BUTTON_STEP = 1.25;
const WHEEL_STEP = 1.15;
const DOUBLE_CLICK_ZOOM = 2.5;

// Keeps the zoomed content covering the viewport (no empty gaps at the
// edges): at zoom z the content is z times the viewport size, so its
// top-left offset can range from (viewport - content) up to 0.
function clampView(zoom, x, y, width, height) {
  return {
    zoom,
    x: Math.min(0, Math.max(width - width * zoom, x)),
    y: Math.min(0, Math.max(height - height * zoom, y)),
  };
}

// Wraps any content (here: a live camera tile with its detection overlay) in
// a zoomable, pannable frame -- mouse wheel zooms toward the cursor, drag
// pans, double-click toggles a close-up, and +/-/0 keys plus the on-screen
// buttons work too. The content is scaled as a whole, so detection boxes stay
// aligned with the video at any zoom.
export default function ZoomPanViewport({ children, className = '' }) {
  const viewportRef = useRef(null);
  const dragRef = useRef(null);
  const [view, setView] = useState({ zoom: 1, x: 0, y: 0 });
  const [dragging, setDragging] = useState(false);

  // Zoom to `nextZoom(previousZoom)` keeping the point (cx, cy) -- in
  // viewport pixels -- fixed on screen.
  const zoomAt = useCallback((nextZoom, cx, cy) => {
    const el = viewportRef.current;
    if (!el) return;
    const { width, height } = el.getBoundingClientRect();
    setView((prev) => {
      const zoom = Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, nextZoom(prev.zoom)));
      const ratio = zoom / prev.zoom;
      return clampView(zoom, cx - (cx - prev.x) * ratio, cy - (cy - prev.y) * ratio, width, height);
    });
  }, []);

  const zoomAtCenter = useCallback(
    (nextZoom) => {
      const el = viewportRef.current;
      if (!el) return;
      const { width, height } = el.getBoundingClientRect();
      zoomAt(nextZoom, width / 2, height / 2);
    },
    [zoomAt]
  );

  const reset = useCallback(() => setView({ zoom: 1, x: 0, y: 0 }), []);

  // Wheel needs a non-passive listener so it can stop the page scrolling
  // behind the modal while zooming.
  useEffect(() => {
    const el = viewportRef.current;
    if (!el) return undefined;
    function onWheel(event) {
      event.preventDefault();
      const rect = el.getBoundingClientRect();
      const factor = event.deltaY < 0 ? WHEEL_STEP : 1 / WHEEL_STEP;
      zoomAt((z) => z * factor, event.clientX - rect.left, event.clientY - rect.top);
    }
    el.addEventListener('wheel', onWheel, { passive: false });
    return () => el.removeEventListener('wheel', onWheel);
  }, [zoomAt]);

  useEffect(() => {
    function onKeyDown(event) {
      if (event.target instanceof HTMLElement && ['INPUT', 'TEXTAREA', 'SELECT'].includes(event.target.tagName)) return;
      if (event.key === '+' || event.key === '=') zoomAtCenter((z) => z * BUTTON_STEP);
      else if (event.key === '-' || event.key === '_') zoomAtCenter((z) => z / BUTTON_STEP);
      else if (event.key === '0') reset();
    }
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [zoomAtCenter, reset]);

  function onPointerDown(event) {
    if (view.zoom <= 1 || event.button !== 0) return;
    dragRef.current = { startX: event.clientX, startY: event.clientY, originX: view.x, originY: view.y };
    setDragging(true);
    event.currentTarget.setPointerCapture(event.pointerId);
  }

  function onPointerMove(event) {
    const drag = dragRef.current;
    const el = viewportRef.current;
    if (!drag || !el) return;
    const { width, height } = el.getBoundingClientRect();
    setView((prev) =>
      clampView(prev.zoom, drag.originX + event.clientX - drag.startX, drag.originY + event.clientY - drag.startY, width, height)
    );
  }

  function endDrag(event) {
    if (!dragRef.current) return;
    dragRef.current = null;
    setDragging(false);
    if (event.currentTarget.hasPointerCapture?.(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId);
    }
  }

  function onDoubleClick(event) {
    if (view.zoom > 1) {
      reset();
      return;
    }
    const rect = viewportRef.current.getBoundingClientRect();
    zoomAt(() => DOUBLE_CLICK_ZOOM, event.clientX - rect.left, event.clientY - rect.top);
  }

  const zoomed = view.zoom > 1;

  return (
    <div
      ref={viewportRef}
      className={`relative select-none overflow-hidden bg-[#070B10] ${className}`}
      style={{ touchAction: 'none', cursor: zoomed ? (dragging ? 'grabbing' : 'grab') : 'zoom-in' }}
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={endDrag}
      onPointerCancel={endDrag}
      onDoubleClick={onDoubleClick}
    >
      <div
        className="h-full w-full"
        style={{
          transform: `translate(${view.x}px, ${view.y}px) scale(${view.zoom})`,
          transformOrigin: '0 0',
          willChange: 'transform',
        }}
      >
        {children}
      </div>

      <div
        className="absolute bottom-3 right-3 flex items-center border border-line bg-ink/85 text-secondary backdrop-blur"
        style={{ cursor: 'default' }}
        onPointerDown={(e) => e.stopPropagation()}
        onDoubleClick={(e) => e.stopPropagation()}
      >
        <button
          type="button"
          aria-label="Zoom out"
          title="Zoom out (-)"
          disabled={view.zoom <= MIN_ZOOM}
          onClick={() => zoomAtCenter((z) => z / BUTTON_STEP)}
          className="p-2 hover:text-primary disabled:opacity-40"
        >
          <Minus size={14} />
        </button>
        <span className="min-w-12 text-center font-mono text-[11px] text-primary" aria-live="polite">
          {Math.round(view.zoom * 100)}%
        </span>
        <button
          type="button"
          aria-label="Zoom in"
          title="Zoom in (+)"
          disabled={view.zoom >= MAX_ZOOM}
          onClick={() => zoomAtCenter((z) => z * BUTTON_STEP)}
          className="p-2 hover:text-primary disabled:opacity-40"
        >
          <Plus size={14} />
        </button>
        <button
          type="button"
          aria-label="Reset zoom"
          title="Reset (0)"
          disabled={!zoomed}
          onClick={reset}
          className="border-l border-line p-2 hover:text-primary disabled:opacity-40"
        >
          <RotateCcw size={14} />
        </button>
      </div>

      {!zoomed && (
        <p className="pointer-events-none absolute right-3 top-3 text-[10px] text-muted">
          Scroll or double-click to zoom
        </p>
      )}
    </div>
  );
}
