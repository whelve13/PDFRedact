import sys
import os

def get_resource_path(relative_path):
    """
    Get the absolute path to a resource.
    Works dynamically whether running from the Python interpreter
    or bundled via PyInstaller.
    """
    try:
        # PyInstaller strictly creates a temp folder at _MEIPASS and saves the path in sys._MEIPASS
        base_path = sys._MEIPASS
    except AttributeError:
        # When running as standard Python script, look for the project root.
        # This file is in: project_root/src/pdf_redactor/utils/resource_handler.py (4 levels deep)
        base_path = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

    return os.path.join(base_path, relative_path)
