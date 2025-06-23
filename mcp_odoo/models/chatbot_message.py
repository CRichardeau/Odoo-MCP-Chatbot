# -*- coding: utf-8 -*-

from odoo import models, fields


class ChatbotMessage(models.Model):
    _name = 'chatbot_custom.message'
    _description = 'Message du Chatbot'

    user_input = fields.Char(string='Entrée utilisateur', required=True)
    bot_response = fields.Char(string='Réponse du bot')
    timestamp = fields.Datetime(string='Horodatage', default=fields.Datetime.now)
