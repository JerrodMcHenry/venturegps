import { notFound } from "next/navigation";

import DirectionB from "@/components/design/directionB/DirectionB";

export default function DirectionBPage() {
  if (process.env.NODE_ENV === "production") {
    notFound();
  }

  return <DirectionB />;
}
