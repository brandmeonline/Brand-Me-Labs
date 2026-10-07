"use client";
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  ClosetConflict,
  createGuestClosetRepository,
  type ClosetCommand,
  type ClosetRepository,
} from "./repository";
import type { ClosetSnapshot } from "../spatial/types";
export function useCloset(injected?: ClosetRepository) {
  const repository = useMemo(
    () => injected ?? createGuestClosetRepository(),
    [injected],
  );
  const [snapshot, setSnapshot] = useState<ClosetSnapshot>(),
    [error, setError] = useState("");
  const refresh = useCallback(async () => {
    try {
      setSnapshot(await repository.read());
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unable to read your closet.");
    }
  }, [repository]);
  useEffect(() => {
    let active = true;
    void repository
      .read()
      .then((s) => {
        if (active) setSnapshot(s);
      })
      .catch((e) => {
        if (active) setError(e.message);
      });
    const stop = repository.subscribe(() => {
      if (active) void refresh();
    });
    return () => {
      active = false;
      stop();
    };
  }, [repository, refresh]);
  const commit = async (
    command: ClosetCommand,
    operationId: string = crypto.randomUUID(),
  ) => {
    if (!snapshot) throw new Error("Your closet is still loading.");
    setError("");
    try {
      const result = await repository.commit(
        command,
        snapshot.version,
        operationId,
      );
      setSnapshot(result.snapshot);
      return result;
    } catch (e) {
      if (e instanceof ClosetConflict) setSnapshot(e.current);
      setError(e instanceof Error ? e.message : "Unable to save.");
      throw e;
    }
  };
  return {
    snapshot,
    error,
    setError,
    commit,
    refresh,
    persistenceLabel: repository.persistenceLabel,
  };
}
