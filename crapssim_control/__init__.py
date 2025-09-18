# crapssim_control/__init__.py
from .spec_validate import (
    validate_spec,
    assert_valid_spec,
    SpecValidationError,
)

# Re-export public API that already existed in your package as needed.
# (Leave your existing imports/exports intact.)