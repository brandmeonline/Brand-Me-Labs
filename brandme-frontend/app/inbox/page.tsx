import { PageHeading } from "@/components/shell/page-heading";
import { Inbox } from "@/features/social/inbox";
export default function Page() {
  return (
    <>
      <PageHeading
        eyebrow="Your updates"
        title="Keep in touch with your world."
        description="Decisions, requests and account updates, visible only to you."
      />
      <Inbox />
    </>
  );
}
