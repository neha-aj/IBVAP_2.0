import { useState } from "react";
import { Download, MapPin, ShieldCheck } from "lucide-react";

import Badge from "../common/Badge";
import { GATEWAY_ORIGIN } from "../../services/api";

// M25 tamper-evidence: maps a verify response's `status` to the closest
// existing Badge tone (see Badge.jsx) rather than adding new ones.
const VERIFY_STATUS_TONE = {
  verified: "online",
  tampered: "offline",
  signature_invalid: "offline",
  file_missing: "offline",
  not_signed: "neutral",
};

const VERIFY_STATUS_LABEL = {
  verified: "Verified",
  tampered: "Tampered",
  signature_invalid: "Signature Invalid",
  file_missing: "File Missing",
  not_signed: "Not Signed",
};

export default function EvidenceDetail({ evidence }) {
  const [verification, setVerification] = useState(null);
  const [isVerifying, setIsVerifying] = useState(false);
  const [verifyError, setVerifyError] = useState(null);

  const exportUrl = evidence?.recordingUrl
    ? `${GATEWAY_ORIGIN}${evidence.recordingUrl}&download=true`
    : undefined;

  // Reset any previous check when the selected evidence item changes, so a
  // stale "Verified" badge never appears to describe a different clip.
  const evidenceId = evidence?.id;
  if (verification && verification.evidenceId !== evidenceId) {
    setVerification(null);
    setVerifyError(null);
  }

  async function handleVerify() {
    if (!evidence?.recordingVerifyUrl) return;
    setIsVerifying(true);
    setVerifyError(null);
    try {
      const response = await fetch(`${GATEWAY_ORIGIN}${evidence.recordingVerifyUrl}`);
      if (!response.ok) throw new Error(`Verify request failed (${response.status})`);
      const result = await response.json();
      setVerification({ ...result, evidenceId });
    } catch (err) {
      setVerifyError(err);
    } finally {
      setIsVerifying(false);
    }
  }

  return (
    <section className="panel mt-2 overflow-hidden border-info">
      <div className="border-b border-line p-4">
        <p className="eyebrow">Evidence Details</p>

        <div className="mt-3 flex flex-wrap gap-2">
          <Badge tone={evidence.severity}>{evidence.severity}</Badge>
          {verification && (
            <Badge tone={VERIFY_STATUS_TONE[verification.status] || "neutral"}>
              {VERIFY_STATUS_LABEL[verification.status] || verification.status}
            </Badge>
          )}
        </div>

        <h2 className="mt-3 text-sm font-semibold text-primary">
          {evidence.event}
        </h2>

        <p className="mt-1 font-mono text-[10px] text-muted">
          {evidence.id}
        </p>
      </div>

      <div className="p-4">
        {evidence.recordingUrl ? (
          <video
            key={evidence.recordingUrl}
            controls
            className="w-full border border-line bg-black"
            src={`${GATEWAY_ORIGIN}${evidence.recordingUrl}`}
          />
        ) : (
          <p className="text-xs text-muted">Capturing clip...</p>
        )}
      </div>

      <div className="space-y-4 p-4 pt-0">
        <DetailRow label="Camera" value={evidence.cameraName} />

        <DetailRow
          label="Time"
          value={new Date(evidence.time).toLocaleString()}
        />

        <DetailRow
          label="Location"
          value={
            <span className="flex items-center gap-1">
              <MapPin size={12} className="text-muted" />
              {evidence.location || "Unknown"}
            </span>
          }
        />

        {evidence.objectType && (
          <DetailRow label="Object Type" value={evidence.objectType} />
        )}

        <div>
          <p className="eyebrow">Description</p>
          <p className="mt-2 text-xs leading-5 text-secondary">
            {evidence.description || `${evidence.event} detected on ${evidence.cameraName}.`}
          </p>
        </div>
      </div>

      <div className="space-y-2 border-t border-line p-4">
        <a
          href={exportUrl}
          aria-disabled={!evidence.recordingUrl}
          className={`flex items-center justify-center gap-2 border px-3 py-2 text-xs font-semibold ${
            evidence.recordingUrl
              ? "border-info bg-info/10 text-info hover:bg-info/15"
              : "cursor-not-allowed border-line bg-panelSecondary text-muted"
          }`}
        >
          <Download size={13} />
          Export for Investigation
        </a>

        <button
          type="button"
          onClick={handleVerify}
          disabled={!evidence.recordingVerifyUrl || isVerifying}
          className={`flex w-full items-center justify-center gap-2 border px-3 py-2 text-xs font-semibold ${
            evidence.recordingVerifyUrl
              ? "border-line bg-panelSecondary text-secondary hover:bg-slate-800/40"
              : "cursor-not-allowed border-line bg-panelSecondary text-muted"
          }`}
        >
          <ShieldCheck size={13} />
          {isVerifying ? "Verifying..." : "Verify Integrity"}
        </button>

        {verifyError && (
          <p className="text-center text-[10px] text-danger">Verification check failed. Try again.</p>
        )}
      </div>
    </section>
  );
}

function DetailRow({ label, value }) {
  return (
    <div className="border border-line bg-panelSecondary p-3">
      <p className="text-[9px] font-bold uppercase tracking-wider text-muted">
        {label}
      </p>

      <p className="mt-1 truncate text-xs font-medium text-primary">
        {value}
      </p>
    </div>
  );
}
