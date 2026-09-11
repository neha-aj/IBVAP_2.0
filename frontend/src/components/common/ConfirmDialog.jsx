import { TriangleAlert, X } from "lucide-react";

// In-app replacement for `window.confirm()` -- native browser confirm/alert
// dialogs are silently no-op'd in some environments (automated browsers,
// certain embedded webviews, or a user who once checked Chrome's "Prevent
// this page from creating additional dialogs" box on ANY dialog, which
// then silently auto-rejects every future one for the rest of the tab's
// life) -- from the user's side that looks exactly like "I click Delete
// and nothing happens", with no error to explain why. A dialog rendered in
// the page itself can't be suppressed that way.
export default function ConfirmDialog({
  open,
  title,
  message,
  confirmLabel = "Confirm",
  tone = "danger",
  onConfirm,
  onCancel,
}) {
  if (!open) return null;

  const toneClasses =
    tone === "danger"
      ? "border-danger/40 bg-danger/10 text-danger hover:bg-danger/15"
      : "border-info bg-info/10 text-info hover:bg-info/15";

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
      <div className="panel w-full max-w-sm overflow-hidden">
        <div className="flex items-start justify-between border-b border-line p-4">
          <div className="flex items-start gap-3">
            <div className="border border-danger/40 bg-danger/10 p-2 text-danger">
              <TriangleAlert size={17} />
            </div>

            <div>
              <p className="eyebrow">Confirm</p>
              <h2 className="mt-1 text-sm font-semibold text-primary">{title}</h2>
            </div>
          </div>

          <button
            type="button"
            onClick={onCancel}
            className="p-2 text-muted hover:bg-panelSecondary hover:text-primary"
            aria-label="Cancel"
          >
            <X size={17} />
          </button>
        </div>

        <div className="p-4">
          <p className="text-xs leading-5 text-secondary">{message}</p>
        </div>

        <div className="flex justify-end gap-2 border-t border-line p-4">
          <button
            type="button"
            onClick={onCancel}
            className="border border-line bg-panelSecondary px-4 py-2 text-xs font-semibold text-secondary hover:text-primary"
          >
            Cancel
          </button>

          <button
            type="button"
            onClick={onConfirm}
            className={`border px-4 py-2 text-xs font-semibold ${toneClasses}`}
          >
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
