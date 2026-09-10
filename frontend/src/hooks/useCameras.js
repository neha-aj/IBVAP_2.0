import { useCallback, useEffect, useRef, useState } from "react";
import { cameraService } from "../services/cameraService";
import { socket } from "../services/socket";

export function useCameras() {
  const [cameras, setCameras] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState(null);
  const subscribedIds = useRef(new Set());

  const refetch = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      setCameras(await cameraService.getAll());
    } catch (err) {
      setError(err);
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    refetch();
  }, [refetch]);

  // Live status updates: camera.status_changed is only broadcast per
  // camera:{id} topic (Realtime Gateway's own topic design has no global
  // "all cameras" channel), so subscribe once per camera currently in the
  // list and unsubscribe from any that drop out.
  useEffect(() => {
    const currentIds = new Set(cameras.map((c) => c.id));
    const toSubscribe = [...currentIds].filter((id) => !subscribedIds.current.has(id));
    const toUnsubscribe = [...subscribedIds.current].filter((id) => !currentIds.has(id));

    if (toSubscribe.length > 0) socket.subscribe(toSubscribe.map((id) => `camera:${id}`));
    if (toUnsubscribe.length > 0) socket.unsubscribe(toUnsubscribe.map((id) => `camera:${id}`));

    subscribedIds.current = currentIds;
  }, [cameras]);

  useEffect(() => {
    return socket.on("camera.status_changed", ({ cameraId, status }) => {
      setCameras((current) => current.map((c) => (c.id === cameraId ? { ...c, status } : c)));
    });
  }, []);

  return { cameras, isLoading, error, refetch };
}
