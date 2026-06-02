import os
import json
import dashscope

TEST_IMAGE_PATH = "/Users/sherry/Downloads/2022年度/008cwwbSgy1hb1zrl1315j30u0780b29.jpg"

def main():
    # 优先从环境变量取，或者直接硬编码（针对当前PoC）
    api_key = os.environ.get("DASHSCOPE_API_KEY", "sk-0d7a29f3aa1a46f6913083ba70629a2d")
    dashscope.api_key = api_key

    print(f"正在分析长图: {TEST_IMAGE_PATH} ...")
    print("这大概需要 10-20 秒，请耐心等待...")

    prompt = """
    你是一个严谨的护肤美妆配方师兼数据标注专家。
    这是一张包含多个美妆护肤产品的“年度爱用”长图。图中每个产品通常会有产品图片、名称、以及相关的评价或成分说明。
    
    你的核心任务是：
    1. 仔细阅读这张长图，识别出图中出现的所有独立产品（预计约5个）。必须保持图层和上下文对齐，绝不能把A产品的成分归属到B产品上。
    2. 针对每个产品，提取出以下结构化信息。如果图中根本未提及某项信息，请如实填写 "未提及"，绝不要自行编造（幻觉）。
       - 产品名称 (Product Name)
       - 核心成分 (Key Ingredients)
       - 适用肤质 (Suitable Skin Types)
       - 核心功效 (Main Efficacy)
    
    请务必仅输出合法的 JSON 格式数组，不要包含任何 markdown 标记或其他多余文字，格式如下：
    [
      {
        "产品名称": "...",
        "核心成分": "...",
        "适用肤质": "...",
        "核心功效": "..."
      }
    ]
    """

    messages = [
        {
            "role": "user",
            "content": [
                {"image": f"file://{TEST_IMAGE_PATH}"},
                {"text": prompt}
            ]
        }
    ]

    try:
        response = dashscope.MultiModalConversation.call(
            model='qwen-vl-max',
            messages=messages
        )
        
        if response.status_code == 200:
            content = response.output.choices[0].message.content[0].get("text", "")
            
            # 清洗 markdown
            text = content.strip()
            if text.startswith("```json"):
                text = text[7:]
            elif text.startswith("```"):
                text = text[3:]
            if text.endswith("```"):
                text = text[:-3]
            text = text.strip()

            print("\n================ 解析成功 ================")
            try:
                parsed_data = json.loads(text)
                print(json.dumps(parsed_data, indent=2, ensure_ascii=False))
                print("==========================================")
            except json.JSONDecodeError:
                print("【错误】模型未返回合法的 JSON，原始输出为：\n", text)
        else:
            print(f"【错误】API调用失败: {response.code} - {response.message}")
            
    except Exception as e:
        print(f"【错误】程序异常: {e}")

if __name__ == "__main__":
    main()
