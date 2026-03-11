# PDF Redaction Tool (V2)

A production-grade, heavily optimized desktop application for securely redacting sensitive information from Digital and Scanned PDFs. 
Refactored and hardened for deep metadata scrubbing, multi-line phrase reconstruction, multithreaded OCR scanning, and complete standalone offline deployment.

## 1. Architecture Directory Structure

```text
/PDFRedact
├── requirements.txt
├── README.md
├── main.py
├── PDFRedactor.spec
├── logo.png
├── tesseract_bin/         # Portable Tesseract-OCR + tessdata (eng, ron, rus)
├── tests/                 # Secure PyTest evaluation suite
└── pdf_redactor/
    ├── core/              # Business Logic
    │   ├── pdf_parser.py
    │   ├── ocr_engine.py
    │   ├── redaction_engine.py
    │   └── redaction_styles.py
    ├── ui/                # PySide6 User Interface
    │   ├── gui.py
    │   └── cli.py
    ├── config/            # Persistent AppData settings manager
    │   └── settings_manager.py
    └── utils/
        └── file_manager.py
```

## 2. Dependency List

The application has been restructured to rely on highly optimized image pipelines and concurrent process pools.

**Python Libraries** (`requirements.txt`):
*   `PyMuPDF` (fitz): Core PDF parsing, quad-phrase matching, and true image/text redaction wiping.
*   `pytesseract`: Wrapper for Tesseract-OCR.
*   `Pillow`: High-level image processing.
*   `rich`: For visually appealing CLI executions.
*   `PySide6`: Modern, responsive tabbed desktop UI.
*   `opencv-python` (cv2): Used for grayscaling, denoising, and thresholding scanned pages before OCR.
*   `numpy`: Array handling bridging OpenCV and Tesseract.
*   `pytest`: Mock layout verification unit tests.

## 3. Instructions to Run

1. Navigate to the project root directory.
2. Activate your virtual environment and install the verified dependencies:
    ```bash
    pip install -r requirements.txt
    ```
3. Run the application GUI. Tesseract OCR executables, Romanian, and Russian models are natively bundled.
    ```bash
    python main.py
    ```

## 4. Instructions to Build Standalone Executable

We utilize `PyInstaller` combined with a custom spec tree to automatically bake your custom `logo.png` and the offline standalone Tesseract binaries directly into the application space, requiring zero setup by the end-user.

1. Install PyInstaller into the virtual environment:
    ```bash
    pip install pyinstaller
    ```
2. Run the build command targeting the pre-configured Spec file:
    ```bash
    pyinstaller PDFRedactor.spec --clean
    ```
3. Your portable, completely standalone `PDFRedactor.exe` will be generated inside the newly created `dist/` folder!
