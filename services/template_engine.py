import os
from pathlib import Path
from typing import Any
import logging
from jinja2 import Environment, FileSystemLoader, select_autoescape

from services.email_interfaces import ITemplateRenderer

logger = logging.getLogger(__name__)

class JinjaTemplateEngine(ITemplateRenderer):
    """
    Template engine using Jinja2.
    Loads templates from the templates/email directory.
    """
    def __init__(self, template_dir: str = None):
        if template_dir is None:
            # Default to <project_root>/templates/email
            base_dir = Path(__file__).parent.parent
            template_dir = str(base_dir / "templates" / "email")
            
        self.env = Environment(
            loader=FileSystemLoader(template_dir),
            autoescape=select_autoescape(['html', 'xml'])
        )

    def render_html(self, template_name: str, **kwargs: Any) -> str:
        """Render an HTML template with the given arguments."""
        try:
            if not template_name.endswith('.html'):
                template_name += '.html'
            template = self.env.get_template(template_name)
            return template.render(**kwargs)
        except Exception as e:
            logger.error(f"Failed to render HTML template {template_name}: {e}")
            raise

    def render_text(self, template_name: str, **kwargs: Any) -> str:
        """
        Render a plain text template.
        For simplicity in this app, we generate plain text manually in the service,
        but this supports future .txt Jinja templates if needed.
        """
        try:
            if not template_name.endswith('.txt'):
                template_name += '.txt'
            template = self.env.get_template(template_name)
            return template.render(**kwargs)
        except Exception as e:
            logger.debug(f"Plain text template {template_name} not found. Fallback to basic string.")
            return ""

# Singleton instance
_template_engine: JinjaTemplateEngine | None = None

def get_template_engine() -> ITemplateRenderer:
    global _template_engine
    if _template_engine is None:
        _template_engine = JinjaTemplateEngine()
    return _template_engine
