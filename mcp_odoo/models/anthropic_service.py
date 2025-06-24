from odoo import models, api, tools
import requests
import json
import logging
from functools import lru_cache
import threading
from concurrent.futures import ThreadPoolExecutor
import time

_logger = logging.getLogger(__name__)

class AnthropicService(models.AbstractModel):
    """Service optimisé pour les appels API Anthropic avec mise en cache et threading"""
    _name = 'anthropic.service'
    _description = 'Service Anthropic centralisé et optimisé'
    
    # Constantes optimisées
    ANTHROPIC_API_URL = 'https://api.anthropic.com/v1/messages'
    DEFAULT_MODEL = 'claude-3-5-sonnet-20241022'
    DEFAULT_MAX_TOKENS = 1000
    MCP_TIMEOUT = 35  # Réduit de 25 à 15s
    DIRECT_TIMEOUT = 15  # Augmenté de 5 à 15s pour éviter les timeouts
    
    # Variables de classe pour persistance
    _thread_pool = None
    _session_cache = {}
    _session_lock = threading.Lock()
    
    # Cache pour les configurations
    _config_cache = {}
    _cache_timeout = 300  # 5 minutes
    
    @api.model
    def _get_thread_pool(self):
        """Initialise le pool de threads de manière paresseuse"""
        if AnthropicService._thread_pool is None:
            AnthropicService._thread_pool = ThreadPoolExecutor(max_workers=3)
        return AnthropicService._thread_pool
    
    @api.model
    @tools.ormcache('config_id')
    def _get_cached_config(self, config_id):
        """Cache la configuration pour éviter les requêtes répétées"""
        config = self.env['chatbot.config'].browse(config_id)
        return {
            'anthropic_api_key': config.anthropic_api_key,
            'anthropic_model': config.anthropic_model,
            'mcp_url': getattr(config, 'mcp_url', None)
        }
    
    @api.model
    def call_anthropic_api(self, user_input, config, fast_mode=True):
        """Point d'entrée principal optimisé"""
        start_time = time.time()
        
        try:
            # Validation rapide des inputs
            if not user_input or not user_input.strip():
                return "KO : Requête vide"
            
            # Cache de la config si c'est un recordset
            if hasattr(config, 'id'):
                cached_config = self._get_cached_config(config.id)
            else:
                cached_config = config
            
            # Validation de la clé API
            if not cached_config.get('anthropic_api_key'):
                return "KO : Clé API Anthropic requise"
            
            # Classification rapide du type d'appel
            use_mcp = bool(cached_config.get('mcp_url'))
            
            # Détection des requêtes simples qui n'ont pas besoin de MCP
            if use_mcp and self._is_simple_query(user_input):
                _logger.info("Requête simple détectée, utilisation d'Anthropic direct")
                use_mcp = False
            
            # Appel optimisé selon le type
            if use_mcp:
                _logger.info("Mode MCP Connector")
                result = self._call_anthropic_with_mcp_optimized(user_input, cached_config, fast_mode)
            else:
                _logger.info("Mode Anthropic direct")
                result = self._call_anthropic_direct_optimized(user_input, cached_config)
            
            elapsed = time.time() - start_time
            _logger.info(f"Appel Anthropic terminé en {elapsed:.2f}s")
            
            return result
            
        except Exception as e:
            _logger.error(f"Erreur dans call_anthropic_api: {str(e)}")
            return f"KO : Erreur: {str(e)}"
    
    @api.model
    def _is_simple_query(self, user_input):
        """Détecte les requêtes simples qui n'ont pas besoin de MCP"""
        simple_patterns = [
            'bonjour', 'salut', 'hello', 'hi', 'bonsoir',
            'comment ça va', 'merci', 'au revoir', 'bye'
        ]
        
        user_lower = user_input.lower().strip()
        # Seules les vraies salutations basiques sont simples
        # Les questions sur les capacités ('que peux-tu faire', 'aide', etc.) doivent utiliser MCP
        return any(pattern in user_lower for pattern in simple_patterns) and len(user_input.strip()) < 20
    
    @api.model
    def _call_anthropic_direct_optimized(self, user_input, config):
        """Version optimisée de l'appel direct"""
        try:
            # Préparation du payload avec session réutilisable
            session = self._get_requests_session()
            
            payload = {
                'model': config.get('anthropic_model') or self.DEFAULT_MODEL,
                'max_tokens': self.DEFAULT_MAX_TOKENS,
                'messages': [{'role': 'user', 'content': user_input}]
            }
            
            headers = {
                'Content-Type': 'application/json',
                'x-api-key': config['anthropic_api_key'],
                'anthropic-version': '2023-06-01'
            }
            
            response = session.post(
                self.ANTHROPIC_API_URL,
                json=payload,
                headers=headers,
                timeout=self.DIRECT_TIMEOUT
            )
            
            return self._process_direct_response(response)
            
        except Exception as e:
            _logger.error(f"Erreur appel direct optimisé: {str(e)}")
            return f"KO : Erreur API: {str(e)}"
    
    @api.model
    def _call_anthropic_with_mcp_optimized(self, user_input, config, fast_mode=True):
        """Version optimisée de l'appel MCP"""
        try:
            session = self._get_requests_session()
            mcp_url = self._prepare_mcp_url_cached(config['mcp_url'])
            
            # Prompt optimisé selon le mode
            content = self._build_optimized_prompt(user_input, fast_mode)
            
            payload = {
                'model': config.get('anthropic_model') or self.DEFAULT_MODEL,
                'max_tokens': self.DEFAULT_MAX_TOKENS if not fast_mode else 500,
                'messages': [{'role': 'user', 'content': content}],
                'mcp_servers': [{
                    'type': 'url',
                    'url': mcp_url,
                    'name': 'odoo-mcp-server',
                    'tool_configuration': {'enabled': True}
                }]
            }
            
            headers = {
                'Content-Type': 'application/json',
                'x-api-key': config['anthropic_api_key'],
                'anthropic-version': '2023-06-01',
                'anthropic-beta': 'mcp-client-2025-04-04'
            }
            
            response = session.post(
                self.ANTHROPIC_API_URL,
                json=payload,
                headers=headers,
                timeout=self.MCP_TIMEOUT
            )
            
            return self._process_mcp_response_optimized(response, fast_mode)
                
        except Exception as e:
            _logger.error(f"Erreur MCP optimisé: {str(e)}")
            return f"KO : Erreur MCP: {str(e)}"
    
    @lru_cache(maxsize=128)
    def _prepare_mcp_url_cached(self, mcp_url):
        """Version mise en cache de la préparation d'URL MCP"""
        if not mcp_url.endswith('/sse') and '/gradio_api/mcp/sse' not in mcp_url:
            if mcp_url.endswith('/gradio_api/mcp'):
                return mcp_url + '/sse'
            elif '/gradio_api/mcp' not in mcp_url:
                return mcp_url.rstrip('/') + '/gradio_api/mcp/sse'
        return mcp_url
    
    @api.model
    def _build_optimized_prompt(self, user_input, fast_mode=True):
        """Construit un prompt optimisé selon le mode"""
        if fast_mode:
            return f"""Tu es un assistant Odoo CRM connecté via MCP.

Requête utilisateur: "{user_input}"

Instructions importantes:
- Si c'est une salutation simple: réponds directement SANS outils
- Si tu as besoin de données Odoo: utilise les outils MCP appropriés
- IMPORTANT: Quand tu utilises les outils MCP, tu DOIS intégrer les résultats dans ta réponse de manière naturelle
- NE JAMAIS afficher les structures JSON brutes ou les métadonnées des outils
- Utilise les données récupérées pour formuler une réponse claire et utile
- Réponds en français et sois précis"""
        else:
            # Version complète pour les requêtes complexes
            return f"""Tu es un assistant Odoo CRM & Sales connecté à un serveur MCP.

Requête utilisateur : "{user_input}"

Instructions importantes :
1. **N'utilise PAS les outils MCP pour :**
   - Les salutations simples (bonjour, salut, hello, etc.)
   - Les présentations ou questions générales
   - Les demandes d'aide générale

2. **Utilise les outils MCP UNIQUEMENT pour :**
   - Analyser des leads ou opportunités spécifiques
   - Obtenir des statistiques CRM/Sales réelles
   - Effectuer du monitoring des performances
   - Rechercher des enregistrements précis

3. **CRITIQUE - Traitement des résultats :**
   - Quand tu utilises un outil MCP, tu reçois des données
   - Tu DOIS intégrer ces données dans ta réponse de manière naturelle
   - NE JAMAIS afficher les structures JSON brutes ou les métadonnées
   - Utilise les informations pour formuler une réponse claire et professionnelle
   - Présente les données de manière organisée et lisible

4. **Réponds en français et sois précis.**"""
    
    @api.model
    def _get_requests_session(self):
        """Retourne une session requests optimisée et réutilisable"""
        session_key = f"anthropic_session_{self.env.cr.dbname}"
        
        with AnthropicService._session_lock:
            if session_key not in AnthropicService._session_cache:
                session = requests.Session()
                # Configuration optimisée
                session.headers.update({
                    'User-Agent': 'Odoo-Anthropic-Client/1.0',
                    'Connection': 'keep-alive'
                })
                # Pool de connexions
                adapter = requests.adapters.HTTPAdapter(
                    pool_connections=5,
                    pool_maxsize=10,
                    max_retries=1
                )
                session.mount('https://', adapter)
                AnthropicService._session_cache[session_key] = session
            
            return AnthropicService._session_cache[session_key]
    
    @api.model
    def _process_direct_response(self, response):
        """Traitement optimisé des réponses directes"""
        if response.status_code == 200:
            data = response.json()
            if 'content' in data and data['content']:
                return data['content'][0].get('text', 'Réponse Anthropic')
            return "Réponse reçue d'Anthropic"
        
        _logger.error(f"Erreur API Anthropic: {response.status_code}")
        return f"KO : Erreur {response.status_code}"
    
    @api.model
    def _process_mcp_response_optimized(self, response, fast_mode=True):
        """Traitement optimisé des réponses MCP"""
        if response.status_code == 200:
            data = response.json()
            if 'content' in data and data['content']:
                return self._format_mcp_response_fast(data['content']) if fast_mode else self._format_mcp_response(data['content'], fast_mode=False)
            return "Réponse MCP reçue"
        
        elif response.status_code == 400:
            return "KO : Configuration MCP incorrecte"
        else:
            return f"KO : Erreur API {response.status_code}"
    
    @api.model
    def _format_mcp_response_fast(self, content_blocks):
        """Formatage ultra-rapide pour le mode fast"""
        result_parts = []
        
        for block in content_blocks:
            if block.get('type') == 'text':
                text = block.get('text', '').strip()
                if text:
                    result_parts.append(text)
        
        return "\n\n".join(result_parts) if result_parts else "Réponse MCP"
    
    @api.model
    def call_anthropic_async(self, user_input, config, callback=None):
        """Version asynchrone pour les appels non-bloquants"""
        def async_call():
            result = self.call_anthropic_api(user_input, config, fast_mode=True)
            if callback:
                callback(result)
            return result
        
        future = self._get_thread_pool().submit(async_call)
        return future
    
    @api.model
    def _format_mcp_response(self, content_blocks, fast_mode=False):
        """Version complète du formatage (conservée pour compatibilité)"""
        if fast_mode:
            return self._format_mcp_response_fast(content_blocks)
        
        # Implémentation complète conservée...
        main_response = []
        tool_results = []
        
        for block in content_blocks:
            if block.get('type') == 'text':
                text_content = block.get('text', '').strip()
                if text_content:
                    # Éviter les structures JSON brutes
                    if not (text_content.startswith('[{') and text_content.endswith('}]')):
                        main_response.append(text_content)
            elif block.get('type') == 'mcp_tool_result':
                if not block.get('is_error', False):
                    tool_content = block.get('content', [])
                    if tool_content and len(tool_content) > 0:
                        result_text = tool_content[0].get('text', str(tool_content))
                        if result_text and result_text.strip():
                            # Inclure tous les tool_results pour traitement ultérieur
                            tool_results.append(result_text.strip())
        
        final_parts = []
        if main_response:
            final_parts.extend(main_response)
        
        return "\n".join(final_parts) if final_parts else "Réponse MCP"
