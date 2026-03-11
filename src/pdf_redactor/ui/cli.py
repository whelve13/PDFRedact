import argparse
import sys
from rich.console import Console
from rich.progress import track
from pdf_redactor.utils.file_manager import FileManager
from pdf_redactor.core.pdf_parser import PDFParser
from pdf_redactor.core.ocr_engine import OCREngine
from pdf_redactor.core.redaction_engine import RedactionEngine
from pdf_redactor.core.redaction_styles import RedactionMode

console = Console()

def run_cli():
    parser = argparse.ArgumentParser(description="PDF Redaction Tool (Batch Processing Supported)")
    parser.add_argument("--input", "-i", required=True, help="Path to input PDF file or directory")
    parser.add_argument("--phrase", "-p", required=True, action="append", 
                        help="Phrase(s) to redact. Use multiple times for multiple phrases.")
    parser.add_argument("--mode", "-m", choices=["black_bar", "red_box", "highlight"], 
                        default="black_bar", help="Redaction mode (style)")
    parser.add_argument("--output", "-o", required=True, help="Output directory for redacted PDFs")
    parser.add_argument("--ocr", action="store_true", help="Force OCR mode for all pages (even those with text layer)")
    parser.add_argument("--case-sensitive", action="store_true", help="Enable case-sensitive phrase matching")
    
    # We will skip --preview for the CLI as it's complex to show visuals in terminal natively.
    # A true 'preview' would just generate images, which we can skip or implement minimally.
    parser.add_argument("--preview", action="store_true", help="Just print found coordinates, do not save redacted file")

    args = parser.parse_args()

    # Map string mode back to enum
    mode_map = {
        "black_bar": RedactionMode.BLACK_BAR,
        "red_box": RedactionMode.RED_BOX,
        "highlight": RedactionMode.HIGHLIGHT
    }
    selected_mode = mode_map[args.mode]

    # Find files
    try:
        pdf_files = FileManager.get_pdf_files(args.input)
    except Exception as e:
        console.print(f"[bold red]Error accessing input:[/bold red] {e}")
        sys.exit(1)

    if not pdf_files:
        console.print("[yellow]No PDF files found in given input path.[/yellow]")
        sys.exit(0)

    console.print(f"[bold green]Found {len(pdf_files)} PDF file(s) to process.[/bold green]")

    for pdf_path in pdf_files:
        console.print(f"\n[cyan]Processing:[/cyan] {pdf_path}")
        
        try:
            # 1. Parsing Phase
            pdf_parser = PDFParser(pdf_path)
            
            # Dictionary to collect all matches from standard and OCR parsing
            # keys are page number, values are list of fitz.Rect
            all_matches = {}

            pages_needing_ocr = []
            pages_text_status = pdf_parser.get_all_pages_text_status()
            
            # Decide which engine processes which page
            for page_num, has_text in pages_text_status.items():
                if args.ocr or not has_text:
                    pages_needing_ocr.append(page_num)
                    
            # Process normal text layers
            pages_with_text = [p for p, has_text in pages_text_status.items() if has_text and not args.ocr]
            
            # Standard pyMuPDF search first
            if pages_with_text:
                console.print(f"  - Searching standard text layer on {len(pages_with_text)} page(s)...")
                # Our pdf_parser current implementation queries the whole document, so let's filter it.
                # Actually our pdf_parser does not take target_pages, it searches all. 
                # That's fine, we'll just use what we get.
                text_matches = pdf_parser.find_phrases(args.phrase, args.case_sensitive)
                for page_num, rects in text_matches.items():
                    if page_num in pages_with_text:
                        all_matches.setdefault(page_num, []).extend(rects)

            pdf_parser.close()
            
            # OCR Layer Search
            if pages_needing_ocr:
                console.print(f"  - Running OCR fallback on {len(pages_needing_ocr)} page(s)...")
                try:
                    ocr_engine = OCREngine(pdf_path)
                    ocr_matches = ocr_engine.find_phrases(args.phrase, args.case_sensitive, target_pages=pages_needing_ocr)
                    for page_num, rects in ocr_matches.items():
                        all_matches.setdefault(page_num, []).extend(rects)
                except Exception as eval_err:
                    console.print(f"  [bold red]OCR Failed on {pdf_path}:[/bold red] {eval_err}")
                    # Continue gracefully if possible, but skip OCR matches

            # Summarize matches
            total_matches = sum(len(rects) for rects in all_matches.values())
            console.print(f"  [bold]Total phrases found:[/bold] {total_matches}")

            if total_matches == 0:
                console.print("  [yellow]No phrases matched. Skipping this file.[/yellow]")
                continue
                
            if args.preview:
                for p_num, rects in all_matches.items():
                    console.print(f"    Page {p_num}: {len(rects)} matches")
                continue

            # 2. Redaction Phase
            console.print("  - Applying redactions...")
            engine = RedactionEngine(pdf_path)
            engine.apply_redactions(all_matches, selected_mode)
            
            # Save Output
            out_path = FileManager.prepare_output_path(pdf_path, args.output)
            engine.save(out_path)
            engine.close()
            
            console.print(f"  [bold green]Saved redacted file to:[/bold green] {out_path}")

        except Exception as e:
            console.print(f"  [bold red]Failed to process {pdf_path}:[/bold red] {e}")

    console.print("\n[bold green]Batch processing complete.[/bold green]")
