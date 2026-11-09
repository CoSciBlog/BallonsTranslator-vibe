# Credits and license notes

BallonsTranslator-vibe is based on [BallonsTranslator](https://github.com/dmMaze/BallonsTranslator), created and maintained by dmMaze and its contributors. This fork remains licensed under the GNU General Public License v3.0 or later; see [LICENSE](LICENSE).

The application builds on open-source projects and model providers credited in the main README files and in the dependency metadata. In particular:

- Comic translation components originate from [manga-image-translator](https://github.com/zyddnys/manga-image-translator) and the upstream projects linked from the README.
- Local model serving can integrate with [Ollama](https://github.com/ollama/ollama). The integration uses Ollama's public HTTP API; no Ollama source code is redistributed here.
- Project-local Python environments are bootstrapped with [uv](https://github.com/astral-sh/uv), which is available under the Apache-2.0 and MIT licenses.

Copyright and license notices shipped with third-party dependencies remain the responsibility of their respective authors. New fork code must not remove or replace those notices.

The primary project documentation is maintained in English. Community-maintained translated guides retain their original language and attribution where provided.

The confirmed page-data reset, transactional project/output backup, background IO integration, restored sidebar thumbnails, and saved thumbnail visibility and size controls are original code in this fork and add no third-party code or dependencies. Thumbnail decoding uses the existing Qt image reader.

Selected text-box grouping reuses the region merger and its geometry/label rules from the GPL-licensed 1.4-vibe branch, retaining the existing X-AnyLabeling port attribution in `utils/merger.py`. The grouped undo integration and safeguards across directional passes add no third-party code or dependency.

The batch pre-upscaling page-list synchronization fix, editable parent-folder input, inclusion of ignored pages during upscaling, error-only upscaling completion messages, and English/German text-format tooltips are original maintenance work in this fork and add no third-party code or dependencies.

Re-inpainting mask normalization, elliptical expansion, and residual-text repair are adapted from this fork's GPL-licensed 1.4-vibe implementation to the 1.5-vibe worker and project persistence paths. They use the existing OpenCV dependency and selected detector/inpainter modules; no new dependency or model is bundled.

The optional main-window placement persistence, responsive Typesetting and Post-merge settings layouts, non-clipping speech-bubble-aware auto layout, translation line-break normalization, bounded local text-box merge integration, undoable selected-region merge, joint overlap separation, complete saved-mask re-inpainting, workflow controls and shortcuts, direct footer-to-settings navigation, extended detector/OCR/inpaint controls and parameter guidance, project-wide text-style application, non-destructive Normal/Uppercase/Lowercase text-case selector, Ollama reasoning-capability presentation, theme-aware text-style popup integration, glossary translation recovery, and staged project-wide Google/DeepL-to-LLM orchestration are maintained as original code in this fork. The Ollama and two-step integrations use the providers' existing HTTP interfaces and introduce no bundled third-party code or new dependency.

The isolated LLM translation benchmark, its transient page/result preview, and its atomic manifest plus per-profile result files are original code in this fork. They reuse the existing Qt text engine and project serialization facilities and add no third-party code, dependency, model, or service.
