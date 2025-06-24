from odoo import models, fields, api
from odoo.exceptions import UserError
import requests
import json
import logging

_logger = logging.getLogger(__name__)

class ChatbotConfig(models.Model):
    _name = 'chatbot.config'
    _description = 'Configuration du Chatbot MCP'
    _rec_name = 'name'

    name = fields.Char(string="Nom", required=True, default="Configuration MCP")
    anthropic_api_key = fields.Char(string="Clé API Anthropic", password=True)
    anthropic_model = fields.Selection([
        ('claude-3-5-sonnet-20241022', 'Claude 3.5 Sonnet (Recommandé)'),
        ('claude-3-5-haiku-20241022', 'Claude 3.5 Haiku (Rapide)'),
        ('claude-3-opus-20240229', 'Claude 3 Opus (Puissant)'),
        ('claude-3-sonnet-20240229', 'Claude 3 Sonnet'),
        ('claude-3-haiku-20240307', 'Claude 3 Haiku'),
    ], string="Modèle Anthropic", default='claude-3-5-sonnet-20241022', 
    help="Choisissez le modèle Claude approprié. Sonnet 3.5 est recommandé pour un bon équilibre performance/coût.")
    is_active = fields.Boolean(string="Actif", default=True)
    mcp_url = fields.Char(
        string="URL MCP Gradio", 
        default="https://aktraiser-mcp-server-odoo.hf.space",
        help="URL du serveur MCP Gradio. Configuré par défaut vers votre serveur Hugging Face Spaces. Exemple: http://localhost:8080 pour un serveur local"
    )
    
    # Champs informatifs
    last_test_date = fields.Datetime(string="Dernier test", readonly=True)
    last_test_result = fields.Text(string="Résultat du dernier test", readonly=True)
    
    @api.model
    def get_active_config(self):
        """Récupère la configuration active ou la première disponible"""
        config = self.search([('is_active', '=', True)], limit=1)
        if not config:
            config = self.search([], limit=1)
        return config
    
    def test_connection(self):
        """Test de connexion MCP réel avec le service Anthropic"""
        self.ensure_one()
        
        if not self.mcp_url:
            raise UserError("Veuillez configurer l'URL MCP Gradio")
        
        if not self.anthropic_api_key:
            raise UserError("Veuillez configurer votre clé API Anthropic")
        
        try:
            # Test avec le service Anthropic réel
            anthropic_service = self.env['anthropic.service']
            test_message = "Test de connexion MCP - récupère les statistiques CRM basiques"
            
            _logger.info(f"Test de connexion MCP vers: {self.mcp_url}")
            
            response = anthropic_service.call_anthropic_api(test_message, self)
            
            # Mettre à jour les informations de test
            self.write({
                'last_test_date': fields.Datetime.now(),
                'last_test_result': response[:500] + "..." if len(response) > 500 else response
            })
            
            if response and not response.startswith("KO"):
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'message': '✅ Test MCP réussi ! Connexion et API fonctionnelles.',
                        'type': 'success',
                        'sticky': False,
                    }
                }
            else:
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'message': f'❌ Test MCP échoué: {response[:100]}...',
                        'type': 'danger',
                        'sticky': True,
                    }
                }
                
        except Exception as e:
            error_msg = str(e)
            _logger.error(f"Erreur lors du test de connexion MCP: {error_msg}")
            
            self.write({
                'last_test_date': fields.Datetime.now(),
                'last_test_result': f"Erreur: {error_msg}"
            })
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'message': f'❌ Erreur de connexion: {error_msg}',
                    'type': 'danger',
                    'sticky': True,
                }
            }
    
    def test_anthropic_direct(self):
        """Test d'appel direct Anthropic sans MCP"""
        self.ensure_one()
        
        if not self.anthropic_api_key:
            raise UserError("Veuillez configurer votre clé API Anthropic")
        
        try:
            anthropic_service = self.env['anthropic.service']
            test_message = "Bonjour, ceci est un test de l'API Anthropic. Réponds simplement 'Test réussi' en français."
            
            # Créer une configuration temporaire sans MCP pour forcer l'appel direct
            temp_config = {
                'anthropic_api_key': self.anthropic_api_key,
                'anthropic_model': self.anthropic_model,
                'mcp_url': None  # Pas d'URL MCP pour forcer l'appel direct
            }
            
            response = anthropic_service.call_anthropic_api(test_message, temp_config)
            
            if response and not response.startswith("KO"):
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'message': f'✅ API Anthropic fonctionnelle !<br/>🤖 Réponse: {response[:100]}...',
                        'type': 'success',
                        'sticky': True,
                    }
                }
            else:
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'message': f'❌ Test API Anthropic échoué: {response}',
                        'type': 'danger',
                        'sticky': True,
                    }
                }
                
        except Exception as e:
            _logger.error(f"Erreur lors du test Anthropic direct: {str(e)}")
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'message': f'❌ Erreur API Anthropic: {str(e)}',
                    'type': 'danger',
                    'sticky': True,
                }
            }
    
    def action_open_chatbot_wizard(self):
        """Ouvrir le wizard de chatbot avec cette configuration"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Chatbot MCP',
            'res_model': 'chatbot.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_config_id': self.id,
                'default_anthropic_api_key': self.anthropic_api_key,
                'default_mcp_url': self.mcp_url,
            }
        }
    
    @api.constrains('anthropic_api_key')
    def _check_api_key_format(self):
        """Validation basique du format de la clé API"""
        for record in self:
            if record.anthropic_api_key:
                if not record.anthropic_api_key.startswith('sk-ant-'):
                    raise UserError("La clé API Anthropic doit commencer par 'sk-ant-'")
                if len(record.anthropic_api_key) < 50:
                    raise UserError("La clé API Anthropic semble trop courte")
    
    @api.constrains('is_active')
    def _check_single_active_config(self):
        """S'assurer qu'il n'y a qu'une seule configuration active"""
        if self.is_active:
            other_active = self.search([('is_active', '=', True), ('id', '!=', self.id)])
            if other_active:
                other_active.write({'is_active': False})
    
    def name_get(self):
        """Affichage personnalisé du nom"""
        result = []
        for record in self:
            name = record.name
            if record.is_active:
                name = f"🟢 {name}"
            else:
                name = f"⚪ {name}"
            
            if record.mcp_url:
                name += " (MCP)"
            
            result.append((record.id, name))
        return result 
