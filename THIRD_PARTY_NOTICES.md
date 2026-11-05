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
| Pillow | HPND and bundled library notices | https://github.com/python-pillow/Pillow |
| RapidOCR 1.4.4 and PP-OCR model conversion | Apache 2.0 | https://github.com/RapidAI/RapidOCR/tree/v1.4.4 |
| PaddleOCR PP-OCRv4 detection/recognition and PP-OCR mobile classification models | Apache 2.0 | https://github.com/PaddlePaddle/PaddleOCR |
| ONNX Runtime | MIT and bundled third-party notices | https://github.com/microsoft/onnxruntime |
| NumPy | BSD and bundled native-library notices | https://github.com/numpy/numpy |
| OpenCV Python | Apache 2.0 and bundled third-party notices | https://github.com/opencv/opencv-python |
| Shapely / GEOS | BSD / LGPL 2.1 | https://github.com/shapely/shapely |
| pyclipper, PyYAML, six, flatbuffers, humanfriendly | MIT | https://pypi.org/ |
| protobuf, SymPy, mpmath | BSD family | https://pypi.org/ |
| tqdm | MPL 2.0 / MIT | https://github.com/tqdm/tqdm |
| coloredlogs, pyreadline3 | MIT / BSD | https://pypi.org/ |

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
Since v0.2.8 Pillow is a runtime dependency for Excel thumbnails and previews.
RapidOCR's three local ONNX weights and native dependencies are delivered as a
separate optional OCR ZIP. Both ZIPs share the CommentExtractor/ root; extract
them into the same destination. No model download is needed at runtime. Its license is included in
`licenses/RapidOCR-1.4.4.txt`, with the upstream PaddleOCR license alongside it.
The build runs `scripts/collect_dependency_licenses.py` to copy installed runtime
license and native-library notices into `licenses/dependencies/`. Full upstream
package metadata is also collected. GEOS source corresponding to Shapely 2.0.7 is
available from the Shapely project and https://libgeos.org/; preserve its LGPL
terms and allow replacement of the bundled dynamic libraries.
lxml remains a fixture-generation dependency and is excluded from the bundle.
The optional OCR download also includes copies of the license and notice texts
under `ocr-licenses/`, so they accompany the separate distribution.
