# Make ExcelExportTool a proper Python package for imports and PyInstaller collection.
# Maintain backward compatibility by re-exporting commonly used modules

# Core modules
from .core import worksheet_data, export_process
# Note: export_all and export_game_client are available as root-level modules
# for command-line usage: python -m ExcelExportTool.export_all
# They should NOT be imported here to avoid circular import issues

# Validation modules
from .validation import worksheet_validator, reference_checker, asset_validator

# Parsing modules
from .parsing import field_parser, excel_processing, data_processing

# Generation modules
from .generation import cs_generation, enum_registry

# Utility modules
from .utils import user_utils, log, path_utils, naming_utils, naming_config, type_utils

# Exceptions (stays at root level)
from . import exceptions

__all__ = [
    # Core
    'worksheet_data', 'export_process',
    # Note: export_all and export_game_client are available as root-level modules
    # for command-line usage: python -m ExcelExportTool.export_all
    # Validation
    'worksheet_validator', 'reference_checker', 'asset_validator',
    # Parsing
    'field_parser', 'excel_processing', 'data_processing',
    # Generation
    'cs_generation', 'enum_registry',
    # Utils
    'user_utils', 'log', 'path_utils', 'naming_utils', 'naming_config', 'type_utils',
    # Exceptions
    'exceptions',
]
