// TODO: Phase 5a/5b v2 backend chưa xong, dùng mock tạm (xem requirements.md "Phase 5a/5b v2").
// Đây là mock CỤC BỘ riêng cho 3 màn hình mới (/quiz, /essay, /essay/practice) - KHÔNG đi qua
// NEXT_PUBLIC_USE_MOCK_DATA / lib/api.ts / lib/mockData.ts, vì cơ chế đó đang phục vụ Chat/Dashboard
// với dữ liệu thật và Quiz/Essay Phase 5a/5b gốc vẫn cắm backend thật (xem quiz_service.py,
// essay_service.py). Việc route /quiz và /essay khỏi backend thật ở đây là TẠM THỜI - đã xác nhận
// với người dùng: PHẢI hoàn thành Bước 2 (backend thật cho ngân hàng đề mới) trước khi nhóm luật UAT.
import type {
  EssayBankCategory,
  EssayBankV2,
  EssaySubmitResponse,
  PracticeQuestionV2,
  QuizAnswer,
  QuizQuestion,
  QuizSetSummaryV2,
  QuizSubmitResponse
} from "@/lib/types";

const MIN_MOCK_DELAY_MS = 300;
const MAX_MOCK_DELAY_MS = 500;

export function withMockDelayV2<T>(value: T): Promise<T> {
  const delay = MIN_MOCK_DELAY_MS + Math.random() * (MAX_MOCK_DELAY_MS - MIN_MOCK_DELAY_MS);
  return new Promise((resolve) => setTimeout(() => resolve(value), delay));
}

export const QUIZ_SET_V2_TOTAL_QUESTIONS = 5;
export const QUIZ_SET_V2_COUNT = 15;

// Trạng thái mẫu để demo đủ 3 trạng thái UI (đã làm/đang làm/chưa làm) như trong Figma
// export (QuizSelectionPage.makeInitialSets) - không phải dữ liệu thật của user nào.
export const MOCK_QUIZ_SETS_V2: QuizSetSummaryV2[] = Array.from({ length: QUIZ_SET_V2_COUNT }, (_, index) => {
  const quizSetId = index + 1;
  const total = QUIZ_SET_V2_TOTAL_QUESTIONS;

  if (quizSetId === 1) return { quiz_set_id: quizSetId, total_questions: total, status: { kind: "done", correct_count: 5 } };
  if (quizSetId === 2) return { quiz_set_id: quizSetId, total_questions: total, status: { kind: "done", correct_count: 4 } };
  if (quizSetId === 3) return { quiz_set_id: quizSetId, total_questions: total, status: { kind: "done", correct_count: 3 } };
  if (quizSetId === 4) return { quiz_set_id: quizSetId, total_questions: total, status: { kind: "in_progress", correct_count: 2 } };
  if (quizSetId === 5) return { quiz_set_id: quizSetId, total_questions: total, status: { kind: "done", correct_count: 5 } };
  if (quizSetId === 6) return { quiz_set_id: quizSetId, total_questions: total, status: { kind: "done", correct_count: 4 } };
  return { quiz_set_id: quizSetId, total_questions: total, status: { kind: "untouched", correct_count: 0 } };
});

