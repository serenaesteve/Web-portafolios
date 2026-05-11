"""
agent_portfolio.py
Agente llama3.2 con tool-calling para construcción modular de portfolios.
Cada sección se monta por separado; el agente orquesta el ensamblado y
asigna el resultado al subdominio correspondiente.
"""

import json, re, uuid, logging, sqlite3, requests
from markupsafe import escape
from datetime import datetime

OLLAMA_URL   = "http://localhost:11434/api/chat"
OLLAMA_MODEL = "llama3.2:latest"
DB_PATH      = "portify.db"
DOMAIN_BASE  = "portify.es"

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# ESTILOS POR PLANTILLA
# ─────────────────────────────────────────────────────────────────────────────
STYLES = {
    "oscuro": {
        "bg": "#080810", "text": "#ededf5", "muted": "#a0a0b8", "dim": "#58586a",
        "border": "rgba(255,255,255,.08)", "card": "rgba(255,255,255,.04)",
        "nav_bg": "rgba(8,8,16,.85)", "nav_border": "rgba(255,255,255,.06)", "nav_link": "#a0a0b8",
        "font_h": "Instrument Serif,serif", "font_b": "DM Sans,sans-serif",
        "font_url": "https://fonts.googleapis.com/css2?family=Instrument+Serif:ital@0;1&family=DM+Sans:wght@300;400;500;600&display=swap",
        "tag_bg": "rgba(255,255,255,.06)", "tag_border": "rgba(255,255,255,.1)", "tag_text": "#c8c8d8",
        "sep": "rgba(255,255,255,.06)", "footer_c": "#3a3a4a",
        "h2_size": "2rem", "proj_text": "#ededf5", "proj_sub": "#a0a0b8",
        "nav_border_top": "3px solid rgba(255,255,255,.06)",
    },
    "minimalista": {
        "bg": "#fafaf8", "text": "#1a1a1a", "muted": "#555", "dim": "#aaa",
        "border": "#e8e4e0", "card": "#fff",
        "nav_bg": "#fafaf8", "nav_border": "#e8e4e0", "nav_link": "#888",
        "font_h": "Playfair Display,serif", "font_b": "Inter,sans-serif",
        "font_url": "https://fonts.googleapis.com/css2?family=Playfair+Display:ital,wght@0,400;0,700;1,400&family=Inter:wght@300;400;500&display=swap",
        "tag_bg": "transparent", "tag_border": "#e0dcd8", "tag_text": "#555",
        "sep": "#e8e4e0", "footer_c": "#aaa",
        "h2_size": "2.2rem", "proj_text": "#1a1a1a", "proj_sub": "#555",
        "nav_border_top": "1px solid #e8e4e0",
    },
    "creativo": {
        "bg": "#fff", "text": "#111", "muted": "#555", "dim": "#888",
        "border": "#eee", "card": "#fff",
        "nav_bg": "#fff", "nav_border": "#111", "nav_link": "#666",
        "font_h": "Space Grotesk,sans-serif", "font_b": "Space Grotesk,sans-serif",
        "font_url": "https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;600;700&display=swap",
        "tag_bg": "transparent", "tag_border": "#111", "tag_text": "#111",
        "sep": "#eee", "footer_c": "#888",
        "h2_size": "2rem", "proj_text": "#111", "proj_sub": "#555",
        "nav_border_top": "3px solid #111",
    },
    "editorial": {
        "bg": "#f5f0e8", "text": "#1a1208", "muted": "#5a4a2a", "dim": "#8a7a5a",
        "border": "#d4c8a8", "card": "#f5f0e8",
        "nav_bg": "#f5f0e8", "nav_border": "#1a1208", "nav_link": "#8a7a5a",
        "font_h": "DM Serif Display,serif", "font_b": "DM Sans,sans-serif",
        "font_url": "https://fonts.googleapis.com/css2?family=DM+Serif+Display:ital@0;1&family=DM+Sans:wght@300;400;500&display=swap",
        "tag_bg": "transparent", "tag_border": "#c4b890", "tag_text": "#5a4a2a",
        "sep": "#d4c8a8", "footer_c": "#8a7a5a",
        "h2_size": "2.4rem", "proj_text": "#1a1208", "proj_sub": "#5a4a2a",
        "nav_border_top": "2px solid #1a1208",
    },
    "organico": {
        "bg": "#fdf6ee", "text": "#2c1810", "muted": "#7a5a3a", "dim": "#8a6a4a",
        "border": "#e8d8c8", "card": "#fff",
        "nav_bg": "rgba(253,246,238,.92)", "nav_border": "#e8d8c8", "nav_link": "#8a6a4a",
        "font_h": "Fraunces,serif", "font_b": "Plus Jakarta Sans,sans-serif",
        "font_url": "https://fonts.googleapis.com/css2?family=Fraunces:ital,wght@0,400;0,700;1,400&family=Plus+Jakarta+Sans:wght@300;400;500;600&display=swap",
        "tag_bg": "transparent", "tag_border": "#e8d8c8", "tag_text": "#5a3a1a",
        "sep": "#e8d8c8", "footer_c": "#8a6a4a",
        "h2_size": "2.1rem", "proj_text": "#2c1810", "proj_sub": "#7a5a3a",
        "nav_border_top": "1px solid #e8d8c8",
    },

    # ── NUEVAS 10 PLANTILLAS ──────────────────────────────────────────────────

    "glass": {
        "bg": "#0f0c29", "text": "#e8eaf6", "muted": "#90a4ae", "dim": "#546e7a",
        "border": "rgba(255,255,255,0.15)", "card": "rgba(255,255,255,0.07)",
        "nav_bg": "rgba(15,12,41,0.7)", "nav_border": "rgba(255,255,255,0.08)", "nav_link": "#90a4ae",
        "font_h": "Outfit,sans-serif", "font_b": "Outfit,sans-serif",
        "font_url": "https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700&display=swap",
        "tag_bg": "rgba(255,255,255,0.1)", "tag_border": "rgba(255,255,255,0.22)", "tag_text": "#e8eaf6",
        "sep": "rgba(255,255,255,0.08)", "footer_c": "#37474f",
        "h2_size": "2.2rem", "proj_text": "#e8eaf6", "proj_sub": "#90a4ae",
        "nav_border_top": "1px solid rgba(255,255,255,0.1)",
        "tag_radius": "999px", "card_radius": "20px",
        "card_extra": "backdrop-filter:blur(20px);-webkit-backdrop-filter:blur(20px)",
        "card_shadow": "0 8px 32px rgba(0,0,0,0.35)",
        "special_css": "body{background:linear-gradient(135deg,#0f0c29 0%,#302b63 50%,#24243e 100%)!important}body::before{content:'';position:fixed;inset:0;background:linear-gradient(135deg,#0f0c29,#302b63,#24243e);z-index:-1}",
        "label": "Glassmorphism", "emoji": "🔮",
    },
    "neo": {
        "bg": "#fff", "text": "#000", "muted": "#333", "dim": "#666",
        "border": "#000", "card": "#fff",
        "nav_bg": "#fff", "nav_border": "#000", "nav_link": "#000",
        "font_h": "Space Grotesk,sans-serif", "font_b": "Space Grotesk,sans-serif",
        "font_url": "https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;600;700&display=swap",
        "tag_bg": "#000", "tag_border": "#000", "tag_text": "#fff",
        "sep": "#000", "footer_c": "#333",
        "h2_size": "2.6rem", "proj_text": "#000", "proj_sub": "#333",
        "nav_border_top": "4px solid #000",
        "tag_radius": "0px", "card_radius": "0px",
        "card_extra": "border:3px solid #000",
        "card_shadow": "6px 6px 0 #000",
        "special_css": "h1,h2{font-weight:700;letter-spacing:-.03em}section{border-top:3px solid #000}",
        "label": "Neobrutalism", "emoji": "⬛",
    },
    "terminal": {
        "bg": "#0d1117", "text": "#00ff41", "muted": "#00c030", "dim": "#007020",
        "border": "rgba(0,255,65,0.4)", "card": "#161b22",
        "nav_bg": "#0d1117", "nav_border": "rgba(0,255,65,0.4)", "nav_link": "#00c030",
        "font_h": "JetBrains Mono,monospace", "font_b": "JetBrains Mono,monospace",
        "font_url": "https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@300;400;500;600;700&display=swap",
        "tag_bg": "rgba(0,255,65,0.08)", "tag_border": "rgba(0,255,65,0.4)", "tag_text": "#00ff41",
        "sep": "rgba(0,255,65,0.2)", "footer_c": "#007020",
        "h2_size": "1.5rem", "proj_text": "#00ff41", "proj_sub": "#00c030",
        "nav_border_top": "1px solid rgba(0,255,65,0.4)",
        "tag_radius": "4px", "card_radius": "4px",
        "card_extra": "", "card_shadow": "0 0 12px rgba(0,255,65,0.15)",
        "h2_prefix": "// ", "hero_prompt": "$ whoami",
        "special_css": "@keyframes blink{0%,100%{opacity:1}50%{opacity:0}}.cursor{animation:blink 1s step-end infinite}::selection{background:#00ff41;color:#0d1117}h2{font-size:1.4rem!important}",
        "label": "Terminal", "emoji": "💻",
    },
    "luxury": {
        "bg": "#09080c", "text": "#f5f0e8", "muted": "#c9a84c", "dim": "#6b5c30",
        "border": "rgba(201,168,76,0.22)", "card": "#110f17",
        "nav_bg": "rgba(9,8,12,0.92)", "nav_border": "rgba(201,168,76,0.15)", "nav_link": "#7a6835",
        "font_h": "Cormorant Garamond,serif", "font_b": "DM Sans,sans-serif",
        "font_url": "https://fonts.googleapis.com/css2?family=Cormorant+Garamond:ital,wght@0,300;0,400;0,600;1,400&family=DM+Sans:wght@300;400;500&display=swap",
        "tag_bg": "rgba(201,168,76,0.08)", "tag_border": "rgba(201,168,76,0.3)", "tag_text": "#c9a84c",
        "sep": "rgba(201,168,76,0.15)", "footer_c": "#3a3020",
        "h2_size": "2.8rem", "proj_text": "#f5f0e8", "proj_sub": "#7a6835",
        "nav_border_top": "1px solid rgba(201,168,76,0.15)",
        "tag_radius": "3px", "card_radius": "2px",
        "card_extra": "border:1px solid rgba(201,168,76,0.22)",
        "card_shadow": "0 20px 60px rgba(0,0,0,0.6)",
        "special_css": "h1,h2,h3{font-style:italic;letter-spacing:.02em}",
        "label": "Luxury", "emoji": "✨",
    },
    "retro": {
        "bg": "#fef3d0", "text": "#2d1b00", "muted": "#7a4f20", "dim": "#b8864e",
        "border": "#d4a24e", "card": "#fff8e7",
        "nav_bg": "#2d1b00", "nav_border": "#d4a24e", "nav_link": "#fef3d0",
        "font_h": "Syne,sans-serif", "font_b": "Syne,sans-serif",
        "font_url": "https://fonts.googleapis.com/css2?family=Syne:wght@400;500;600;700;800&display=swap",
        "tag_bg": "#2d1b00", "tag_border": "#2d1b00", "tag_text": "#fef3d0",
        "sep": "#d4a24e", "footer_c": "#b8864e",
        "h2_size": "2.4rem", "proj_text": "#2d1b00", "proj_sub": "#7a4f20",
        "nav_border_top": "3px solid #d4a24e",
        "tag_radius": "4px", "card_radius": "8px",
        "card_extra": "", "card_shadow": "4px 4px 0 #d4a24e",
        "special_css": "",
        "label": "Retro", "emoji": "📼",
    },
    "nordic": {
        "bg": "#ffffff", "text": "#1a1a1a", "muted": "#555", "dim": "#999",
        "border": "#e5e5e5", "card": "#fafafa",
        "nav_bg": "#fff", "nav_border": "#e5e5e5", "nav_link": "#999",
        "font_h": "Josefin Sans,sans-serif", "font_b": "Josefin Sans,sans-serif",
        "font_url": "https://fonts.googleapis.com/css2?family=Josefin+Sans:ital,wght@0,300;0,400;0,600;0,700;1,300&display=swap",
        "tag_bg": "transparent", "tag_border": "#1a1a1a", "tag_text": "#1a1a1a",
        "sep": "#e5e5e5", "footer_c": "#ccc",
        "h2_size": "1.7rem", "proj_text": "#1a1a1a", "proj_sub": "#666",
        "nav_border_top": "1px solid #e5e5e5",
        "tag_radius": "0px", "card_radius": "4px",
        "card_extra": "", "card_shadow": "none",
        "special_css": "h1,h2,h3{text-transform:uppercase;letter-spacing:.12em;font-weight:700}p{font-weight:300;letter-spacing:.04em}",
        "label": "Nordic", "emoji": "❄️",
    },
    "pastel": {
        "bg": "#fff5f9", "text": "#3d2a3a", "muted": "#9c7b94", "dim": "#c4a8be",
        "border": "#f0d4e8", "card": "#fff",
        "nav_bg": "rgba(255,245,249,0.92)", "nav_border": "#f0d4e8", "nav_link": "#c4a8be",
        "font_h": "Nunito,sans-serif", "font_b": "Nunito,sans-serif",
        "font_url": "https://fonts.googleapis.com/css2?family=Nunito:wght@300;400;600;700;800&display=swap",
        "tag_bg": "#fde8f4", "tag_border": "#f0d4e8", "tag_text": "#9c7b94",
        "sep": "#f0d4e8", "footer_c": "#c4a8be",
        "h2_size": "2rem", "proj_text": "#3d2a3a", "proj_sub": "#9c7b94",
        "nav_border_top": "1px solid #f0d4e8",
        "tag_radius": "999px", "card_radius": "20px",
        "card_extra": "", "card_shadow": "0 4px 24px rgba(255,133,161,0.12)",
        "special_css": "",
        "label": "Pastel", "emoji": "🌸",
    },
    "neon": {
        "bg": "#08001a", "text": "#00eeff", "muted": "#9b59b6", "dim": "#4a2b5c",
        "border": "rgba(0,238,255,0.2)", "card": "#0d0028",
        "nav_bg": "rgba(8,0,26,0.88)", "nav_border": "rgba(0,238,255,0.15)", "nav_link": "#9b59b6",
        "font_h": "Rajdhani,sans-serif", "font_b": "Rajdhani,sans-serif",
        "font_url": "https://fonts.googleapis.com/css2?family=Rajdhani:wght@400;500;600;700&display=swap",
        "tag_bg": "rgba(0,238,255,0.07)", "tag_border": "rgba(0,238,255,0.3)", "tag_text": "#00eeff",
        "sep": "rgba(0,238,255,0.15)", "footer_c": "#4a2b5c",
        "h2_size": "2.2rem", "proj_text": "#00eeff", "proj_sub": "#9b59b6",
        "nav_border_top": "1px solid rgba(0,238,255,0.2)",
        "tag_radius": "4px", "card_radius": "8px",
        "card_extra": "", "card_shadow": "0 0 20px rgba(0,238,255,0.1),inset 0 0 20px rgba(0,238,255,0.02)",
        "special_css": "body{background:#08001a}body::before{content:'';position:fixed;inset:0;background-image:linear-gradient(rgba(0,238,255,0.03) 1px,transparent 1px),linear-gradient(90deg,rgba(0,238,255,0.03) 1px,transparent 1px);background-size:40px 40px;pointer-events:none;z-index:0}.w,.n{position:relative;z-index:1}nav{z-index:100!important}h1,h2{text-shadow:0 0 30px currentColor;text-transform:uppercase;letter-spacing:.06em}",
        "label": "Neon", "emoji": "⚡",
    },
    "magazine": {
        "bg": "#fff", "text": "#1a1a1a", "muted": "#444", "dim": "#888",
        "border": "#ddd", "card": "#f8f8f8",
        "nav_bg": "#fff", "nav_border": "#1a1a1a", "nav_link": "#555",
        "font_h": "Libre Baskerville,serif", "font_b": "Source Sans 3,sans-serif",
        "font_url": "https://fonts.googleapis.com/css2?family=Libre+Baskerville:ital,wght@0,400;0,700;1,400&family=Source+Sans+3:wght@300;400;600&display=swap",
        "tag_bg": "#1a1a1a", "tag_border": "#1a1a1a", "tag_text": "#fff",
        "sep": "#ddd", "footer_c": "#888",
        "h2_size": "2.6rem", "proj_text": "#1a1a1a", "proj_sub": "#444",
        "nav_border_top": "4px double #1a1a1a",
        "tag_radius": "0px", "card_radius": "0px",
        "card_extra": "border-left:4px solid #1a1a1a;border-top:none;border-right:none;border-bottom:none;border-radius:0",
        "card_shadow": "none",
        "h2_prefix": "— ",
        "special_css": "h2{font-style:italic;border-bottom:2px solid #1a1a1a;padding-bottom:10px}section{padding:64px 0}",
        "label": "Magazine", "emoji": "📰",
    },
    "gradient": {
        "bg": "#4f46e5", "text": "#fff", "muted": "rgba(255,255,255,0.75)", "dim": "rgba(255,255,255,0.5)",
        "border": "rgba(255,255,255,0.22)", "card": "rgba(255,255,255,0.12)",
        "nav_bg": "rgba(79,70,229,0.82)", "nav_border": "rgba(255,255,255,0.15)", "nav_link": "rgba(255,255,255,0.7)",
        "font_h": "Archivo,sans-serif", "font_b": "Archivo,sans-serif",
        "font_url": "https://fonts.googleapis.com/css2?family=Archivo:ital,wght@0,400;0,500;0,600;0,700;1,400&display=swap",
        "tag_bg": "rgba(255,255,255,0.15)", "tag_border": "rgba(255,255,255,0.3)", "tag_text": "#fff",
        "sep": "rgba(255,255,255,0.15)", "footer_c": "rgba(255,255,255,0.4)",
        "h2_size": "2.2rem", "proj_text": "#fff", "proj_sub": "rgba(255,255,255,0.75)",
        "nav_border_top": "1px solid rgba(255,255,255,0.15)",
        "tag_radius": "999px", "card_radius": "16px",
        "card_extra": "backdrop-filter:blur(12px);-webkit-backdrop-filter:blur(12px)",
        "card_shadow": "0 8px 32px rgba(0,0,0,0.18)",
        "special_css": "body{background:linear-gradient(135deg,#4f46e5 0%,#7c3aed 40%,#db2777 75%,#f59e0b 100%)!important;min-height:100vh}body::before{content:'';position:fixed;inset:0;background:inherit;z-index:-1}",
        "label": "Gradient", "emoji": "🌈",
    },
    "cv": {
        "bg": "#ffffff", "text": "#1a1a2e", "muted": "#4a4a6a", "dim": "#8888aa",
        "border": "#d8d8e8", "card": "#f8f8fc",
        "nav_bg": "#fff", "nav_border": "#d8d8e8", "nav_link": "#4a4a6a",
        "font_h": "Inter,sans-serif", "font_b": "Inter,sans-serif",
        "font_url": "https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap",
        "tag_bg": "#f0f0f8", "tag_border": "#d8d8e8", "tag_text": "#4a4a6a",
        "sep": "#d8d8e8", "footer_c": "#aaa",
        "h2_size": "1rem", "proj_text": "#1a1a2e", "proj_sub": "#4a4a6a",
        "nav_border_top": "1px solid #d8d8e8",
        "tag_radius": "4px", "card_radius": "6px",
        "card_extra": "", "card_shadow": "none",
        "special_css": (
            "@media print{"
            "nav,#theme-toggle,#pf-contact-form,footer{display:none!important}"
            "body{background:#fff!important;font-size:11pt}"
            ".cv-hero{padding:24px 0 16px!important}"
            "section{padding:14px 0!important;break-inside:avoid}"
            "article{break-inside:avoid}"
            "@page{margin:16mm 14mm;size:A4}"
            "}"
            "body{max-width:820px;margin:0 auto}"
            ".cv-print-btn{position:fixed;bottom:20px;right:20px;padding:10px 18px;"
            "background:#1a1a2e;color:#fff;border:none;border-radius:8px;font-size:.85rem;"
            "font-weight:600;cursor:pointer;z-index:999;box-shadow:0 4px 16px rgba(0,0,0,.2)}"
            "@media print{.cv-print-btn{display:none}}"
        ),
        "label": "CV / Resume", "emoji": "📄",
    },
}

