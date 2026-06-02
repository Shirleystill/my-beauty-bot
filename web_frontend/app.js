const chatWindow = document.getElementById('chatWindow');
const userInput = document.getElementById('userInput');
const sendBtn = document.getElementById('sendBtn');

// 简单存储历史记录
let chatHistory = [];

// 自动调整输入框高度
userInput.addEventListener('input', function() {
    this.style.height = 'auto';
    this.style.height = (this.scrollHeight) + 'px';
    if (this.value.trim() === '') {
        this.style.height = 'auto';
    }
});

// 处理回车发送 (Shift+Enter 换行)
userInput.addEventListener('keydown', function(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        sendMessage();
    }
});

sendBtn.addEventListener('click', sendMessage);

function addMessageToUI(role, content) {
    const msgDiv = document.createElement('div');
    msgDiv.className = `message ${role}-message`;
    
    const bubble = document.createElement('div');
    bubble.className = 'bubble';
    
    // 如果是 bot 初始化阶段，可以有一个打字机效果的占位
    if (role === 'bot' && content === '') {
        bubble.id = 'current-bot-bubble';
    } else {
        bubble.textContent = content;
    }
    
    msgDiv.appendChild(bubble);
    chatWindow.appendChild(msgDiv);
    scrollToBottom();
    
    return bubble;
}

function showTypingIndicator() {
    const msgDiv = document.createElement('div');
    msgDiv.className = 'message bot-message typing-indicator-container';
    msgDiv.id = 'typing-indicator';
    
    const bubble = document.createElement('div');
    bubble.className = 'bubble typing-indicator';
    
    bubble.innerHTML = `
        <div class="dot"></div>
        <div class="dot"></div>
        <div class="dot"></div>
    `;
    
    msgDiv.appendChild(bubble);
    chatWindow.appendChild(msgDiv);
    scrollToBottom();
}

function removeTypingIndicator() {
    const indicator = document.getElementById('typing-indicator');
    if (indicator) {
        indicator.remove();
    }
}

function scrollToBottom() {
    chatWindow.scrollTo({
        top: chatWindow.scrollHeight,
        behavior: 'smooth'
    });
}

async function sendMessage() {
    const text = userInput.value.trim();
    if (!text) return;

    // 清空输入框并重置高度
    userInput.value = '';
    userInput.style.height = 'auto';

    // 添加用户消息到 UI
    addMessageToUI('user', text);
    
    // 保存到历史记录（如果历史太长可以切片）
    chatHistory.push({ role: 'user', content: text });

    // 显示思考中的动画
    showTypingIndicator();

    try {
        const response = await fetch('/api/chat', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                query: text,
                history: chatHistory.slice(-4) // 只取最后两轮对话
            })
        });

        removeTypingIndicator();

        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }

        const botBubble = addMessageToUI('bot', '');
        let fullResponse = '';

        // 处理 SSE 流式响应
        const reader = response.body.getReader();
        const decoder = new TextDecoder('utf-8');
        let buffer = '';

        while (true) {
            const { value, done } = await reader.read();
            if (done) break;

            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split('\n\n');
            
            // 最后一个元素是不完整的片段，留到下一次处理
            buffer = lines.pop();

            for (const line of lines) {
                if (line.startsWith('data: ')) {
                    const dataStr = line.substring(6);
                    try {
                        const dataObj = JSON.parse(dataStr);
                        if (dataObj.error) {
                            botBubble.textContent += `[Error: ${dataObj.error}]`;
                        } else if (dataObj.content) {
                            fullResponse += dataObj.content;
                            botBubble.textContent = fullResponse;
                            scrollToBottom();
                        }
                    } catch (e) {
                        console.error('JSON Parse Error:', e, dataStr);
                    }
                }
            }
        }
        
        // 补全最后一个片段
        if (buffer.startsWith('data: ')) {
             const dataStr = buffer.substring(6);
             try {
                 const dataObj = JSON.parse(dataStr);
                 if (dataObj.content) {
                     fullResponse += dataObj.content;
                     botBubble.textContent = fullResponse;
                 }
             } catch(e) {}
        }
        botBubble.removeAttribute('id');

        // 保存 bot 回复到历史记录
        chatHistory.push({ role: 'assistant', content: fullResponse });

    } catch (error) {
        console.error('Fetch Error:', error);
        removeTypingIndicator();
        addMessageToUI('bot', '不好意思，连接出现了一点问题...请检查后端服务是否启动。');
    }
}
