# -*- coding: utf-8 -*-
import logging
import requests
from datetime import timedelta
from typing import Dict, Any, List, Optional
from odoo import models, fields, api
from odoo.exceptions import UserError
from .base_service import BaseService

_logger = logging.getLogger(__name__)


class AnthropicService(BaseService, models.Model):
    """Service for managing Anthropic API interactions."""
    
    _name = 'anthropic.service'
    _description = 'Anthropic API Service'
    _rec_name = 'create_date'
    
    # Fields
    request_data = fields.Text('Request Data')
    response_data = fields.Text('Response Data')
    error_message = fields.Text('Error Message')
    success = fields.Boolean('Success', default=False)
    
    @api.model
    def create_chat_completion(
        self,
        messages: List[Dict[str, str]],
        model: str = 'claude-3-5-sonnet-20241022',
        temperature: float = 0.7,
        max_tokens: int = 4096
    ) -> Dict[str, Any]:
        """
        Create a chat completion using Anthropic API.
        
        Args:
            messages: List of message dictionaries
            model: Model to use
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate
            
        Returns:
            API response dictionary
        """
        config = self.env['chatbot.config'].sudo().search([], limit=1)
        if not config or not config.api_key:
            raise UserError('Anthropic API key not configured')
        
        # Prepare headers using base method
        headers = self._prepare_headers(config.api_key, 'application/json')
        headers.update({
            'x-api-key': config.api_key,
            'anthropic-version': '2023-06-01',
            'anthropic-beta': 'tools-2024-04-04'
        })
        
        # Build system prompt with Odoo context
        system_prompt = self._build_system_prompt()
        
        # Define available tools if MCP is connected
        tools = []
        config = self.env['chatbot.config'].get_active_config()
        if config.mcp_connected:
            tools = [
                {
                    "name": "search_odoo_records",
                    "description": "Search for records in Odoo database",
                    "input_schema": {
                        "type": "object",
                        "properties": {
                            "model": {
                                "type": "string",
                                "description": "Odoo model name (e.g., 'crm.lead', 'res.partner')"
                            },
                            "domain": {
                                "type": "array",
                                "description": "Search domain (e.g., [['name', 'ilike', 'test']])",
                                "default": []
                            },
                            "fields": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "Fields to retrieve",
                                "default": ["name", "id"]
                            },
                            "limit": {
                                "type": "integer",
                                "description": "Maximum number of records",
                                "default": 10
                            },
                            "order": {
                                "type": "string",
                                "description": "Sort order (e.g., 'create_date desc')",
                                "default": "id desc"
                            }
                        },
                        "required": ["model"]
                    }
                },
                {
                    "name": "read_odoo_record",
                    "description": "Read specific fields from an Odoo record",
                    "input_schema": {
                        "type": "object",
                        "properties": {
                            "model": {
                                "type": "string",
                                "description": "Odoo model name"
                            },
                            "record_id": {
                                "type": "integer",
                                "description": "Record ID"
                            },
                            "fields": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "Fields to read"
                            }
                        },
                        "required": ["model", "record_id", "fields"]
                    }
                }
            ]
        
        # Prepare payload
        payload = {
            'model': model,
            'messages': messages,
            'system': system_prompt,
            'temperature': temperature,
            'max_tokens': max_tokens
        }
        
        # Add tools if available
        if tools:
            payload['tools'] = tools
            # Let Claude decide when to use tools
            payload['tool_choice'] = {'type': 'auto'}
        
        # Log request
        service_record = self.create({
            'request_data': str(payload),
            'success': False
        })
        
        try:
            # Make API request
            response = requests.post(
                'https://api.anthropic.com/v1/messages',
                json=payload,
                headers=headers,
                timeout=30
            )
            
            if response.status_code == 200:
                data = response.json()
                
                # Update service record
                service_record.write({
                    'response_data': str(data),
                    'success': True
                })
                
                # Process the response
                result_text = ""
                tool_calls = []
                
                content = data.get('content', [])
                for item in content:
                    if item.get('type') == 'text':
                        result_text += item.get('text', '')
                    elif item.get('type') == 'tool_use':
                        tool_calls.append(item)
                
                # If there are tool calls, execute them
                if tool_calls:
                    tool_results = []
                    for tool_call in tool_calls:
                        tool_name = tool_call.get('name')
                        tool_input = tool_call.get('input', {})
                        tool_id = tool_call.get('id')
                        
                        try:
                            # Execute the tool
                            tool_result = self._execute_tool(tool_name, tool_input)
                            tool_results.append({
                                'type': 'tool_result',
                                'tool_use_id': tool_id,
                                'content': str(tool_result)
                            })
                        except Exception as e:
                            tool_results.append({
                                'type': 'tool_result',
                                'tool_use_id': tool_id,
                                'content': f"Error: {str(e)}",
                                'is_error': True
                            })
                    
                    # Continue the conversation with tool results
                    messages_with_tools = messages + [{
                        'role': 'assistant',
                        'content': content
                    }, {
                        'role': 'user',
                        'content': tool_results
                    }]
                    
                    # Make another API call with tool results
                    return self.create_chat_completion(
                        messages=messages_with_tools,
                        model=model,
                        temperature=temperature,
                        max_tokens=max_tokens
                    )
                
                # Return the text response
                return {
                    'success': True,
                    'message': result_text,
                    'usage': data.get('usage', {})
                }
            else:
                error_msg = f'API Error: {response.status_code} - {response.text}'
                service_record.write({
                    'error_message': error_msg,
                    'success': False
                })
                raise UserError(error_msg)
                
        except requests.exceptions.RequestException as e:
            error_msg = f'Network error: {str(e)}'
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
        config = self.env['chatbot.config'].get_active_config()
        
        # Check if MCP is connected
        mcp_instructions = ""
        if config.mcp_connected:
            mcp_instructions = """
You have DIRECT ACCESS to the Odoo database through the MCP server. You can:
- Search records: Use search_records(model, domain, fields, limit)
- Create records: Use create_record(model, values)
- Update records: Use update_record(model, record_id, values)
- Delete records: Use delete_record(model, record_id)
- Execute methods: Use execute_method(model, method, args)

Common Odoo models:
- crm.lead: CRM leads and opportunities
- res.partner: Contacts and companies
- sale.order: Sales orders
- account.move: Invoices and bills
- product.product: Products

When users ask about Odoo data, ALWAYS use the tools to query the database directly instead of saying you cannot access it. For example:
- To find the latest lead: use search_odoo_records with model='crm.lead', order='create_date desc', limit=1
- To get partner details: use read_odoo_record with model='res.partner', record_id=ID, fields=['name', 'email', 'phone']
"""
        
        return f"""You are an AI assistant integrated with Odoo ERP system.

Current context:
- User: {user.name}
- Company: {company.name}
- Language: {user.lang or 'en_US'}
{mcp_instructions}
You have access to Odoo's business context and can help with:
- Answering questions about business data
- Explaining processes and workflows
- Providing insights and recommendations
- Helping with Odoo usage

Always provide helpful, accurate, and contextual responses."""
    
    def _execute_tool(self, tool_name: str, tool_input: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute a tool call through MCP server.
        
        Args:
            tool_name: Name of the tool to execute
            tool_input: Tool parameters
            
        Returns:
            Tool execution result
        """
        config = self.env['chatbot.config'].get_active_config()
        if not config.mcp_connected:
            raise UserError('MCP not connected')
        
        
        # Map tool names to MCP endpoints
        if tool_name == 'search_odoo_records':
            url = f"{config.mcp_server_url.rstrip('/')}/search"
            payload = {
                'model': tool_input.get('model'),
                'domain': tool_input.get('domain', []),
                'fields': tool_input.get('fields', ['name', 'id']),
                'limit': tool_input.get('limit', 10),
                'order': tool_input.get('order', 'id desc')
            }
        elif tool_name == 'read_odoo_record':
            url = f"{config.mcp_server_url.rstrip('/')}/read"
            payload = {
                'model': tool_input.get('model'),
                'ids': [tool_input.get('record_id')],
                'fields': tool_input.get('fields')
            }
        else:
            raise UserError(f'Unknown tool: {tool_name}')
        
        # Execute the request
        try:
            response = requests.post(
                url,
                json=payload,
                headers={'Content-Type': 'application/json'},
                timeout=30
            )
            
            if response.status_code == 200:
                return response.json()
            else:
                raise UserError(f'MCP Error: {response.status_code} - {response.text}')
                
        except Exception as e:
            raise UserError(f'Tool execution error: {str(e)}')
    
    
    @api.autovacuum
    def _gc_old_records(self):
        """Clean up old service records (keep last 7 days)."""
        days_to_keep = 7
        domain = [
            ('create_date', '<', fields.Datetime.now() - timedelta(days=days_to_keep))
        ]
        records = self.search(domain)
        records.unlink()
        _logger.info(f'Cleaned up {len(records)} old Anthropic service records')
