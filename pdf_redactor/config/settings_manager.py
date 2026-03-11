import json
import os
from pdf_redactor.core.redaction_styles import RedactionMode

class SettingsManager:
    """
    Manages user preferences and defaults, saving to a persistent local JSON file 
    in the user directory (AppData).
    """
    DEFAULT_SETTINGS = {
        "ocr_enabled": False,
        "case_sensitive": False,
        "default_mode": RedactionMode.BLACK_BAR.value,
        "output_directory": "",
        "ocr_language": "eng",
        "generate_audit": False
    }
    
    def __init__(self):
        # Configure persistent config path in user directory
        app_data = os.getenv('APPDATA')
        if app_data:
            self.config_dir = os.path.join(app_data, 'PDFRedactor')
        else:
            self.config_dir = os.path.join(os.path.expanduser('~'), '.pdfredactor')
            
        os.makedirs(self.config_dir, exist_ok=True)
        self.config_file = os.path.join(self.config_dir, "config.json")
        self.settings = self.DEFAULT_SETTINGS.copy()
        self.load()

    def load(self):
        """Loads settings from disk if the file exists."""
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, "r") as f:
                    loaded = json.load(f)
                    self.settings.update(loaded)
            except Exception:
                pass

    def save(self):
        """Saves current settings to disk."""
        with open(self.config_file, "w") as f:
            json.dump(self.settings, f, indent=4)

    def get(self, key):
        return self.settings.get(key)
        
    def set(self, key, value):
        self.settings[key] = value
