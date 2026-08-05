// Static mock content used while NEXT_PUBLIC_USE_MOCK_DATA=true.
// All legal content below only references BLTTHS 2015 articles, matching what
// Phase 3 ingestion will actually load (no Hien Phap or other un-ingested sources).
import type {
  ChatQueryResponse,
  ChatSuggestion,
  ConversationDetailResponse,
  ConversationSummary,
  DashboardStats,
  EssayQuestion,
  EssaySubmitResponse,
  KeywordYesterday,
  QuizAnswer,
  QuizQuestion,
  QuizSetSummary,
  QuizSubmitResponse,
  WeakTopic
} from "@/lib/types";

const MIN_MOCK_DELAY_MS = 300;
const MAX_MOCK_DELAY_MS = 500;

// Simulates real network latency so loading states can be exercised during mock development.
export function withMockDelay<T>(value: T): Promise<T> {
  const delay = MIN_MOCK_DELAY_MS + Math.random() * (MAX_MOCK_DELAY_MS - MIN_MOCK_DELAY_MS);
  return new Promise((resolve) => setTimeout(() => resolve(value), delay));
}

export const MOCK_CHAT_SUGGESTIONS: ChatSuggestion[] = [
  { id: "sug-1", text: "Điều kiện tạm giam là gì?" },
  { id: "sug-2", text: "Quy trình khởi tố vụ án" },
  { id: "sug-3", text: "Quyền im lặng trong BLTTHS" },
  { id: "sug-4", text: "Thời hạn tạm giữ là bao lâu?" }
];

const MOCK_ANSWER_PRESUMPTION_OF_INNOCENCE: ChatQueryResponse = {
  answer:
    "Điều 23 BLTTHS 2015 quy định nguyên tắc suy đoán vô tội - một trong những nguyên tắc quan trọng nhất của tố tụng hình sự Việt Nam.\n\n" +
    "**Nội dung cốt lõi**\n\n" +
    "Người bị buộc tội được coi là không có tội cho đến khi tội của họ được chứng minh theo đúng trình tự, thủ tục luật định và có bản án kết tội của Tòa án đã có hiệu lực pháp luật.\n\n" +
    "**Ba hệ quả pháp lý trực tiếp**\n\n" +
    "1. Nghĩa vụ chứng minh thuộc về cơ quan tiến hành tố tụng, không phải người bị buộc tội. Bị can, bị cáo có quyền nhưng không có nghĩa vụ tự chứng minh vô tội.\n" +
    "2. Khi không đủ căn cứ và không thể làm sáng tỏ việc buộc tội, cơ quan có thẩm quyền phải kết luận người bị buộc tội không có tội.\n" +
    "3. Lời nhận tội của bị can, bị cáo chỉ có giá trị chứng cứ khi phù hợp với các chứng cứ khác, không thể là căn cứ duy nhất để kết tội.",
  citations: [
    { dieu_number: "23", dieu_title: "Suy đoán vô tội", law_version: "BLTTHS 2015" },
    { dieu_number: "15", dieu_title: "Xác định sự thật của vụ án", law_version: "BLTTHS 2015" },
    { dieu_number: "98", dieu_title: "Lời nhận tội của bị can, bị cáo", law_version: "BLTTHS 2015" }
  ]
};

const MOCK_ANSWER_TAM_GIAM: ChatQueryResponse = {
  answer:
    "Điều 119 BLTTHS 2015 quy định về biện pháp tạm giam.\n\n" +
    "**Đối tượng áp dụng**\n\n" +
    "Tạm giam có thể áp dụng đối với bị can, bị cáo về tội đặc biệt nghiêm trọng, tội rất nghiêm trọng, hoặc một số trường hợp tội nghiêm trọng/ít nghiêm trọng theo các điểm được liệt kê tại Điều 119.\n\n" +
    "**Thời hạn tạm giam**\n\n" +
    "Thời hạn tạm giam để điều tra được quy định tại Điều 173, tối đa không quá 4 tháng đối với tội ít nghiêm trọng và có thể gia hạn đối với vụ án phức tạp hơn, tùy theo tính chất vụ án.",
  citations: [
    { dieu_number: "119", dieu_title: "Tạm giam", law_version: "BLTTHS 2015" },
    { dieu_number: "120", dieu_title: "Chế độ tạm giam", law_version: "BLTTHS 2015" },
    { dieu_number: "173", dieu_title: "Thời hạn tạm giam để điều tra", law_version: "BLTTHS 2015" }
  ]
};

