import { useEffect, useMemo, useRef, useState } from 'react';
import DOMPurify from 'dompurify';
import {
  Button,
  Card,
  Empty,
  Input,
  List,
  Space,
  Spin,
  Tag,
  Typography,
  message,
} from 'antd';
import {
  ClearOutlined,
  LinkOutlined,
  SearchOutlined,
  VideoCameraOutlined,
} from '@ant-design/icons';
import { useServiceToken } from '../hooks/useServiceToken';
import {
  getVideoSearchConversation,
  listVideoSearchConversations,
  streamCourseVideoSearch,
  type VideoSearchConversation,
  type VideoSearchMessageRecord,
  type VideoSearchResponse,
} from '../services/videoSearchApi';

const { Paragraph, Text, Title } = Typography;
const { TextArea } = Input;

type VideoPayload = {
  keywords: string;
  course: VideoSearchResponse['course'];
};

type ChatMessage = {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  promptTokens?: number;
  completionTokens?: number;
  totalTokens?: number;
  toolCall?: {
    name: string;
    arguments: { keywords: string };
  };
  video?: VideoPayload;
};

const EXAMPLE_PROMPTS = [
  '帮我找一个讲解肿瘤微环境治疗的视频',
  '我想看乳腺癌术后辅助治疗方案的视频',
  '找一个关于糖尿病并发症管理的临床教学视频',
];

function parseToolArguments(value?: string | null): ChatMessage['toolCall'] | undefined {
  if (!value) return undefined;
  try {
    const args = JSON.parse(value);
    return { name: 'course_video_search', arguments: args };
  } catch {
    return undefined;
  }
}

function parseVideoResult(value?: string | null): VideoPayload | undefined {
  if (!value) return undefined;
  try {
    return JSON.parse(value);
  } catch {
    return undefined;
  }
}

function fromRecord(record: VideoSearchMessageRecord): ChatMessage {
  return {
    id: String(record.id),
    role: record.role === 'user' ? 'user' : 'assistant',
    content: record.content || '',
    promptTokens: record.prompt_tokens,
    completionTokens: record.completion_tokens,
    totalTokens: record.total_tokens,
    toolCall: parseToolArguments(record.tool_arguments),
    video: parseVideoResult(record.video_result),
  };
}

function createMessage(role: ChatMessage['role'], content: string): ChatMessage {
  return {
    id: `${Date.now()}-${Math.random().toString(16).slice(2)}`,
    role,
    content,
  };
}

