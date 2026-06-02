import os
import json
import time
import requests
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright
import dashscope

# 配置环境变量
API_KEY_PATH = os.path.join(os.path.dirname(__file__), "API_KEY.txt")
if os.path.exists(API_KEY_PATH):
    with open(API_KEY_PATH, "r") as f:
        os.environ["DASHSCOPE_API_KEY"] = f.read().strip()
dashscope.api_key = os.environ.get("DASHSCOPE_API_KEY")

def download_image(url, save_dir, index):
    if not os.path.exists(save_dir):
        os.makedirs(save_dir)
    # 处理 //wx1.sinaimg.cn 这种缺乏协议的 URL
    if url.startswith("//"):
        url = "https:" + url
    
    # 尝试将微博缩略图 URL 替换为高清大图 URL
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
        print(f"[-] 下载图片失败 {url}: {e}")
        return None

def extract_json_from_image(image_path):
    prompt = """
    你是一个严谨的护肤美妆数据标注专家。
    这张图可能包含美妆产品，也可能是博主自拍等无关内容。
    1. 请仔细识别图中的所有独立美妆产品。
    2. 如果这张图完全没有产品（比如纯自拍、纯风景），请直接返回空数组: []
    3. 如果有产品，请针对每个产品提取以下信息：
       - 产品名称 (Product Name)
       - 核心成分 (Key Ingredients)
       - 适用肤质 (Suitable Skin Types)
       - 核心功效 (Main Efficacy)
       - 博主特色原话 (Original Quotes): 【极其重要】必须一字不差地从图中“逐字抄写”博主形容该产品的特色原话（包括吐槽、专业术语或比喻）。绝不允许你自己发散编造！请原样摘录图中的真实词汇（如：“弱得要死”、“合成酯架构”、“老干妈油膜感爆炸”）。
       - 博主使用心得 (Subjective Review): 【极其重要】一字不差地摘录博主在图中描述的具体质感、洗感、使用体验（如：“上脸有一种乳霜到凝胶的转化”、“体验奢华的无泡洁面”）。严禁使用任何网络烂梗（绝对禁止脑补“绝绝子”、“干皮亲妈”等图中不存在的词汇）！没提就写“未提及”。
       
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
            return json.loads(text)
        else:
            print(f"[-] 模型API失败: {response.code} {response.message}")
            return []
    except Exception as e:
        print(f"[-] 提取图片时发生异常: {e}")
        return []

def main():
    if not dashscope.api_key:
        print("【严重错误】未找到 API Key。请确保 API_KEY.txt 文件存在且填写正确。")
        return

    target_url = input("请输入要抓取的微博正文链接 (如 https://weibo.com/...): ").strip()
    if not target_url:
        return
        
    print("\n[+] 正在启动浏览器，请在弹出的窗口中扫码登录微博...")
    with sync_playwright() as p:
        try:
            # 【核心 Workaround】：不下载独立的 Chromium，直接调起你 Mac 电脑上现装的 Google Chrome！
            browser = p.chromium.launch(headless=False, channel="chrome")
        except Exception as e:
            print("\n【错误】调起本地 Chrome 失败。请确认你电脑上装了 Google Chrome 浏览器！")
            print(f"详情: {e}")
            return
            
        context = browser.new_context(viewport={'width': 1280, 'height': 800})
        page = context.new_page()
        
        page.goto(target_url)
        
        # 将控制权交还给用户进行登录
        input("\n>>> 【人工接管】请在弹出的浏览器中扫码登录。确认【页面已完全加载出正文和图片】后，回到终端按回车键继续 <<<")
        
        print("\n[+] 开始解析页面...")
        # 获取所有可能的正文段落
        try:
            # 宽泛抓取常见微博正文节点
            article_text = page.locator("div.detail_wbtext_4CRf9, div.weibo-text, article").first.inner_text()
        except:
            article_text = "【未自动匹配到正文，请检查页面结构】"
            
        print(f"[+] 正文提取完毕 (截取前50字): {article_text[:50]}...")
        
        # 提取图片 URL
        print("[+] 正在提取图片...")
        image_elements = page.locator("img").all()
        image_urls = []
        for img in image_elements:
            src = img.get_attribute("src")
            # 过滤掉头像、表情包等小图，只保留微博配图
            if src and "sinaimg.cn" in src and ("bmiddle" in src or "orj360" in src or "large" in src or "mw690" in src):
                if src not in image_urls:
                    image_urls.append(src)
                    
        print(f"[+] 共发现 {len(image_urls)} 张潜在长图/配图。")
        browser.close()

    # 第二阶段：下载并蒸馏
    print("\n[+] 开始下载并蒸馏图片...")
    save_dir = os.path.join(os.path.dirname(__file__), "weibo_images_temp")
    
    all_products = []
    
    for idx, url in enumerate(image_urls):
        print(f"  -> [{idx+1}/{len(image_urls)}] 正在下载: {url}")
        local_path = download_image(url, save_dir, idx)
        if local_path:
            print(f"  -> [{idx+1}/{len(image_urls)}] 正在发送给大模型提取...")
            products = extract_json_from_image(local_path)
            if not products:
                print(f"  -> [忽略记录] 模型判定该图无效（如自拍、空景），已丢弃该图片数据。")
            else:
                print(f"  -> [成功] 提取到 {len(products)} 个产品。")
                all_products.extend(products)

    # 第三阶段：组装 Markdown
    print("\n[+] 开始组装 Markdown 报告...")
    md_content = f"# 微博美妆知识蒸馏报告\n\n"
    md_content += f"**源链接**: {target_url}\n\n"
    md_content += f"## 1. 微博正文内容\n\n> {article_text.replace(chr(10), chr(10)+'> ')}\n\n"
    md_content += f"## 2. 提取出的产品矩阵 (共 {len(all_products)} 个产品)\n\n"
    
    for idx, prod in enumerate(all_products):
        obj_facts = prod.get("客观事实", {})
        subj_persona = prod.get("主观人格", {})
        
        md_content += f"### {idx+1}. {prod.get('产品名称', '未知')}\n"
        md_content += f"#### 🧪 客观事实提取\n"
        md_content += f"- **核心成分**: {obj_facts.get('核心成分', '')}\n"
        md_content += f"- **适用肤质**: {obj_facts.get('适用肤质', '')}\n"
        md_content += f"- **核心功效**: {obj_facts.get('核心功效', '')}\n"
        md_content += f"#### 🎭 主观人格提取\n"
        md_content += f"- **博主特色原话**: > {subj_persona.get('博主特色原话', '未提及')}\n"
        md_content += f"- **博主使用心得**: > {subj_persona.get('博主使用心得', '未提及')}\n\n"
        
    output_file = os.path.join(os.path.dirname(__file__), "TopicA_Result.md")
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(md_content)
        
    print(f"\n[√] 完美竣工！蒸馏结果已保存至: {output_file}")

if __name__ == "__main__":
    main()
