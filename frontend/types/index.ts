export interface User {
  id: string;
  email: string;
  is_active: boolean;
  created_at: string;
  updated_at?: string;
}

export interface Message {
  role: 'user' | 'assistant';
  content: string;
  timestamp: string;
  sources?: SearchResult[];
}

export interface ChatThread {
  id: string;
  title: string;
  messages: Message[];
  created: string;
  last_updated: string;
  user_id: string;
}

export interface SearchResult {
  id: string;
  score: number;
  content: string;
  title: string;
  explicit?: boolean;
  full_content?: string;
  keyword_score?: number;
  matched_keywords?: string[];
  linked_contexts?: LinkedContext[];
}

export interface LinkedContext {
  note_path: string;
  relevance: number;
  context: string;
}

export interface UserSettings {
  personal_info: string;
  memory: string;
  model: string;
  openai_api_key?: string;
  excluded_folders: string[];
  suggested_prompts: string[];
}

export interface FileUpload {
  file_id: string;
  filename: string;
  upload_time: string;
  status: string;
  embedding_status?: string;
}

export interface ChatResponse {
  content: string;
  sources?: SearchResult[];
  thread_id: string;
  done: boolean;
} 