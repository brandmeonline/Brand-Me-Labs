"use client";
import Link from "next/link";
import { useState } from "react";
import { useResource } from "@/lib/client/use-resource";
import { command, explainError } from "@/lib/client/gateway";
import { ResourceState } from "@/components/ui/resource-state";
import { Button } from "@/components/ui/button";
type Notice = {
  notification_id: string;
  type: string;
  subject_ref: string | null;
  created_at: string;
  read_at: string | null;
};
function destination(ref: string | null) {
  const match = /^(decision|relationship|outfit|share):([a-f0-9-]{36})$/.exec(
    ref ?? "",
  );
  if (!match) return null;
  return match[1] === "decision"
    ? `/circle/decisions/${match[2]}`
    : match[1] === "relationship"
      ? "/circle"
      : match[1] === "share"
        ? `/share/${match[2]}`
        : `/style/outfits/${match[2]}`;
}
export function Inbox() {
  const [cursor, setCursor] = useState<string | null>(null),
    [busy, setBusy] = useState(false),
    [message, setMessage] = useState("");
  const r = useResource<{ items: Notice[]; next_cursor: string | null }>(
    `/notifications?limit=24${cursor ? `&cursor=${encodeURIComponent(cursor)}` : ""}`,
  );
  return (
    <div className="bm-flow-stack">
      <ResourceState {...r} retry={r.reload} />
      {r.data?.items.length === 0 && <p>No updates here yet.</p>}
      {r.data?.items.map((n) => (
        <article className="bm-flow-card" key={n.notification_id}>
          <h2>{n.type.replaceAll("_", " ")}</h2>
          <p>
            <time dateTime={n.created_at}>
              {new Date(n.created_at).toLocaleString()}
            </time>{" "}
            · {n.read_at ? "Read" : "Unread"}
          </p>
          <div className="bm-actions">
            {destination(n.subject_ref) && (
              <Link
                className="bm-button bm-button-secondary"
                href={destination(n.subject_ref)!}
              >
                Open update
              </Link>
            )}
            {!n.read_at && (
              <Button
                variant="secondary"
                pending={busy}
                onClick={async () => {
                  setBusy(true);
                  try {
                    await command("/notifications/read", {
                      ids: [n.notification_id],
                    });
                    r.reload();
                    setMessage("Marked as read.");
                  } catch (e) {
                    setMessage(explainError(e));
                  } finally {
                    setBusy(false);
                  }
                }}
              >
                Mark as read
              </Button>
            )}
          </div>
        </article>
      ))}
      <div className="bm-actions">
        {cursor && (
          <Button variant="secondary" onClick={() => setCursor(null)}>
            Newest updates
          </Button>
        )}
        {r.data?.next_cursor && (
          <Button
            variant="secondary"
            onClick={() => setCursor(r.data!.next_cursor)}
          >
            Older updates
          </Button>
        )}
      </div>
      <p role="status">{message}</p>
      <p className="bm-support">
        Access is checked when you open an update. A revoked or blocked record
        may no longer be available.
      </p>
    </div>
  );
}
