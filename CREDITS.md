# Credits and license notes

BallonsTranslator-vibe is based on [BallonsTranslator](https://github.com/dmMaze/BallonsTranslator), created and maintained by dmMaze and its contributors. This fork remains licensed under the GNU General Public License v3.0 or later; see [LICENSE](LICENSE).

The application builds on open-source projects and model providers credited in the main README files and in the dependency metadata. In particular:

- Comic translation components originate from [manga-image-translator](https://github.com/zyddnys/manga-image-translator) and the upstream projects linked from the README.
- Local model serving can integrate with [Ollama](https://github.com/ollama/ollama). The integration uses Ollama's public HTTP API; no Ollama source code is redistributed here.
- Project-local Python environments are bootstrapped with [uv](https://github.com/astral-sh/uv), which is available under the Apache-2.0 and MIT licenses.

Copyright and license notices shipped with third-party dependencies remain the responsibility of their respective authors. New fork code must not remove or replace those notices.

The primary project documentation is maintained in English. Community-maintained translated guides retain their original language and attribution where provided.

The optional translation line-break normalization, text-box wrapping and merge integration, compact Stroke color control, Ollama memory-estimate presentation, theme-aware text-style popup integration, and Google/DeepL-to-Ollama two-step orchestration are maintained as original code in this fork. The two-step integration uses the providers' existing HTTP interfaces and introduces no bundled third-party code or new dependency.