function markdownToHtml(markdown: string): string {
  const escaped = markdown
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');

  const html = escaped
    .replace(/```([\s\S]*?)```/g, '<pre><code>$1</code></pre>')
    .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
    .replace(/`([^`]+)`/g, '<code>$1</code>')
    .replace(/\[([^\]]+)\]\((https?:\/\/[^)]+)\)/g, '<a href="$2" target="_blank" rel="noreferrer">$1</a>')
    .replace(/\n/g, '<br />');

  return DOMPurify.sanitize(html);
}

function MarkdownText({ content }: { content: string }) {
  const html = useMemo(() => markdownToHtml(content), [content]);
  return (
    <div
      style={{ lineHeight: 1.8 }}
      dangerouslySetInnerHTML={{ __html: html }}
    />
  );
}

export default function VideoSearchExamplePage() {
  const { serviceToken } = useServiceToken();
  const abortRef = useRef<AbortController | null>(null);
  const [input, setInput] = useState('');
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [conversations, setConversations] = useState<VideoSearchConversation[]>([]);
  const [currentConversationId, setCurrentConversationId] = useState<number | null>(null);
  const [conversationsLoading, setConversationsLoading] = useState(false);
  const [loading, setLoading] = useState(false);

  const loadConversations = async () => {
    setConversationsLoading(true);
    try {
      setConversations(await listVideoSearchConversations(serviceToken));
    } catch {
      message.error('对话列表加载失败');
    } finally {
      setConversationsLoading(false);
    }
  };

  useEffect(() => {
    void loadConversations();
  }, [serviceToken]);

  const updateAssistant = (
    messageId: string,
    updater: (message: ChatMessage) => ChatMessage,
  ) => {
    setMessages((prev) =>
      prev.map((item) => (item.id === messageId ? updater(item) : item)),
    );
  };

  const handleSubmit = async () => {
    const query = input.trim();
    if (!query || loading) return;

    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    const assistantMessage = createMessage('assistant', '');
    setInput('');
    setLoading(true);
    setMessages((prev) => [...prev, createMessage('user', query), assistantMessage]);

    try {
      await streamCourseVideoSearch(
        {
          query,
          token: serviceToken,
          conversation_id: currentConversationId,
        },
        {
          onConversation: ({ conversation }) => {
            setCurrentConversationId(conversation.id);
            setConversations((prev) => {
              const withoutCurrent = prev.filter((item) => item.id !== conversation.id);
              return [conversation, ...withoutCurrent];
            });
          },
          onMessage: (delta) => {
            updateAssistant(assistantMessage.id, (item) => ({
              ...item,
              content: item.content + delta,
            }));
          },
          onToolCall: (toolCall) => {
            updateAssistant(assistantMessage.id, (item) => ({
              ...item,
              toolCall,
            }));
          },
          onVideo: (video) => {
            updateAssistant(assistantMessage.id, (item) => ({
              ...item,
              video,
            }));
          },
          onError: (errorText) => {
            updateAssistant(assistantMessage.id, (item) => ({
              ...item,
              content: item.content || errorText,
            }));
            message.error(errorText);
          },
          onDone: (payload) => {
            if (payload.message) {
              updateAssistant(assistantMessage.id, (item) => ({
                ...item,
                id: String(payload.message!.id),
                promptTokens: payload.message!.prompt_tokens,
                completionTokens: payload.message!.completion_tokens,
                totalTokens: payload.message!.total_tokens,
              }));
            }
            setLoading(false);
            void loadConversations();
          },
        },
        controller.signal,
      );
    } catch (err: any) {
      if (err?.name !== 'AbortError') {
        const errorText = err?.message || '视频搜索失败';
        updateAssistant(assistantMessage.id, (item) => ({
          ...item,
          content: item.content || errorText,
        }));
        message.error(errorText);
      }
    } finally {
      setLoading(false);
      abortRef.current = null;
    }
  };

  const handleClear = () => {
    abortRef.current?.abort();
    abortRef.current = null;
    setInput('');
    setMessages([]);
    setLoading(false);
  };

  const handleNewConversation = () => {
    handleClear();
    setCurrentConversationId(null);
  };

  const handleSelectConversation = async (id: number) => {
    if (loading) return;
    setCurrentConversationId(id);
    try {
      const detail = await getVideoSearchConversation(id, serviceToken);
      setMessages(detail.messages.map(fromRecord));
    } catch {
      message.error('对话加载失败');
    }
  };

  return (
    <div style={{ maxWidth: 1180, margin: '0 auto' }}>
      <div style={{ marginBottom: 20 }}>
        <Space align="center" size={10} style={{ marginBottom: 8 }}>
          <VideoCameraOutlined style={{ fontSize: 22, color: '#1a1a2e' }} />
          <Title level={4} style={{ margin: 0 }}>
            调用视频
          </Title>
        </Space>
      </div>

      <div className="chat-container" style={{ display: 'flex', flexWrap: 'wrap', gap: 16, alignItems: 'flex-start' }}>
        <Card
          size="small"
          title="对话记录"
          extra={
            <Button size="small" type="link" onClick={handleNewConversation}>
              新建
            </Button>
          }
          styles={{ body: { padding: 0 } }}
          style={{ width: 260, flex: '0 0 260px' }}
        >
          <List
            loading={conversationsLoading}
            dataSource={conversations}
            locale={{ emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无对话" /> }}
            renderItem={(item) => (
              <List.Item
                onClick={() => {
                  void handleSelectConversation(item.id);
                }}
                style={{
                  cursor: loading ? 'not-allowed' : 'pointer',
                  padding: '10px 12px',
                  background: currentConversationId === item.id ? '#f0f5ff' : '#fff',
                }}
              >
                <List.Item.Meta
                  title={
                    <Text ellipsis style={{ maxWidth: 210 }}>
                      {item.title}
                    </Text>
                  }
                  description={
                    <Text type="secondary" style={{ fontSize: 12 }}>
                      {item.total_tokens} tokens
                    </Text>
                  }
                />
              </List.Item>
            )}
          />
        </Card>

        <Card
          title="调用视频"
          styles={{ body: { padding: 0 } }}
          style={{ flex: '1 1 520px', minWidth: 320 }}
        >
          <div
            style={{
              minHeight: 440,
              maxHeight: 'calc(100vh - 360px)',
              overflowY: 'auto',
              padding: 20,
              background: '#fafafa',
            }}
          >
            {messages.length > 0 ? (
              <Space direction="vertical" size={16} style={{ width: '100%' }}>
                {messages.map((item) => (
                  <div
                    key={item.id}
                    style={{
                      display: 'flex',
                      justifyContent: item.role === 'user' ? 'flex-end' : 'flex-start',
                    }}
                  >
                    <div
                      style={{
                        width: item.role === 'assistant' ? 'min(760px, 92%)' : 'auto',
                        maxWidth: item.role === 'user' ? '76%' : '92%',
                        padding: '12px 14px',
                        borderRadius: 8,
                        background: item.role === 'user' ? '#1a1a2e' : '#fff',
                        border:
                          item.role === 'user'
                            ? '1px solid #1a1a2e'
                            : '1px solid #ececec',
                        color: item.role === 'user' ? '#fff' : '#1f1f1f',
                      }}
                    >
                      {item.content ? (
                        item.role === 'assistant' ? (
                          <MarkdownText content={item.content} />
                        ) : (
                          <div style={{ whiteSpace: 'pre-wrap' }}>{item.content}</div>
                        )
                      ) : (
                        <Space>
                          <Spin size="small" />
                          <Text type="secondary">正在思考...</Text>
                        </Space>
                      )}

                      {item.toolCall && (
                        <div style={{ marginTop: 12 }}>
                          <Tag color="blue">tool: {item.toolCall.name}</Tag>
                          <Tag>{item.toolCall.arguments.keywords}</Tag>
                        </div>
                      )}

                      {item.video && (
                        <div style={{ marginTop: 12 }}>
                          <Text strong>{item.video.course.course_title || '视频课程'}</Text>
                          {item.video.course.lesson_url ? (
                            <Space direction="vertical" size={8} style={{ width: '100%', marginTop: 8 }}>
                              <video
                                controls
                                src={item.video.course.lesson_url}
                                style={{
                                  width: '100%',
                                  maxHeight: 360,
                                  borderRadius: 8,
                                  background: '#000',
                                }}
                              >
                                当前浏览器不支持视频播放。
                              </video>
                              <Button
                                type="link"
                                icon={<LinkOutlined />}
                                href={item.video.course.lesson_url}
                                target="_blank"
                                rel="noreferrer"
                                style={{ padding: 0 }}
                              >
                                新窗口打开视频
                              </Button>
                            </Space>
                          ) : (
                            <Paragraph type="secondary" style={{ marginTop: 8, marginBottom: 0 }}>
                              暂无可播放链接。
                            </Paragraph>
                          )}
                        </div>
                      )}

                      {item.role === 'assistant' && item.totalTokens !== undefined && (
                        <div
                          style={{
                            marginTop: 10,
                            textAlign: 'right',
                            fontSize: 12,
                            color: '#8c8c8c',
                          }}
                        >
                          {item.totalTokens} tokens
                          {item.promptTokens !== undefined && item.completionTokens !== undefined && (
                            <span>
                              {' '}
                              ({item.promptTokens} / {item.completionTokens})
                            </span>
                          )}
                        </div>
                      )}
                    </div>
                  </div>
                ))}
              </Space>
            ) : (
              <Empty
                image={Empty.PRESENTED_IMAGE_SIMPLE}
                description="输入医疗视频搜索需求"
                style={{ marginTop: 120 }}
              />
            )}
          </div>

          <div style={{ padding: 16, borderTop: '1px solid #f0f0f0', background: '#fff' }}>
            <Space direction="vertical" size="middle" style={{ width: '100%' }}>
              <TextArea
                rows={4}
                value={input}
                disabled={loading}
                onChange={(event) => setInput(event.target.value)}
                placeholder="请输入医疗相关视频搜索需求，例如：帮我找一个讲解肿瘤微环境治疗的视频"
                onPressEnter={(event) => {
                  if (!event.shiftKey) {
                    event.preventDefault();
                    void handleSubmit();
                  }
                }}
              />

              <Space wrap>
                {EXAMPLE_PROMPTS.map((prompt) => (
                  <Button
                    key={prompt}
                    size="small"
                    disabled={loading}
                    onClick={() => setInput(prompt)}
                  >
                    {prompt}
                  </Button>
                ))}
              </Space>

              <Space>
                <Button
                  type="primary"
                  icon={<SearchOutlined />}
                  loading={loading}
                  disabled={!input.trim()}
                  onClick={() => {
                    void handleSubmit();
                  }}
                >
                  发送
                </Button>
                <Button
                  icon={<ClearOutlined />}
                  disabled={!input && messages.length === 0}
                  onClick={handleClear}
                >
                  清空
                </Button>
              </Space>
            </Space>
          </div>
        </Card>
      </div>
    </div>
  );
}
