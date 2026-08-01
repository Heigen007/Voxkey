"""PyInstaller entry point.

A separate file with absolute imports: PyInstaller runs the entry script as
`__main__`, where the package-relative imports in voxkey/__main__.py would
not resolve.
"""

import sys

from voxkey.app import main

if __name__ == '__main__':
    sys.exit(main())
