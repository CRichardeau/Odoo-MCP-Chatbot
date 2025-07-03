{
    'name': 'Chatbot Custom MCP',
    'version': '18.0.2.0.0',
    'summary': 'Module de base pour un chatbot Odoo avec MCP Gradio.',
    'description': 'Permet la gestion de messages pour un chatbot personnalisé connecté à l\'API Anthropic via MCP Gradio.',
    'author': 'CHEF PIXEL',
    'website': 'https://chef-pixel.fr',
    'support': "hello@chef-pixel.fr",
    'category': 'Tools',
    'depends': ['base'],
    'license': 'LGPL-3',
    'data': [
        'security/ir.model.access.csv',
        'views/chatbot_v18.xml',
        'views/chatbot_messages.xml',
        'wizard/chatbot_wizard_view.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'mcp_odoo/static/src/scss/chatbot_modal.scss',
             'MCP_Odoo/static/src/js/chatbot_widget.js',
        ],
    },
    'images': ['static/description/icon.png'],
    'installable': True,
    'application': True,
    'auto_install': False,
}
