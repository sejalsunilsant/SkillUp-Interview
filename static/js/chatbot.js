document.addEventListener('DOMContentLoaded', function() {
    // 1. References to DOM Elements (Assuming chatbot.html is included in the page)
    const toggle = document.getElementById('chat-toggle');
    const window_el = document.getElementById('chat-window');
    const closeBtn = document.getElementById('close-chat');
    const sendBtn = document.getElementById('send-chat');
    const input = document.getElementById('chat-input');
    const messagesContainer = document.getElementById('chat-messages');

    if (!toggle) {
        console.warn('Chatbot elements not found. Make sure chatbot.html is included.');
        return;
    }

    let history = [];

    // 2. Event Handlers
    function toggleChat() {
        if (window_el.style.display === 'none') {
            window_el.style.display = 'flex';
            input.focus();
            const badge = document.querySelector('.notification-badge');
            if (badge) badge.style.display = 'none';
        } else {
            window_el.style.display = 'none';
        }
    }

    toggle.onclick = toggleChat;
    closeBtn.onclick = toggleChat;

    async function sendMessage() {
        const text = input.value.trim();
        if (!text) return;

        // Add user message to UI
        appendMessage('user', text);
        input.value = '';
        
        // Add typing indicator
        const typingIndicator = document.createElement('div');
        typingIndicator.className = 'message assistant typing';
        typingIndicator.innerText = 'HR is analyzing your data';
        messagesContainer.appendChild(typingIndicator);
        messagesContainer.scrollTop = messagesContainer.scrollHeight;

        try {
            const response = await fetch('/api/hr-chat', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    message: text,
                    history: history
                })
            });

            const data = await response.json();
            
            // Remove typing indicator
            if (typingIndicator.parentNode) {
                messagesContainer.removeChild(typingIndicator);
            }

            if (data.response) {
                appendMessage('assistant', data.response);
                history.push({ role: 'user', content: text });
                history.push({ role: 'assistant', content: data.response });
                if (history.length > 20) history = history.slice(-20);
            } else {
                appendMessage('assistant', "I'm sorry, I'm having some trouble responding right now.");
            }
        } catch (error) {
            console.error('Chat error:', error);
            if (typingIndicator.parentNode) messagesContainer.removeChild(typingIndicator);
            appendMessage('assistant', "Connection error. Please check your internet.");
        }
    }

    function appendMessage(role, text) {
        const msgDiv = document.createElement('div');
        msgDiv.className = `message ${role}`;
        
        let formattedText = text
            .replace(/\n/g, '<br>')
            .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
            .replace(/\*(.*?)\*/g, '<em>$1</em>')
            .replace(/## (.*?)(<br>|$)/g, '<h3>$1</h3>')
            .replace(/^- (.*?)(<br>|$)/gm, '<li>$1</li>');

        msgDiv.innerHTML = formattedText;
        messagesContainer.appendChild(msgDiv);
        messagesContainer.scrollTop = messagesContainer.scrollHeight;
    }

    sendBtn.onclick = sendMessage;
    input.onkeypress = (e) => {
        if (e.key === 'Enter') sendMessage();
    };

    // 3. Sidebar Link Integration
    const nav = document.querySelector('.sidebar-nav');
    if (nav) {
        // Prevent duplicate sidebar links if the script runs multiple times
        if (!document.getElementById('sidebar-hr-assistant')) {
            const hrNavItem = document.createElement('a');
            hrNavItem.href = '#';
            hrNavItem.id = 'sidebar-hr-assistant';
            hrNavItem.className = 'nav-item';
            hrNavItem.innerHTML = `
                <i class="ph-bold ph-chats-circle nav-icon"></i>
                <span class="nav-text">HR Assistant</span>
            `;
            hrNavItem.onclick = (e) => {
                e.preventDefault();
                if (window_el.style.display === 'none') {
                    toggleChat();
                } else {
                    window_el.focus();
                }
            };
            nav.appendChild(hrNavItem);
        }
    }
});
