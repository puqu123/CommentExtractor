# Third-party notices

CommentExtractor is licensed under GNU AGPL v3.0 only. It uses the following libraries:

| Component | License family | Upstream |
|---|---|---|
| PySide6 / Qt / shiboken6 | LGPL v3 / GPL / commercial, depending on component | https://doc.qt.io/qtforpython-6/licenses.html |
| openpyxl | MIT | https://openpyxl.readthedocs.io/ |
| et-xmlfile | MIT | https://pypi.org/project/et-xmlfile/ |
| defusedxml | PSF | https://github.com/tiran/defusedxml |
| CPython | PSF and included third-party notices | https://docs.python.org/3/license.html |
| PyInstaller runtime bootloader | GPL with bootloader exception | https://pyinstaller.org/en/stable/license.html |

This table is an index, not a replacement for upstream license texts. The build copies
installed package metadata (including license texts) into `_internal`. Qt and native
components also carry upstream notices collected by the packaging hooks. Keep the
entire distribution directory intact. Review native bundled-library notices when
changing the dependency set before a public binary release.

Copies of the LGPL v3, GPL v3, and Python 3.9.13 license are included in `licenses/`.
The PyInstaller bootloader exception is included as `licenses/PyInstaller-COPYING.txt`.

The source and build instructions for CommentExtractor accompany the repository.
Upstream source for exact dependency versions can be obtained from their project
sites / PyPI. Installed versions are recorded in `requirements-lock.txt` for the
Windows development environment. PyMuPDF / MuPDF have been removed in v0.2.3.
Pillow and lxml are development tools for icons and synthetic Office fixtures;
they are explicitly excluded from the Windows application bundle.
