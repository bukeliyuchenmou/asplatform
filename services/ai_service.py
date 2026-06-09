import httpx
import json
from typing import AsyncIterator, List


class AIService:
    def __init__(self, config: dict):
        self.api_key = config["api_key"]
        self.base_url = config["base_url"]
        self.model = config["model"]

    async def chat_completion(self, messages: list, temperature: float = 0.7):
        """
        Call the OpenAI-compatible API and return content + token usage.
        Returns: dict with {"content": str, "prompt_tokens": int, "completion_tokens": int, "total_tokens": int}
        Or on error: {"content": error_message, "prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        """
        # Fallback if no real key is provided
        if self.api_key == "your-api-key-here":
            return {
                "content": "[Mock Response] This is a mock response because no API key is set. Content would have been generated using OpenAI-compatible API.",
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0
            }

        # DeepSeek Reasoner or other slow LLMs might need longer timeout
        async with httpx.AsyncClient(timeout=300.0) as client:
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            payload = {
                "model": self.model,
                "messages": messages,
                "temperature": temperature
            }
            try:
                response = await client.post(f"{self.base_url}/chat/completions", headers=headers, json=payload)
                response.raise_for_status()
                data = response.json()
                content = data["choices"][0]["message"]["content"]
                usage = data.get("usage", {})
                return {
                    "content": content,
                    "prompt_tokens": usage.get("prompt_tokens", 0),
                    "completion_tokens": usage.get("completion_tokens", 0),
                    "total_tokens": usage.get("total_tokens", 0)
                }
            except httpx.ReadTimeout:
                return {
                    "content": "AI 服务响应超时，请稍后重试。生成长文本（如提纲或全文）时，大模型可能需要更长时间处理。",
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "total_tokens": 0
                }
            except Exception as e:
                return {
                    "content": f"AI 服务调用出错: {str(e)}",
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "total_tokens": 0
                }

    async def chat_completion_stream(
        self,
        messages: list,
        temperature: float = 0.7,
        tools: list | None = None,
        tool_choice: str | dict | None = "auto",
    ) -> AsyncIterator[dict]:
        if self.api_key == "your-api-key-here":
            yield {
                "type": "content",
                "content": "当前未配置 AI API Key，无法发起流式 tools 请求。",
            }
            return

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = tool_choice or "auto"

        tool_calls: dict[int, dict] = {}

        async with httpx.AsyncClient(timeout=300.0) as client:
            async with client.stream(
                "POST",
                f"{self.base_url}/chat/completions",
                headers=headers,
                json=payload,
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line.startswith("data:"):
                        continue

                    data = line.removeprefix("data:").strip()
                    if data == "[DONE]":
                        break

                    try:
                        chunk = json.loads(data)
                    except json.JSONDecodeError:
                        continue

                    choice = (chunk.get("choices") or [{}])[0]
                    usage = chunk.get("usage")
                    if usage:
                        yield {
                            "type": "usage",
                            "usage": {
                                "prompt_tokens": usage.get("prompt_tokens", 0),
                                "completion_tokens": usage.get("completion_tokens", 0),
                                "total_tokens": usage.get("total_tokens", 0),
                            },
                        }

                    delta = choice.get("delta") or {}
                    content = delta.get("content")
                    if content:
                        yield {"type": "content", "content": content}

                    for tool_call in delta.get("tool_calls") or []:
                        index = tool_call.get("index", 0)
                        current = tool_calls.setdefault(
                            index,
                            {
                                "id": "",
                                "type": "function",
                                "function": {"name": "", "arguments": ""},
                            },
                        )
                        if tool_call.get("id"):
                            current["id"] += tool_call["id"]
                        if tool_call.get("type"):
                            current["type"] = tool_call["type"]

                        function_delta = tool_call.get("function") or {}
                        if function_delta.get("name"):
                            current["function"]["name"] += function_delta["name"]
                        if function_delta.get("arguments"):
                            current["function"]["arguments"] += function_delta["arguments"]

        if tool_calls:
            yield {
                "type": "tool_calls",
                "tool_calls": [tool_calls[index] for index in sorted(tool_calls)],
            }

    async def generate_research_topics(self, discipline: str, research_direction: str, keywords: List[str], count: int = 5):
        prompt = f"""你是一位顶尖的学术导师。请结合最新的学术热点和期刊发表趋势，根据以下信息生成 {count} 个具有高度学术价值、创新性且合规可行的论著选题：

【输入信息】
学科领域：{discipline}
研究方向：{research_direction}
核心关键词：{', '.join(keywords)}

【输出要求】
请直接输出 JSON 格式，不要有任何多余的文字说明或 Markdown 代码块以外的内容。
格式如下：
{{
  "topics": [
    {{
      "title": "选题题目",
      "discipline_field": "具体学科细分领域",
      "research_hotspot": "当前研究热点简述",
      "innovation_level": "high/medium/low",
      "difficulty_level": "high/medium/low",
      "feasibility": "high/medium/low",
      "description": "选题的详细描述，包含研究背景、目的和预期贡献（约 150 字）",
      "extended_directions": ["扩展研究方向 1", "扩展研究方向 2", "扩展研究方向 3"]
    }}
  ]
}}
"""
        return await self.chat_completion([{"role": "user", "content": prompt}], temperature=0.8)

    async def analyze_topic(self, topic: str, discipline: str):
        from services import literature_service

        # Fetch real literature to provide as context
        # 1. Search for similar papers (more specific to the topic)
        similar_citations = await literature_service.search_literature(f"{topic} {discipline}", max_results=3)
        # 2. Search for recommended references (broader)
        recommended_citations = await literature_service.search_literature(topic, max_results=3)

        lit_context = "以下是从学术数据库检索到的真实文献，请务必在返回的 JSON 中使用这些信息：\n\n"

        if similar_citations:
            lit_context += "【可作为相似文献参考】：\n"
            for i, cit in enumerate(similar_citations):
                lit_context += f"- 题目：{cit['title']}, 作者：{', '.join(cit['authors'][:2])}, 来源：{cit['source']} ({cit['year']}), 链接：{cit.get('link', '')}\n"

        if recommended_citations:
            lit_context += "\n【可作为推荐参考文献】：\n"
            for i, cit in enumerate(recommended_citations):
                lit_context += f"- 题目：{cit['title']}, 作者：{', '.join(cit['authors'][:2])}, 来源：{cit['source']} ({cit['year']}), 链接：{cit.get('link', '')}\n"

        prompt = f"""你是一位资深的学术期刊审稿人。请对以下论著选题进行深度的可行性与创新性分析：

【选题信息】
题目：{topic}
学科：{discipline}

{lit_context}

【分析要求】
1. 请直接输出 JSON 格式，不要有任何多余的文字说明或 Markdown 代码块以外的内容。
2. 必须包含 similar_papers 数组和 recommended_references 数组。
3. 数组中的题目、作者、年份、来源和链接 **必须与上面提供的真实文献完全一致**。
4. 严禁编造任何 URL 链接。

格式如下：
{{
  "similar_papers": [
    {{
      "title": "题目",
      "authors": "作者",
      "journal": "期刊",
      "year": 2023,
      "similarity": 75,
      "summary": "内容简介",
      "link": "真实的链接"
    }}
  ],
  "overall_similarity": 65,
  "analysis": {{
    "innovation": "创新点分析",
    "scientific_value": "科学价值评估",
    "practical_significance": "实践意义评估"
  }},
  "research_background": "详细的研究背景介绍",
  "research_significance": "详细的研究意义阐述",
  "feasibility_analysis": "详细的可行性分析",
  "potential_innovations": ["创新点 1", "创新点 2"],
  "extended_directions": ["扩展方向 1", "扩展方向 2"],
  "recommended_references": [
    {{
      "title": "题目",
      "authors": "作者",
      "year": 2022,
      "source": "出版源",
      "link": "真实的链接"
    }}
  ]
}}
"""
        return await self.chat_completion([{"role": "user", "content": prompt}], temperature=0.7)

    async def refine_topic(self, topic: str, discipline: str, requirements: str):
        prompt = f"""你是一位资深的学术导师。用户选中了一个初步选题，并提出了进一步的细化要求。请根据这些信息生成一个更精准、更具研究价值的新选题。

【原始选题】
题目：{topic}
学科：{discipline}

【用户细化要求】
{requirements}

【输出要求】
请直接输出 JSON 格式，不要有任何多余的文字说明或 Markdown 代码块以外的内容。
格式如下：
{{
  "title": "细化后的新题目",
  "discipline_field": "具体学科细分领域",
  "research_hotspot": "当前研究热点简述",
  "innovation_level": "high/medium/low",
  "difficulty_level": "high/medium/low",
  "feasibility": "high/medium/low",
  "description": "细化后的选题详细描述",
  "extended_directions": ["扩展方向 1", "扩展方向 2"]
}}
"""
        return await self.chat_completion([{"role": "user", "content": prompt}], temperature=0.7)
