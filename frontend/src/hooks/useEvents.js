import { useCallback, useEffect, useRef, useState } from "react";
import { eventService } from "../services/eventService";
import { socket } from "../services/socket";
import { EMPTY_FILTERS, eventMatchesFilters, toQueryParams } from "../utils/eventFilters";

// A live camera feed can emit informational events (e.g. "Direction
// Observed") several times a second per moving object -- without a cap
// this array would grow forever for as long as the page stays open,
// eventually showing an unusably huge "number of events" to the user even
// though the backend itself only keeps the most recent page server-side.
// Raised from 200 now that older pages can be loaded on demand: it only
// trims what's *displayed* (the oldest rows of a long scroll-back), never
// what an export fetches.
const MAX_LIVE_EVENTS = 3000;
const PAGE_SIZE = 100;

// Events matching `filters`, fetched from the server (so a filter reaches
// every stored event, not just the newest page), with "Load more" paging and
// live pushes that are kept only if they match the active filters.
export function useEvents(filters = EMPTY_FILTERS) {
  const [events, setEvents] = useState([]);
  const [total, setTotal] = useState(0);
  const [isLoading, setIsLoading] = useState(true);
  const [isLoadingMore, setIsLoadingMore] = useState(false);
  const [error, setError] = useState(null);

  const filterKey = JSON.stringify(filters);
  // Latest filters for the socket handler / paging, without resubscribing or
  // rebuilding callbacks on every change.
  const filtersRef = useRef(filters);
  filtersRef.current = filters;
  const pageRef = useRef(1);
  const activeKeyRef = useRef(filterKey);
  // Ids currently in the list -- lets a live push be de-duplicated (and the
  // running total bumped) without doing side effects inside a state updater.
  const knownIdsRef = useRef(new Set());

  useEffect(() => {
    let cancelled = false;
    activeKeyRef.current = filterKey;
    pageRef.current = 1;

    async function load() {
      setIsLoading(true);
      setError(null);
      try {
        const data = await eventService.getPage({ ...toQueryParams(filtersRef.current), page: 1, pageSize: PAGE_SIZE });
        if (cancelled) return;
        knownIdsRef.current = new Set(data.items.map((e) => e.id));
        setEvents(data.items);
        setTotal(data.total);
      } catch (err) {
        if (!cancelled) setError(err);
      } finally {
        if (!cancelled) setIsLoading(false);
      }
    }

    load();
    return () => {
      cancelled = true;
    };
  }, [filterKey]);

  const loadMore = useCallback(async () => {
    const key = activeKeyRef.current;
    setIsLoadingMore(true);
    try {
      const nextPage = pageRef.current + 1;
      const data = await eventService.getPage({ ...toQueryParams(filtersRef.current), page: nextPage, pageSize: PAGE_SIZE });
      // The filters changed while this was in flight -- those rows belong to a
      // different query now.
      if (key !== activeKeyRef.current) return;
      pageRef.current = nextPage;
      const fresh = data.items.filter((e) => !knownIdsRef.current.has(e.id));
      fresh.forEach((e) => knownIdsRef.current.add(e.id));
      setTotal(data.total);
      setEvents((current) => [...current, ...fresh]);
    } catch (err) {
      setError(err);
    } finally {
      setIsLoadingMore(false);
    }
  }, []);

  useEffect(() => {
    socket.subscribe(["events"]);
    const offNew = socket.on("event.new", (event) => {
      // Not part of the current view -- e.g. another camera while one is
      // selected, or "yesterday" -- so it stays out of the list.
      if (!eventMatchesFilters(event, filtersRef.current)) return;
      // Same duplicate-entry guard as useAlerts.js's "alert.new" handler --
      // this push can race the initial fetch.
      if (knownIdsRef.current.has(event.id)) return;
      knownIdsRef.current.add(event.id);
      setTotal((t) => t + 1);
      setEvents((current) => [event, ...current].slice(0, MAX_LIVE_EVENTS));
    });
    return () => {
      offNew();
      socket.unsubscribe(["events"]);
    };
  }, []);

  return { events, total, hasMore: events.length < total, loadMore, isLoading, isLoadingMore, error };
}