ANIM_CSS = (
    "@keyframes _fIn{from{opacity:0}to{opacity:1}}"
    "@keyframes _sUp{from{opacity:0;transform:translateY(36px)}to{opacity:1;transform:none}}"
    "@keyframes _sLt{from{opacity:0;transform:translateX(36px)}to{opacity:1;transform:none}}"
    "@keyframes _zIn{from{opacity:0;transform:scale(.9)}to{opacity:1;transform:scale(1)}}"
    "@keyframes _fl{0%,100%{transform:translateY(0)}50%{transform:translateY(-10px)}}"
    "@keyframes _blob{0%,100%{border-radius:60% 40% 30% 70%/60% 30% 70% 40%}50%{border-radius:30% 60% 70% 40%/50% 60% 30% 60%}}"
    ".anim-el{opacity:0;animation-fill-mode:both;animation-duration:.7s;animation-timing-function:cubic-bezier(.22,1,.36,1)}"
    ".anim-el.vis{opacity:1}"
)
ANIM_MAP = {
    "fade":       ".anim-el.vis{animation-name:_fIn}",
    "slide-up":   ".anim-el.vis{animation-name:_sUp}",
    "slide-left": ".anim-el.vis{animation-name:_sLt}",
    "zoom":       ".anim-el.vis{animation-name:_zIn}",
    "float":      ".anim-el{opacity:1!important}.anim-el.vis{animation-name:_fl;animation-duration:3s;animation-iteration-count:infinite;animation-timing-function:ease-in-out}",
    "typewriter": "",
}
ANIM_DELAYS = "".join(
    ".anim-el:nth-child(%d){animation-delay:%.2fs}" % (i, i * 0.09) for i in range(1, 20)
)
ANIM_JS = (
    '<script>(function(){'
    'var io=new IntersectionObserver(function(es){es.forEach(function(e){'
    'if(e.isIntersecting)e.target.classList.add("vis")});},{threshold:.1,rootMargin:"0px 0px -40px 0px"});'
    'document.querySelectorAll(".anim-el").forEach(function(el){io.observe(el)});'
    '})();</script>'
)

