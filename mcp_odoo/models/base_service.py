# -*- coding: utf-8 -*-
from odoo import api, models
import logging

_logger = logging.getLogger(__name__)

class BaseService(models.AbstractModel):
    """Classe de base abstraite pour les services chatbot"""
    _name = 'base.service'
    _description = 'Service de base pour les intégrations chatbot'
    
    @api.model
    def _make_api_request(self, url, headers, data, timeout=30):
        """Méthode commune pour faire des requêtes API"""
        import requests
        
        try:
            response = requests.post(
                url,
                headers=headers,
                json=data,
                timeout=timeout
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.Timeout:
            _logger.error(f"Timeout lors de l'appel API à {url}")
            return {"error": "Timeout lors de l'appel API"}
        except requests.exceptions.RequestException as e:
            _logger.error(f"Erreur lors de l'appel API: {str(e)}")
            return {"error": f"Erreur lors de l'appel API: {str(e)}"}
    
    @api.model
    def _prepare_headers(self, api_key, content_type="application/json"):
        """Prépare les headers communs pour les requêtes API"""
        return {
            "Content-Type": content_type,
            "Authorization": f"Bearer {api_key}" if api_key else ""
        }
    
    @api.model
    def _log_api_call(self, service_name, user_input, response):
        """Log les appels API pour le monitoring"""
        _logger.info(f"{service_name} - Input: {user_input[:100]}...")
        _logger.info(f"{service_name} - Response: {str(response)[:200]}...")
    
    @api.model
    def _validate_config(self, config):
        """Valide la configuration du service"""
        if not config:
            return False, "Aucune configuration trouvée"
        if not config.api_key:
            return False, "Clé API manquante"
        if not config.active:
            return False, "Configuration inactive"
        return True, None
    
    @api.model
    def call_api(self, user_input, config, **kwargs):
        """Méthode à surcharger dans les classes enfants"""
        raise NotImplementedError("Cette méthode doit être implémentée dans la classe enfant")
