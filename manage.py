#!/usr/bin/env python
"""Django's command-line utility for administrative tasks."""

import os
from pathlib import Path
import sys


def main() -> None:
    """Run administrative tasks."""
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.local")

    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(  # noqa: TRY003
            "Couldn't import Django. Are you sure it's installed and "  # noqa: EM101
            "available on your PYTHONPATH environment variable? Did you "
            "forget to activate a virtual environment?",
        ) from exc

    # This allows easy placement of apps within the interior
    # wfcast directory.
    current_path = Path(__file__).parent.resolve()
    sys.path.append(str(current_path / "wfcast"))

    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
