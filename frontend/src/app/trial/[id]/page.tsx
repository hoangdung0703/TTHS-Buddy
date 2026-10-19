import { TrialHearing } from "@/components/trial/TrialHearing";
import { TrialShell } from "@/components/trial/TrialShell";

interface TrialPageProps {
  params: Promise<{ id: string }>;
}

// Unwraps the Next.js 15 route param; TrialHearing does the GET /api/trials/{id} client-side.
export default async function TrialPage({ params }: TrialPageProps) {
  const { id } = await params;

  return (
    <TrialShell title="Phiên tòa giả định">
      <TrialHearing sessionId={id} />
    </TrialShell>
  );
}
