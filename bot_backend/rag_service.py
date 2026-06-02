import os
import glob
import dashscope

# 配置环境变量与目录
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
API_KEY_PATH = os.path.join(BASE_DIR, "API_KEY.txt")
KB_DIR = os.path.join(BASE_DIR, "knowledge_base")

def init_api_key():
    if os.path.exists(API_KEY_PATH):
        with open(API_KEY_PATH, "r", encoding="utf-8") as f:
            os.environ["DASHSCOPE_API_KEY"] = f.read().strip()
    dashscope.api_key = os.environ.get("DASHSCOPE_API_KEY")

def load_knowledge_base():
    """读取并切块本地知识库"""
    chunks = []
    if not os.path.exists(KB_DIR):
        print(f"[-] 知识库目录不存在: {KB_DIR}")
        return chunks
        
    for file_path in glob.glob(os.path.join(KB_DIR, "*.md")):
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
            
            parts = content.split("### ")
            header_part = parts[0]
            if "## 1. 微博正文内容" in header_part:
                main_text = header_part.split("## 1. 微博正文内容")[1].split("## 2.")[0].strip()
                if main_text and len(main_text) > 20:
                    chunks.append(f"[博主日常感悟/正文]\n{main_text}")
            
            for p in parts[1:]:
                if p.strip():
                    chunks.append(f"[产品评价]\n{p.strip()}")
    return chunks

def retrieve_chunks(query, chunks, top_k=5):
    """本地检索器 (基于 N-gram 字符匹配度)"""
    def score_chunk(q, c):
        score = 0
        for i in range(len(q) - 1):
            if q[i:i+2] in c:
                score += 2
        for char in q:
            if char in c:
                score += 0.5
        return score / (len(c) ** 0.1)

    scored_chunks = [(score_chunk(query, c), c) for c in chunks]
    scored_chunks = sorted([x for x in scored_chunks if x[0] > 0], key=lambda x: x[0], reverse=True)
    return [c for score, c in scored_chunks[:top_k]]

def build_system_prompt():
    return """
[Role]
你是一位资深、理智、见多识广的美妆护肤博主。
现在有粉丝向你提问。你需要根据【检索到的知识库事实】（即你以前写过的心得），像回复朋友一样，自然、连贯、口语化地给粉丝写一段回复。

[Constraints - 极其重要]
1. 像真人聊天（严禁没头没尾）：回复必须要有自然的开头过渡（例如：“手干裂确实难受，你可以试试…” 或者 “这个诉求的话，我首推…”），不要像机器一样干巴巴地背书或生硬截断。
2. 融会贯通，拒绝生搬硬套：请把【检索到的事实】当做你的脑内记忆，消化后用口语重新组织说出来。绝对不要生硬地“复制粘贴”给出的片段。
3. 语气约束：保持理智、略带傲娇的实干派口吻。不刻意讨好，靠真实体验和成分逻辑说服人。
4. 句式风格：你可以灵活采用“欲扬先抑”的叙事（即先吐槽它某个缺点比如包装丑、味道怪、初印象一般，然后再夸它的核心绝杀功效），但不要死板，请根据具体产品自然发挥。
5. 禁忌词汇：绝对禁止使用烂大街的小红书套话（如：绝绝子、亲妈、闭眼冲、YYDS、天花板）。
6. 幻觉控制：只基于【检索到的事实】推荐。如果知识库中没有对应的产品，直接用高冷语气回复“最近没用到好用的相关产品，不瞎推”。

[Output]
直接输出自然、连贯的博主回复，字数控制在 150 字左右。
"""

# 在模块加载时初始化数据
init_api_key()
GLOBAL_CHUNKS = load_knowledge_base()

def generate_chat_stream(query: str, history: list):
    """
    生成流式对话响应，结合历史记录
    """
    if not dashscope.api_key:
        yield '{"error": "Missing API Key"}'
        return
        
    relevant_chunks = retrieve_chunks(query, GLOBAL_CHUNKS, top_k=5)
    context_text = "\n\n---\n\n".join(relevant_chunks)
    
    prompt = f"【粉丝问题】: {query}\n\n【检索到的知识库事实】:\n{context_text}"
    
    messages = [{'role': 'system', 'content': build_system_prompt()}]
    
    # 填入历史记录（简化处理，只传前几轮避免token过长）
    for msg in history[-4:]:
        messages.append({'role': msg.get('role', 'user'), 'content': msg.get('content', '')})
        
    messages.append({'role': 'user', 'content': prompt})
    
    try:
        response = dashscope.Generation.call(
            model='qwen-max',
            messages=messages,
            result_format='message',
            stream=True
        )
        
        full_response = ""
        for chunk in response:
            if chunk.status_code == 200:
                delta = chunk.output.choices[0].message.content
                new_text = delta[len(full_response):]
                if new_text:
                    # 返回 SSE 格式的字符串
                    # 这里为了兼容大多数前端简单处理，我们只发送文本片段
                    # 在实际的 FastAPI StreamingResponse 中可以 yields "data: content\n\n"
                    import json
                    yield f"data: {json.dumps({'content': new_text})}\n\n"
                full_response = delta
            else:
                import json
                yield f"data: {json.dumps({'error': f'接口报错: {chunk.code} - {chunk.message}'})}\n\n"
                break
    except Exception as e:
        import json
        yield f"data: {json.dumps({'error': str(e)})}\n\n"
