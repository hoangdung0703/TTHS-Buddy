"use client";

import { Suspense } from "react";

import { AuthenticatedLayout } from "@/components/layout/AuthenticatedLayout";
import { ChatView } from "@/components/chat/ChatView";

// Bare /chat (no conversationId segment) = always a brand new conversation, matching the
// pre-existing "Hoi thoai moi" behavior (see requirements.md Phase 4 Extension 2). Reloading an
// existing conversation lives at /chat/[conversationId] instead.
// Suspense boundary is required by Next.js 15 because ChatView calls useSearchParams() (reads
// ?q= for the Dashboard "Ôn tập" auto-send flow) - without it, `next build` fails to statically
// render this page.
export default function ChatPage() {
  return (
    <AuthenticatedLayout title="Trợ lý AI">
      <Suspense fallback={null}>
        <ChatView conversationId={null} />
      </Suspense>
    </AuthenticatedLayout>
  );
}
