import { notFound } from "next/navigation";

import DirectionC from "@/components/design/directionC/DirectionC";

export default function DirectionCPage() {
  if (process.env.NODE_ENV === "production") {
    notFound();
  }

  return <DirectionC />;
}