const MOCK_ANSWER_FALLBACK: ChatQueryResponse = {
  answer:
    "Không tìm thấy nội dung phù hợp trong dữ liệu pháp luật đã nạp cho câu hỏi này. " +
    "Vui lòng đặt câu hỏi cụ thể hơn về một Điều/Khoản trong BLTTHS 2015, hoặc câu hỏi nằm ngoài phạm vi dữ liệu hiện có.",
  citations: []
};

// Very small keyword router so different demo questions can surface distinct mock answers
// without wiring a real retrieval pipeline yet.
export function resolveMockChatAnswer(question: string): ChatQueryResponse {
  const normalized = question.toLowerCase();

  if (normalized.includes("suy đoán") || normalized.includes("vô tội") || normalized.includes("điều 23")) {
    return MOCK_ANSWER_PRESUMPTION_OF_INNOCENCE;
  }

  if (normalized.includes("tạm giam") || normalized.includes("tạm giữ") || normalized.includes("điều 119")) {
    return MOCK_ANSWER_TAM_GIAM;
  }

  if (normalized.trim().length === 0) {
    return MOCK_ANSWER_FALLBACK;
  }

  return MOCK_ANSWER_PRESUMPTION_OF_INNOCENCE;
}

// Phase 4 Extension 2: mock-mode stand-in for GET /api/chat/conversations - keeps the Sidebar
// history list non-empty in demo/mock mode instead of the old hardcoded list living in
// Sidebar.tsx itself.
export const MOCK_CONVERSATIONS: ConversationSummary[] = [
  { conversation_id: "mock-conv-1", title: "Điều 23 - Suy đoán vô tội", updated_at: new Date().toISOString() },
  {
    conversation_id: "mock-conv-2",
    title: "Điều kiện và thủ tục tạm giam",
    updated_at: new Date(Date.now() - 24 * 60 * 60 * 1000).toISOString()
  },
  {
    conversation_id: "mock-conv-3",
    title: "Quy trình khởi tố vụ án hình sự",
    updated_at: new Date(Date.now() - 6 * 24 * 60 * 60 * 1000).toISOString()
  }
];

// Feature nhỏ - xóa/đổi tên hội thoại: mutate MOCK_CONVERSATIONS in place (not reassigned) so
// mock mode exercises the same delete/rename UX as the real backend instead of silently no-oping.
export function deleteMockConversation(conversationId: string): void {
  const index = MOCK_CONVERSATIONS.findIndex((conversation) => conversation.conversation_id === conversationId);
  if (index !== -1) {
    MOCK_CONVERSATIONS.splice(index, 1);
  }
}

export function renameMockConversation(conversationId: string, title: string): void {
  const conversation = MOCK_CONVERSATIONS.find((item) => item.conversation_id === conversationId);
  const trimmed = title.trim();
  if (conversation && trimmed.length > 0) {
    conversation.title = trimmed;
  }
}

export function resolveMockConversationDetail(conversationId: string): ConversationDetailResponse {
  const summary = MOCK_CONVERSATIONS.find((conversation) => conversation.conversation_id === conversationId);
  const question = summary?.title ?? "Câu hỏi mẫu";
  const mockAnswer = resolveMockChatAnswer(question);

  return {
    conversation_id: conversationId,
    turns: [{ question, answer: mockAnswer.answer, created_at: summary?.updated_at ?? new Date().toISOString() }]
  };
}

export const MOCK_QUIZ_SETS: QuizSetSummary[] = [
  { quiz_set: 1, total_questions: 18, main_topics: ["Biện pháp ngăn chặn", "Khởi tố bị can"] },
  { quiz_set: 2, total_questions: 18, main_topics: ["Chứng cứ", "Thời hạn kháng cáo"] },
  { quiz_set: 3, total_questions: 18, main_topics: ["Người làm chứng", "Suy đoán vô tội"] },
  { quiz_set: 4, total_questions: 18, main_topics: ["Tranh tụng", "Xác định sự thật của vụ án"] },
  { quiz_set: 5, total_questions: 18, main_topics: ["Xét xử công khai", "Pháp chế xã hội chủ nghĩa"] }
];

