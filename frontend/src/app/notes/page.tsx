"use client";

import { NotebookPen, Pencil, Plus, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";

import { AuthenticatedLayout } from "@/components/layout/AuthenticatedLayout";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { createNote, deleteNote, getNotes, updateNote } from "@/lib/api";
import type { Note } from "@/lib/types";

interface NoteFormState {
  title: string;
  content: string;
  tag: string;
}

function formatUpdatedAt(updatedAt: string): string {
  return new Date(updatedAt).toLocaleString("vi-VN", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit"
  });
}

// Form dùng chung cho cả thêm mới và sửa ghi chú - văn bản thuần cho bản đầu (chưa cần rich
// text, đúng scope "chỉ làm phần nền tảng" của bước này). editingNoteId=null -> tạo mới,
// ngược lại -> sửa đúng ghi chú đó (PUT /api/notes/{id}).
function NoteForm({
  editingNoteId,
  initial,
  onCancel,
  onSaved
}: {
  editingNoteId: string | null;
  initial: NoteFormState;
  onCancel: () => void;
  onSaved: (note: Note) => void;
}) {
  const [form, setForm] = useState<NoteFormState>(initial);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(event: React.FormEvent): Promise<void> {
    event.preventDefault();
    const content = form.content.trim();
    if (content.length === 0) {
      setError("Nội dung ghi chú không được để trống.");
      return;
    }

    setSaving(true);
    setError(null);

    const payload = {
      title: form.title.trim() || null,
      content,
      tag: form.tag.trim() || null
    };

    try {
      const saved = editingNoteId !== null ? await updateNote(editingNoteId, payload) : await createNote(payload);
      onSaved(saved);
    } catch {
      setError("Không lưu được ghi chú. Vui lòng thử lại.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-3 rounded-xl border border-border bg-card p-5 shadow-sm">
      <Input
        value={form.title}
        onChange={(event) => setForm((current) => ({ ...current, title: event.target.value }))}
        placeholder="Tiêu đề (không bắt buộc)"
        maxLength={200}
      />
      <Input
        value={form.tag}
        onChange={(event) => setForm((current) => ({ ...current, tag: event.target.value }))}
        placeholder="Chủ đề / tag (không bắt buộc, ví dụ: Điều 60, Bắt người)"
        maxLength={100}
      />
      <Textarea
        value={form.content}
        onChange={(event) => setForm((current) => ({ ...current, content: event.target.value }))}
        placeholder="Nội dung ghi chú..."
        maxLength={20000}
        autoFocus
      />
      {error ? <p className="text-sm text-red-600">{error}</p> : null}
      <div className="flex items-center gap-2">
        <Button type="submit" size="sm" disabled={saving}>
          {saving ? "Đang lưu..." : editingNoteId !== null ? "Lưu thay đổi" : "Thêm ghi chú"}
        </Button>
        <Button type="button" variant="outline" size="sm" onClick={onCancel} disabled={saving}>
          Hủy
        </Button>
      </div>
    </form>
  );
}

// Ngưỡng để quyết định có cần nút "Xem thêm" hay không - xấp xỉ độ dài nội dung vượt quá
// khoảng hiển thị của line-clamp-5 ở khổ card này, không cần đo DOM thật.
const CONTENT_PREVIEW_THRESHOLD = 320;

function NoteCard({
  note,
  onEdit,
  onDelete
}: {
  note: Note;
  onEdit: () => void;
  onDelete: () => void;
}) {
  const [isExpanded, setIsExpanded] = useState(false);
  const canCollapse = note.content.length > CONTENT_PREVIEW_THRESHOLD;

  return (
    <div className="flex min-w-0 flex-col gap-2 overflow-hidden rounded-xl border border-border bg-card p-5 shadow-sm">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          {note.tag ? (
            <span className="mb-1.5 inline-flex max-w-full items-center break-words rounded-full bg-accent/15 px-2 py-0.5 text-[0.7rem] font-medium text-accent-foreground/80">
              {note.tag}
            </span>
          ) : null}
          <h3 className="break-words font-serif text-lg font-light tracking-tight text-foreground">
            {note.title || "Ghi chú không tiêu đề"}
          </h3>
        </div>
        <div className="flex shrink-0 items-center gap-1">
          <button
            type="button"
            onClick={onEdit}
            aria-label="Sửa ghi chú"
            className="flex h-9 w-9 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-accent hover:text-accent-foreground"
          >
            <Pencil className="h-4 w-4" />
          </button>
          <button
            type="button"
            onClick={onDelete}
            aria-label="Xóa ghi chú"
            className="flex h-9 w-9 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-red-100 hover:text-red-600"
          >
            <Trash2 className="h-4 w-4" />
          </button>
        </div>
      </div>
      <p
        className={`min-w-0 whitespace-pre-wrap break-words text-sm font-light leading-relaxed text-foreground/90 ${
          isExpanded || !canCollapse ? "" : "line-clamp-5"
        }`}
      >
        {note.content}
      </p>
      {canCollapse ? (
        <button
          type="button"
          onClick={() => setIsExpanded((value) => !value)}
          className="self-start text-xs font-medium text-primary hover:underline"
        >
          {isExpanded ? "Thu gọn" : "Xem thêm"}
        </button>
      ) : null}
      <p className="mt-1 text-xs text-muted-foreground">Cập nhật {formatUpdatedAt(note.updated_at)}</p>
    </div>
  );
}

export default function NotesPage() {
  const [notes, setNotes] = useState<Note[] | null>(null);
  const [loadError, setLoadError] = useState(false);
  const [isCreating, setIsCreating] = useState(false);
  const [editingNoteId, setEditingNoteId] = useState<string | null>(null);

  useEffect(() => {
    loadNotes();
  }, []);

  function loadNotes(): void {
    setLoadError(false);
    getNotes()
      .then(setNotes)
      .catch(() => setLoadError(true));
  }

  function handleCreated(note: Note): void {
    setNotes((current) => [note, ...(current ?? [])]);
    setIsCreating(false);
  }

  function handleUpdated(note: Note): void {
    setNotes((current) => (current ?? []).map((item) => (item.id === note.id ? note : item)));
    setEditingNoteId(null);
  }

  async function handleDelete(note: Note): Promise<void> {
    const confirmed = window.confirm(`Xóa ghi chú "${note.title || "Ghi chú không tiêu đề"}"? Hành động này không thể hoàn tác.`);
    if (!confirmed) {
      return;
    }

    const previous = notes;
    setNotes((current) => (current ?? []).filter((item) => item.id !== note.id));

    try {
      await deleteNote(note.id);
    } catch {
      setNotes(previous ?? null);
    }
  }

  return (
    <AuthenticatedLayout title="Vở ghi">
      <div className="mx-auto max-w-3xl px-6 py-8">
        <div className="mb-8 flex flex-wrap items-end justify-between gap-4">
          <div>
            <h1 className="mb-1.5 font-serif text-3xl font-light tracking-tight text-foreground">Vở ghi cá nhân</h1>
            <p className="text-sm font-light text-muted-foreground">Ghi chú tự do theo chủ đề bạn đang học</p>
          </div>

          {!isCreating ? (
            <Button
              size="sm"
              onClick={() => {
                setEditingNoteId(null);
                setIsCreating(true);
              }}
            >
              <Plus className="h-4 w-4" />
              Ghi chú mới
            </Button>
          ) : null}
        </div>

        {isCreating ? (
          <div className="mb-6">
            <NoteForm
              editingNoteId={null}
              initial={{ title: "", content: "", tag: "" }}
              onCancel={() => setIsCreating(false)}
              onSaved={handleCreated}
            />
          </div>
        ) : null}

        {loadError ? (
          <div className="flex items-center justify-between rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
            <span>Không tải được danh sách ghi chú.</span>
            <Button variant="outline" size="sm" onClick={loadNotes}>
              Thử lại
            </Button>
          </div>
        ) : null}

        {notes === null && !loadError ? (
          <div className="flex flex-col gap-3">
            {Array.from({ length: 3 }).map((_, index) => (
              <div key={index} className="h-32 animate-pulse rounded-xl border border-border bg-muted/60" />
            ))}
          </div>
        ) : null}

        {notes !== null && notes.length === 0 && !isCreating ? (
          <div className="flex flex-col items-center gap-3 rounded-xl border border-dashed border-border py-16 text-center">
            <NotebookPen className="h-8 w-8 text-muted-foreground" strokeWidth={1.4} />
            <p className="text-sm text-muted-foreground">Bạn chưa có ghi chú nào. Bắt đầu bằng nút &quot;Ghi chú mới&quot;.</p>
          </div>
        ) : null}

        {notes !== null ? (
          <div className="flex flex-col gap-4">
            {notes.map((note) =>
              editingNoteId === note.id ? (
                <NoteForm
                  key={note.id}
                  editingNoteId={note.id}
                  initial={{ title: note.title ?? "", content: note.content, tag: note.tag ?? "" }}
                  onCancel={() => setEditingNoteId(null)}
                  onSaved={handleUpdated}
                />
              ) : (
                <NoteCard
                  key={note.id}
                  note={note}
                  onEdit={() => {
                    setIsCreating(false);
                    setEditingNoteId(note.id);
                  }}
                  onDelete={() => void handleDelete(note)}
                />
              )
            )}
          </div>
        ) : null}
      </div>
    </AuthenticatedLayout>
  );
}