# SVG icons for social networks
_ICONS = {
    "email":     '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="4" width="20" height="16" rx="2"/><path d="m22 7-8.97 5.7a1.94 1.94 0 0 1-2.06 0L2 7"/></svg>',
    "website":   '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><path d="M12 2a14.5 14.5 0 0 0 0 20 14.5 14.5 0 0 0 0-20"/><path d="M2 12h20"/></svg>',
    "linkedin":  '<svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><path d="M20.447 20.452h-3.554v-5.569c0-1.328-.027-3.037-1.852-3.037-1.853 0-2.136 1.445-2.136 2.939v5.667H9.351V9h3.414v1.561h.046c.477-.9 1.637-1.85 3.37-1.85 3.601 0 4.267 2.37 4.267 5.455v6.286zM5.337 7.433a2.062 2.062 0 0 1-2.063-2.065 2.064 2.064 0 1 1 2.063 2.065zm1.782 13.019H3.555V9h3.564v11.452zM22.225 0H1.771C.792 0 0 .774 0 1.729v20.542C0 23.227.792 24 1.771 24h20.451C23.2 24 24 23.227 24 22.271V1.729C24 .774 23.2 0 22.222 0h.003z"/></svg>',
    "github":    '<svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><path d="M12 0C5.374 0 0 5.373 0 12c0 5.302 3.438 9.8 8.207 11.387.599.111.793-.261.793-.577v-2.234c-3.338.726-4.033-1.416-4.033-1.416-.546-1.387-1.333-1.756-1.333-1.756-1.089-.745.083-.729.083-.729 1.205.084 1.839 1.237 1.839 1.237 1.07 1.834 2.807 1.304 3.492.997.107-.775.418-1.305.762-1.604-2.665-.305-5.467-1.334-5.467-5.931 0-1.311.469-2.381 1.236-3.221-.124-.303-.535-1.524.117-3.176 0 0 1.008-.322 3.301 1.23A11.509 11.509 0 0 1 12 5.803c1.02.005 2.047.138 3.006.404 2.291-1.552 3.297-1.23 3.297-1.23.653 1.653.242 2.874.118 3.176.77.84 1.235 1.911 1.235 3.221 0 4.609-2.807 5.624-5.479 5.921.43.372.823 1.102.823 2.222v3.293c0 .319.192.694.801.576C20.566 21.797 24 17.3 24 12c0-6.627-5.373-12-12-12z"/></svg>',
    "twitter":   '<svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><path d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-4.714-6.231-5.401 6.231H2.744l7.73-8.835L1.254 2.25H8.08l4.259 5.63zm-1.161 17.52h1.833L7.084 4.126H5.117z"/></svg>',
    "instagram": '<svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><path d="M12 2.163c3.204 0 3.584.012 4.85.07 3.252.148 4.771 1.691 4.919 4.919.058 1.265.069 1.645.069 4.849 0 3.205-.012 3.584-.069 4.849-.149 3.225-1.664 4.771-4.919 4.919-1.266.058-1.644.07-4.85.07-3.204 0-3.584-.012-4.849-.07-3.26-.149-4.771-1.699-4.919-4.92-.058-1.265-.07-1.644-.07-4.849 0-3.204.013-3.583.07-4.849.149-3.227 1.664-4.771 4.919-4.919 1.266-.057 1.645-.069 4.849-.069zm0-2.163c-3.259 0-3.667.014-4.947.072-4.358.2-6.78 2.618-6.98 6.98-.059 1.281-.073 1.689-.073 4.948 0 3.259.014 3.668.072 4.948.2 4.358 2.618 6.78 6.98 6.98 1.281.058 1.689.072 4.948.072 3.259 0 3.668-.014 4.948-.072 4.354-.2 6.782-2.618 6.979-6.98.059-1.28.073-1.689.073-4.948 0-3.259-.014-3.667-.072-4.947-.196-4.354-2.617-6.78-6.979-6.98-1.281-.059-1.69-.073-4.949-.073zm0 5.838a6.162 6.162 0 1 0 0 12.324 6.162 6.162 0 0 0 0-12.324zM12 16a4 4 0 1 1 0-8 4 4 0 0 1 0 8zm6.406-11.845a1.44 1.44 0 1 0 0 2.881 1.44 1.44 0 0 0 0-2.881z"/></svg>',
    "youtube":   '<svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><path d="M23.498 6.186a3.016 3.016 0 0 0-2.122-2.136C19.505 3.545 12 3.545 12 3.545s-7.505 0-9.377.505A3.017 3.017 0 0 0 .502 6.186C0 8.07 0 12 0 12s0 3.93.502 5.814a3.016 3.016 0 0 0 2.122 2.136c1.871.505 9.376.505 9.376.505s7.505 0 9.377-.505a3.015 3.015 0 0 0 2.122-2.136C24 15.93 24 12 24 12s0-3.93-.502-5.814zM9.545 15.568V8.432L15.818 12l-6.273 3.568z"/></svg>',
    "tiktok":    '<svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><path d="M19.59 6.69a4.83 4.83 0 0 1-3.77-4.25V2h-3.45v13.67a2.89 2.89 0 0 1-2.88 2.5 2.89 2.89 0 0 1-2.89-2.89 2.89 2.89 0 0 1 2.89-2.89c.28 0 .54.04.79.1V9.01a6.33 6.33 0 0 0-.79-.05 6.34 6.34 0 0 0-6.34 6.34 6.34 6.34 0 0 0 6.34 6.34 6.34 6.34 0 0 0 6.33-6.34V8.69a8.18 8.18 0 0 0 4.78 1.52V6.75a4.85 4.85 0 0 1-1.01-.06z"/></svg>',
}

# ─────────────────────────────────────────────────────────────────────────────
# GENERADORES DE SECCIÓN
# ─────────────────────────────────────────────────────────────────────────────

def _esc(v): return str(escape(v)) if v else ""

def _valid_color(c):
    return c if c and re.match(r'^#[0-9a-fA-F]{3,8}$', str(c)) else "#F18A8E"

def _ini(nombre):
    p = (nombre or "").strip().split()
    if not p: return "P"
    return (p[0][0] + p[-1][0]).upper() if len(p) >= 2 else p[0][0].upper()

def _avatar_html(foto, nombre, color, size=80, radius="50%"):
    if foto and foto.startswith("data:"):
        return f'<img src="{foto}" style="width:{size}px;height:{size}px;border-radius:{radius};object-fit:cover;display:block">'
    ini = _ini(nombre)
    fs = int(size * 0.38)
    return (f'<div style="width:{size}px;height:{size}px;border-radius:{radius};background:{color};color:#fff;'
            f'display:flex;align-items:center;justify-content:center;font-size:{fs}px;font-weight:700;flex-shrink:0">{ini}</div>')

def _proj_url_html(url, color):
    url = (url or "").strip()
    if not url or url in ["#", "ninguna", "none", ""]: return ""
    if not url.startswith("http"): url = "https://" + url
    return f'<a href="{_esc(url)}" target="_blank" style="color:{color};font-size:.78rem;font-weight:600">Ver ↗</a>'

def _proj_img_html(imagen, color, h=200):
    if imagen and (imagen.startswith("data:") or imagen.startswith("http")):
        return f'<div style="height:{h}px;overflow:hidden"><img src="{imagen}" style="width:100%;height:100%;object-fit:cover"></div>'
    return (f'<div style="height:{h}px;background:linear-gradient(135deg,{color}44,{color}18);'
            f'display:flex;align-items:center;justify-content:center">'
            f'<svg width="48" height="48" viewBox="0 0 64 64" fill="none">'
            f'<rect x="8" y="14" width="48" height="36" rx="4" stroke="{color}" stroke-width="2" fill="none" opacity=".5"/>'
            f'<circle cx="22" cy="26" r="5" fill="{color}" opacity=".4"/>'
            f'<path d="M8 40l14-10 10 8 8-7 16 12" stroke="{color}" stroke-width="2" stroke-linecap="round" opacity=".5"/>'
            f'</svg></div>')


def tool_generar_nav(nombre, plantilla, color):
    s = STYLES.get(plantilla, STYLES["oscuro"])
    c = _valid_color(color)
    n = _esc(nombre)
    is_dark = plantilla in ("oscuro", "glass", "terminal", "luxury", "neon", "gradient")
    logo_style = (
        f'font-family:{s["font_h"]};font-size:1.05rem;font-weight:700;letter-spacing:-.02em;'
        + (f'background:linear-gradient(135deg,{c} 0%,#a78bfa 100%);-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text'
           if is_dark else f'color:{s["text"]}')
    )
    link_hover = f"transition:color .2s"
    return (
        f'<nav style="position:sticky;top:0;z-index:100;background:{s["nav_bg"]};'
        f'backdrop-filter:blur(24px);-webkit-backdrop-filter:blur(24px);'
        f'border-bottom:{s["nav_border_top"]};padding:0">'
        f'<div class="w" style="display:flex;align-items:center;justify-content:space-between;height:58px">'
        f'<span style="{logo_style}">{n}</span>'
        f'<div style="display:flex;gap:4px">'
        f'<a href="#skills" style="color:{s["nav_link"]};font-size:.78rem;font-weight:500;text-decoration:none;padding:6px 12px;border-radius:8px;{link_hover}">Skills</a>'
        f'<a href="#proyectos" style="color:{s["nav_link"]};font-size:.78rem;font-weight:500;text-decoration:none;padding:6px 12px;border-radius:8px;{link_hover}">Proyectos</a>'
        f'<a href="#experiencia" style="color:{s["nav_link"]};font-size:.78rem;font-weight:500;text-decoration:none;padding:6px 12px;border-radius:8px;{link_hover}">Experiencia</a>'
        f'<a href="#contacto" style="color:{s["nav_link"]};font-size:.78rem;font-weight:500;text-decoration:none;padding:8px 14px;border-radius:8px;background:{c};color:#fff!important;{link_hover}">Contactar</a>'
        f'</div></div></nav>'
    )


