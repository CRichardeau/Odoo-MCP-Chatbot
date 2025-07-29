# -*- coding: utf-8 -*-
import logging
import json
from datetime import timedelta
from typing import Dict, Any, List, Optional
from odoo import models, fields, api
from odoo.exceptions import UserError
from .base_service import BaseService

_logger = logging.getLogger(__name__)


class MCPService(BaseService, models.Model):
    """Service for managing MCP server interactions."""
    
    _name = 'mcp.service'
    _description = 'MCP Server Service'
    _rec_name = 'create_date'
    
    # Fields
    request_data = fields.Text('Request Data')
    response_data = fields.Text('Response Data')
    error_message = fields.Text('Error Message')
    success = fields.Boolean('Success', default=False)
    
    @api.model
    def send_message_to_mcp(
        self,
        messages: List[Dict[str, str]],
        model: str = 'claude-3-5-sonnet-20241022',
        temperature: float = 0.7,
        max_tokens: int = 4096
    ) -> Dict[str, Any]:
        """
        Send a message to the MCP server.
        
        Args:
            messages: List of message dictionaries
            model: Model to use
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate
            
        Returns:
            API response dictionary
        """
        config = self.env['chatbot.config'].sudo().search([], limit=1)
        if not config:
            raise UserError('Chatbot configuration not found')
        
        if not config.mcp_server_url:
            raise UserError('MCP server URL not configured')
        
        if not config.api_key:
            raise UserError('Anthropic API key not configured')
        
        # Build system prompt with Odoo context
        system_prompt = self._build_system_prompt()
        
        # Prepare payload for MCP server
        payload = {
            'messages': messages,
            'system': system_prompt,
            'model': model,
            'temperature': temperature,
            'max_tokens': max_tokens,
            'api_key': config.api_key
        }
        
        # Log request
        service_record = self.create({
            'request_data': json.dumps(payload, indent=2),
            'success': False
        })
        
        try:
            # Make request to MCP server
            url = f"{config.mcp_server_url.rstrip('/')}/messages"
            
            headers = self._prepare_headers('', 'application/json')
            headers['Accept'] = 'application/json'
            
            data = self._make_api_request(
                url=url,
                headers=headers,
                data=payload,
                timeout=60  # Increased timeout for MCP server
            )
            
            if 'error' not in data:
                
                # Update service record
                service_record.write({
                    'response_data': json.dumps(data, indent=2),
                    'success': True
                })
                
                # Extract message content - handle different response formats
                if 'message' in data:
                    return {
                        'success': True,
                        'message': data['message'],
                        'usage': data.get('usage', {})
                    }
                elif 'content' in data:
                    # Handle Anthropic-style response
                    return {
                        'success': True,
                        'message': data['content'],
                        'usage': data.get('usage', {})
                    }
                elif 'choices' in data and len(data['choices']) > 0:
                    # Handle OpenAI-style response
                    return {
                        'success': True,
                        'message': data['choices'][0].get('message', {}).get('content', ''),
                        'usage': data.get('usage', {})
                    }
                elif 'error' in data:
                    raise UserError(f"MCP Server Error: {data['error']}")
                else:
                    # Log the unexpected response for debugging
                    _logger.error(f"Unexpected MCP response format: {json.dumps(data)}")
                    raise UserError('Unexpected response format from MCP server')
            else:
                error_msg = data.get('error', 'Unknown error from MCP server')
                service_record.write({
                    'error_message': error_msg,
                    'success': False
                })
                raise UserError(error_msg)
        except Exception as e:
            error_msg = f'Unexpected error: {str(e)}'
            service_record.write({
                'error_message': error_msg,
                'success': False
            })
            raise UserError(error_msg)
    
    def _build_system_prompt(self) -> str:
        """
        Build system prompt with Odoo context.
        
        Returns:
            System prompt string
        """
        user = self.env.user
        company = user.company_id
        
        return f"""You are an AI assistant integrated with Odoo ERP system through MCP (Model Context Protocol).

Current context:
- User: {user.name}
- Company: {company.name}
- Language: {user.lang or 'en_US'}

You have access to Odoo's business context and can help with:
- Answering questions about business data
- Explaining processes and workflows
- Providing insights and recommendations
- Helping with Odoo usage

Always provide helpful, accurate, and contextual responses."""
    
    
    @api.autovacuum
    def _gc_old_records(self):
        """Clean up old service records (keep last 7 days)."""
        days_to_keep = 7
        domain = [
            ('create_date', '<', fields.Datetime.now() - timedelta(days=days_to_keep))
        ]
        records = self.search(domain)
        records.unlink()
        _logger.info(f'Cleaned up {len(records)} old MCP service records')