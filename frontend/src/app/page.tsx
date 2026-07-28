import Link from "next/link";

import { Button } from "@/components/ui/button";

export default function HomePage() {
  return (
    <main className="flex min-h-screen items-center justify-center px-6 py-16">
      <section className="w-full max-w-4xl overflow-hidden rounded-3xl border border-border bg-card/90 shadow-2xl backdrop-blur">
        <div className="grid gap-10 p-8 md:grid-cols-[1.2fr_0.8fr] md:p-12">
          <div className="space-y-6 animate-fade-in-up">
            <div className="inline-flex rounded-full border border-border bg-secondary px-4 py-1 text-sm font-medium text-secondary-foreground">
              Phase 1 scaffold
            </div>
            <div className="space-y-3">
              <h1 className="max-w-xl text-4xl font-semibold tracking-tight text-foreground md:text-6xl">
                TTHS Buddy
              </h1>
              <p className="max-w-2xl text-base leading-7 text-muted-foreground md:text-lg">
                A Next.js and FastAPI scaffold for a grounded legal study assistant built around Vietnamese criminal procedure law.
              </p>
            </div>
            <div className="flex flex-wrap gap-3">
              <Button asChild>
                <Link href="/login">Sign in</Link>
              </Button>
              <Button variant="secondary" asChild>
                <Link href="/register">Create account</Link>
              </Button>
            </div>
          </div>
          <aside className="grid gap-4 rounded-2xl border border-border bg-muted/40 p-6 text-sm text-muted-foreground">
            <div>
              <p className="font-medium text-foreground">Included in this scaffold</p>
              <p className="mt-1">Strict TypeScript, Tailwind CSS, shadcn/ui base config, and a health-first backend.</p>
            </div>
            <div>
              <p className="font-medium text-foreground">Next steps</p>
              <p className="mt-1">Auth, ingestion, RAG, quiz, and dashboard are intentionally left for later phases.</p>
            </div>
          </aside>
        </div>
      </section>
    </main>
  );
}