export const MOCK_QUIZ_QUESTIONS: QuizQuestion[] = [
  {
    question_id: "q-109-1",
    question_text: "Theo Điều 109 BLTTHS 2015, biện pháp ngăn chặn được áp dụng khi nào?",
    mcq_options: [
      "Chỉ sau khi có bản án kết tội của Tòa án",
      "Khi cần kịp thời ngăn chặn tội phạm hoặc khi có căn cứ cho thấy bị can, bị cáo sẽ gây khó khăn cho điều tra, truy tố, xét xử",
      "Chỉ khi bị can tự nguyện yêu cầu",
      "Chỉ áp dụng đối với pháp nhân thương mại"
    ],
    dieu_number: "109",
    topic_category: "Biện pháp ngăn chặn"
  },
  {
    question_id: "q-113-1",
    question_text:
      "Lệnh bắt bị can, bị cáo để tạm giam theo Điều 113 phải được ai phê chuẩn trước khi thi hành (trừ trường hợp khẩn cấp)?",
    mcq_options: [
      "Viện kiểm sát cùng cấp",
      "Trưởng Công an cấp huyện",
      "Chủ tịch Ủy ban nhân dân",
      "Hội đồng xét xử phúc thẩm"
    ],
    dieu_number: "113",
    topic_category: "Biện pháp ngăn chặn"
  },
  {
    question_id: "q-119-1",
    question_text: "Theo Điều 119, tạm giam có thể áp dụng đối với bị can, bị cáo phạm tội ít nghiêm trọng trong trường hợp nào?",
    mcq_options: [
      "Không bao giờ áp dụng cho tội ít nghiêm trọng",
      "Đã bị áp dụng biện pháp ngăn chặn khác nhưng tiếp tục vi phạm, hoặc có dấu hiệu bỏ trốn/cản trở điều tra",
      "Chỉ khi bị can tự thú",
      "Chỉ áp dụng khi Viện kiểm sát đề nghị không cần chứng cứ"
    ],
    dieu_number: "119",
    topic_category: "Biện pháp ngăn chặn"
  },
  {
    question_id: "q-120-1",
    question_text: "Chế độ tạm giam theo Điều 120 được thực hiện như thế nào đối với người bị tạm giam?",
    mcq_options: [
      "Giam giữ như đối với người đã bị kết án tử hình",
      "Khác với chế độ đối với người đang chấp hành án phạt tù, theo quy định pháp luật về thi hành tạm giữ, tạm giam",
      "Không có quy định riêng, áp dụng tùy tiện theo từng địa phương",
      "Do gia đình bị can tự quyết định"
    ],
    dieu_number: "120",
    topic_category: "Biện pháp ngăn chặn"
  },
  {
    question_id: "q-173-1",
    question_text: "Thời hạn tạm giam để điều tra tối đa đối với tội phạm ít nghiêm trọng theo Điều 173 là bao lâu?",
    mcq_options: ["Không quá 1 tháng", "Không quá 2 tháng", "Không quá 3 tháng", "Không quá 4 tháng"],
    dieu_number: "173",
    topic_category: "Biện pháp ngăn chặn"
  }
];

const MOCK_QUIZ_CORRECT_ANSWERS: Record<string, string> = {
  "q-109-1":
    "Khi cần kịp thời ngăn chặn tội phạm hoặc khi có căn cứ cho thấy bị can, bị cáo sẽ gây khó khăn cho điều tra, truy tố, xét xử",
  "q-113-1": "Viện kiểm sát cùng cấp",
  "q-119-1": "Đã bị áp dụng biện pháp ngăn chặn khác nhưng tiếp tục vi phạm, hoặc có dấu hiệu bỏ trốn/cản trở điều tra",
  "q-120-1": "Khác với chế độ đối với người đang chấp hành án phạt tù, theo quy định pháp luật về thi hành tạm giữ, tạm giam",
  "q-173-1": "Không quá 3 tháng"
};

export function gradeMockQuiz(answers: QuizAnswer[]): QuizSubmitResponse {
  const results = answers.map((answer) => {
    const correctOption = MOCK_QUIZ_CORRECT_ANSWERS[answer.question_id] ?? "";
    const question = MOCK_QUIZ_QUESTIONS.find((item) => item.question_id === answer.question_id);

    return {
      question_id: answer.question_id,
      is_correct: answer.selected_option === correctOption,
      mcq_correct: correctOption,
      dieu_number: question?.dieu_number ?? "",
      explanation: null
    };
  });

  const score = results.filter((result) => result.is_correct).length;

  return { score, total: results.length, results };
}

