from enum import Enum
from typing import Tuple

class RedactionMode(Enum):
    BLACK_BAR = "black_bar"
    RED_BOX = "red_box"
    HIGHLIGHT = "highlight"

class RedactionStyleDef:
    """
    Defines the visual properties of a redaction.
    Colors are typically represented as RGB tuples from 0.0 to 1.0 in PyMuPDF.
    """
    def __init__(self, fill: Tuple[float, float, float] = None, 
                 stroke: Tuple[float, float, float] = None, 
                 width: float = 1.0):
        self.fill = fill
        self.stroke = stroke
        self.width = width

STYLES = {
    RedactionMode.BLACK_BAR: RedactionStyleDef(
        fill=(0, 0, 0),       # Solid black
        stroke=(0, 0, 0),
        width=1.0
    ),
    RedactionMode.RED_BOX: RedactionStyleDef(
        fill=None,            # No fill, just outline
        stroke=(1, 0, 0),     # Solid red
        width=1.5
    ),
    RedactionMode.HIGHLIGHT: RedactionStyleDef(
        fill=(1, 1, 0),       # Solid yellow
        stroke=None,          # No border
        width=0.0
    )
}
