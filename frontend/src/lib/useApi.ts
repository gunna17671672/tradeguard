"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError } from "./api";

/** Fetch-on-mount (and on dep change) with loading/error state and reload(). */
export function useApi<T>(fn: () => Promise<T>, deps: unknown[] = []) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const generation = useRef(0);

  const load = useCallback(() => {
    const mine = ++generation.current;
    setLoading(true);
    setError(null);
    fn().then(
      (result) => {
        if (generation.current === mine) {
          setData(result);
          setLoading(false);
        }
      },
      (err: unknown) => {
        if (generation.current === mine) {
          setError(err instanceof ApiError ? err.message : String(err));
          setLoading(false);
        }
      },
    );
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  useEffect(() => {
    load();
  }, [load]);

  return { data, error, loading, reload: load };
}