def tool_generar_hero(nombre, rol, descripcion, color, plantilla, foto="", n_proyectos=0, n_skills=0):
    s = STYLES.get(plantilla, STYLES["oscuro"])
    c = _valid_color(color)
    n = _esc(nombre)
    r = _esc(rol)
    d = _esc(descripcion)
    anio = datetime.now().year
    card_r = s.get("card_radius", "20px")
    card_extra = s.get("card_extra", "")
    card_shadow = s.get("card_shadow", "")

    parts = n.split() if " " in n else [n]
    n1 = parts[0]
    n2 = " ".join(parts[1:]) if len(parts) > 1 else ""

    is_dark = plantilla in ("oscuro", "glass", "terminal", "luxury", "neon", "gradient")
    avatar_r = "50%" if plantilla not in ("oscuro", "luxury", "neo", "nordic") else "16px"
    avatar_size = 100
    avatar = _avatar_html(foto, nombre, c, avatar_size, avatar_r)

    # Decorative background blob (dark themes only)
    blob_html = ""
    if is_dark and plantilla not in ("terminal", "neon"):
        blob_html = (
            f'<div aria-hidden="true" style="position:absolute;top:-80px;right:-60px;width:420px;height:420px;'
            f'background:radial-gradient(ellipse,{c}22 0%,transparent 70%);'
            f'pointer-events:none;z-index:0;filter:blur(40px)"></div>'
            f'<div aria-hidden="true" style="position:absolute;bottom:-40px;left:-80px;width:320px;height:320px;'
            f'background:radial-gradient(ellipse,#7c6dfa18 0%,transparent 70%);'
            f'pointer-events:none;z-index:0;filter:blur(50px)"></div>'
        )

    stats = ""
    if n_proyectos or n_skills:
        items = ""
        if n_proyectos:
            items += (f'<div style="padding:14px 20px;border-radius:12px;background:{s["card"]};border:1px solid {s["border"]}">'
                      f'<div style="font-size:1.8rem;font-weight:800;color:{c};line-height:1">{n_proyectos}+</div>'
                      f'<div style="font-size:.68rem;color:{s["dim"]};text-transform:uppercase;letter-spacing:.08em;margin-top:2px">Proyectos</div></div>')
        if n_skills:
            items += (f'<div style="padding:14px 20px;border-radius:12px;background:{s["card"]};border:1px solid {s["border"]}">'
                      f'<div style="font-size:1.8rem;font-weight:800;color:{c};line-height:1">{n_skills}+</div>'
                      f'<div style="font-size:.68rem;color:{s["dim"]};text-transform:uppercase;letter-spacing:.08em;margin-top:2px">Skills</div></div>')
        stats = f'<div class="anim-el" style="display:flex;gap:10px;margin-top:28px">{items}</div>'

    prompt_html = ""
    if s.get("hero_prompt"):
        prompt_html = f'<p style="font-family:inherit;font-size:.85rem;color:{s["muted"]};margin-bottom:12px">{s["hero_prompt"]} <span class="cursor">█</span></p>'

    # Name with gradient accent on second part
    grad_accent = (
        f'background:linear-gradient(135deg,{c} 0%,#a78bfa 100%);'
        f'-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text'
    ) if is_dark else f'color:{c}'

    name_html = (
        f'<h1 class="anim-el" style="font-family:{s["font_h"]};font-size:clamp(2.8rem,6vw,5.5rem);'
        f'line-height:.92;letter-spacing:-.04em;font-weight:700;margin-bottom:16px;color:{s["text"]}">'
        f'{n1}<br><span style="{grad_accent}">{n2}</span></h1>'
        if n2 else
        f'<h1 class="anim-el" style="font-family:{s["font_h"]};font-size:clamp(2.8rem,6vw,5.5rem);'
        f'line-height:.92;letter-spacing:-.04em;font-weight:700;margin-bottom:16px;color:{s["text"]}">{n1}</h1>'
    )

    # CTA buttons
    cta_html = (
        f'<div class="anim-el" style="display:flex;gap:10px;flex-wrap:wrap;margin-top:28px">'
        f'<a href="#proyectos" style="display:inline-flex;align-items:center;gap:7px;padding:11px 22px;'
        f'border-radius:10px;background:{c};color:#fff;font-weight:600;font-size:.88rem;text-decoration:none;'
        f'transition:opacity .2s,transform .2s">Ver proyectos</a>'
        f'<a href="#contacto" style="display:inline-flex;align-items:center;gap:7px;padding:11px 22px;'
        f'border-radius:10px;border:1px solid {s["border"]};color:{s["text"]};font-weight:500;font-size:.88rem;text-decoration:none;'
        f'transition:opacity .2s,transform .2s">Contactar →</a>'
        f'</div>'
    )

    # Avatar card (right side)
    shadow_style = f";box-shadow:{card_shadow}" if card_shadow else ""
    # Avatar with glow ring
    avatar_ring = (
        f'<div style="width:{avatar_size+10}px;height:{avatar_size+10}px;border-radius:{avatar_r};'
        f'padding:5px;background:linear-gradient(135deg,{c}66,#7c6dfa44);margin:0 auto 16px">'
        f'<div style="border-radius:{avatar_r};overflow:hidden;width:100%;height:100%">{avatar}</div>'
        f'</div>'
    )
    card_style = (
        f"background:{s['card']};border:1px solid {s['border']};border-radius:{card_r};"
        f"padding:28px 24px;text-align:center;{card_extra}{shadow_style};position:relative;overflow:hidden"
    )
    card_deco = (
        f'<div aria-hidden="true" style="position:absolute;top:-30px;right:-30px;width:120px;height:120px;'
        f'background:radial-gradient(circle,{c}20,transparent 70%);pointer-events:none"></div>'
    ) if is_dark else ""

    return (
        f'<section style="padding:100px 0 80px;position:relative;overflow:hidden">'
        f'{blob_html}'
        f'<div class="w" style="display:grid;grid-template-columns:1fr 300px;gap:60px;align-items:center;position:relative;z-index:1">'
        f'<div>'
        f'<div class="anim-el" style="display:inline-flex;align-items:center;gap:8px;padding:5px 12px 5px 5px;'
        f'border-radius:999px;background:{s["card"]};border:1px solid {s["border"]};margin-bottom:20px">'
        f'<span style="width:6px;height:6px;border-radius:50%;background:{c};display:block;box-shadow:0 0 6px {c}"></span>'
        f'<span style="font-size:.68rem;font-weight:600;letter-spacing:.08em;text-transform:uppercase;color:{s["dim"]}">Portfolio · {anio}</span>'
        f'</div>'
        f'{prompt_html}{name_html}'
        f'<p class="anim-el" style="color:{c};font-size:.95rem;font-weight:600;margin-bottom:12px">{r}</p>'
        f'<p class="anim-el" style="color:{s["muted"]};font-size:.95rem;max-width:500px;line-height:1.9;font-weight:300">{d}</p>'
        f'{stats}{cta_html}'
        f'</div>'
        f'<div class="anim-el" style="{card_style}">'
        f'{card_deco}{avatar_ring}'
        f'<h3 style="font-family:{s["font_h"]};font-size:1.15rem;font-weight:700;margin-bottom:4px;color:{s["text"]}">{n}</h3>'
        f'<p style="color:{c};font-size:.82rem;font-weight:600;margin-bottom:12px">{r}</p>'
        f'<div style="width:40px;height:2px;background:{c};margin:0 auto;border-radius:2px;opacity:.6"></div>'
        f'</div>'
        f'</div></section>'
    )


def tool_generar_skills(skills, color, plantilla):
    if not skills: return ""
    s = STYLES.get(plantilla, STYLES["oscuro"])
    c = _valid_color(color)
    tr = s.get("tag_radius", "10px")
    prefix = s.get("h2_prefix", "")
    # First skill gets accent styling, rest are standard
    tags = ""
    for i, sk in enumerate(skills):
        if i == 0:
            tags += (f'<span class="anim-el" style="padding:9px 18px;border-radius:{tr};'
                     f'background:{c};color:#fff;'
                     f'font-size:.85rem;font-weight:600;cursor:default;'
                     f'transition:transform .2s,box-shadow .2s">{_esc(sk)}</span>')
        else:
            tags += (f'<span class="anim-el" style="padding:9px 18px;border-radius:{tr};'
                     f'background:{s["tag_bg"]};border:1px solid {s["tag_border"]};'
                     f'font-size:.85rem;font-weight:500;color:{s["tag_text"]};cursor:default;'
                     f'transition:border-color .2s,transform .2s">{_esc(sk)}</span>')
    return (
        f'<section id="skills" style="padding:72px 0;border-top:1px solid {s["sep"]}">'
        f'<div class="n">'
        f'<div style="display:flex;align-items:center;gap:16px;margin-bottom:32px">'
        f'<h2 style="font-family:{s["font_h"]};font-size:{s["h2_size"]};font-weight:700;margin:0;color:{s["text"]};white-space:nowrap">{prefix}Habilidades</h2>'
        f'<div style="flex:1;height:1px;background:linear-gradient(90deg,{s["sep"]},transparent)"></div></div>'
        f'<div style="display:flex;flex-wrap:wrap;gap:10px">{tags}</div>'
        f'</div></section>'
    )


def tool_generar_proyectos(proyectos, color, plantilla):
    if not proyectos: return ""
    s = STYLES.get(plantilla, STYLES["oscuro"])
    c = _valid_color(color)
    cr = s.get("card_radius", "16px")
    tr = s.get("tag_radius", "6px")
    card_extra = s.get("card_extra", "")
    card_shadow = s.get("card_shadow", "")
    prefix = s.get("h2_prefix", "")
    shadow_style = f";box-shadow:{card_shadow}" if card_shadow else ""

    def _tec_tags(tec_str):
        if not tec_str: return ""
        parts = [t.strip() for t in re.split(r'[,/;·•]', tec_str) if t.strip()]
        return "".join(
            f'<span style="padding:3px 9px;border-radius:{tr};background:{s["tag_bg"]};'
            f'border:1px solid {s["tag_border"]};font-size:.72rem;font-weight:500;color:{s["tag_text"]}">{_esc(t)}</span>'
            for t in parts[:5]
        )

    cards_html = ""
    for i, p in enumerate(proyectos):
        titulo = _esc(p.get("titulo", ""))
        desc   = _esc(p.get("descripcion", ""))
        tec    = p.get("tecnologias", "")
        img_h  = _proj_img_html(p.get("imagen", ""), c, h=220)
        url    = (p.get("url", "") or "").strip()
        url_clean = url if url.startswith("http") else ("https://" + url if url else "")

        url_btn = ""
        if url_clean and url_clean not in ["https://", "https://#"]:
            url_btn = (f'<a href="{_esc(url_clean)}" target="_blank" '
                       f'style="display:inline-flex;align-items:center;gap:5px;padding:7px 14px;'
                       f'border-radius:8px;background:{c};color:#fff;font-size:.78rem;font-weight:600;text-decoration:none">'
                       f'Ver proyecto ↗</a>')

        if i == 0 and len(proyectos) > 1:
            # Featured card — full width
            cards_html += (
                f'<article class="anim-el" style="grid-column:1/-1;background:{s["card"]};border:1px solid {s["border"]};'
                f'border-radius:{cr};overflow:hidden;{card_extra}{shadow_style};'
                f'display:grid;grid-template-columns:1fr 1fr;gap:0">'
                f'<div style="position:relative">{_proj_img_html(p.get("imagen",""), c, h=260)}'
                f'<div style="position:absolute;top:12px;left:12px;padding:4px 10px;border-radius:6px;'
                f'background:{c};color:#fff;font-size:.68rem;font-weight:700;letter-spacing:.06em;text-transform:uppercase">Destacado</div></div>'
                f'<div style="padding:32px 28px;display:flex;flex-direction:column;justify-content:center">'
                f'<h4 style="font-family:{s["font_h"]};font-size:1.3rem;font-weight:700;margin-bottom:10px;color:{s["proj_text"]};line-height:1.2">{titulo}</h4>'
                f'<p style="color:{s["proj_sub"]};font-size:.9rem;margin-bottom:16px;line-height:1.75;flex:1">{desc}</p>'
                f'<div style="display:flex;flex-wrap:wrap;gap:6px;margin-bottom:16px">{_tec_tags(tec)}</div>'
                f'{url_btn}</div></article>'
            )
        else:
            # Regular card
            cards_html += (
                f'<article class="anim-el" style="background:{s["card"]};border:1px solid {s["border"]};'
                f'border-radius:{cr};overflow:hidden;animation-delay:{i*0.08:.2f}s;{card_extra}{shadow_style};'
                f'transition:transform .25s,box-shadow .25s;display:flex;flex-direction:column">'
                f'{img_h}'
                f'<div style="padding:22px;flex:1;display:flex;flex-direction:column">'
                f'<h4 style="font-family:{s["font_h"]};font-size:1.05rem;font-weight:600;margin-bottom:8px;color:{s["proj_text"]}">{titulo}</h4>'
                f'<p style="color:{s["proj_sub"]};font-size:.87rem;margin-bottom:14px;line-height:1.75;flex:1">{desc}</p>'
                f'<div style="display:flex;flex-wrap:wrap;gap:6px;margin-bottom:14px">{_tec_tags(tec)}</div>'
                f'{url_btn}</div></article>'
            )

    return (
        f'<section id="proyectos" style="padding:72px 0;border-top:1px solid {s["sep"]}">'
        f'<div class="w">'
        f'<div style="display:flex;align-items:center;gap:16px;margin-bottom:32px">'
        f'<h2 style="font-family:{s["font_h"]};font-size:{s["h2_size"]};font-weight:700;margin:0;color:{s["text"]};white-space:nowrap">{prefix}Proyectos</h2>'
        f'<div style="flex:1;height:1px;background:linear-gradient(90deg,{s["sep"]},transparent)"></div></div>'
        f'<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:20px">{cards_html}</div>'
        f'</div></section>'
    )


