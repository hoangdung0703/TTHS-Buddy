import { TrialRecordView } from "@/components/trial/TrialRecordView";
import { TrialShell } from "@/components/trial/TrialShell";

interface TrialRecordPageProps {
  params: Promise<{ id: string }>;
}

export default async function TrialRecordPage({ params }: TrialRecordPageProps) {
  const { id } = await params;

  return (
    <TrialShell title="Biên bản phiên tòa">
      <TrialRecordView sessionId={id} />
    </TrialShell>
  );
}
