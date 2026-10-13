# Third-party notices

The bridge's Win32 control selection and clipboard message format were informed
by [kronenz/kakaotalk-mcp](https://github.com/kronenz/kakaotalk-mcp), reviewed at
commit `7b41dd9da473e7a9e2f4b07ec27bdf3289fcc5fb`. This project implements its own
guarded adapter, parser, journals and channel; it does not install the upstream
MCP server or use its network/login implementation.

Upstream MIT notice:

> MIT License
>
> Copyright (c) 2025 kronenz
>
> Permission is hereby granted, free of charge, to any person obtaining a copy
> of this software and associated documentation files (the "Software"), to deal
> in the Software without restriction, including without limitation the rights
> to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
> copies of the Software, and to permit persons to whom the Software is
> furnished to do so, subject to the following conditions:
>
> The above copyright notice and this permission notice shall be included in all
> copies or substantial portions of the Software.
>
> THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
> IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
> FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
> AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
> LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
> OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
> SOFTWARE.

Runtime dependencies retain their own licenses:

| Component | License / source |
| --- | --- |
| Python | [PSF license](https://docs.python.org/3/license.html) |
| PySide6, Shiboken6, Qt 6 | [LGPLv3/GPLv3/commercial](https://doc.qt.io/qtforpython-6/licenses.html); this build uses the LGPL distribution and dynamic DLLs |
| pywin32 | [PSF-derived license](https://github.com/mhammond/pywin32/blob/main/License.txt) |
| websockets | [BSD-3-Clause](https://github.com/python-websockets/websockets/blob/main/LICENSE) |
| ws | [MIT](https://github.com/websockets/ws/blob/master/LICENSE) |
| OpenClaw SDK (host peer) | [MIT](https://github.com/openclaw/openclaw/blob/main/LICENSE) |
| PyInstaller (build tool) | [GPL with bootloader exception](https://pyinstaller.org/en/stable/license.html) |

The portable build includes distribution metadata/license files under `licenses`
and dynamically loaded Qt libraries under `_internal`. Users may replace those
libraries with compatible modified versions and may debug those modifications;
this project's license does not restrict those rights. Corresponding Qt/PySide
source is available at [Qt source archives](https://download.qt.io/official_releases/)
and [qtproject/pyside-pyside-setup](https://code.qt.io/pyside/pyside-setup.git/).
Release maintainers must retain the notices and offer the exact corresponding
LGPL dependency source with a public binary release. No third-party binary or
signing certificate is checked into this repository.
