import os
import glob
from typing import List

class FileManager:
    @staticmethod
    def get_pdf_files(input_path: str) -> List[str]:
        """
        Returns a list of PDF file paths given an input directory or raw file path.
        """
        input_path = os.path.abspath(input_path)
        if not os.path.exists(input_path):
            raise FileNotFoundError(f"Input path does not exist: {input_path}")
            
        if os.path.isfile(input_path):
            if input_path.lower().endswith('.pdf'):
                return [input_path]
            else:
                raise ValueError("Provided file is not a PDF")
        
        elif os.path.isdir(input_path):
            # Recursively find pdfs or just top level?
            # Let's do top level for simplicity, but wait, usually batch is top level
            search_pattern = os.path.join(input_path, "*.pdf")
            files = glob.glob(search_pattern)
            return files
            
        return []

    @staticmethod
    def prepare_output_path(input_file: str, output_dir: str) -> str:
        """
        Ensures output directory exists and generates an output file path 
        by appending '_redacted' to the original filename.
        """
        output_dir = os.path.abspath(output_dir)
        os.makedirs(output_dir, exist_ok=True)
        
        base_name = os.path.basename(input_file)
        name, ext = os.path.splitext(base_name)
        new_name = f"{name}_redacted{ext}"
        
        return os.path.join(output_dir, new_name)
