"use client";

import { AuthenticatedLayout } from "@/components/layout/AuthenticatedLayout";
import { ChatView } from "@/components/chat/ChatView";

// Bare /chat (no conversationId segment) = always a brand new conversation, matching the
// pre-existing "Hoi thoai moi" behavior (see requirements.md Phase 4 Extension 2). Reloading an
// existing conversation lives at /chat/[conversationId] instead.
export default function ChatPage() {
  return (
    <AuthenticatedLayout title="Trợ lý AI">
      <ChatView conversationId={null} />
    </AuthenticatedLayout>
  );
}