def tool_generar_experiencia(experiencia, color, plantilla):
    if not experiencia: return ""
    s = STYLES.get(plantilla, STYLES["oscuro"])
    c = _valid_color(color)
    prefix = s.get("h2_prefix", "")
    cr = s.get("card_radius", "14px")
    card_extra = s.get("card_extra", "")
    card_shadow = s.get("card_shadow", "")
    shadow_style = f";box-shadow:{card_shadow}" if card_shadow else ""
    items = ""
    total = len([e for e in experiencia if isinstance(e, (dict, str))])
    idx = 0
    for e in experiencia:
        if isinstance(e, dict):
            t = _esc(e.get("titulo", ""))
            d = _esc(e.get("descripcion", ""))
        elif isinstance(e, str) and e.strip():
            t, d = "", _esc(e)
        else:
            continue
        is_last = (idx == total - 1)
        title_h = (f'<p style="font-family:{s["font_h"]};font-weight:700;font-size:1rem;margin-bottom:6px;color:{s["text"]}">{t}</p>'
                   if t else "")
        items += (
            f'<div class="anim-el" style="display:grid;grid-template-columns:44px 1fr;gap:0;position:relative">'
            # Timeline dot + line
            f'<div style="display:flex;flex-direction:column;align-items:center">'
            f'<div style="width:14px;height:14px;border-radius:50%;background:{c};flex-shrink:0;'
            f'box-shadow:0 0 0 4px {c}20,0 0 12px {c}44;margin-top:4px"></div>'
            + (f'<div style="width:2px;flex:1;background:linear-gradient({c}44,{c}11);margin-top:6px;min-height:24px"></div>' if not is_last else '')
            + f'</div>'
            # Content card
            f'<div style="padding-bottom:{28 if not is_last else 0}px;padding-left:4px">'
            f'<div style="background:{s["card"]};border:1px solid {s["border"]};border-radius:{cr};'
            f'padding:18px 20px;{card_extra}{shadow_style}">'
            f'{title_h}'
            f'<p style="color:{s["muted"]};font-size:.88rem;line-height:1.8;margin:0">{d}</p>'
            f'</div></div>'
            f'</div>'
        )
        idx += 1
    return (
        f'<section id="experiencia" style="padding:72px 0;border-top:1px solid {s["sep"]}">'
        f'<div class="n">'
        f'<div style="display:flex;align-items:center;gap:16px;margin-bottom:32px">'
        f'<h2 style="font-family:{s["font_h"]};font-size:{s["h2_size"]};font-weight:700;margin:0;color:{s["text"]};white-space:nowrap">{prefix}Experiencia</h2>'
        f'<div style="flex:1;height:1px;background:linear-gradient(90deg,{s["sep"]},transparent)"></div></div>'
        f'<div style="max-width:680px">{items}</div>'
        f'</div></section>'
    )


def tool_generar_contacto(email, redes, color, plantilla, portfolio_id=None):
    s = STYLES.get(plantilla, STYLES["oscuro"])
    c = _valid_color(color)
    cr = s.get("card_radius", "24px")
    card_extra = s.get("card_extra", "")
    card_shadow = s.get("card_shadow", "")
    prefix = s.get("h2_prefix", "")
    shadow_style = f";box-shadow:{card_shadow}" if card_shadow else ""
    redes = redes or {}
    is_dark = plantilla in ("oscuro", "glass", "terminal", "luxury", "neon", "gradient")

    # Email CTA button
    email_btn = ""
    if email:
        email_btn = (
            f'<a href="mailto:{_esc(email)}" style="display:inline-flex;align-items:center;gap:8px;'
            f'padding:13px 28px;border-radius:12px;background:{c};color:#fff;font-weight:600;'
            f'font-size:.9rem;text-decoration:none;transition:opacity .2s,transform .2s">'
            f'{_ICONS["email"]} {_esc(email)}</a>'
        )

    # Social icon buttons
    networks = [
        ("website",   redes.get("website","")),
        ("linkedin",  redes.get("linkedin","")),
        ("github",    redes.get("github","")),
        ("twitter",   redes.get("twitter","")),
        ("instagram", redes.get("instagram","")),
        ("youtube",   redes.get("youtube","")),
        ("tiktok",    redes.get("tiktok","")),
    ]
    social_btns = ""
    for key, url in networks:
        if url and url not in ["#", "ninguna", "none", ""]:
            if not url.startswith("http"): url = "https://" + url
            icon = _ICONS.get(key, "")
            labels = {"website":"Web","linkedin":"LinkedIn","github":"GitHub","twitter":"Twitter",
                      "instagram":"Instagram","youtube":"YouTube","tiktok":"TikTok"}
            social_btns += (
                f'<a href="{_esc(url)}" target="_blank" title="{labels.get(key,key)}" '
                f'style="display:inline-flex;align-items:center;justify-content:center;width:44px;height:44px;'
                f'border-radius:10px;border:1px solid {s["border"]};color:{s["text"]};text-decoration:none;'
                f'transition:border-color .2s,transform .2s,background .2s" '
                f'aria-label="{labels.get(key,key)}">{icon}</a>'
            )

    # Background decoration for dark themes
    bg_deco = ""
    if is_dark and plantilla not in ("terminal", "neon"):
        bg_deco = (f'<div aria-hidden="true" style="position:absolute;inset:0;'
                   f'background:radial-gradient(ellipse at 50% 0%,{c}14,transparent 70%);'
                   f'border-radius:inherit;pointer-events:none"></div>')

    card_style = (
        f"background:{s['card']};border:1px solid {s['border']};border-radius:{cr};"
        f"padding:60px 40px;text-align:center;{card_extra}{shadow_style};position:relative;overflow:hidden"
    )
    social_row = f'<div style="display:flex;gap:10px;justify-content:center;flex-wrap:wrap;margin-top:16px">{social_btns}</div>' if social_btns else ""

    inp_style = (f"width:100%;padding:11px 14px;border-radius:10px;border:1px solid {s['border']};"
                 f"background:{s['card']};color:{s['text']};font-size:.9rem;font-family:inherit;"
                 f"outline:none;transition:border-color .2s")
    contact_form = ""
    if portfolio_id:
        contact_form = (
            f'<div style="margin-top:36px;padding-top:32px;border-top:1px solid {s["sep"]};text-align:left">'
            f'<p style="font-size:.75rem;font-weight:700;letter-spacing:.08em;text-transform:uppercase;color:{s["muted"]};margin-bottom:16px;text-align:center">Envíame un mensaje directo</p>'
            f'<form id="pf-contact-form" onsubmit="pfSendMsg(event,{portfolio_id})" style="display:flex;flex-direction:column;gap:10px;max-width:480px;margin:0 auto">'
            f'<div style="display:grid;grid-template-columns:1fr 1fr;gap:10px">'
            f'<input name="nombre" placeholder="Tu nombre" required style="{inp_style}">'
            f'<input name="email"  type="email" placeholder="Tu email" required style="{inp_style}">'
            f'</div>'
            f'<textarea name="mensaje" placeholder="Tu mensaje..." rows="4" required style="{inp_style};resize:vertical"></textarea>'
            f'<button type="submit" id="pf-contact-btn" style="padding:12px 24px;border-radius:10px;background:{c};color:#fff;font-weight:600;font-size:.9rem;border:none;cursor:pointer;transition:opacity .2s">Enviar mensaje</button>'
            f'<p id="pf-contact-msg" style="font-size:.82rem;text-align:center;display:none"></p>'
            f'</form></div>'
            f'<script>'
            f'async function pfSendMsg(e,pid){{'
            f'e.preventDefault();'
            f'const f=e.target,btn=document.getElementById("pf-contact-btn"),msg=document.getElementById("pf-contact-msg");'
            f'btn.textContent="Enviando...";btn.disabled=true;'
            f'try{{'
            f'const r=await fetch(`/portfolio/${{pid}}/contactar`,{{method:"POST",headers:{{"Content-Type":"application/json"}},'
            f'body:JSON.stringify({{nombre:f.nombre.value,email:f.email.value,mensaje:f.mensaje.value}})}});'
            f'const d=await r.json();'
            f'if(d.ok){{msg.style.color="{c}";msg.textContent="✓ Mensaje enviado. ¡Gracias!";msg.style.display="block";f.reset();}}'
            f'else{{msg.style.color="#e06a7c";msg.textContent=d.error||"Error al enviar";msg.style.display="block";}}'
            f'}}catch(err){{msg.style.color="#e06a7c";msg.textContent="Error de conexión";msg.style.display="block";}}'
            f'btn.textContent="Enviar mensaje";btn.disabled=false;'
            f'}}'
            f'</script>'
        )

    return (
        f'<section id="contacto" style="padding:80px 0;border-top:1px solid {s["sep"]}">'
        f'<div class="n">'
        f'<div class="anim-el" style="{card_style}">'
        f'{bg_deco}'
        f'<div style="position:relative;z-index:1">'
        f'<p style="font-size:.68rem;font-weight:700;letter-spacing:.1em;text-transform:uppercase;color:{c};margin-bottom:12px;text-align:center">¿Trabajamos juntos?</p>'
        f'<h2 style="font-family:{s["font_h"]};font-size:{s["h2_size"]};font-weight:700;margin-bottom:12px;color:{s["text"]};text-align:center">{prefix}Hablemos</h2>'
        f'<p style="color:{s["muted"]};margin-bottom:32px;font-size:.95rem;max-width:440px;margin-left:auto;margin-right:auto;line-height:1.8;text-align:center">Abierto a oportunidades, colaboraciones y proyectos interesantes.</p>'
        f'<div style="text-align:center">{email_btn}{social_row}</div>'
        f'{contact_form}'
        f'</div></div></div></section>'
    )


