/** @odoo-module **/

import { Component, useState, onMounted, onWillUnmount } from "@odoo/owl";
import { Dialog } from "@web/core/dialog/dialog";
import { _t } from "@web/core/l10n/translation";
import { useService } from "@web/core/utils/hooks";

/**
 * Widget Chatbot MCP avec interface moderne
 */
export class ChatbotWidget extends Component {
    static template = "chatbot_custom.ChatbotWidget";
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
     * Initialiser la session de chat
     */
    async initializeChat() {
        try {
            // Générer un nouvel ID de session
            this.state.currentSessionId = this._generateSessionId();
            
            // Message de bienvenue
            this._addMessage({
                type: 'bot',
                content: `
                    <div class="welcome-message">
                        <h4>🤖 Assistant MCP Odoo</h4>
                        <p>Bonjour ! Je suis votre assistant intelligent pour Odoo.</p>
                        <p><strong>Exemples de commandes :</strong></p>
                        <ul>
                            <li>• "Liste les leads"</li>
                            <li>• "Statistiques CRM"</li>
                            <li>• "Recherche commandes"</li>
                            <li>• "Analyser les devis"</li>
                        </ul>
                    </div>
                `,
                timestamp: new Date()
            });
            
        } catch (error) {
            console.error("Erreur initialisation chat:", error);
        }
    }

    /**
     * Charger l'historique des conversations
     */
    async loadConversationHistory() {
        try {
            const history = await this.rpc("/web/dataset/call_kw", {
                model: "chatbot_custom.message",
                method: "get_conversation_history",
                args: [15], // Derniers 15 messages
                kwargs: {}
            });
            
            this.state.conversationHistory = history || [];
            
        } catch (error) {
            console.error("Erreur chargement historique:", error);
        }
    }

    /**
     * Envoyer un message
     */
    async sendMessage() {
        if (!this.state.userInput.trim() || this.state.isLoading) {
            return;
        }

        const userMessage = this.state.userInput.trim();
        this.state.userInput = "";
        this.state.isLoading = true;

        // Ajouter le message utilisateur
        this._addMessage({
            type: 'user',
            content: userMessage,
            timestamp: new Date()
        });

        // Indicateur de frappe
        this._addTypingIndicator();

        try {
            // Enregistrer en base
            const messageRecord = await this.rpc("/web/dataset/call_kw", {
                model: "chatbot_custom.message",
                method: "create",
                args: [{
                    user_input: userMessage,
                    session_id: this.state.currentSessionId,
                    status: 'sent'
                }],
                kwargs: {}
            });

            // Appeler le service chatbot
            const startTime = Date.now();
            const response = await this.rpc("/web/dataset/call_kw", {
                model: "chatbot.wizard",
                method: "process_message_api",
                args: [userMessage],
                kwargs: {}
            });

            const responseTime = (Date.now() - startTime) / 1000;

            // Supprimer l'indicateur de frappe
            this._removeTypingIndicator();

            // Ajouter la réponse
            this._addMessage({
                type: 'bot',
                content: response || "Désolé, je n'ai pas pu traiter votre demande.",
                timestamp: new Date()
            });

            // Mettre à jour en base
            await this.rpc("/web/dataset/call_kw", {
                model: "chatbot_custom.message",
                method: "write",
                args: [messageRecord, {
                    bot_response: response,
                    status: 'processed',
                    response_time: responseTime
                }],
                kwargs: {}
            });

            // Recharger l'historique
            this.loadConversationHistory();

        } catch (error) {
            console.error("Erreur envoi message:", error);
            this._removeTypingIndicator();
            
            this._addMessage({
                type: 'bot',
                content: `<div class="error-message">❌ Erreur: ${error.message || 'Problème de connexion'}</div>`,
                timestamp: new Date()
            });

            this.notification.add(
                _t("Erreur lors de l'envoi du message"),
                { type: "danger" }
            );
        } finally {
            this.state.isLoading = false;
        }
    }

