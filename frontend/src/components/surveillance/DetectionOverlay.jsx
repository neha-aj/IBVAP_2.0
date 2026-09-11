import { PersonStanding, Armchair, Moon } from 'lucide-react';

// Small badge glyph per posture -- deliberately icon-only, no text label,
// so it stays legible even in the corner of a small detection box where
// there's no room for the word "standing"/"sitting"/"sleeping" (unlike the
// existing per-detection label above each box, which does have room).
const POSTURE_ICON = { standing: PersonStanding, sitting: Armchair, sleeping: Moon };

// Max distance (in the same 0-100 percentage-of-frame units bbox/pose
// coordinates already use) between a detection box's own center and a pose
// reading's center point for them to be considered the same person. There
// is no shared track id between detection-service and pose-service to join
// on directly (see usePoses.js's own comment), so this is a simple nearest-
// neighbor match -- generous enough to tolerate the two services sampling
// at different rates/moments (a person can move a little between one
// service's frame and the other's), tight enough not to badge the wrong
// person in a crowd.
const POSE_MATCH_MAX_DISTANCE = 15;

function nearestPose(box, poses) {
  if (!poses || poses.length === 0) return null;
  const boxCenterX = box.x + box.width / 2;
  const boxCenterY = box.y + box.height / 2;
  let best = null;
  let bestDistance = Infinity;
  for (const pose of poses) {
    const distance = Math.hypot(pose.x - boxCenterX, pose.y - boxCenterY);
    if (distance < bestDistance) {
      bestDistance = distance;
      best = pose;
    }
  }
  return bestDistance <= POSE_MATCH_MAX_DISTANCE ? best : null;
}

export default function DetectionOverlay({ detections = [], poses = [] }) {
  return (
    <div className="pointer-events-none absolute inset-0">
      {detections.map((d) => {
        const box = d.bbox || d;
        const matchedPose = d.type === 'person' ? nearestPose(box, poses) : null;
        const PostureIcon = matchedPose ? POSTURE_ICON[matchedPose.posture] : null;
        return (
          <div
            key={d.id}
            className={`absolute border ${d.type === 'person' ? 'border-info' : 'border-warning'}`}
            style={{ left: `${box.x}%`, top: `${box.y}%`, width: `${box.width}%`, height: `${box.height}%` }}
          >
            <span
              className={`absolute -top-5 left-0 whitespace-nowrap px-1 py-0.5 text-[9px] font-bold tracking-wide ${d.type === 'person' ? 'bg-info text-primary' : 'bg-warning text-ink'}`}
            >
              {d.type.toUpperCase()} {Math.round(d.confidence * 100)}%{d.trackId ? ` · #${d.trackId}` : ''}
            </span>
            {PostureIcon && (
              <span
                title={matchedPose.posture}
                className="absolute -right-1.5 -top-1.5 grid h-4 w-4 place-items-center rounded-full bg-ink/80 text-info ring-1 ring-info"
              >
                <PostureIcon size={10} strokeWidth={2.5} />
              </span>
            )}
          </div>
        );
      })}
    </div>
  );
}
