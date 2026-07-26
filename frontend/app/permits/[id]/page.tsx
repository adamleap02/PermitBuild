import { PermitDetailClient } from "@/components/permits/permit-detail-client";

export default function PermitDetailPage({ params }: { params: { id: string } }) {
  const id = Number(params.id);
  return <PermitDetailClient id={id} />;
}
