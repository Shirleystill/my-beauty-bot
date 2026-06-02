import os
import json
import time
import requests
import shutil
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright
import dashscope

# 批量处理的链接列表
BATCH_URLS = [
    "https://weibo.com/7514128928/Qr1NU4BwX",
    "https://weibo.com/7514128928/QkX7ijhQM",
    "https://weibo.com/7514128928/QcRUy6E0G",
    "https://weibo.com/7514128928/PdjSdzaHj",
    "https://weibo.com/7514128928/PaaKqq65Q",
    "https://weibo.com/7514128928/P8BEdnRWV",
    "https://weibo.com/7514128928/P6cCV8HZH",
    "https://weibo.com/7514128928/OEzlPBOau",
    "https://weibo.com/7514128928/NEYH8wG44",
    "https://weibo.com/7514128928/MsQdg66Yx"
]

# 配置环境变量与目录
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
API_KEY_PATH = os.path.join(BASE_DIR, "API_KEY.txt")
KB_DIR = os.path.join(BASE_DIR, "knowledge_base")
TEMP_IMG_DIR = os.path.join(BASE_DIR, "weibo_images_temp")

if os.path.exists(API_KEY_PATH):
    with open(API_KEY_PATH, "r") as f:
        os.environ["DASHSCOPE_API_KEY"] = f.read().strip()
dashscope.api_key = os.environ.get("DASHSCOPE_API_KEY")

# 确保知识库目录存在
if not os.path.exists(KB_DIR):
    os.makedirs(KB_DIR)

def download_image(url, save_dir, index):
    if not os.path.exists(save_dir):
        os.makedirs(save_dir)
    # 处理缺乏协议的 URL
    if url.startswith("//"):
        url = "https:" + url
    
    # 获取高清大图
    url = url.replace("/bmiddle/", "/large/").replace("/orj360/", "/large/").replace("/mw690/", "/large/")
    
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        ext = url.split('.')[-1]
        if len(ext) > 4 or not ext.isalpha():
            ext = "jpg"
        file_path = os.path.join(save_dir, f"image_{index}.{ext}")
        with open(file_path, "wb") as f:
            f.write(resp.content)
        return file_path
    except Exception as e:
        print(f"  [-] 下载图片失败 {url}: {e}")
        return None

