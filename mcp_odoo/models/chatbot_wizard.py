# -*- coding: utf-8 -*-
import time
import uuid
import re
import logging
from odoo import models, fields, api
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class ChatbotWizard(models.TransientModel):
    """Interactive chatbot wizard with MCP integration."""
    
    _name = 'chatbot.wizard'
    _description = 'MCP Chatbot Interface'
    
    # Main fields
    user_input = fields.Text(
        string='Your Message',
        required=True,
        placeholder='Ask your question...'
    )
    
    bot_response = fields.Html(
        string='Assistant Response',
        readonly=True
    )
    
    previous_user_message = fields.Text(
        string='Previous User Message',
        readonly=True
    )
    
    config_id = fields.Many2one(
        'chatbot.config',
        string='Configuration',
        readonly=True
    )
    
    # UI Control fields
    show_config = fields.Boolean(
        string='Show Configuration',
        default=False
    )
    
    show_history = fields.Boolean(
        string='Show History',
        default=False
    )
    
    # Session management
    current_session_id = fields.Char(
        string='Session ID',
        default=lambda self: str(uuid.uuid4())[:12]
    )
    
    # Conversation history
    conversation_history = fields.One2many(
        'chatbot.message',
        compute='_compute_conversation_history',
        string='Conversation History'
    )
    
    @api.depends('current_session_id')
    def _compute_conversation_history(self):
        """Compute conversation history for current user."""
        for wizard in self:
            history = self.env['chatbot.message'].search([
                ('user_id', '=', self.env.user.id)
            ], limit=20, order='create_date desc')
            wizard.conversation_history = history
    
    @api.model
    def default_get(self, fields_list):
        """Get default values with active configuration."""
        defaults = super().default_get(fields_list)
        
        # Get active configuration
        config = self.env['chatbot.config'].get_active_config()
        if config:
            defaults['config_id'] = config.id
        
        return defaults
    
    def action_send_message(self):
        """Send message to MCP server and get response."""
        if not self.user_input:
            return self._return_wizard()
        
        start_time = time.time()
        
        # Save user message
        self.previous_user_message = self.user_input
        
        # Get configuration
        config = self.config_id or self.env['chatbot.config'].get_active_config()
        if not config:
            raise UserError('No chatbot configuration found')
        
        # Check daily limit
        config.check_daily_limit()
        
        # Create message record
        message = self.env['chatbot.message'].create({
            'user_message': self.previous_user_message,
            'session_id': self.current_session_id,
            'config_id': config.id,
            'status': 'sent'
        })
        
        try:
            # Call Anthropic service directly
            service = self.env['anthropic.service']
            result = service.create_chat_completion(
                messages=[{
                    'role': 'user',
                    'content': self.previous_user_message
                }],
                model=config.model_name,
                temperature=config.temperature,
                max_tokens=config.max_tokens
            )
            
            response_time = time.time() - start_time
            
            if not result.get('success'):
                raise UserError(result.get('message', 'Unknown error'))
            
            # Update message record
            bot_response = result.get('message', '')
            message.write({
                'bot_response': bot_response,
                'status': 'processed',
                'response_time': response_time,
                'usage_data': str(result.get('usage', {}))
            })
            
            # Format and display response
            self.bot_response = self._format_response(bot_response, response_time)
            
        except Exception as e:
            error_msg = str(e)
            _logger.error(f"Chatbot error: {error_msg}")
            
            # Update message with error
            message.write({
                'bot_response': error_msg,
                'status': 'error',
                'error_message': error_msg,
                'response_time': time.time() - start_time
            })
            
            self.bot_response = self._format_error(error_msg)
        
        # Clear input
        self.user_input = ""
        
        return self._return_wizard()
    
    def _format_response(self, response, response_time=None):
        """Format response for HTML display."""
        if not response:
            return ""
        
        # Convert line breaks
        formatted = response.replace('\n', '<br/>')
        
        # Convert basic markdown
        formatted = re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', formatted)
        formatted = re.sub(r'\*(.*?)\*', r'<em>\1</em>', formatted)
        formatted = re.sub(r'`(.*?)`', r'<code>\1</code>', formatted)
        
        # Add performance footer
        footer = ""
        if response_time:
            footer = f"""
            <div style="margin-top: 15px; padding: 10px; background: #f8f9fa; 
                        border-radius: 6px; font-size: 12px; color: #6c757d;">
                ⚡ Response generated in {response_time:.2f}s • MCP Assistant
            </div>
            """
        
        return f"""
        <div style="padding: 15px; background: #f8f9fa; border-radius: 8px; 
                    border-left: 4px solid #007bff;">
            {formatted}
        </div>
        {footer}
        """
    
    def _format_error(self, error):
        """Format error message."""
        return f"""
        <div style="background: #f8d7da; border: 1px solid #f5c6cb; 
                    color: #721c24; padding: 15px; border-radius: 8px;">
            <h5>❌ Error</h5>
            <p><strong>Details:</strong> {error}</p>
            <p><strong>Possible solutions:</strong></p>
            <ul>
                <li>Check your API key configuration</li>
                <li>Verify network connectivity</li>
                <li>Check API rate limits</li>
            </ul>
        </div>
        """
    
    def action_toggle_config(self):
        """Toggle configuration display."""
        self.show_config = not self.show_config
        return self._return_wizard()
    
    def action_toggle_history(self):
        """Toggle history display."""
        self.show_history = not self.show_history
        return self._return_wizard()
    
    def action_clear_conversation(self):
        """Clear current conversation."""
        self.user_input = ""
        self.bot_response = ""
        self.previous_user_message = ""
        self.current_session_id = str(uuid.uuid4())[:12]
        return self._return_wizard()
    
    def action_open_config(self):
        """Open configuration window."""
        return {
            'type': 'ir.actions.act_window',
            'name': 'Chatbot Configuration',
            'res_model': 'chatbot.config',
            'view_mode': 'tree,form',
            'target': 'new',
        }
    
    def action_load_history_message(self):
        """Load a message from history."""
        message_id = self.env.context.get('active_id')
        if message_id:
            message = self.env['chatbot.message'].browse(message_id)
            if message.exists() and message.user_id == self.env.user:
                self.user_input = message.user_message
                self.bot_response = self._format_response(message.bot_response)
        return self._return_wizard()
    
    @api.model
    def process_message_api(self, user_message):
        """API endpoint for processing messages (used by JavaScript)."""
        try:
            config = self.env['chatbot.config'].get_active_config()
            config.check_daily_limit()
            
            # Call Anthropic service directly
            service = self.env['anthropic.service']
            result = service.create_chat_completion(
                messages=[{
                    'role': 'user',
                    'content': user_message
                }],
                model=config.model_name,
                temperature=config.temperature,
                max_tokens=config.max_tokens
            )
            
            if not result.get('success'):
                return {'error': True, 'message': result.get('message')}
            
            return {
                'error': False,
                'message': result.get('message', ''),
                'usage': result.get('usage', {})
            }
            
        except Exception as e:
            _logger.error(f"API error: {str(e)}")
            return {'error': True, 'message': str(e)}
    
    def _return_wizard(self):
        """Return wizard in modal mode."""
        return {
            'type': 'ir.actions.act_window',
            'name': 'MCP Assistant',
            'res_model': 'chatbot.wizard',
            'view_mode': 'form',
            'res_id': self.id,
            'target': 'new',
            'context': self.env.context,
        }
