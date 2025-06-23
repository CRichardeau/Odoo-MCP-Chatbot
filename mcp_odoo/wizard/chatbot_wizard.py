# -*- coding: utf-8 -*-

from odoo import models, fields, api


class ChatbotWizard(models.TransientModel):
    _name = 'chatbot.wizard'
    _description = 'Interface modale pour le chatbot MCP'

    user_input = fields.Text(string='Votre message', required=True)
    bot_response = fields.Html(string='Réponse du chatbot', readonly=True)
    config_id = fields.Many2one('chatbot.config', string='Configuration', readonly=True)

    # Champs de configuration quick
    show_config = fields.Boolean(string='Afficher configuration', default=False)
    anthropic_api_key = fields.Char(string='Clé API Anthropic', password=True)
    mcp_url = fields.Char(string='URL MCP Gradio')

    @api.model
    def default_get(self, fields_list):
        """Récupérer la configuration active par défaut"""
        defaults = super().default_get(fields_list)
        config = self.env['chatbot.config'].search([('is_active', '=', True)], limit=1)
        if config:
            defaults['config_id'] = config.id
            defaults['anthropic_api_key'] = config.anthropic_api_key
            defaults['mcp_url'] = config.mcp_url
        return defaults

    def action_send_message(self):
        """Envoyer le message au chatbot et afficher la réponse"""
        if not self.user_input:
            return

        # Récupérer ou créer la configuration
        config = self._get_or_create_config()

        if not config:
            self.bot_response = "KO : Configuration manquante"
            return self._return_wizard()

        # Créer l'enregistrement du message
        message = self.env['chatbot_custom.message'].create({
            'user_input': self.user_input,
            'timestamp': fields.Datetime.now()
        })

        try:
            # Utiliser le service Anthropic commun
            anthropic_service = self.env['anthropic.service']

            # Appel initial avec MCP
            raw_response = anthropic_service.call_anthropic_api(self.user_input, config)

            # Post-traitement intelligent pour améliorer la présentation
            if (config.mcp_url and
                    ("**Résultats :**" in raw_response or
                     "[{'role': 'assistant'" in raw_response or
                     len(raw_response) > 300)):

                formatted_response = anthropic_service.post_process_with_llm(
                    raw_response, self.user_input, config
                )
                bot_response = formatted_response if formatted_response else raw_response
            else:
                bot_response = raw_response

            # Mettre à jour le message et le wizard
            message.write({'bot_response': bot_response})
            self.bot_response = self._format_response(bot_response)

        except Exception as e:
            error_msg = f"KO : Erreur: {str(e)}"
            message.write({'bot_response': error_msg})
            self.bot_response = error_msg

        return self._return_wizard()

    def action_toggle_config(self):
        """Basculer l'affichage de la configuration"""
        self.show_config = not self.show_config
        return self._return_wizard()

    def action_save_config(self):
        """Sauvegarder la configuration rapide"""
        if self.anthropic_api_key or self.mcp_url:
            config = self.env['chatbot.config'].search([('is_active', '=', True)], limit=1)
            if not config:
                config = self.env['chatbot.config'].create({
                    'name': 'Configuration Chatbot',
                    'is_active': True
                })

            vals = {}
            if self.anthropic_api_key:
                vals['anthropic_api_key'] = self.anthropic_api_key
            if self.mcp_url:
                vals['mcp_url'] = self.mcp_url

            if vals:
                config.write(vals)
                self.config_id = config.id

        self.show_config = False
        return self._return_wizard()

    def _get_or_create_config(self):
        """Récupérer ou créer la configuration"""
        if self.config_id:
            return self.config_id

        # Chercher une config active
        config = self.env['chatbot.config'].search([('is_active', '=', True)], limit=1)
        if config:
            return config

        # Créer une config temporaire si on a les paramètres
        if self.anthropic_api_key:
            config = self.env['chatbot.config'].create({
                'name': 'Configuration Temporaire',
                'anthropic_api_key': self.anthropic_api_key,
                'mcp_url': self.mcp_url or '',
                'is_active': True
            })
            self.config_id = config.id
            return config

        return False

    def _format_response(self, response):
        """Formater la réponse pour l'affichage HTML"""
        if not response:
            return ""

        # Convertir les sauts de ligne en <br/>
        formatted = response.replace('\n', '<br/>')

        # Convertir le markdown basique en HTML
        formatted = formatted.replace('**', '<strong>').replace('**', '</strong>')
        formatted = formatted.replace('*', '<em>').replace('*', '</em>')

        return formatted

    def _return_wizard(self):
        """Retourner le wizard en mode modal"""
        return {
            'type': 'ir.actions.act_window',
            'name': 'Chatbot MCP',
            'res_model': 'chatbot.wizard',
            'view_mode': 'form',
            'res_id': self.id,
            'target': 'new',
            'context': self.env.context,
        }

    def action_clear_conversation(self):
        """Effacer la conversation"""
        self.user_input = ""
        self.bot_response = ""
        return self._return_wizard()

    def action_open_config(self):
        """Ouvrir la configuration complète"""
        return {
            'type': 'ir.actions.act_window',
            'name': 'Configuration Chatbot',
            'res_model': 'chatbot.config',
            'view_mode': 'list,form',
            'target': 'current',
        }

    def _valid_field_parameter(self, field, name):
        return name in ['password'] or super()._valid_field_parameter(field, name)