def _dark_light_toggle(plantilla, color, s):
    """Floating dark/light toggle button with CSS alt-theme override."""
    c = _valid_color(color)
    is_dark = plantilla in ("oscuro", "glass", "terminal", "luxury", "neon", "gradient")
    # Alt theme: swap bg ↔ near-white for dark, or near-black for light
    if is_dark:
        alt_bg   = "#f5f5f0"
        alt_text = "#1a1a1a"
        alt_card = "#ffffff"
        alt_muted= "#555555"
        alt_nav  = "rgba(245,245,240,.92)"
        alt_sep  = "#e5e5e5"
        moon, sun = "☀️", "🌙"
        init_icon = sun  # starts dark → show sun to switch to light
    else:
        alt_bg   = "#0e0e18"
        alt_text = "#ededf5"
        alt_card = "rgba(255,255,255,.05)"
        alt_muted= "#a0a0b8"
        alt_nav  = "rgba(14,14,24,.88)"
        alt_sep  = "rgba(255,255,255,.08)"
        moon, sun = "🌙", "☀️"
        init_icon = moon  # starts light → show moon to switch to dark

    alt_css = (
        f"body.alt-theme{{background:{alt_bg}!important;color:{alt_text}!important}}"
        f"body.alt-theme nav{{background:{alt_nav}!important}}"
        f"body.alt-theme [style*='background:{s['card']}']{{background:{alt_card}!important}}"
        f"body.alt-theme [style*=\"background:{s['bg']}\"]{{background:{alt_bg}!important}}"
        f"body.alt-theme p,body.alt-theme span,body.alt-theme li{{color:{alt_muted}}}"
        f"body.alt-theme h1,body.alt-theme h2,body.alt-theme h3,body.alt-theme h4{{color:{alt_text}!important}}"
    )
    btn_style = (
        f"position:fixed;bottom:24px;right:24px;z-index:999;width:44px;height:44px;"
        f"border-radius:50%;background:{s['card']};border:1px solid {s['border']};"
        f"cursor:pointer;font-size:1.1rem;display:flex;align-items:center;justify-content:center;"
        f"box-shadow:0 4px 16px rgba(0,0,0,.25);transition:transform .2s"
    )
    js = (
        f'<script>'
        f'(function(){{'
        f'var btn=document.getElementById("theme-toggle");'
        f'var isDark={"true" if is_dark else "false"};'
        f'var sun="{sun}",moon="{moon}";'
        f'var stored=localStorage.getItem("pf-theme");'
        f'if(stored==="alt"){{document.body.classList.add("alt-theme");btn.textContent=isDark?moon:sun;}}'
        f'btn.addEventListener("click",function(){{'
        f'var isAlt=document.body.classList.toggle("alt-theme");'
        f'btn.textContent=isAlt?(isDark?moon:sun):(isDark?sun:moon);'
        f'localStorage.setItem("pf-theme",isAlt?"alt":"default");'
        f'}});'
        f'}})();'
        f'</script>'
    )
    return (
        f'<style>{alt_css}</style>'
        f'<button id="theme-toggle" aria-label="Cambiar tema" style="{btn_style}">{init_icon}</button>'
        + js
    )


def tool_generar_footer(nombre, plantilla, color):
    s = STYLES.get(plantilla, STYLES["oscuro"])
    c = _valid_color(color)
    anio = datetime.now().year
    return (
        f'<footer style="padding:36px 0;border-top:1px solid {s["sep"]}">'
        f'<div class="w" style="display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:12px">'
        f'<p style="color:{s["footer_c"]};font-size:.78rem;margin:0">'
        f'<span style="color:{s["text"]};font-weight:600">{_esc(nombre)}</span>'
        f' &middot; {anio}</p>'
        f'<p style="color:{s["footer_c"]};font-size:.72rem;margin:0">'
        f'Hecho con <a href="https://portify.es" style="color:{c};font-weight:600;text-decoration:none">Portify</a></p>'
        f'</div></footer>'
    )


def tool_ensamblar_y_guardar(secciones, datos, usuario_id, domain_base=DOMAIN_BASE):
    """Ensambla el HTML final, guarda en DB y asigna subdominio."""
    plantilla = datos.get("plantilla", "oscuro")
    color     = _valid_color(datos.get("color", "#F18A8E"))
    animacion = datos.get("animacion", "fade")
    nombre    = datos.get("nombre", "Usuario")

    s = STYLES.get(plantilla, STYLES["oscuro"])
    special_css = s.get("special_css", "")
    anim_css = ANIM_CSS + ANIM_MAP.get(animacion, ANIM_MAP["fade"]) + ANIM_DELAYS
    css_base = (
        f"*{{box-sizing:border-box;margin:0;padding:0}}html{{scroll-behavior:smooth}}"
        f"body{{font-family:{s['font_b']};background:{s['bg']};color:{s['text']};line-height:1.65;min-height:100vh}}"
        f"a{{text-decoration:none;color:inherit}}"
        f"img{{max-width:100%;display:block}}"
        f".w{{width:min(1100px,calc(100% - 48px));margin:0 auto}}"
        f".n{{width:min(780px,calc(100% - 48px));margin:0 auto}}"
        # Responsive hero grid
        f"@media(max-width:860px){{"
        f".w,.n{{width:calc(100% - 28px)}}"
        f"section .w[style*='grid-template-columns:1fr 300px'],"
        f"section .w[style*='grid-template-columns:1fr 320px']{{grid-template-columns:1fr!important}}"
        f"article[style*='grid-template-columns:1fr 1fr']{{grid-template-columns:1fr!important}}"
        f"h1{{font-size:clamp(2.4rem,8vw,3.5rem)!important}}"
        f"}}"
        # Hover effects via :hover pseudo (inline styles can't do this, so we use a class)
        f".proj-card:hover{{transform:translateY(-4px);box-shadow:0 12px 40px rgba(0,0,0,.2)}}"
        f".social-btn:hover{{transform:translateY(-2px);border-color:{s['text']}40!important}}"
        f".cta-btn:hover{{opacity:.88;transform:translateY(-1px)}}"
    )

    slug = uuid.uuid4().hex[:10]
    titulo = f"Portfolio de {nombre}"
    base_slug = re.sub(r'[^a-z0-9]', '', nombre.lower().strip())[:20] or f"user{usuario_id}"
    foto = datos.get("foto_perfil", "") or datos.get("foto", "")

    with sqlite3.connect(DB_PATH) as db:
        db.row_factory = sqlite3.Row
        # Generar usuario_slug único ANTES de construir el HTML
        usuario_slug = base_slug
        for n in range(2, 100):
            taken = db.execute("SELECT 1 FROM portfolios WHERE usuario_slug=?", (usuario_slug,)).fetchone()
            if not taken:
                break
            usuario_slug = f"{base_slug}{n}"

        # Construir HTML con canonical URL real
        canonical_url = f"https://{usuario_slug}.{domain_base}"
        og      = _og_tags(nombre, datos.get("rol",""), datos.get("descripcion",""), foto, canonical_url, color)
        favicon = _favicon(nombre, color)

        # Insert first to get the pid, then build HTML with correct pid for contact form
        cur = db.execute(
            "INSERT INTO portfolios (usuario_id,titulo,datos,html_generado,slug,usuario_slug,plantilla,animacion) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (usuario_id, titulo, json.dumps(datos), "", slug, usuario_slug, plantilla, animacion)
        )
        pid = cur.lastrowid

        contacto_sec = secciones.get("contacto", "")
        # Rebuild contact section with actual pid for the embedded form
        if not contacto_sec:
            contacto_sec = tool_generar_contacto(
                datos.get("email",""), datos.get("redes",{}), color, plantilla, portfolio_id=pid
            )
        else:
            # Re-generate with portfolio_id now that we have it
            contacto_sec = tool_generar_contacto(
                datos.get("email",""), datos.get("redes",{}), color, plantilla, portfolio_id=pid
            )

        toggle = _dark_light_toggle(plantilla, color, s)

        html = (
            f'<!DOCTYPE html><html lang="es"><head>'
            f'<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<title>{_esc(nombre)} &middot; Portfolio</title>'
            f'{og}{favicon}'
            f'<link rel="preconnect" href="https://fonts.googleapis.com">'
            f'<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
            f'<link href="{s["font_url"]}" rel="stylesheet">'
            f'<style>{anim_css}{css_base}{special_css}</style></head><body>'
            + secciones.get("nav", "")
            + secciones.get("hero", "")
            + secciones.get("skills", "")
            + secciones.get("proyectos", "")
            + secciones.get("experiencia", "")
            + contacto_sec
            + secciones.get("footer", "")
            + toggle
            + ANIM_JS
            + '</body></html>'
        )
        db.execute("UPDATE portfolios SET html_generado=? WHERE id=?", (html, pid))

    subdominio_url = f"https://{usuario_slug}.{domain_base}"
    logger.info(f"[Agent] Portfolio guardado: id={pid}, slug={slug}, subdominio={subdominio_url}")
    return {"ok": True, "portfolio_id": pid, "slug": slug, "usuario_slug": usuario_slug, "subdominio_url": subdominio_url}


