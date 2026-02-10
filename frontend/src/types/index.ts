export interface Citation {
  doc_id: string;
  version_id: string;
  source_uri: string;
  title: string;
  start_offset: number;
  end_offset: number;
  text: string;
}

export interface Claim {
  text: string;
  citations: Citation[];
}

export interface Message {
  id: string;
  role: "user" | "assistant" | "system";
  content: string;
  claims?: Claim[];
  citations?: Citation[];
  mode?: "ANSWER" | "ASK_CLARIFYING" | "ABSTAIN_NO_EVIDENCE" | "ANSWER_WITH_CONFLICTS";
  confidence?: number;
  timestamp: Date;
  isStreaming?: boolean;
}

export interface QueryResponse {
  query_id: string;
  final_text: string;
  claims: Claim[];
  mode: "ANSWER" | "ASK_CLARIFYING" | "ABSTAIN_NO_EVIDENCE" | "ANSWER_WITH_CONFLICTS";
  confidence: number;
  followups: string[];
}

export interface UploadedFile {
  id: string;
  name: string;
  size: number;
  type: string;
  status: "uploading" | "uploaded" | "error";
}
