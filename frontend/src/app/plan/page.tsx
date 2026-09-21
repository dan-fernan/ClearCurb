import type { Metadata } from "next";
import PlannerApp from "@/components/PlannerApp";

export const metadata: Metadata = {
  title: "Plan a route · ClearCurb",
};

export default function PlanPage() {
  return <PlannerApp />;
}
