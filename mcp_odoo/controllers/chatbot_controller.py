from odoo import http
from odoo.http import request
import logging

_logger = logging.getLogger(__name__)

class ChatbotController(http.Controller):
    
    def _process_message(self, user_input, fast_mode=False):
        """Méthode interne pour traiter les messages"""
        if not user_input or not user_input.strip():
            return {
                'success': False,
                'error': 'Message vide non autorisé'
            }
            
        try:
            # Créer l'enregistrement du message utilisateur
            message = request.env['chatbot.message'].create({
                'user_input': user_input.strip(),
                'timestamp': request.env['chatbot.message']._fields['timestamp'].default()
            })
            
            # Récupérer la configuration active
            config = request.env['chatbot.config'].search([('active', '=', True)], limit=1)
            
            if not config:
                bot_response = "KO Aucune configuration active trouvée"
                _logger.warning("Aucune configuration chatbot active trouvée")
            elif not config.api_key:
                bot_response = "KO Clé API Anthropic non configurée"
                _logger.warning("Clé API Anthropic manquante dans la configuration")
            else:
                # Utiliser le service Anthropic commun avec le mode rapide
                anthropic_service = request.env['anthropic.service']
                bot_response = anthropic_service.call_anthropic_api(user_input.strip(), config, fast_mode=fast_mode)
            
            # Mettre à jour le message avec la réponse du bot
            message.write({'bot_response': bot_response})
            
            mode_label = "RAPIDE" if fast_mode else "normal"
            _logger.info(f"Message chatbot {mode_label} traité avec succès (ID: {message.id})")
            
            result = {
                'success': True,
                'message_id': message.id,
                'user_input': user_input.strip(),
                'bot_response': bot_response,
                'timestamp': message.timestamp.isoformat()
            }
            
            if fast_mode:
                result['mode'] = 'fast'
                
            return result
            
        except Exception as e:
            _logger.error(f"Erreur lors du traitement du message chatbot: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }
    
    @http.route('/api/chatbot/send_message', type='json', auth='user', methods=['POST'])
    def send_message(self, user_input, fast_mode=False):
        """API pour envoyer un message au chatbot et recevoir la réponse"""
        return self._process_message(user_input, fast_mode)

    @http.route('/api/chatbot/get_messages', type='json', auth='user', methods=['GET'])
    def get_messages(self, limit=10):
        """Récupérer les derniers messages"""
        try:
            # Validation des paramètres
            limit = min(max(int(limit), 1), 100)  # Entre 1 et 100
            
            messages = request.env['MCP_Odoo.message'].search(
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

    @http.route('/api/chatbot/send_message_fast', type='json', auth='user', methods=['POST'])
    def send_message_fast(self, user_input):
        """API RAPIDE pour envoyer un message au chatbot - sans post-traitement"""
        return self._process_message(user_input, fast_mode=True)