// 75 câu mcq_4choice thuần túy đã có sẵn từ Phase 5a gốc (xem requirements.md) sẽ mix ngẫu
// nhiên vào 15 bộ x 5 câu khi Bước 2 xong. Ở đây chỉ có 5 câu mẫu, tái dùng lại cho mọi bộ đề
// (đổi question_id theo quiz_set_id để không đụng nhau) - đủ để demo luồng làm bài/nộp bài.
const QUIZ_QUESTION_TEMPLATES: Array<{ text: string; options: string[]; correctIndex: number; dieu: string; topic: string }> = [
  {
    text: "Theo Điều 111 BLTTHS 2015, ai có quyền bắt người phạm tội quả tang?",
    options: ["Chỉ Cơ quan điều tra", "Chỉ Viện kiểm sát", "Bất kỳ người nào cũng có quyền bắt", "Chỉ Tòa án"],
    correctIndex: 2,
    dieu: "111",
    topic: "Biện pháp ngăn chặn"
  },
  {
    text: "Nguyên tắc suy đoán vô tội (Điều 13 BLTTHS 2015) đặt nghĩa vụ chứng minh tội phạm thuộc về ai?",
    options: [
      "Người bị buộc tội",
      "Luật sư bào chữa",
      "Cơ quan có thẩm quyền tiến hành tố tụng",
      "Người bị hại"
    ],
    correctIndex: 2,
    dieu: "13",
    topic: "Nguyên tắc cơ bản"
  },
  {
    text: "Theo Điều 143 BLTTHS 2015, khởi tố vụ án hình sự dựa trên căn cứ nào?",
    options: [
      "Khi có dấu hiệu tội phạm",
      "Khi bị can nhận tội",
      "Khi có bản án sơ thẩm",
      "Khi hết thời hiệu truy cứu"
    ],
    correctIndex: 0,
    dieu: "143",
    topic: "Khởi tố vụ án"
  },
  {
    text: "Theo Điều 179 BLTTHS 2015, khởi tố bị can được thực hiện khi nào?",
    options: [
      "Ngay khi khởi tố vụ án",
      "Khi có đủ căn cứ xác định người thực hiện hành vi phạm tội",
      "Chỉ sau khi xét xử sơ thẩm",
      "Khi Viện kiểm sát yêu cầu bất kỳ lúc nào không cần căn cứ"
    ],
    correctIndex: 1,
    dieu: "179",
    topic: "Khởi tố bị can"
  },
  {
    text: "Theo Điều 113 BLTTHS 2015, lệnh bắt bị can để tạm giam (trừ trường hợp khẩn cấp) phải được ai phê chuẩn?",
    options: ["Viện kiểm sát cùng cấp", "Ủy ban nhân dân xã", "Trưởng Công an xã", "Không cần phê chuẩn"],
    correctIndex: 0,
    dieu: "113",
    topic: "Biện pháp ngăn chặn"
  }
];

export function getMockQuizQuestionsV2(quizSetId: number): QuizQuestion[] {
  return QUIZ_QUESTION_TEMPLATES.map((template, index) => ({
    question_id: `quiz-v2-set${quizSetId}-q${index + 1}`,
    question_text: template.text,
    mcq_options: template.options,
    dieu_number: template.dieu,
    topic_category: template.topic
  }));
}

export function gradeMockQuizV2(quizSetId: number, answers: QuizAnswer[]): QuizSubmitResponse {
  const questions = getMockQuizQuestionsV2(quizSetId);

  const results = answers.map((answer) => {
    const index = questions.findIndex((question) => question.question_id === answer.question_id);
    const template = QUIZ_QUESTION_TEMPLATES[index];
    const correctOption = template?.options[template.correctIndex] ?? "";

    return {
      question_id: answer.question_id,
      is_correct: answer.selected_option === correctOption,
      mcq_correct: correctOption,
      dieu_number: template?.dieu ?? ""
    };
  });

  const score = results.filter((result) => result.is_correct).length;
  return { score, total: results.length, results };
}

// Số liệu "Bán trắc nghiệm" (15 câu) là số THẬT đã biết từ dữ liệu cũ (15 câu mcq_true_false
// chuyển từ trắc nghiệm sang, xem requirements.md). 3 ngân hàng còn lại (Lý thuyết/Vận dụng/
// Tình huống) chưa có ngân hàng đề mới - số liệu dưới đây là MOCK tạm, không phải số thật.
export const MOCK_ESSAY_BANKS_V2: EssayBankV2[] = [
  {
    category: "ly_thuyet",
    title: "Lý thuyết",
    subtitle: "Khái niệm & Nguyên tắc",
    description: "Câu hỏi về khái niệm, nguyên tắc cơ bản của Bộ luật Tố tụng hình sự.",
    total_questions: 12,
    progress: { kind: "started", attempted_count: 7 }
  },
  {
    category: "van_dung",
    title: "Vận dụng",
    subtitle: "Áp dụng thực tiễn",
    description: "Câu hỏi vận dụng quy định pháp luật vào các tình huống cụ thể.",
    total_questions: 10,
    progress: { kind: "complete", attempted_count: 10 }
  },
  {
    category: "ban_trac_nghiem",
    title: "Bán trắc nghiệm",
    subtitle: "Nhận định Đúng / Sai",
    description: "Xác định nhận định đúng hay sai, có kèm giải thích lý luận chi tiết.",
    total_questions: 15,
    progress: { kind: "untouched", attempted_count: 0 }
  },
  {
    category: "tinh_huong",
    title: "Tình huống",
    subtitle: "Phân tích vụ án",
    description: "Phân tích tình huống thực tế dựa trên điều luật, quy trình tố tụng.",
    total_questions: 8,
    progress: { kind: "started", attempted_count: 2 }
  }
];

interface EssayBankQuestionSeed {
  question_id: string;
  question_text: string;
  dieu_number: string;
  topic_category: string;
  key_points: string[];
  suggested_dieu: string[];
}

const ESSAY_BANK_QUESTIONS_V2: Record<EssayBankCategory, EssayBankQuestionSeed[]> = {
  ly_thuyet: [
    {
      question_id: "essay-v2-ly-thuyet-1",
      question_text:
        "Phân biệt khởi tố vụ án hình sự và khởi tố bị can. Nêu căn cứ, thẩm quyền và hệ quả pháp lý của từng loại.",
      dieu_number: "143, 179",
      topic_category: "Khởi tố",
      key_points: [
        "Khởi tố vụ án căn cứ khi có dấu hiệu tội phạm (Điều 143), do CQĐT/VKS/HĐXX quyết định",
        "Khởi tố bị can khi có đủ căn cứ xác định người thực hiện hành vi phạm tội (Điều 179)",
        "Khởi tố vụ án là điều kiện tiên quyết trước khi khởi tố bị can",
        "Hệ quả: bị can có quyền được thông báo về tội danh bị khởi tố"
      ],
      suggested_dieu: ["143", "179"]
    }
  ],
  van_dung: [
    {
      question_id: "essay-v2-van-dung-1",
      question_text:
        "Anh A bị bắt quả tang đang thực hiện hành vi trộm cắp. Cảnh sát khu vực có quyền lập biên bản bắt người phạm tội quả tang không? Trình tự thủ tục tiếp theo là gì?",
      dieu_number: "111, 113",
      topic_category: "Biện pháp ngăn chặn",
      key_points: [
        "Bất kỳ người nào cũng có quyền bắt người phạm tội quả tang (Điều 111 khoản 1)",
        "Sau khi bắt, phải giải ngay đến CQĐT, VKS hoặc UBND cấp xã",
        "CQĐT phải lấy lời khai ngay và trong 12 giờ phải ra lệnh tạm giữ hoặc thả",
        "Biên bản bắt người phải được lập ngay tại chỗ, có người chứng kiến"
      ],
      suggested_dieu: ["111", "113"]
    }
  ],
  ban_trac_nghiem: [
    {
      question_id: "essay-v2-ban-trac-nghiem-1",
      question_text:
        "Nhận định: \"Trong mọi trường hợp, Viện kiểm sát phải phê chuẩn lệnh bắt tạm giam của Cơ quan điều tra trước khi thi hành.\" — Đúng hay sai? Giải thích.",
      dieu_number: "113, 119",
      topic_category: "Biện pháp ngăn chặn",
      key_points: [
        "SAI - có ngoại lệ quan trọng",
        "Trường hợp bắt khẩn cấp (Điều 110): có thể thi hành trước, VKS phê chuẩn hoặc không phê chuẩn trong 12 giờ",
        "Bắt tạm giam thông thường (Điều 113) phải có phê chuẩn của VKS trước khi thi hành",
        "Phân biệt rõ bắt khẩn cấp khác với bắt tạm giam - hai chế định khác nhau"
      ],
      suggested_dieu: ["110", "113"]
    }
  ],
  tinh_huong: [
    {
      question_id: "essay-v2-tinh-huong-1",
      question_text:
        "Bị cáo B bị truy tố về tội cướp giật tài sản. Tại phiên tòa sơ thẩm, B khai có alibi nhưng không có nhân chứng. HĐXX có được tuyên B có tội chỉ dựa trên lời khai của người bị hại không? Phân tích theo nguyên tắc suy đoán vô tội.",
      dieu_number: "13, 85",
      topic_category: "Nguyên tắc cơ bản",
      key_points: [
        "Nguyên tắc suy đoán vô tội: người bị buộc tội được coi là vô tội cho đến khi được chứng minh theo trình tự BLTTHS (Điều 13)",
        "Nghĩa vụ chứng minh thuộc về cơ quan tiến hành tố tụng, không phải bị can/bị cáo",
        "Lời khai đơn độc của người bị hại chưa đủ - phải có chứng cứ khác corroborate",
        "Mọi nghi ngờ không thể loại trừ phải được giải thích theo hướng có lợi cho bị can"
      ],
      suggested_dieu: ["13", "85"]
    }
  ]
};

