from odoo import models, fields, api

class ChatbotMessage(models.Model):
    _name = 'chatbot_custom.message'
    _description = 'Message du Chatbot'
    _order = 'timestamp desc'
    _rec_name = 'user_input'

    user_input = fields.Char(string='Entrée utilisateur', required=True)
    bot_response = fields.Html(string='Réponse du bot')
    timestamp = fields.Datetime(string='Horodatage', default=fields.Datetime.now, readonly=True)
    
    # Nouveaux champs pour l'historique
    user_id = fields.Many2one('res.users', string='Utilisateur', default=lambda self: self.env.user, readonly=True)
    session_id = fields.Char(string='Session ID', default=lambda self: self._generate_session_id())
    conversation_id = fields.Char(string='Conversation', compute='_compute_conversation_id', store=True)
    message_type = fields.Selection([
        ('user', 'Message utilisateur'),
        ('bot', 'Réponse bot'),
        ('system', 'Message système')
    ], string='Type de message', default='user')
    status = fields.Selection([
        ('draft', 'Brouillon'),
        ('sent', 'Envoyé'),
        ('processed', 'Traité'),
        ('error', 'Erreur')
    ], string='Statut', default='draft')
    
    # Métadonnées
    response_time = fields.Float(string='Temps de réponse (s)', help='Temps de traitement en secondes')
    error_message = fields.Text(string='Message d\'erreur')
    config_used = fields.Many2one('chatbot.config', string='Configuration utilisée')
    
    @api.model
    def _generate_session_id(self):
        """Générer un ID de session unique"""
        import uuid
        return str(uuid.uuid4())[:8]
    
    @api.depends('user_id', 'session_id')
    def _compute_conversation_id(self):
        """Calculer l'ID de conversation basé sur l'utilisateur et la session"""
        for record in self:
            if record.user_id and record.session_id:
                record.conversation_id = f"{record.user_id.login}_{record.session_id}"
            else:
                record.conversation_id = f"unknown_{record.session_id or 'nosession'}"
    
    @api.model
    def get_conversation_history(self, limit=10):
        """Récupérer l'historique de conversation pour l'utilisateur actuel"""
        return self.search([
            ('user_id', '=', self.env.user.id)
        ], limit=limit, order='timestamp desc')
    
    @api.model 
    def get_user_sessions(self):
        """Récupérer toutes les sessions de l'utilisateur actuel"""
        return self.read_group(
            [('user_id', '=', self.env.user.id)],
            ['conversation_id', 'timestamp:max'],
            ['conversation_id'],
            orderby='timestamp desc'
        )
    
    def action_view_details(self):
        """Ouvrir la vue détaillée du message"""
        return {
            'type': 'ir.actions.act_window',
            'name': f'💬 Détail: {self.user_input[:50]}...',
            'res_model': 'chatbot_custom.message',
            'view_mode': 'form',
            'res_id': self.id,
            'target': 'new',
            'context': self.env.context,
        }
    
    def action_replay_message(self):
        """Rejouer ce message dans un nouveau wizard chatbot"""
        wizard = self.env['chatbot.wizard'].create({
            'user_input': self.user_input,
            'current_session_id': self._generate_session_id()
        })
        
        return {
            'type': 'ir.actions.act_window',
            'name': '🔄 Rejouer la conversation',
            'res_model': 'chatbot.wizard',
            'view_mode': 'form',
            'res_id': wizard.id,
            'target': 'new',
            'context': {
                'default_user_input': self.user_input,
                'replay_mode': True
            },
        }
    
    @api.model
    def get_statistics(self):
        """Récupérer des statistiques d'usage"""
        domain = [('user_id', '=', self.env.user.id)]
        
        stats = {
            'total_messages': self.search_count(domain),
            'processed_messages': self.search_count(domain + [('status', '=', 'processed')]),
            'error_messages': self.search_count(domain + [('status', '=', 'error')]),
            'avg_response_time': 0,
            'sessions_count': 0
        }
        
        # Calculer le temps de réponse moyen
        processed_messages = self.search(domain + [('status', '=', 'processed'), ('response_time', '>', 0)])
        if processed_messages:
            stats['avg_response_time'] = sum(processed_messages.mapped('response_time')) / len(processed_messages)
        
        # Compter les sessions uniques
        sessions = self.read_group(domain, ['session_id'], ['session_id'])
        stats['sessions_count'] = len(sessions)
        
        return stats
    
    def name_get(self):
        """Nom d'affichage personnalisé"""
        result = []
        for record in self:
            # Tronquer le message utilisateur pour l'affichage
            name = record.user_input[:60]
            if len(record.user_input) > 60:
                name += "..."
            
            # Ajouter un indicateur de statut
            status_icon = {
                'draft': '📝',
                'sent': '📤',
                'processed': '✅',
                'error': '❌'
            }.get(record.status, '❓')
            
            name = f"{status_icon} {name}"
            result.append((record.id, name))
        
        return result 
