# Notices and Credits

BallonsTranslator Vibe remains licensed under GPL-3.0. See `LICENSE` for the full license text.

Credits:

- Upstream project: `dmMaze/BallonsTranslator`
- AI-modified downstream variant referenced by this project: `thomaswantstobeaskeleton/BallonsTranslator-Pro`
- Fork maintenance, Pinokio launcher integration, archive import/export, reference glossary import/export, translated-folder glossary templates, Gloss Scan current-manga glossary generation, and GPU-aware runtime launcher repair: this `BallonsTranslator-vibe` fork

Archive import/export operates on local files. ZIP/CBZ handling uses Python standard-library ZIP support, PDF export uses the existing Pillow dependency, CBR import uses the user's local `7z`-compatible extractor when available, and CBR export uses the user's local `rar`/WinRAR command when available.

Gloss Scan and glossary import/export operate on local project OCR text and JSON files. They do not add a bundled cloud service, model, or third-party runtime dependency.
