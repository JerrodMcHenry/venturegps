import { notFound } from "next/navigation";

import DirectionsComparison from "@/components/design/directions/DirectionsComparison";

export default function DirectionsComparisonPage() {
  if (process.env.NODE_ENV === "production") {
    notFound();
  }

  return <DirectionsComparison />;
}