# ─────────────────────────────────────────────────────────────────────────────
# DEFINICIÓN DE HERRAMIENTAS PARA OLLAMA
# ─────────────────────────────────────────────────────────────────────────────
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "generar_nav",
            "description": "Genera la barra de navegación del portfolio",
            "parameters": {
                "type": "object",
                "properties": {
                    "nombre":    {"type": "string"},
                    "plantilla": {"type": "string"},
                    "color":     {"type": "string"},
                },
                "required": ["nombre", "plantilla", "color"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "generar_hero",
            "description": "Genera la sección principal/hero del portfolio",
            "parameters": {
                "type": "object",
                "properties": {
                    "nombre":       {"type": "string"},
                    "rol":          {"type": "string"},
                    "descripcion":  {"type": "string"},
                    "color":        {"type": "string"},
                    "plantilla":    {"type": "string"},
                    "foto":         {"type": "string"},
                    "n_proyectos":  {"type": "integer"},
                    "n_skills":     {"type": "integer"},
                },
                "required": ["nombre", "rol", "descripcion", "color", "plantilla"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "generar_skills",
            "description": "Genera la sección de habilidades. Omitir si la lista está vacía.",
            "parameters": {
                "type": "object",
                "properties": {
                    "skills":    {"type": "array", "items": {"type": "string"}},
                    "color":     {"type": "string"},
                    "plantilla": {"type": "string"},
                },
                "required": ["skills", "color", "plantilla"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "generar_proyectos",
            "description": "Genera la sección de proyectos. Omitir si la lista está vacía.",
            "parameters": {
                "type": "object",
                "properties": {
                    "proyectos": {"type": "array"},
                    "color":     {"type": "string"},
                    "plantilla": {"type": "string"},
                },
                "required": ["proyectos", "color", "plantilla"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "generar_experiencia",
            "description": "Genera la sección de experiencia. Omitir si la lista está vacía.",
            "parameters": {
                "type": "object",
                "properties": {
                    "experiencia": {"type": "array"},
                    "color":       {"type": "string"},
                    "plantilla":   {"type": "string"},
                },
                "required": ["experiencia", "color", "plantilla"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "generar_contacto",
            "description": "Genera la sección de contacto",
            "parameters": {
                "type": "object",
                "properties": {
                    "email":     {"type": "string"},
                    "redes":     {"type": "object"},
                    "color":     {"type": "string"},
                    "plantilla": {"type": "string"},
                },
                "required": ["email", "color", "plantilla"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "generar_footer",
            "description": "Genera el footer del portfolio",
            "parameters": {
                "type": "object",
                "properties": {
                    "nombre":    {"type": "string"},
                    "plantilla": {"type": "string"},
                    "color":     {"type": "string"},
                },
                "required": ["nombre", "plantilla", "color"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "ensamblar_y_guardar",
            "description": "Ensambla todas las secciones generadas en el HTML final, lo guarda en la base de datos y asigna el subdominio. Llamar SOLO cuando todas las secciones necesarias estén listas.",
            "parameters": {
                "type": "object",
                "properties": {
                    "secciones_listas": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Lista de secciones ya generadas: ['nav','hero','skills',...]",
                    },
                },
                "required": ["secciones_listas"],
            },
        },
    },
]

AGENT_SYSTEM_PROMPT = """Eres un agente de construcción de portfolios. Tu trabajo es generar cada sección del portfolio usando las herramientas disponibles y luego ensamblarlo.

PROCESO OBLIGATORIO (en este orden):
1. generar_nav
2. generar_hero
3. generar_skills (solo si hay skills)
4. generar_proyectos (solo si hay proyectos)
5. generar_experiencia (solo si hay experiencia)
6. generar_contacto
7. generar_footer
8. ensamblar_y_guardar

Usa los datos exactos que te proporcionan. No omitas pasos. No inventes datos.
Responde SOLO con llamadas a herramientas, sin texto."""


# ─────────────────────────────────────────────────────────────────────────────
# AGENTE
# ─────────────────────────────────────────────────────────────────────────────

class PortfolioAgent:
    """Agente llama3.2 que construye portfolios sección a sección con tool calling."""

    def __init__(self, domain_base=DOMAIN_BASE):
        self.domain_base = domain_base
        self._secciones: dict = {}
        self._datos: dict = {}
        self._usuario_id: int = 0

    def run(self, datos: dict, usuario_id: int) -> dict:
        """
        Punto de entrada. Recibe los datos del portfolio y el usuario_id.
        Devuelve {ok, portfolio_id, slug, usuario_slug, subdominio_url} o {ok:False, error}.
        """
        self._secciones = {}
        self._datos = datos
        self._usuario_id = usuario_id

        # Secciones requeridas según los datos disponibles
        required = ["nav", "hero"]
        if datos.get("habilidades"): required.append("skills")
        if datos.get("proyectos"):   required.append("proyectos")
        if datos.get("experiencia"): required.append("experiencia")
        required += ["contacto", "footer"]

        messages = [
            {"role": "system", "content": AGENT_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    f"Construye el portfolio con estos datos:\n"
                    f"{json.dumps(datos, ensure_ascii=False)}\n\n"
                    f"Secciones a generar en orden: {', '.join(required)}, luego ensamblar_y_guardar."
                ),
            },
        ]

        for iteration in range(12):
            resp = self._call_ollama(messages)
            if not resp:
                break

            msg = resp.get("message", {})
            tool_calls = msg.get("tool_calls") or []

            if not tool_calls:
                # El modelo paró — comprobar si faltan secciones y reintentar una vez
                missing = [s for s in required if s not in self._secciones]
                if missing:
                    logger.info(f"[Agent] Sin tool_calls. Secciones pendientes: {missing}. Reintentando.")
                    messages.append({
                        "role": "user",
                        "content": f"Aún faltan estas secciones: {missing}. Llámales ahora y después ensamblar_y_guardar."
                    })
                    continue
                # Todas las secciones están, ensamblar directamente
                break

            messages.append({"role": "assistant", "content": "", "tool_calls": tool_calls})

            for tc in tool_calls:
                fn   = tc.get("function", {})
                name = fn.get("name", "")
                args = fn.get("arguments") or {}
                if isinstance(args, str):
                    try:
                        args = json.loads(args)
                    except Exception:
                        args = {}

                logger.info(f"[Agent] tool={name} keys={list(args.keys())}")
                result = self._dispatch(name, args)

                messages.append({
                    "role": "tool",
                    "content": json.dumps(result, ensure_ascii=False),
                })

                if name == "ensamblar_y_guardar" and isinstance(result, dict) and result.get("ok"):
                    return result

        # Fallback: generar secciones que falten directamente y ensamblar
        logger.info("[Agent] Fallback — generando secciones faltantes directamente")
        self._fallback_generate(required)
        return tool_ensamblar_y_guardar(self._secciones, self._datos, self._usuario_id, self.domain_base)

    def _fallback_generate(self, required: list):
        """Genera directamente las secciones que el LLM no llegó a producir."""
        d  = self._datos
        c  = _valid_color(d.get("color", "#F18A8E"))
        pl = d.get("plantilla", "oscuro")

        if "nav"        not in self._secciones: self._secciones["nav"]        = tool_generar_nav(d.get("nombre",""), pl, c)
        if "hero"       not in self._secciones: self._secciones["hero"]       = tool_generar_hero(d.get("nombre",""), d.get("rol",""), d.get("descripcion",""), c, pl, d.get("foto_perfil","") or d.get("foto",""), len(d.get("proyectos",[])), len(d.get("habilidades",[])))
        if "skills"     in required and "skills"     not in self._secciones: self._secciones["skills"]     = tool_generar_skills(d.get("habilidades",[]), c, pl)
        if "proyectos"  in required and "proyectos"  not in self._secciones: self._secciones["proyectos"]  = tool_generar_proyectos(d.get("proyectos",[]), c, pl)
        if "experiencia" in required and "experiencia" not in self._secciones: self._secciones["experiencia"] = tool_generar_experiencia(d.get("experiencia",[]), c, pl)
        if "contacto"   not in self._secciones: self._secciones["contacto"]   = tool_generar_contacto(d.get("email",""), d.get("redes",{}), c, pl)
        if "footer"     not in self._secciones: self._secciones["footer"]     = tool_generar_footer(d.get("nombre",""), pl, c)

    # ── Ollama call ───────────────────────────────────────────────────────────

    def _call_ollama(self, messages: list) -> dict | None:
        try:
            r = requests.post(
                OLLAMA_URL,
                json={"model": OLLAMA_MODEL, "messages": messages, "tools": TOOLS, "stream": False},
                timeout=120,
            )
            r.raise_for_status()
            return r.json()
        except Exception as e:
            logger.error(f"[Agent] Ollama error: {e}")
            return None

    # ── Tool dispatcher ───────────────────────────────────────────────────────

    def _dispatch(self, name: str, args: dict):
        d  = self._datos
        c  = _valid_color(d.get("color", "#F18A8E"))
        pl = d.get("plantilla", "oscuro")

        # Helpers para extraer con fallback a datos del portfolio
        def _g(key, fallback=None):
            return args.get(key) or d.get(key) or (fallback if fallback is not None else "")

        def _normalize_proyectos(lst):
            """Asegura que cada elemento sea un dict con las claves esperadas."""
            result = []
            for item in (lst or []):
                if isinstance(item, dict):
                    result.append(item)
                elif isinstance(item, str) and item.strip():
                    result.append({"titulo": item, "descripcion": "", "tecnologias": "", "url": "", "imagen": ""})
            return result

        if name == "generar_nav":
            html = tool_generar_nav(_g("nombre"), _g("plantilla") or pl, _g("color") or c)
            self._secciones["nav"] = html
            return {"ok": True, "seccion": "nav", "chars": len(html)}

        elif name == "generar_hero":
            html = tool_generar_hero(
                nombre=_g("nombre"),
                rol=_g("rol"),
                descripcion=_g("descripcion"),
                color=_g("color") or c,
                plantilla=_g("plantilla") or pl,
                foto=args.get("foto") or d.get("foto_perfil") or d.get("foto") or "",
                n_proyectos=args.get("n_proyectos", len(d.get("proyectos", []))),
                n_skills=args.get("n_skills", len(d.get("habilidades", []))),
            )
            self._secciones["hero"] = html
            return {"ok": True, "seccion": "hero", "chars": len(html)}

        elif name == "generar_skills":
            # El modelo puede usar 'skills' o 'habilidades'
            skills = args.get("skills") or args.get("habilidades") or d.get("habilidades", [])
            if isinstance(skills, str):
                skills = [s.strip() for s in skills.split(",") if s.strip()]
            html = tool_generar_skills(skills, _g("color") or c, _g("plantilla") or pl)
            self._secciones["skills"] = html
            return {"ok": True, "seccion": "skills", "chars": len(html)}

        elif name == "generar_proyectos":
            proyectos = _normalize_proyectos(args.get("proyectos") or d.get("proyectos", []))
            html = tool_generar_proyectos(proyectos, _g("color") or c, _g("plantilla") or pl)
            self._secciones["proyectos"] = html
            return {"ok": True, "seccion": "proyectos", "chars": len(html)}

        elif name == "generar_experiencia":
            exp = args.get("experiencia") or d.get("experiencia", [])
            html = tool_generar_experiencia(exp, _g("color") or c, _g("plantilla") or pl)
            self._secciones["experiencia"] = html
            return {"ok": True, "seccion": "experiencia", "chars": len(html)}

        elif name == "generar_contacto":
            redes = args.get("redes") or d.get("redes") or {}
            if not isinstance(redes, dict):
                redes = {}
            html = tool_generar_contacto(_g("email"), redes, _g("color") or c, _g("plantilla") or pl)
            self._secciones["contacto"] = html
            return {"ok": True, "seccion": "contacto", "chars": len(html)}

        elif name == "generar_footer":
            html = tool_generar_footer(_g("nombre"), _g("plantilla") or pl, _g("color") or c)
            self._secciones["footer"] = html
            return {"ok": True, "seccion": "footer", "chars": len(html)}

        elif name == "ensamblar_y_guardar":
            return tool_ensamblar_y_guardar(
                self._secciones,
                self._datos,
                self._usuario_id,
                self.domain_base,
            )

        else:
            return {"ok": False, "error": f"Tool desconocida: {name}"}


# ─────────────────────────────────────────────────────────────────────────────
# GENERADOR UNIVERSAL (usado por app.py para preview y edición)
# ─────────────────────────────────────────────────────────────────────────────

def _favicon(nombre, color):
    """Genera un favicon SVG con las iniciales del usuario sobre fondo de su color."""
    ini = _ini(nombre)[:2]
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32">'
        f'<rect width="32" height="32" rx="8" fill="{color}"/>'
        f'<text x="16" y="22" text-anchor="middle" font-family="system-ui,sans-serif" '
        f'font-size="15" font-weight="700" fill="white">{ini}</text>'
        f'</svg>'
    )
    import base64 as _b64
    b64 = _b64.b64encode(svg.encode()).decode()
    return f'<link rel="icon" type="image/svg+xml" href="data:image/svg+xml;base64,{b64}">'


def _og_tags(nombre, rol, descripcion, foto, canonical_url, color):
    """Genera meta tags Open Graph y Twitter Card."""
    title   = _esc(f"{nombre} — Portfolio")
    desc_raw = f"{rol}. {descripcion}"[:160] if rol else descripcion[:160]
    desc    = _esc(desc_raw)
    url     = _esc(canonical_url) if canonical_url else ""
    tags = (
        f'<meta property="og:type" content="profile">'
        f'<meta property="og:title" content="{title}">'
        f'<meta property="og:description" content="{desc}">'
        f'<meta name="description" content="{desc}">'
        f'<meta name="theme-color" content="{color}">'
        f'<meta name="twitter:card" content="summary">'
        f'<meta name="twitter:title" content="{title}">'
        f'<meta name="twitter:description" content="{desc}">'
    )
    if url:
        tags += f'<meta property="og:url" content="{url}"><link rel="canonical" href="{url}">'
    # Solo añadir og:image si la foto es una URL de disco (no base64)
    if foto and foto.startswith("/static/"):
        img_url = _esc(f"{canonical_url.rstrip('/') if canonical_url else ''}{foto}")
        tags += (
            f'<meta property="og:image" content="{img_url}">'
            f'<meta name="twitter:image" content="{img_url}">'
        )
    return tags


def _generar_cv(datos: dict, canonical_url: str = "", portfolio_id: int = None) -> str:
    """Genera un CV de una página optimizado para impresión."""
    color  = _valid_color(datos.get("color", "#1a1a2e"))
    nombre = datos.get("nombre", "Portfolio")
    rol    = datos.get("rol", "")
    desc   = datos.get("descripcion", "")
    email  = datos.get("email", "")
    redes  = datos.get("redes", {}) or {}
    skills = datos.get("habilidades", []) or []
    projs  = datos.get("proyectos", []) or []
    exps   = datos.get("experiencia", []) or []
    foto   = datos.get("foto_perfil", "") or datos.get("foto", "")
    s      = STYLES["cv"]
    og     = _og_tags(nombre, rol, desc, foto, canonical_url, color)
    favicon= _favicon(nombre, color)
    anio   = datetime.now().year

    # Contact line
    contacts = []
    if email: contacts.append(f'<a href="mailto:{_esc(email)}" style="color:{color}">{_esc(email)}</a>')
    for key in ["website","linkedin","github","twitter"]:
        url = redes.get(key,"")
        if url and url not in ["","#","ninguna","none"]:
            if not url.startswith("http"): url = "https://" + url
            label = url.replace("https://","").replace("http://","").rstrip("/")
            contacts.append(f'<a href="{_esc(url)}" target="_blank" style="color:{color}">{label}</a>')
    contact_line = " · ".join(contacts)

    # Skills chips
    tag_html = "".join(
        f'<span style="display:inline-block;padding:3px 10px;border-radius:4px;border:1px solid {s["border"]};'
        f'background:{s["tag_bg"]};font-size:.78rem;font-weight:500;color:{s["muted"]}">{_esc(sk)}</span>'
        for sk in skills
    )

    # Projects
    proj_html = ""
    for p in projs[:4]:
        t   = _esc(p.get("titulo",""))
        d   = _esc(p.get("descripcion",""))
        tec = _esc(p.get("tecnologias",""))
        url = (p.get("url","") or "").strip()
        url_a = f' <a href="{_esc(url if url.startswith("http") else "https://"+url)}" target="_blank" style="color:{color};font-size:.75rem">↗</a>' if url else ""
        proj_html += (
            f'<div style="margin-bottom:10px">'
            f'<p style="font-weight:600;font-size:.88rem;margin-bottom:2px">{t}{url_a}</p>'
            f'<p style="color:{s["muted"]};font-size:.82rem;line-height:1.6;margin-bottom:3px">{d}</p>'
            f'<span style="font-size:.75rem;color:{color};font-weight:500">{tec}</span>'
            f'</div>'
        )

    # Experience
    exp_html = ""
    for e in exps:
        t = _esc(e.get("titulo","")) if isinstance(e,dict) else ""
        d = _esc(e.get("descripcion","")) if isinstance(e,dict) else _esc(e)
        exp_html += (
            f'<div style="margin-bottom:10px;padding-left:12px;border-left:2px solid {color}44">'
            + (f'<p style="font-weight:600;font-size:.88rem;margin-bottom:2px">{t}</p>' if t else "")
            + f'<p style="color:{s["muted"]};font-size:.82rem;line-height:1.6">{d}</p>'
            f'</div>'
        )

    avatar = _avatar_html(foto, nombre, color, 72, "8px")
    sec_title = (f'<h2 style="font-size:.7rem;font-weight:700;text-transform:uppercase;letter-spacing:.1em;'
                 f'color:{color};margin-bottom:10px;padding-bottom:6px;border-bottom:1px solid {s["sep"]}">{{t}}</h2>')

    body = (
        # Header
        f'<header class="cv-hero" style="padding:32px 0 20px;border-bottom:2px solid {color}">'
        f'<div style="display:flex;align-items:center;gap:20px">'
        f'{avatar}'
        f'<div style="flex:1">'
        f'<h1 style="font-size:1.6rem;font-weight:700;letter-spacing:-.03em;margin-bottom:4px">{_esc(nombre)}</h1>'
        f'<p style="font-size:.95rem;font-weight:500;color:{color};margin-bottom:6px">{_esc(rol)}</p>'
        f'<p style="font-size:.78rem;color:{s["muted"]};line-height:1.5">{contact_line}</p>'
        f'</div></div>'
        f'</header>'
        # Two-column layout
        f'<div style="display:grid;grid-template-columns:1fr 2fr;gap:28px;padding:24px 0">'
        # LEFT column
        f'<div>'
        + (sec_title.format(t="Sobre mí") + f'<p style="font-size:.83rem;color:{s["muted"]};line-height:1.7;margin-bottom:20px">{_esc(desc)}</p>' if desc else "")
        + (sec_title.format(t="Habilidades") + f'<div style="display:flex;flex-wrap:wrap;gap:5px">{tag_html}</div>' if tag_html else "")
        + f'</div>'
        # RIGHT column
        f'<div>'
        + (sec_title.format(t="Proyectos") + proj_html if proj_html else "")
        + (sec_title.format(t="Experiencia") + exp_html if exp_html else "")
        + f'</div>'
        f'</div>'
        f'<p style="text-align:center;font-size:.7rem;color:{s["dim"]};padding-top:12px;border-top:1px solid {s["sep"]}">'
        f'{_esc(nombre)} · {anio} · Creado con <a href="https://portify.es" style="color:{color}">Portify</a></p>'
    )

    print_btn = f'<button class="cv-print-btn" onclick="window.print()">🖨 Descargar PDF</button>'
    special_css = s.get("special_css","")

    return (
        f'<!DOCTYPE html><html lang="es"><head>'
        f'<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
        f'<title>{_esc(nombre)} · CV</title>'
        f'{og}{favicon}'
        f'<link rel="preconnect" href="https://fonts.googleapis.com">'
        f'<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
        f'<link href="{s["font_url"]}" rel="stylesheet">'
        f'<style>'
        f'*{{box-sizing:border-box;margin:0;padding:0}}'
        f'body{{font-family:{s["font_b"]};background:#fff;color:{s["text"]};line-height:1.5}}'
        f'a{{text-decoration:none;color:inherit}}'
        f'.w{{width:min(800px,calc(100% - 40px));margin:0 auto}}'
        f'{special_css}'
        f'</style></head><body>'
        f'<div class="w">{body}</div>'
        f'{print_btn}'
        f'</body></html>'
    )


def generar_html_universal(datos: dict, canonical_url: str = "", portfolio_id: int = None) -> str:
    """Genera el HTML completo de un portfolio usando los section generators.
    Compatible con las 16 plantillas. Usado por generar_html() en app.py."""
    plantilla = datos.get("plantilla", "oscuro")
    if plantilla not in STYLES:
        plantilla = "oscuro"
    if plantilla == "cv":
        return _generar_cv(datos, canonical_url, portfolio_id)
    color = _valid_color(datos.get("color", "#F18A8E"))
    animacion = datos.get("animacion", "fade")
    nombre = datos.get("nombre", "Portfolio")
    rol = datos.get("rol", "")
    descripcion = datos.get("descripcion", "")
    foto = datos.get("foto_perfil", "") or datos.get("foto", "")
    s = STYLES[plantilla]

    og      = _og_tags(nombre, rol, descripcion, foto, canonical_url, color)
    favicon = _favicon(nombre, color)
    anim_css = ANIM_CSS + ANIM_MAP.get(animacion, ANIM_MAP["fade"]) + ANIM_DELAYS
    special_css = s.get("special_css", "")
    css_base = (
        f"*{{box-sizing:border-box;margin:0;padding:0}}html{{scroll-behavior:smooth}}"
        f"body{{font-family:{s['font_b']};background:{s['bg']};color:{s['text']};line-height:1.65;min-height:100vh}}"
        f"a{{text-decoration:none;color:inherit}}"
        f"img{{max-width:100%;display:block}}"
        f".w{{width:min(1100px,calc(100% - 48px));margin:0 auto}}"
        f".n{{width:min(780px,calc(100% - 48px));margin:0 auto}}"
        f"@media(max-width:860px){{"
        f".w,.n{{width:calc(100% - 28px)}}"
        f"section .w[style*='grid-template-columns:1fr 300px'],"
        f"section .w[style*='grid-template-columns:1fr 320px']{{grid-template-columns:1fr!important}}"
        f"article[style*='grid-template-columns:1fr 1fr']{{grid-template-columns:1fr!important}}"
        f"h1{{font-size:clamp(2.4rem,8vw,3.5rem)!important}}"
        f"}}"
        f".proj-card:hover{{transform:translateY(-4px);box-shadow:0 12px 40px rgba(0,0,0,.2)}}"
        f".social-btn:hover{{transform:translateY(-2px)}}"
        f".cta-btn:hover{{opacity:.88;transform:translateY(-1px)}}"
    )

    nav        = tool_generar_nav(nombre, plantilla, color)
    hero       = tool_generar_hero(nombre, rol, descripcion, color, plantilla,
                                   foto=foto,
                                   n_proyectos=len(datos.get("proyectos", [])),
                                   n_skills=len(datos.get("habilidades", [])))
    skills_sec = tool_generar_skills(datos.get("habilidades", []), color, plantilla) if datos.get("habilidades") else ""
    proj_sec   = tool_generar_proyectos(datos.get("proyectos", []), color, plantilla) if datos.get("proyectos") else ""
    exp_sec    = tool_generar_experiencia(datos.get("experiencia", []), color, plantilla) if datos.get("experiencia") else ""
    contact    = tool_generar_contacto(datos.get("email", ""), datos.get("redes", {}), color, plantilla, portfolio_id=portfolio_id)
    footer     = tool_generar_footer(nombre, plantilla, color)
    toggle     = _dark_light_toggle(plantilla, color, s) if portfolio_id else ""

    return (
        f'<!DOCTYPE html><html lang="es"><head>'
        f'<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
        f'<title>{_esc(nombre)} &middot; Portfolio</title>'
        f'{og}{favicon}'
        f'<link rel="preconnect" href="https://fonts.googleapis.com">'
        f'<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
        f'<link href="{s["font_url"]}" rel="stylesheet">'
        f'<style>{anim_css}{css_base}{special_css}</style></head><body>'
        f'{nav}{hero}{skills_sec}{proj_sec}{exp_sec}{contact}{footer}'
        f'{toggle}{ANIM_JS}</body></html>'
    )

# Lista pública de todas las plantillas disponibles
PLANTILLAS_DISPONIBLES = {k: {"label": v.get("label", k.capitalize()), "emoji": v.get("emoji", "🎨")} for k, v in STYLES.items()}

# ─────────────────────────────────────────────────────────────────────────────
# EJECUCIÓN STANDALONE (test)
# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    test_datos = {
        "nombre": "Thais López",
        "rol": "Diseñadora UX",
        "descripcion": "Apasionada del diseño centrado en el usuario con 3 años de experiencia.",
        "habilidades": ["Figma", "UX Research", "Prototyping", "HTML/CSS"],
        "proyectos": [
            {"titulo": "App bancaria", "descripcion": "Rediseño completo de app móvil", "tecnologias": "Figma, Maze", "url": "", "imagen": ""},
        ],
        "experiencia": [{"titulo": "UX Designer en Accenture", "descripcion": "2021–2024. Proyectos de banca y retail."}],
        "email": "thais@ejemplo.com",
        "redes": {"linkedin": "linkedin.com/in/thais", "github": "", "twitter": "", "instagram": "", "youtube": "", "tiktok": "", "website": ""},
        "plantilla": "minimalista",
        "color": "#3E627F",
        "animacion": "fade",
    }
    agent = PortfolioAgent()
    result = agent.run(test_datos, usuario_id=1)
    print(json.dumps(result, indent=2, ensure_ascii=False))
