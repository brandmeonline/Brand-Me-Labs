import { PageHeading } from "@/components/shell/page-heading";
import { Discover } from "@/features/commerce/catalog";
export default function Page() {
  return (
    <>
      <PageHeading
        eyebrow="Shops"
        title="A world to discover."
        description="Search connected catalogs with source, freshness and provider disclosures in view."
      />
      <Discover />
    </>
  );
}
