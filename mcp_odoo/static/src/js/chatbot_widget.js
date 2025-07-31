/** @odoo-module **/

import { Component, useState, onMounted } from "@odoo/owl";
import { Dialog } from "@web/core/dialog/dialog";
import { _t } from "@web/core/l10n/translation";
import { useService } from "@web/core/utils/hooks";

/**
 * MCP Chatbot Widget with modern interface
 */
export class ChatbotWidget extends Component {
    static template = "MCP_Odoo.ChatbotWidget";
    static components = { Dialog };

    setup() {
        this.rpc = useService("rpc");
        this.notification = useService("notification");
        
        this.state = useState({
            messages: [],
            userInput: "",
            isLoading: false,
            showHistory: false,
            conversationHistory: [],
            currentSessionId: null
        });

        onMounted(() => {
            this.initializeChat();
            this.loadConversationHistory();
            this.hideDefaultButtons();
        });
    }

    /**
     * Initialize chat session
     */
    async initializeChat() {
        try {
            // Generate new session ID
            this.state.currentSessionId = this._generateSessionId();
            
            // Welcome message
            this._addMessage({
                type: 'bot',
                content: `
                    <div class="welcome-message">
                        <h4>MCP Assistant</h4>
                        <p>Hello! I'm your intelligent assistant for Odoo.</p>
                        <p><strong>Example commands:</strong></p>
                        <ul>
                            <li>• Search partners</li>
                            <li>• Show CRM statistics</li>
                            <li>• List recent orders</li>
                            <li>• Create new task</li>
                        </ul>
                    </div>
                `,
                timestamp: new Date()
            });
            
        } catch (error) {
            console.error("Chat initialization error:", error);
        }
    }

    /**
     * Load conversation history
     */
    async loadConversationHistory() {
        try {
            const history = await this.rpc("/web/dataset/call_kw", {
                model: "chatbot.message",
                method: "get_conversation_history",
                args: [],
                kwargs: { limit: 20 }
            });
            
            this.state.conversationHistory = history || [];
            
        } catch (error) {
            console.error("Error loading history:", error);
        }
    }

    /**
     * Send message
     */
    async sendMessage() {
        if (!this.state.userInput.trim() || this.state.isLoading) {
            return;
        }

        const userMessage = this.state.userInput.trim();
        this.state.userInput = "";
        this.state.isLoading = true;

        // Add user message
        this._addMessage({
            type: 'user',
            content: userMessage,
            timestamp: new Date()
        });

        // Show typing indicator
        this._addTypingIndicator();

        try {
            // Call chatbot service
            const startTime = Date.now();
            const response = await this.rpc("/web/dataset/call_kw", {
                model: "chatbot.wizard",
                method: "process_message_api",
                args: [userMessage],
                kwargs: {}
            });

            const responseTime = (Date.now() - startTime) / 1000;

            // Remove typing indicator
            this._removeTypingIndicator();

            if (response.error) {
                throw new Error(response.message || "Unknown error");
            }

            // Add bot response
            this._addMessage({
                type: 'bot',
                content: this._formatResponse(response.message || "No response received."),
                timestamp: new Date(),
                responseTime: responseTime
            });

            // Update history
            await this.loadConversationHistory();

        } catch (error) {
            console.error("Message error:", error);
            this._removeTypingIndicator();
            
            // Show error message
            this._addMessage({
                type: 'error',
                content: `<div class="error-message">
                    <strong>Error:</strong> ${error.message || "Failed to process message"}
                </div>`,
                timestamp: new Date()
            });
            
            this.notification.add(
                _t("Error processing message"),
                { type: 'danger' }
            );
        } finally {
            this.state.isLoading = false;
        }
    }

    /**
     * Format response with markdown support
     */
    _formatResponse(text) {
        if (!text) return "";
        
        // Convert line breaks
        let formatted = text.replace(/\n/g, '<br/>');
        
        // Convert basic markdown
        formatted = formatted.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
        formatted = formatted.replace(/\*(.*?)\*/g, '<em>$1</em>');
        formatted = formatted.replace(/`(.*?)`/g, '<code>$1</code>');
        
        // Convert lists
        formatted = formatted.replace(/^• (.*)$/gm, '<li>$1</li>');
        formatted = formatted.replace(/(<li>.*<\/li>)/s, '<ul>$1</ul>');
        
        return formatted;
    }

    /**
     * Add message to chat
     */
    _addMessage(message) {
        this.state.messages.push({
            id: Date.now(),
            ...message
        });
        
        // Scroll to bottom
        this._scrollToBottom();
    }

    /**
     * Add typing indicator
     */
    _addTypingIndicator() {
        this._addMessage({
            type: 'typing',
            content: '<div class="typing-indicator"><span></span><span></span><span></span></div>',
            timestamp: new Date()
        });
    }

    /**
     * Remove typing indicator
     */
    _removeTypingIndicator() {
        this.state.messages = this.state.messages.filter(msg => msg.type !== 'typing');
    }

    /**
     * Generate session ID
     */
    _generateSessionId() {
        return Math.random().toString(36).substring(2, 14);
    }

    /**
     * Scroll chat to bottom
     */
    _scrollToBottom() {
        setTimeout(() => {
            const chatContainer = document.querySelector('.chatbot-messages');
            if (chatContainer) {
                chatContainer.scrollTop = chatContainer.scrollHeight;
            }
        }, 100);
    }

    /**
     * Hide default modal buttons
     */
    hideDefaultButtons() {
        const modal = this.el.closest('.modal-content');
        if (modal) {
            const footer = modal.querySelector('.modal-footer');
            if (footer) {
                footer.style.display = 'none';
            }
        }
    }

    /**
     * Toggle history panel
     */
    toggleHistory() {
        this.state.showHistory = !this.state.showHistory;
    }

    /**
     * Load message from history
     */
    loadHistoryMessage(message) {
        this.state.userInput = message.user_message;
        this.state.showHistory = false;
    }

    /**
     * Clear conversation
     */
    clearConversation() {
        this.state.messages = [];
        this.state.currentSessionId = this._generateSessionId();
        this.initializeChat();
        
        this.notification.add(
            _t("Conversation cleared"),
            { type: 'info' }
        );
    }

    /**
     * Handle Enter key press
     */
    onKeyPress(event) {
        if (event.key === 'Enter' && !event.shiftKey) {
            event.preventDefault();
            this.sendMessage();
        }
    }
}
