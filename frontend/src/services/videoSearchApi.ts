import { fetchEventSource } from '@microsoft/fetch-event-source';
import api from './api';

export interface VideoSearchRequest {
  query: string;
  token?: string | null;
  conversation_id?: number | null;
}

export interface VideoSearchResponse {
  reply: string;
  tool_name: string;
  tool_arguments: {
    keywords: string;
  };
  course: {
    is_match: boolean;
    course_title: string;
    lesson_url: string;
  };
}

export async function searchCourseVideo(
  data: VideoSearchRequest,
): Promise<VideoSearchResponse> {
  const response = await api.post<VideoSearchResponse>('/api/video-search/course', data);
  return response.data;
}

export interface VideoSearchStreamHandlers {
  onConversation?: (payload: { conversation: VideoSearchConversation }) => void;
  onMessage?: (delta: string) => void;
  onToolCall?: (payload: { name: string; arguments: { keywords: string } }) => void;
  onVideo?: (payload: {
    keywords: string;
    course: VideoSearchResponse['course'];
  }) => void;
  onError?: (message: string) => void;
  onDone?: (payload: { ok?: boolean; message?: VideoSearchMessageRecord }) => void;
}

export interface VideoSearchMessageRecord {
  id: number;
  role: 'user' | 'assistant' | string;
  content: string;
  tool_name?: string | null;
  tool_arguments?: string | null;
  video_result?: string | null;
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
  created_at: string;
}

export interface VideoSearchConversation {
  id: number;
  title: string;
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
  created_at: string;
  updated_at: string;
}

export interface VideoSearchConversationDetail extends VideoSearchConversation {
  messages: VideoSearchMessageRecord[];
}

export async function listVideoSearchConversations(
  token?: string | null,
): Promise<VideoSearchConversation[]> {
  const response = await api.get<VideoSearchConversation[]>('/api/video-search/conversations', {
    params: { token },
  });
  return response.data;
}

export async function getVideoSearchConversation(
  id: number,
  token?: string | null,
): Promise<VideoSearchConversationDetail> {
  const response = await api.get<VideoSearchConversationDetail>(
    `/api/video-search/conversations/${id}`,
    { params: { token } },
  );
  return response.data;
}

export async function streamCourseVideoSearch(
  data: VideoSearchRequest,
  handlers: VideoSearchStreamHandlers,
  signal?: AbortSignal,
): Promise<void> {
  const adminToken = localStorage.getItem('adminToken');
  await fetchEventSource('/api/video-search/chat/stream', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(adminToken ? { Authorization: `Bearer ${adminToken}` } : {}),
    },
    body: JSON.stringify(data),
    signal,
    openWhenHidden: true,
    async onopen(response) {
      if (!response.ok) {
        throw new Error(`视频搜索请求失败: ${response.status}`);
      }
    },
    onmessage(event) {
      const payload = JSON.parse(event.data);
      if (event.event === 'conversation') {
        handlers.onConversation?.(payload);
      } else if (event.event === 'message') {
        handlers.onMessage?.(payload.delta ?? '');
      } else if (event.event === 'tool_call') {
        handlers.onToolCall?.(payload);
      } else if (event.event === 'video') {
        handlers.onVideo?.(payload);
      } else if (event.event === 'error') {
        handlers.onError?.(payload.message ?? '视频搜索失败');
      } else if (event.event === 'done') {
        handlers.onDone?.(payload);
      }
    },
    onerror(error) {
      throw error;
    },
  });
}