export function getMockEssayBankQuestionsV2(category: EssayBankCategory) {
  return ESSAY_BANK_QUESTIONS_V2[category].map((seed) => ({
    question_id: seed.question_id,
    question_text: seed.question_text,
    dieu_number: seed.dieu_number,
    topic_category: seed.topic_category,
    bank_category: category
  }));
}

// Cùng heuristic overlap-từ-khóa đơn giản như gradeMockEssay (lib/mockData.ts) - chỉ để demo
// cấu trúc matched/missing, không phải LLM-as-judge thật (xem Phase 5b essay_service.py).
function gradeAgainstKeyPoints(questionId: string, userAnswer: string): EssaySubmitResponse {
  const seed = Object.values(ESSAY_BANK_QUESTIONS_V2)
    .flat()
    .find((item) => item.question_id === questionId);

  if (seed === undefined) {
    return { matched_points: [], missing_points: [], feedback: "Không tìm thấy rubric cho câu hỏi này.", suggested_dieu: [] };
  }

  const normalizedAnswer = userAnswer.toLowerCase();
  const matched: string[] = [];
  const missing: string[] = [];

  seed.key_points.forEach((point) => {
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

  return { matched_points: matched, missing_points: missing, feedback, suggested_dieu: seed.suggested_dieu };
}

export function gradeMockEssayBankV2(questionId: string, userAnswer: string): EssaySubmitResponse {
  return gradeAgainstKeyPoints(questionId, userAnswer);
}

// Minigame "Tôi hỏi bạn trả lời" - lấy ngẫu nhiên từ TOÀN BỘ pool tự luận (mọi category),
// legalRef/feedback hiển thị ngay trong phase trả lời câu hỏi lẫn phase xem kết quả, khác với
// luồng /essay/[category] (feedback chỉ hiện sau khi nộp bài).
const PRACTICE_BANK_LABELS: Record<EssayBankCategory, string> = {
  ly_thuyet: "Lý thuyết",
  van_dung: "Vận dụng",
  ban_trac_nghiem: "Bán trắc nghiệm",
  tinh_huong: "Tình huống"
};

export const MOCK_PRACTICE_QUESTIONS_V2: PracticeQuestionV2[] = (
  Object.entries(ESSAY_BANK_QUESTIONS_V2) as Array<[EssayBankCategory, EssayBankQuestionSeed[]]>
).flatMap(([category, seeds]) =>
  seeds.map((seed) => ({
    question_id: `practice-${seed.question_id}`,
    bank_category: category,
    bank_label: PRACTICE_BANK_LABELS[category],
    question_text: seed.question_text,
    legal_ref: `Điều ${seed.dieu_number} BLTTHS 2015`,
    key_points: seed.key_points,
    feedback:
      "Đây là câu hỏi luyện tập ngẫu nhiên từ toàn bộ ngân hàng tự luận. So sánh câu trả lời của bạn với các điểm cần có bên dưới."
  }))
);

export function getRandomMockPracticeQuestion(excludeQuestionId?: string): PracticeQuestionV2 {
  const candidates = MOCK_PRACTICE_QUESTIONS_V2.filter((question) => question.question_id !== excludeQuestionId);
  const pool = candidates.length > 0 ? candidates : MOCK_PRACTICE_QUESTIONS_V2;
  return pool[Math.floor(Math.random() * pool.length)];
}

export function gradeMockPracticeAnswer(question: PracticeQuestionV2, userAnswer: string): EssaySubmitResponse {
  const normalizedAnswer = userAnswer.toLowerCase();
  const matched: string[] = [];
  const missing: string[] = [];

  question.key_points.forEach((point) => {
    const firstKeyword = point.split(" ").slice(0, 3).join(" ").toLowerCase();
    if (normalizedAnswer.includes(firstKeyword.slice(0, 6))) {
      matched.push(point);
    } else {
      missing.push(point);
    }
  });

  return { matched_points: matched, missing_points: missing, feedback: question.feedback, suggested_dieu: [] };
}

// ============================================================================
// TODO: Phase 7 v2 - chờ Quiz v2/Essay v2 backend (Bước 2). Dashboard's Khối 1 (MCQ tổng hợp)
// và Khối 2 (4 tracker tự luận) đọc trực tiếp từ mock ở trên (MOCK_QUIZ_SETS_V2/
// MOCK_ESSAY_BANKS_V2) để nhất quán với những gì /quiz và /essay đang hiển thị - không tạo
// thêm 1 bộ mock riêng cho dashboard. Khi Bước 2 xong, thay getMockQuizOverallStatsV2() bằng
// GET /api/quiz/stats-v2 (hoặc tương đương) và MOCK_ESSAY_BANKS_V2 bằng GET /api/essay/banks thật.
// ============================================================================

export interface QuizOverallStatsV2 {
  overall_correct_percentage: number;
  correct_total: number;
  questions_attempted: number;
  sets_touched: number;
  total_sets: number;
}

export function getMockQuizOverallStatsV2(): QuizOverallStatsV2 {
  const touchedSets = MOCK_QUIZ_SETS_V2.filter((set) => set.status.kind !== "untouched");
  const correctTotal = touchedSets.reduce((acc, set) => acc + set.status.correct_count, 0);
  const questionsAttempted = touchedSets.length * QUIZ_SET_V2_TOTAL_QUESTIONS;

  return {
    overall_correct_percentage: questionsAttempted > 0 ? Math.round((correctTotal / questionsAttempted) * 100) : 0,
    correct_total: correctTotal,
    questions_attempted: questionsAttempted,
    sets_touched: touchedSets.length,
    total_sets: QUIZ_SET_V2_COUNT
  };
}

// TODO: Phase 7 v2 - chờ Quiz v2/Essay v2 backend (Bước 2). Mapping "topic_category (thật, từ
// GET /api/dashboard/weak-topics) -> essay bank category (Essay v2)" là TẠM, dựa trên từ khóa
// đơn giản - topic_category thật ở Phase 5a/5b gốc chưa từng được gắn với 1 trong 4 category
// Essay v2 (Lý thuyết/Vận dụng/Bán trắc nghiệm/Tình huống). Bước 2 cần thay bằng mapping thật
// dựa trên category thực sự của câu hỏi trong ngân hàng đề mới, không suy đoán theo từ khóa nữa.
export function mapWeakTopicToEssayBankCategoryMock(topicCategory: string): EssayBankCategory {
  const normalized = topicCategory.toLowerCase();

  if (normalized.includes("tình huống") || normalized.includes("vụ án")) {
    return "tinh_huong";
  }

  if (normalized.includes("vận dụng") || normalized.includes("áp dụng") || normalized.includes("thực tiễn")) {
    return "van_dung";
  }

  if (normalized.includes("đúng") || normalized.includes("sai") || normalized.includes("nhận định")) {
    return "ban_trac_nghiem";
  }

  return "ly_thuyet";
}
