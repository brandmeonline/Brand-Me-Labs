import { createGuestClosetRepository } from "../closet/repository";
import { deletePreview } from "./previewMedia";
/** Retryable deletion saga: keep the media record until all linked guest copies are removed. */
export async function deletePhotoPreview(mediaId: string) {
  const repository = createGuestClosetRepository();
  let snapshot = await repository.read();
  for (const item of snapshot.items.filter(
    (item) => item.previewMediaId === mediaId,
  )) {
    const result = await repository.commit(
      { type: "undo_add", itemId: item.id, expectedItemVersion: item.version },
      snapshot.version,
      crypto.randomUUID(),
    );
    snapshot = result.snapshot;
  }
  await deletePreview(mediaId);
}
