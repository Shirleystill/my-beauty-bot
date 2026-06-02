import os
import glob
import sys
import dashscope

# 配置环境变量与目录
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
API_KEY_PATH = os.path.join(BASE_DIR, "API_KEY.txt")
KB_DIR = os.path.join(BASE_DIR, "knowledge_base")

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
            
            # 简单粗暴的分块策略：按照 "### "（产品级）和 "## 1."（正文级）切分
            parts = content.split("### ")
            # 第一个 part 通常包含博主正文和元数据
            header_part = parts[0]
            if "## 1. 微博正文内容" in header_part:
                main_text = header_part.split("## 1. 微博正文内容")[1].split("## 2.")[0].strip()
                if main_text and len(main_text) > 20:
                    chunks.append(f"[博主日常感悟/正文]\n{main_text}")
            
            # 剩下的 parts 都是独立的产品
            for p in parts[1:]:
                if p.strip():
                    chunks.append(f"[产品评价]\n{p.strip()}")
    return chunks

def retrieve_chunks(query, chunks, top_k=5):
    """
    纯 Python 实现的轻量级本地检索器 (基于 N-gram 字符匹配度)
    无需安装向量数据库，适合十万字级别的 MVP 场景
    """
    def score_chunk(q, c):
        score = 0
        # 2-gram 匹配
        for i in range(len(q) - 1):
            if q[i:i+2] in c:
                score += 2
        # 单字匹配 (权重低)
        for char in q:
            if char in c:
                score += 0.5
        # 惩罚过长的无用文本，稍微提升精准度
        return score / (len(c) ** 0.1)

    scored_chunks = [(score_chunk(query, c), c) for c in chunks]
    # 过滤掉零分项并排序
    scored_chunks = sorted([x for x in scored_chunks if x[0] > 0], key=lambda x: x[0], reverse=True)
    return [c for score, c in scored_chunks[:top_k]]

def build_system_prompt():
    """我们在此前【专题 B】中提炼的文风字典与人格约束"""
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

def chat_loop():
    if not dashscope.api_key:
        print("【错误】缺少 DashScope API Key。")
        return
        
    print("[+] 正在加载专属知识库...")
    chunks = load_knowledge_base()
    print(f"[+] 加载完成！共切分出 {len(chunks)} 个知识卡片。")
    print("==================================================")
    print("✨ 博主数字分身已上线 (输入 'quit' 退出) ✨")
    print("==================================================\n")
    
    # 初始化历史对话
    messages = [{'role': 'system', 'content': build_system_prompt()}]
    
    while True:
        try:
            user_input = input("👩‍🦰 粉丝 (你): ").strip()
            if user_input.lower() in ['quit', 'exit', 'q']:
                break
            if not user_input:
                continue
                
            # 1. 本地检索
            relevant_chunks = retrieve_chunks(user_input, chunks, top_k=5)
            context_text = "\n\n---\n\n".join(relevant_chunks)
            
            # 2. 组装 Prompt
            prompt = f"【粉丝问题】: {user_input}\n\n【检索到的知识库事实】:\n{context_text}"
            messages.append({'role': 'user', 'content': prompt})
            
            # 3. 调用大模型
            print("🤖 分身 (思考中...) \r", end="")
            response = dashscope.Generation.call(
                model='qwen-max',
                messages=messages,
                result_format='message',
                stream=True
            )
            
            print("💅 分身回复: ", end="")
            full_response = ""
            for chunk in response:
                if chunk.status_code == 200:
                    delta = chunk.output.choices[0].message.content
                    # 避免重复打印，通过计算差异来实现打字机效果
                    new_text = delta[len(full_response):]
                    print(new_text, end="", flush=True)
                    full_response = delta
                else:
                    print(f"\n[-] 接口报错: {chunk.code} - {chunk.message}")
                    break
            print("\n")
            
            # 剔除带有冗长上下文的 user prompt，用精简的 query 替换以节省历史 Token
            messages[-1] = {'role': 'user', 'content': user_input}
            messages.append({'role': 'assistant', 'content': full_response})
            
        except KeyboardInterrupt:
            print("\n[+] 退出对话。")
            break
        except Exception as e:
            print(f"\n[-] 发生错误: {e}")

if __name__ == "__main__":
    chat_loop()
