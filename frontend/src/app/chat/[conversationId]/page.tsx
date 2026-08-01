import { AuthenticatedLayout } from "@/components/layout/AuthenticatedLayout";
import { ChatView } from "@/components/chat/ChatView";

interface ChatConversationPageProps {
  params: Promise<{ conversationId: string }>;
}

// Reload an existing conversation (see requirements.md Phase 4 Extension 2) - ChatView does the
// actual GET /api/chat/conversations/{id} fetch + message hydration client-side; this Server
// Component only unwraps the route param (Next.js 15 params is a Promise) and hands it down.
export default async function ChatConversationPage({ params }: ChatConversationPageProps) {
  const { conversationId } = await params;

  return (
    <AuthenticatedLayout title="Trợ lý AI">
      <ChatView conversationId={conversationId} />
    </AuthenticatedLayout>
  );
}
