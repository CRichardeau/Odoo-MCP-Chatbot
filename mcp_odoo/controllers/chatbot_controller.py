# -*- coding: utf-8 -*-
import logging
from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)


class ChatbotController(http.Controller):

    @http.route('/api/chatbot/send_message', type='json', auth='user', methods=['POST'])
    def send_message(self, user_input):
        """
        API for sending a message to the chatbot and getting a response
        Args:
            user_input:

        Returns:

        """
        if not user_input or not user_input.strip():
            return {
                'success': False,
                'error': 'Message vide non autorisé'
            }

        try:
            # Create user message record
            message = request.env['chatbot_custom.message'].create({
                'user_input': user_input.strip(),
                'timestamp': request.env['chatbot_custom.message']._fields['timestamp'].default()
            })

            # Retrieve the active configuration
            config = request.env['chatbot.config'].search([('is_active', '=', True)], limit=1)

            if not config:
                bot_response = "KO Aucune configuration active trouvée"
                _logger.warning("Aucune configuration chatbot active trouvée")
            elif not config.anthropic_api_key:
                bot_response = "KO Clé API Anthropic non configurée"
                _logger.warning("Clé API Anthropic manquante dans la configuration")
            else:
                # Use the common Anthropic service
                anthropic_service = request.env['anthropic.service']
                bot_response = anthropic_service.call_anthropic_api(user_input.strip(), config)

            # Update the message with the bot response
            message.write({'bot_response': bot_response})

            _logger.info(f"Message chatbot traité avec succès (ID: {message.id})")

            return {
                'success': True,
                'message_id': message.id,
                'user_input': user_input.strip(),
                'bot_response': bot_response,
                'timestamp': message.timestamp.isoformat()
            }

        except Exception as e:
            _logger.error(f"Erreur lors du traitement du message chatbot: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }

    @http.route('/api/chatbot/get_messages', type='json', auth='user', methods=['GET'])
    def get_messages(self, limit=10):
        """
        Retrieve the latest messages
        Args:
            limit:

        Returns:

        """
        try:
            # Validate parameters
            limit = min(max(int(limit), 1), 100)  # Entre 1 et 100

            messages = request.env['chatbot_custom.message'].search(
                [],
                order='timestamp desc',
                limit=limit
            )

            result = []
            for msg in messages:
                result.append({
                    'id': msg.id,
                    'user_input': msg.user_input,
                    'bot_response': msg.bot_response,
                    'timestamp': msg.timestamp.isoformat() if msg.timestamp else None
                })

            _logger.info(f"Récupération de {len(result)} messages chatbot")

            return {
                'success': True,
                'messages': result,
                'total': len(result)
            }

        except Exception as e:
            _logger.error(f"Erreur lors de la récupération des messages: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }
