# -*- coding: utf-8 -*-
import uuid
import logging
from datetime import timedelta
from odoo import models, fields, api

_logger = logging.getLogger(__name__)


class ChatbotMessage(models.Model):
    """Model to store chatbot conversation history."""
    
    _name = 'chatbot.message'
    _description = 'Chatbot Message'
    _order = 'create_date desc'
    _rec_name = 'user_message'
    
    # Main fields
    user_message = fields.Text(
        string='User Message',
        required=True
    )
    
    bot_response = fields.Text(
        string='Bot Response'
    )
    
    # User and session tracking
    user_id = fields.Many2one(
        'res.users',
        string='User',
        default=lambda self: self.env.user,
        readonly=True,
        required=True
    )
    
    session_id = fields.Char(
        string='Session ID',
        required=True,
        index=True
    )
    
    # Configuration
    config_id = fields.Many2one(
        'chatbot.config',
        string='Configuration Used',
        ondelete='set null'
    )
    
    # Status tracking
    status = fields.Selection([
        ('draft', 'Draft'),
        ('sent', 'Sent'),
        ('processed', 'Processed'),
        ('error', 'Error')
    ], string='Status', default='draft', required=True)
    
    # Performance metrics
    response_time = fields.Float(
        string='Response Time (s)',
        help='Time taken to generate response in seconds'
    )
    
    error_message = fields.Text(
        string='Error Message'
    )
    
    # Usage data
    usage_data = fields.Text(
        string='Usage Data',
        help='JSON data about token usage'
    )
    
    # Computed fields
    conversation_date = fields.Date(
        string='Conversation Date',
        compute='_compute_conversation_date',
        store=True
    )
    
    @api.depends('create_date')
    def _compute_conversation_date(self):
        """Extract date from create_date for grouping."""
        for record in self:
            if record.create_date:
                record.conversation_date = record.create_date.date()
            else:
                record.conversation_date = fields.Date.today()
    
    @api.model
    def get_conversation_history(self, session_id=None, limit=50):
        """
        Get conversation history for current user.
        
        Args:
            session_id: Optional session ID to filter
            limit: Maximum number of messages
            
        Returns:
            Recordset of messages
        """
        domain = [('user_id', '=', self.env.user.id)]
        if session_id:
            domain.append(('session_id', '=', session_id))
        
        return self.search(domain, limit=limit, order='create_date desc')
    
    @api.model
    def get_user_sessions(self):
        """Get all unique sessions for current user."""
        sessions = self.read_group(
            [('user_id', '=', self.env.user.id)],
            ['session_id', 'create_date:max'],
            ['session_id'],
            orderby='create_date desc'
        )
        
        return [{
            'session_id': s['session_id'],
            'last_message': s['create_date'],
            'message_count': s['session_id_count']
        } for s in sessions]
    
    @api.model
    def get_statistics(self):
        """Get usage statistics for current user."""
        domain = [('user_id', '=', self.env.user.id)]
        
        # Basic counts
        total_messages = self.search_count(domain)
        processed_messages = self.search_count(
            domain + [('status', '=', 'processed')]
        )
        error_messages = self.search_count(
            domain + [('status', '=', 'error')]
        )
        
        # Calculate average response time
        processed_with_time = self.search(
            domain + [
                ('status', '=', 'processed'),
                ('response_time', '>', 0)
            ]
        )
        
        avg_response_time = 0
        if processed_with_time:
            total_time = sum(processed_with_time.mapped('response_time'))
            avg_response_time = total_time / len(processed_with_time)
        
        # Count unique sessions
        sessions = self.read_group(domain, ['session_id'], ['session_id'])
        
        return {
            'total_messages': total_messages,
            'processed_messages': processed_messages,
            'error_messages': error_messages,
            'avg_response_time': round(avg_response_time, 2),
            'sessions_count': len(sessions),
            'success_rate': (
                round((processed_messages / total_messages) * 100, 1)
                if total_messages > 0 else 0
            )
        }
    
    def action_view_details(self):
        """Open detailed view of the message."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': f'Message Details: {self.user_message[:50]}...',
            'res_model': 'chatbot.message',
            'view_mode': 'form',
            'res_id': self.id,
            'target': 'new',
            'context': self.env.context,
        }
    
    def action_replay_message(self):
        """Replay this message in a new chatbot wizard."""
        self.ensure_one()
        
        # Create new wizard with the message
        wizard = self.env['chatbot.wizard'].create({
            'user_input': self.user_message,
            'current_session_id': str(uuid.uuid4())[:12]
        })
        
        return {
            'type': 'ir.actions.act_window',
            'name': 'Replay Conversation',
            'res_model': 'chatbot.wizard',
            'view_mode': 'form',
            'res_id': wizard.id,
            'target': 'new',
            'context': {
                'default_user_input': self.user_message,
                'replay_mode': True
            },
        }
    
    def name_get(self):
        """Custom display name."""
        result = []
        for record in self:
            # Truncate message for display
            name = record.user_message[:60]
            if len(record.user_message) > 60:
                name += "..."
            
            # Add status indicator
            status_icon = {
                'draft': '📝',
                'sent': '📤',
                'processed': '✅',
                'error': '❌'
            }.get(record.status, '❓')
            
            name = f"{status_icon} {name}"
            result.append((record.id, name))
        
        return result
    
    @api.model
    def cleanup_old_messages(self, days=30):
        """Clean up messages older than specified days."""
        cutoff_date = fields.Datetime.now() - timedelta(days=days)
        old_messages = self.search([
            ('create_date', '<', cutoff_date)
        ])
        
        count = len(old_messages)
        old_messages.unlink()
        
        _logger.info(f"Cleaned up {count} old chatbot messages")
        return count