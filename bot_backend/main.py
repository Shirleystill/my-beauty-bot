from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import List, Optional
import uvicorn

# 导入我们的 rag_service
from rag_service import generate_chat_stream

app = FastAPI(title="Beauty Blogger Avatar API")

# 配置 CORS，允许前端跨域请求
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 在生产环境中应该限制为前端的实际地址
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class Message(BaseModel):
    role: str
    content: str

class ChatRequest(BaseModel):
    query: str
    history: Optional[List[Message]] = []

@app.post("/api/chat")
async def chat_endpoint(req: ChatRequest):
    """
    处理聊天请求并返回 Server-Sent Events (SSE) 格式的流式响应
    """
    # 将 history 从 BaseModel 转换为字典列表
    history_dicts = [{"role": msg.role, "content": msg.content} for msg in req.history]
    
    # 返回 StreamingResponse
    return StreamingResponse(
        generate_chat_stream(req.query, history_dicts),
        media_type="text/event-stream"
    )

import os
frontend_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "web_frontend")
app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="static")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    print(f"[+] 启动后端服务，端口: {port}...")
    uvicorn.run(app, host="0.0.0.0", port=port)
