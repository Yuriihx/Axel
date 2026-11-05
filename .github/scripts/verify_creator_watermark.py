"""Guard the official AXEL creator attribution against accidental removal."""
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[2]
SOURCE_PATH = ROOT / "wsgi.py"
source = SOURCE_PATH.read_text(encoding="utf-8")

match = re.search(r'_CREATOR_WATERMARK\s*=\s*"""(.*?)"""', source, re.DOTALL)
if not match:
    sys.exit("ERROR: _CREATOR_WATERMARK block is missing from wsgi.py")

watermark = match.group(1)
required = {
    "accessible watermark label": 'aria-label="Criador do sistema"',
    "creator name": "Yuri Bibiano dos Santos",
    "LinkedIn profile": 'href="https://www.linkedin.com/in/yuribibiano/"',
    "new-tab behavior": 'target="_blank"',
    "safe external-link relationship": 'rel="noopener noreferrer"',
    "watermark element": 'class="axel-creator-watermark"',
}
missing = [label for label, text in required.items() if text not in watermark]
if missing:
    sys.exit("ERROR: watermark is missing: " + ", ".join(missing))

hook = re.search(
    r'@app\.after_request\s+def hosting_response_headers\(response\):(.*?)(?=\n\n[^ \t]|\Z)',
    source,
    re.DOTALL,
)
if not hook:
    sys.exit("ERROR: the response hook that displays the watermark is missing")

hook_body = hook.group(1)
required_hook = (
    'request.endpoint in {"index", "hosting_login", "hosting_signup"}',
    'html.replace("</body>", _CREATOR_WATERMARK + "</body>", 1)',
)
missing_hook = [text for text in required_hook if text not in hook_body]
if missing_hook:
    sys.exit("ERROR: watermark injection is missing or changed in hosting_response_headers")

print("Creator watermark is present and injected into the AXEL HTML pages.")
