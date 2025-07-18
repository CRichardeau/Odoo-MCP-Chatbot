# -*- coding: utf-8 -*-
import logging
import requests
from odoo import models, fields, api
from odoo.exceptions import ValidationError, UserError

_logger = logging.getLogger(__name__)


class ChatbotConfig(models.Model):
    """Configuration model for Anthropic chatbot integration."""
    
    _name = 'chatbot.config'
    _description = 'Chatbot Configuration'
    _rec_name = 'name'
    
    # Basic Information
    name = fields.Char(
        string='Configuration Name',
        required=True,
        default='MCP Configuration'
    )
    
    # API Configuration
    api_key = fields.Char(
        string='Anthropic API Key',
        required=False,  # Changed to False to avoid NOT NULL constraint errors
        groups='base.group_system',
        help='Your Anthropic API key (starts with sk-ant-)'
    )
    
    # MCP Server Configuration
    mcp_server_url = fields.Char(
        string='MCP Server URL',
        default='https://mpc-server-odoo.onrender.com',
        required=True,
        help='URL of the MCP server (e.g., https://mpc-server-odoo.onrender.com)'
    )
    
    # Odoo Connection Settings for MCP
    odoo_url = fields.Char(
        string='Odoo URL',
        help='URL of your Odoo instance (e.g., https://mycompany.odoo.com)'
    )
    
    odoo_db = fields.Char(
        string='Database Name',
        help='Name of the Odoo database to connect to'
    )
    
    odoo_username = fields.Char(
        string='Odoo Username',
        help='Username for Odoo authentication'
    )
    
    odoo_password = fields.Char(
        string='Odoo Password',
        help='Password or API key for Odoo authentication'
    )
    
    mcp_connected = fields.Boolean(
        string='MCP Connected',
        readonly=True,
        default=False,
        help='Indicates if MCP server is connected to Odoo'
    )
    
    model_name = fields.Selection(
        selection=[
            ('claude-3-5-sonnet-20241022', 'Claude 3.5 Sonnet (Recommended)'),
            ('claude-3-5-haiku-20241022', 'Claude 3.5 Haiku (Fast)'),
            ('claude-3-opus-20240229', 'Claude 3 Opus (Powerful)'),
            ('claude-3-sonnet-20240229', 'Claude 3 Sonnet'),
            ('claude-3-haiku-20240307', 'Claude 3 Haiku'),
        ],
        string='Model',
        default='claude-3-5-sonnet-20241022',
        required=True,
        help='Select the Claude model to use'
    )
    
    # Chat Settings
    temperature = fields.Float(
        string='Temperature',
        default=0.7,
        help='Controls randomness: 0 = deterministic, 1 = creative'
    )
    
    max_tokens = fields.Integer(
        string='Max Tokens',
        default=4096,
        help='Maximum number of tokens to generate'
    )
    
    timeout = fields.Integer(
        string='API Timeout (seconds)',
        default=30,
        help='Timeout for API requests in seconds'
    )
    
    # System Settings
    active = fields.Boolean(
        string='Active',
        default=True,
        help='Enable/disable this configuration'
    )
    
    system_prompt_prefix = fields.Text(
        string='System Prompt Prefix',
        help='Additional context to prepend to system prompts',
        default='You are a helpful AI assistant integrated with Odoo ERP.'
    )
    
    # Usage Information
    last_test_date = fields.Datetime(
        string='Last Test Date',
        readonly=True
    )
    
    last_test_result = fields.Text(
        string='Last Test Result',
        readonly=True
    )
    
    # Usage Limits
    daily_message_limit = fields.Integer(
        string='Daily Message Limit',
        default=1000,
        help='Maximum messages per day (0 = unlimited)'
    )
    
    message_count_today = fields.Integer(
        string='Messages Today',
        compute='_compute_message_count_today',
        help='Number of messages sent today'
    )
    
    @api.depends('write_date')
    def _compute_message_count_today(self):
        """Compute the number of messages sent today."""
        for record in self:
            today_start = fields.Datetime.now().replace(
                hour=0, minute=0, second=0, microsecond=0
            )
            count = self.env['chatbot.message'].search_count([
                ('create_date', '>=', today_start)
            ])
            record.message_count_today = count
    
    @api.constrains('api_key')
    def _check_api_key(self):
        """Validate API key format."""
        for record in self:
            if record.api_key:
                if not record.api_key.startswith('sk-ant-'):
                    raise ValidationError(
                        "API key must start with 'sk-ant-'"
                    )
                if len(record.api_key) < 50:
                    raise ValidationError(
                        "API key seems too short"
                    )
    
    @api.constrains('temperature')
    def _check_temperature(self):
        """Validate temperature range."""
        for record in self:
            if not 0 <= record.temperature <= 1:
                raise ValidationError('Temperature must be between 0 and 1')
    
    @api.constrains('max_tokens')
    def _check_max_tokens(self):
        """Validate max tokens."""
        for record in self:
            if record.max_tokens < 1 or record.max_tokens > 100000:
                raise ValidationError('Max tokens must be between 1 and 100,000')
    
    @api.constrains('active')
    def _check_single_active(self):
        """Ensure only one configuration is active."""
        if self.active:
            other_active = self.search([
                ('active', '=', True),
                ('id', '!=', self.id)
            ])
            if other_active:
                other_active.write({'active': False})
    
    @api.model
    def get_active_config(self):
        """Get the active configuration."""
        config = self.search([('active', '=', True)], limit=1)
        if not config:
            config = self.search([], limit=1)
            if config:
                config.active = True
        if not config:
            # Créer une configuration par défaut si aucune n'existe
            config = self.create({
                'name': 'MCP Configuration',
                'active': True,
                'api_key': '',  # Empty by default, user must configure
                'mcp_server_url': 'https://mpc-server-odoo.onrender.com',
                'model_name': 'claude-3-5-sonnet-20241022',
                'temperature': 0.7,
                'max_tokens': 4096,
                'timeout': 30,
                'system_prompt_prefix': 'Vous êtes un assistant IA intégré à Odoo ERP.',
                'daily_message_limit': 1000,
            })
        return config
    
    def test_connection(self):
        """Test the API connection."""
        self.ensure_one()
        try:
            # Test with a simple message using Anthropic API directly
            service = self.env['anthropic.service']
            result = service.create_chat_completion(
                messages=[{
                    'role': 'user',
                    'content': 'Hello, please respond with "Connection successful" if you can read this.'
                }],
                model=self.model_name,
                temperature=0,
                max_tokens=50
            )
            
            # Update test information
            self.write({
                'last_test_date': fields.Datetime.now(),
                'last_test_result': result.get('message', 'No response')[:500]
            })
            
            if result.get('success'):
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': 'Success',
                        'message': 'Connection test successful!',
                        'type': 'success',
                        'sticky': False,
                    }
                }
            else:
                raise ValidationError('Connection test failed')
                
        except Exception as e:
            error_msg = str(e)
            self.write({
                'last_test_date': fields.Datetime.now(),
                'last_test_result': f'Error: {error_msg}'
            })
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Error',
                    'message': f'Connection test failed: {error_msg}',
                    'type': 'danger',
                    'sticky': False,
                }
            }
    
    def action_open_chatbot(self):
        """Open the chatbot wizard."""
        self.ensure_one()
        
        # Vérifier si la configuration est complète
        if not self.api_key:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Configuration Requise',
                    'message': 'Veuillez configurer votre clé API Anthropic avant d\'utiliser le chatbot.',
                    'type': 'warning',
                    'sticky': True,
                }
            }
        
        return {
            'type': 'ir.actions.act_window',
            'name': 'MCP Chatbot',
            'res_model': 'chatbot.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_config_id': self.id,
            }
        }
    
    def action_view_history(self):
        """View chat history."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Historique des Conversations',
            'res_model': 'chatbot.message',
            'view_mode': 'list,form',
            'domain': [],
            'context': {
                'search_default_user_id': self.env.user.id,
                'default_config_id': self.id,
            }
        }
    
    @api.model
    def check_daily_limit(self):
        """Check if daily message limit has been reached."""
        config = self.get_active_config()
        if config.daily_message_limit > 0:
            if config.message_count_today >= config.daily_message_limit:
                raise ValidationError(
                    f'Daily message limit ({config.daily_message_limit}) reached'
                )
        return True
    
    def name_get(self):
        """Custom name display."""
        result = []
        for record in self:
            name = record.name
            if record.active:
                name = f"● {name}"
            result.append((record.id, name))
        return result
    
    def connect_mcp_to_odoo(self):
        """Connect MCP server to Odoo instance."""
        self.ensure_one()
        
        # Validate required fields
        if not all([self.odoo_url, self.odoo_db, self.odoo_username, self.odoo_password]):
            raise ValidationError(
                'Please fill in all Odoo connection fields: URL, Database, Username, and Password'
            )
        
        if not self.mcp_server_url:
            raise ValidationError('MCP Server URL is required')
        
        try:
            import requests
            
            # Prepare connection data
            connection_data = {
                'url': self.odoo_url.rstrip('/'),
                'database': self.odoo_db,
                'username': self.odoo_username,
                'password': self.odoo_password
            }
            
            # Send connection request to MCP server
            url = f"{self.mcp_server_url.rstrip('/')}/connect"
            response = requests.post(
                url,
                json=connection_data,
                headers={'Content-Type': 'application/json'},
                timeout=30
            )
            
            if response.status_code == 200:
                result = response.json()
                # Check for success status or connected field
                if result.get('status') == 'success' or result.get('connected'):
                    self.mcp_connected = True
                    success_msg = result.get('message', 'MCP successfully connected to Odoo!')
                    return {
                        'type': 'ir.actions.client',
                        'tag': 'display_notification',
                        'params': {
                            'title': 'Success',
                            'message': success_msg,
                            'type': 'success',
                            'sticky': False,
                        }
                    }
                else:
                    error_msg = result.get('error', result.get('message', 'Connection failed'))
                    raise UserError(f'MCP Connection Failed: {error_msg}')
            else:
                raise UserError(f'MCP Server Error: {response.status_code} - {response.text}')
                
        except requests.exceptions.RequestException as e:
            raise UserError(f'Network Error: {str(e)}')
        except Exception as e:
            raise UserError(f'Unexpected Error: {str(e)}')
    
    def disconnect_mcp_from_odoo(self):
        """Disconnect MCP server from Odoo."""
        self.ensure_one()
        
        if not self.mcp_connected:
            raise ValidationError('MCP is not connected')
        
        try:
            # For now, just mark as disconnected
            # In the future, you might want to send a disconnect request to the MCP server
            self.mcp_connected = False
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Success',
                    'message': 'MCP disconnected from Odoo',
                    'type': 'info',
                    'sticky': False,
                }
            }
        except Exception as e:
            raise UserError(f'Error disconnecting: {str(e)}')