    /**
     * Ajouter un message à la conversation
     */
    _addMessage(message) {
        this.state.messages.push({
            id: Date.now() + Math.random(),
            ...message
        });
        
        // Auto-scroll vers le bas
        this._scrollToBottom();
    }

    /**
     * Ajouter l'indicateur de frappe
     */
    _addTypingIndicator() {
        this._addMessage({
            type: 'bot',
            content: `
                <div class="typing-indicator">
                    <div class="dot"></div>
                    <div class="dot"></div>
                    <div class="dot"></div>
                    <span style="margin-left: 10px;">Assistant en cours de traitement...</span>
                </div>
            `,
            timestamp: new Date(),
            isTyping: true
        });
    }

    /**
     * Supprimer l'indicateur de frappe
     */
    _removeTypingIndicator() {
        this.state.messages = this.state.messages.filter(msg => !msg.isTyping);
    }

    /**
     * Faire défiler vers le bas
     */
    _scrollToBottom() {
        setTimeout(() => {
            const chatContainer = document.querySelector('.chat-conversation');
            if (chatContainer) {
                chatContainer.scrollTop = chatContainer.scrollHeight;
            }
        }, 100);
    }

    /**
     * Effacer la conversation
     */
    clearConversation() {
        this.state.messages = [];
        this.state.currentSessionId = this._generateSessionId();
        this.initializeChat();
    }

    /**
     * Basculer l'affichage de l'historique
     */
    toggleHistory() {
        this.state.showHistory = !this.state.showHistory;
        if (this.state.showHistory) {
            this.loadConversationHistory();
        }
    }

    /**
     * Charger une conversation depuis l'historique
     */
    async loadHistoryConversation(messageId) {
        try {
            const message = await this.rpc("/web/dataset/call_kw", {
                model: "chatbot_custom.message",
                method: "browse",
                args: [messageId],
                kwargs: {}
            });

            if (message && message.length > 0) {
                this.clearConversation();
                
                // Ajouter les messages de l'historique
                const historyMessage = message[0];
                this._addMessage({
                    type: 'user',
                    content: historyMessage.user_input,
                    timestamp: new Date(historyMessage.timestamp)
                });

                if (historyMessage.bot_response) {
                    this._addMessage({
                        type: 'bot',
                        content: historyMessage.bot_response,
                        timestamp: new Date(historyMessage.timestamp)
                    });
                }
            }

            this.state.showHistory = false;
            
        } catch (error) {
            console.error("Erreur chargement conversation:", error);
        }
    }

    /**
     * Gérer l'appui sur Entrée
     */
    onKeyPress(event) {
        if (event.key === 'Enter' && !event.shiftKey) {
            event.preventDefault();
            this.sendMessage();
        }
    }

    /**
     * Mettre à jour l'input utilisateur
     */
    onInputChange(event) {
        this.state.userInput = event.target.value;
    }

    /**
     * Générer un ID de session unique
     */
    _generateSessionId() {
        return 'sess_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9);
    }

    /**
     * Formater l'horodatage
     */
    formatTimestamp(timestamp) {
        if (!timestamp) return "";
        const date = new Date(timestamp);
        return date.toLocaleTimeString('fr-FR', {
            hour: '2-digit',
            minute: '2-digit'
        });
    }

    /**
     * Obtenir la classe CSS pour le message
     */
    getMessageClass(messageType) {
        return `chat-message ${messageType}-message`;
    }

    /**
     * Masquer les boutons Save/Discard automatiques d'Odoo
     */
    hideDefaultButtons() {
        // Attendre que la modal soit complètement rendue
        setTimeout(() => {
            const modalFooter = document.querySelector('.modal-footer');
            if (modalFooter) {
                modalFooter.style.display = 'none';
            }
            
            // Alternative plus spécifique
            const saveBtn = document.querySelector('button[data-hotkey="s"]');
            const discardBtn = document.querySelector('button[data-hotkey="j"]');
            
            if (saveBtn) saveBtn.style.display = 'none';
            if (discardBtn) discardBtn.style.display = 'none';
        }, 100);
    }
} 