def extract_json_from_image(image_path):
    prompt = """
    你是一个严谨的护肤美妆数据标注专家。
    这张图可能包含美妆产品，也可能是博主自拍、文字截图等纯配图。
    1. 请仔细识别图中的所有独立美妆产品。
    2. 如果这张图完全没有产品介绍（比如纯自拍、风景、聊天截图），请直接返回空数组: []
    3. 如果有产品，请针对每个产品提取以下信息：
       - 产品名称 (Product Name)
       - 核心成分 (Key Ingredients)
       - 适用肤质 (Suitable Skin Types)
       - 核心功效 (Main Efficacy)
       - 博主特色原话 (Original Quotes): 【极其重要】必须一字不差地从图中“逐字抄写”博主形容该产品的特色原话（包括吐槽、专业术语或比喻）。绝不允许你自己发散编造！
       - 博主使用心得 (Subjective Review): 【极其重要】一字不差地摘录博主在图中描述的具体质感、洗感、使用体验。严禁使用任何网络烂梗！没提就写“未提及”。
       
    只返回合法的 JSON 数组，格式:
    [
      {
        "产品名称": "...",
        "客观事实": {
            "核心成分": "...",
            "适用肤质": "...",
            "核心功效": "..."
        },
        "主观人格": {
            "博主特色原话": "...",
            "博主使用心得": "..."
        }
      }
    ]
    """
    messages = [
        {
            "role": "user",
            "content": [
                {"image": f"file://{image_path}"},
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
            if text.startswith("```json"): text = text[7:]
            elif text.startswith("```"): text = text[3:]
            if text.endswith("```"): text = text[:-3]
            text = text.strip()
            if text == "[]":
                return []
            return json.loads(text)
        else:
            print(f"  [-] 模型API失败: {response.code} {response.message}")
            return []
    except Exception as e:
        print(f"  [-] 提取图片时发生异常: {e}")
        return []

def main():
    if not dashscope.api_key:
        print("【严重错误】未找到 API Key。请确保 API_KEY.txt 文件存在且填写正确。")
        return

    print(f"[+] 准备处理 {len(BATCH_URLS)} 条链接。")
    print(f"[+] 知识库存放路径: {KB_DIR}")
    
    # --- 阶段 1: 启动浏览器并全局登录 ---
    print("\n[+] 正在启动浏览器，请准备扫码登录微博...")
    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(headless=False, channel="chrome")
        except Exception as e:
            print("\n【错误】调起本地 Chrome 失败。请确认你电脑上装了 Google Chrome 浏览器！")
            print(f"详情: {e}")
            return
            
        context = browser.new_context(viewport={'width': 1280, 'height': 800})
        page = context.new_page()
        
        # 访问微博主页用于通用登录
        page.goto("https://weibo.com/")
        input("\n>>> 【人工接管】请在弹出的浏览器中扫码登录微博。确认【已成功登录】后，回到终端按回车键继续！ <<<\n")
        
        # --- 阶段 2: 循环处理批量链接 ---
        for i, url in enumerate(BATCH_URLS):
            url = url.strip()
            if not url: continue
            
            # 提取 Post ID 作为缓存 Key
            # 处理末尾可能有 / 的情况
            post_id = url.rstrip('/').split('/')[-1]
            if "?" in post_id:
                post_id = post_id.split("?")[0]
            
            output_file = os.path.join(KB_DIR, f"{post_id}.md")
            
            print(f"\n=======================================================")
            print(f"[{i+1}/{len(BATCH_URLS)}] 正在处理: {url}")
            print(f"ID: {post_id}")
            
            # 【核心逻辑：检查缓存】
            if os.path.exists(output_file):
                print(f"[√] 命中本地缓存！该博文已存在于知识库，直接跳过 (阅后免焚)。")
                continue
                
            print(f"[*] 未命中缓存，开始抓取...")
            
            # 访问页面
            try:
                page.goto(url)
                # 等待页面加载（给一点缓冲时间让正文出现）
                page.wait_for_timeout(3000) 
            except Exception as e:
                print(f"[-] 页面访问失败: {e}")
                continue
            
            # 提取正文
            try:
                # 宽泛抓取常见微博正文节点，这里尽量取多一些类名以防微博改版
                article_text = page.locator("div.detail_wbtext_4CRf9, div.weibo-text, article").first.inner_text()
            except:
                article_text = "【未自动匹配到正文，或者该贴无正文文字】"
                
            print(f"  [+] 提取正文片段: {article_text[:50].replace(chr(10), ' ')}...")
            
            # 提取图片 URL
            image_elements = page.locator("img").all()
            image_urls = []
            for img in image_elements:
                src = img.get_attribute("src")
                if src and "sinaimg.cn" in src and ("bmiddle" in src or "orj360" in src or "large" in src or "mw690" in src):
                    if src not in image_urls:
                        image_urls.append(src)
            
            print(f"  [+] 共发现 {len(image_urls)} 张配图。")
            
            # 提取所有产品
            all_products = []
            if len(image_urls) > 0:
                print("  [+] 开始下载并调用视觉模型进行蒸馏...")
                for idx, img_url in enumerate(image_urls):
                    local_path = download_image(img_url, TEMP_IMG_DIR, idx)
                    if local_path:
                        products = extract_json_from_image(local_path)
                        if not products:
                            print(f"      -> 图[{idx+1}] 为非产品图，已过滤。")
                        else:
                            print(f"      -> 图[{idx+1}] 提取到 {len(products)} 个产品事实。")
                            all_products.extend(products)
            
            # --- 阶段 3: 组装 Markdown 并保存 ---
            md_content = f"# 微博图文知识库存档\n\n"
            md_content += f"**博文ID**: `{post_id}`\n"
            md_content += f"**源链接**: {url}\n\n"
            md_content += f"## 1. 微博正文内容\n\n> {article_text.replace(chr(10), chr(10)+'> ')}\n\n"
            md_content += f"## 2. 提取产品矩阵 (共 {len(all_products)} 个产品)\n\n"
            
            if len(all_products) == 0:
                md_content += "*(本条微博未提取出具体产品事实)*\n"
            else:
                for p_idx, prod in enumerate(all_products):
                    obj_facts = prod.get("客观事实", {})
                    subj_persona = prod.get("主观人格", {})
                    
                    md_content += f"### {p_idx+1}. {prod.get('产品名称', '未知')}\n"
                    md_content += f"#### 🧪 客观事实\n"
                    md_content += f"- **核心成分**: {obj_facts.get('核心成分', '')}\n"
                    md_content += f"- **适用肤质**: {obj_facts.get('适用肤质', '')}\n"
                    md_content += f"- **核心功效**: {obj_facts.get('核心功效', '')}\n"
                    md_content += f"#### 🎭 主观评价\n"
                    md_content += f"- **博主原话**: > {subj_persona.get('博主特色原话', '未提及')}\n"
                    md_content += f"- **使用心得**: > {subj_persona.get('博主使用心得', '未提及')}\n\n"
            
            with open(output_file, "w", encoding="utf-8") as f:
                f.write(md_content)
                
            print(f"[√] 本条入库完成！保存至: knowledge_base/{post_id}.md")
            
            # 【核心逻辑：阅后即焚】
            if os.path.exists(TEMP_IMG_DIR):
                shutil.rmtree(TEMP_IMG_DIR, ignore_errors=True)
                print(f"  [+] 已清理临时下载的图片文件 (阅后即焚)。")
                
        # 循环结束
        browser.close()
        
    print("\n=======================================================")
    print("[🎉] 所有批量链接处理完毕！")
    print(f"[查看库] 请前往 {KB_DIR} 查看纯文本归档结果。")

if __name__ == "__main__":
    main()
