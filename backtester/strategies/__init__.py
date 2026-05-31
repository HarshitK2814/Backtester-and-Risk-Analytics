# strategies package
from strategies.grid import GridStrategy
from strategies.dca  import DCAStrategy
from strategies.pla  import PLAStrategy

STRATEGY_REGISTRY = {
    "GRID": GridStrategy,
    "DCA":  DCAStrategy,
    "PLA":  PLAStrategy,
}

__all__ = ["GridStrategy", "DCAStrategy", "PLAStrategy", "STRATEGY_REGISTRY"]