export const MOCK_ESSAY_QUESTIONS: EssayQuestion[] = [
  {
    question_id: "e-119-1",
    question_text:
      "Trình bày điều kiện áp dụng biện pháp tạm giam theo Điều 119 BLTTHS 2015 và ý nghĩa của việc giới hạn các điều kiện này.",
    dieu_number: "119",
    topic_category: "Biện pháp ngăn chặn"
  },
  {
    question_id: "e-23-1",
    question_text:
      "Phân tích nội dung nguyên tắc suy đoán vô tội theo Điều 23 BLTTHS 2015 và các hệ quả pháp lý trực tiếp của nguyên tắc này.",
    dieu_number: "23",
    topic_category: "Nguyên tắc cơ bản"
  }
];

const MOCK_ESSAY_KEY_POINTS: Record<string, { required: string[]; suggestedDieu: string[] }> = {
  "e-119-1": {
    required: [
      "Tạm giam chỉ áp dụng đối với bị can, bị cáo về tội đặc biệt nghiêm trọng, tội rất nghiêm trọng",
      "Đối với tội nghiêm trọng/ít nghiêm trọng chỉ áp dụng khi có thêm điều kiện cụ thể (bỏ trốn, cản trở điều tra, tiếp tục phạm tội...)",
      "Mục đích là giới hạn việc hạn chế quyền tự do thân thể, tránh lạm dụng biện pháp ngăn chặn"
    ],
    suggestedDieu: ["119", "109"]
  },
  "e-23-1": {
    required: [
      "Người bị buộc tội được coi là không có tội cho đến khi có bản án kết tội có hiệu lực pháp luật",
      "Nghĩa vụ chứng minh thuộc về cơ quan tiến hành tố tụng, không phải người bị buộc tội",
      "Lời nhận tội không phải là căn cứ duy nhất để kết tội"
    ],
    suggestedDieu: ["23", "15", "98"]
  }
};

// Simple keyword-overlap heuristic to demo the matched/missing structure without a real LLM judge.
export function gradeMockEssay(questionId: string, userAnswer: string): EssaySubmitResponse {
  const rubric = MOCK_ESSAY_KEY_POINTS[questionId];

  if (rubric === undefined) {
    return {
      matched_points: [],
      missing_points: [],
      feedback: "Không tìm thấy rubric cho câu hỏi này.",
      suggested_dieu: []
    };
  }

  const normalizedAnswer = userAnswer.toLowerCase();
  const matched: string[] = [];
  const missing: string[] = [];

  rubric.required.forEach((point) => {
    const firstKeyword = point.split(" ").slice(0, 3).join(" ").toLowerCase();
    if (normalizedAnswer.includes(firstKeyword.slice(0, 6))) {
      matched.push(point);
    } else {
      missing.push(point);
    }
  });

  const feedback =
    missing.length === 0
      ? "Câu trả lời đã bám sát các ý chính trong rubric. Làm rõ thêm ví dụ thực tiễn sẽ giúp bài làm đầy đủ hơn."
      : "Câu trả lời đã nêu được một phần nội dung, còn thiếu một số ý quan trọng so với rubric. Xem lại các ý còn thiếu bên dưới.";

  return {
    matched_points: matched,
    missing_points: missing,
    feedback,
    suggested_dieu: rubric.suggestedDieu
  };
}

export const MOCK_KEYWORDS_YESTERDAY: KeywordYesterday[] = [
  { dieu_number: "119", keyword: "Tạm giam", count: 4 },
  { dieu_number: "120", keyword: "Điều kiện tạm giam", count: 3 },
  { dieu_number: "173", keyword: "Thời hạn điều tra", count: 2 },
  { dieu_number: "23", keyword: "Suy đoán vô tội", count: 2 },
  { dieu_number: "15", keyword: "Xác định sự thật", count: 1 },
  { dieu_number: "86", keyword: "Nguồn chứng cứ", count: 1 }
];

export const MOCK_WEAK_TOPICS: WeakTopic[] = [
  { topic_category: "Biện pháp ngăn chặn", score_percentage: 42 },
  { topic_category: "Thẩm quyền xét xử", score_percentage: 55 },
  { topic_category: "Chứng cứ và chứng minh", score_percentage: 61 }
];

export const MOCK_DASHBOARD_STATS: DashboardStats = {
  total_quiz_attempts: 8,
  average_score: 71,
  dieu_studied_count: 34
};
